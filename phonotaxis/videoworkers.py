"""
Multi-threaded video processing worker classes.

This module provides the individual worker components that make up the
phonotaxis video-processing pipeline.  Each worker runs in its own
``threading.Thread`` and communicates with its neighbours through one of
two thread-safe channels defined in ``resultbus``:

* **ResultBus** (pub/sub) — ``CaptureWorker`` and ``FileCaptureWorker``
  publish raw frames to a named topic; any number of downstream workers
  subscribe and receive their own independent ``ResultRingBuffer`` queue.

* **SharedBuffer** (point-to-point) — each ``ProcessWorker`` writes its
  final ``WorkerResult`` into a dedicated ``SharedBuffer`` so the
  coordinating thread (e.g. ``VideoThread``) can poll results and emit Qt
  signals without holding any locks.

Pipeline overview::

    ┌───────────────────────┐   publish('capture')   ┌────────────────────┐
    │  CaptureWorker  /     │ ─────────────────────► │  ResultBus         │
    │  FileCaptureWorker    │                         └──────┬─────────────┘
    └───────────────────────┘                                │ subscribe()
                                                             ▼
                                                    ┌────────────────────┐
                                                    │  ProcessWorker     │
                                                    │  (+ strategy fn)   │
                                                    └──────┬─────────────┘
                                         try_write_result  │     │ publish (optional)
                                                           ▼     ▼
                                                    ┌─────────┐  ResultBus
                                                    │ Shared  │  (for chaining)
                                                    │ Buffer  │
                                                    └─────────┘
                                              ┌───────────────────────┐
                                              │  RecordWorker         │
                                              │  (subscribe('capture'))│
                                              └───────────────────────┘

Classes
-------
CaptureWorker
    Reads frames from a live ``VideoSource`` as fast as the camera allows
    and publishes each frame as a ``WorkerResult`` to a ``ResultBus``.

FileCaptureWorker
    Like ``CaptureWorker`` but for file-backed sources.  Supports
    rate-limiting, looping, pause/resume, and optional back-pressure
    (``wait_on_full``) to avoid flooding slow downstream subscribers.

ContourTracker
    Stateful, callable processing strategy.  Applies an optional
    circular/rectangular mask, inverts and thresholds the frame, and
    locates the largest dark contour.  Returns a dict with the processed
    frame, centroid, contour, and orientation.  Designed to be passed as
    the ``strategy`` argument of ``ProcessWorker``.

ProcessWorker
    Generic pipeline stage.  Subscribes to a ``ResultBus`` topic, passes
    each incoming ``WorkerResult`` through an arbitrary ``strategy``
    callable, and writes the output to a ``SharedBuffer`` for the
    coordinator.  Optionally re-publishes results to a second ``ResultBus``
    to enable chained or fan-out processing.

RecordWorker
    Subscribes to a ``ResultBus`` topic and writes frames to a video file
    via an ``ffmpeg`` subprocess (hardware-accelerated by default, with a
    ``libx264`` software fallback).  Recording can be started and stopped
    independently of the worker's run-loop.

No Qt dependencies — all classes are pure Python and suitable for use
outside a GUI context (e.g. benchmarks, unit tests).
"""
import time
import queue
import cv2
import numpy as np
import subprocess
import threading
from typing import Callable, List, Optional
from .resultbus import WorkerResult, ResultBus, ResultRingBuffer, SharedBuffer

from .videosource import VideoSource


class CaptureWorker:
    """Reads frames from a VideoSource, publishes to ResultBus."""
    def __init__(self, video_source: VideoSource, publish_to_bus: ResultBus, name: str = 'capture'):
        self.video_source = video_source
        self.publish_to_bus = publish_to_bus
        self.name = name
        self.running: bool = True
        self.ready_event = threading.Event()
        self.error_message: Optional[str] = None
        self.captured_count: int = 0
        self.capture_log = {}
        
        # Properties cached during run()
        self.fps: float = 0.0
        self.frame_width: int = 0
        self.frame_height: int = 0

    def _ensure_grayscale(self, frame):
        if len(frame.shape) == 3:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame

    def run(self):
        if not self.video_source.open():
            self.error_message = f"Failed to open video source: {self.video_source}"
            self.ready_event.set()
            return

        self.fps = self.video_source.fps
        self.frame_width = self.video_source.frame_width
        self.frame_height = self.video_source.frame_height
        self.ready_event.set()

        try:
            while self.running:
                ret, frame = self.video_source.read()
                timestamp = time.time()
                if ret:
                    self.captured_count += 1
                    self.capture_log[timestamp] = self.captured_count
                    gray = self._ensure_grayscale(frame)
                    
                    result = WorkerResult(timestamp, {'frame': gray}, self.name)
                    self.publish_to_bus.publish(result)
                else:
                    time.sleep(0.001)
        finally:
            self.video_source.release()

    def stop(self):
        self.running = False


class FileCaptureWorker:
    """Reads frames from a VideoSource (file), publishes to ResultBus at controlled rate."""
    def __init__(
        self,
        video_source: VideoSource,
        publish_to_bus: ResultBus,
        fps_limit: Optional[float] = None,
        loop: bool = False,
        paused: bool = False,
        wait_on_full: bool = True,
        name: str = 'capture'
    ):
        self.video_source = video_source
        self.publish_to_bus = publish_to_bus
        self.fps_limit = fps_limit
        self.loop = loop
        self.paused = paused
        self.wait_on_full = wait_on_full
        self.name = name
        self.running: bool = True
        self.ready_event = threading.Event()
        self.error_message: Optional[str] = None
        self.captured_count: int = 0
        self.capture_log = {}
        
        self.fps = 30.0
        self.frame_width = 0
        self.frame_height = 0

    @property
    def file_fps(self) -> float:
        return self.fps

    @file_fps.setter
    def file_fps(self, value: float):
        self.fps = value

    def _ensure_grayscale(self, frame):
        if len(frame.shape) == 3:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame

    def run(self):
        if not self.video_source.open():
            self.error_message = f"Failed to open video source: {self.video_source}"
            self.ready_event.set()
            return

        self.file_fps = self.video_source.fps
        self.frame_width = self.video_source.frame_width
        self.frame_height = self.video_source.frame_height
        self.ready_event.set()

        fps = self.fps_limit if self.fps_limit is not None else self.file_fps
        frame_interval = 1.0 / fps if fps > 0 else 0.0
        
        last_frame_time = time.time()
        
        try:
            while self.running:
                if self.paused:
                    time.sleep(0.01)
                    continue

                if frame_interval > 0:
                    target_time = last_frame_time + frame_interval
                    sleep_dur = target_time - time.time()
                    if sleep_dur > 0.0015:
                        time.sleep(sleep_dur - 0.001)
                    while time.time() < target_time:
                        pass
                
                if self.wait_on_full:
                    while self.running:
                        any_full = False
                        with self.publish_to_bus._lock:
                            subs = self.publish_to_bus._subscribers.get(self.name, [])
                            for q in subs:
                                if q.full():
                                    any_full = True
                                    break
                        if any_full:
                            time.sleep(0.001)
                        else:
                            break

                if not self.running:
                    break

                last_frame_time = time.time()
                ret, frame = self.video_source.read()
                
                if not ret:
                    if self.loop:
                        if self.video_source.set_position(0):
                            ret, frame = self.video_source.read()
                            if not ret:
                                break
                        else:
                            break
                    else:
                        break
                        
                self.captured_count += 1
                timestamp = time.time()
                self.capture_log[timestamp] = self.captured_count
                gray = self._ensure_grayscale(frame)
                
                result = WorkerResult(timestamp, {'frame': gray}, self.name)
                self.publish_to_bus.publish(result)
        finally:
            self.video_source.release()

    def stop(self):
        self.running = False


class ContourTracker:
    """Stateful strategy for contour-based dark-object tracking."""
    def __init__(self, threshold: int, minarea: int, tracking: bool = True, blur_sigma: float = 3.0):
        self.threshold: int = threshold
        self.minarea: int = minarea
        self.tracking: bool = tracking
        self.mask_enabled: bool = False
        self.mask_coords: Optional[list] = None
        self.mode: str = 'grayscale'
        self._cached_mask = None
        self._cached_key = None
        self.blur_sigma: float = blur_sigma

    def set_circular_mask(self, coords):
        self.mask_coords = coords
        self.mask_enabled = True

    def set_rectangular_mask(self, coords):
        self.mask_coords = coords
        self.mask_enabled = True

    def disable_mask(self):
        self.mask_enabled = False
        self.mask_coords = None
        self._cached_mask = None
        self._cached_key = None

    def apply_circular_mask(self, frame):
        if not self.mask_enabled or self.mask_coords is None or len(self.mask_coords) != 3:
            return frame
        height, width = frame.shape
        center_x, center_y, radius = self.mask_coords
        if radius <= 0:
            return frame
            
        key = (height, width, center_x, center_y, radius)
        if self._cached_key != key or self._cached_mask is None:
            y_coords, x_coords = np.ogrid[:height, :width]
            distance_sq = (x_coords - center_x)**2 + (y_coords - center_y)**2
            self._cached_mask = distance_sq > radius**2
            self._cached_key = key
            
        masked_frame = frame.copy()
        masked_frame[self._cached_mask] = 255
        return masked_frame

    def apply_rectangular_mask(self, frame):
        if not self.mask_enabled or self.mask_coords is None or len(self.mask_coords) != 4:
            return frame
        height, width = frame.shape
        x1, y1, x2, y2 = self.mask_coords
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(width, x2) if x2 is not None else width
        y2 = min(height, y2) if y2 is not None else height
        if x1 >= x2 or y1 >= y2:
            return frame
            
        key = (height, width, x1, y1, x2, y2)
        if self._cached_key != key or self._cached_mask is None:
            mask = np.ones((height, width), dtype=np.bool_)
            mask[y1:y2, x1:x2] = False
            self._cached_mask = mask
            self._cached_key = key
            
        masked_frame = frame.copy()
        masked_frame[self._cached_mask] = 255
        return masked_frame

    def apply_mask(self, frame):
        if not self.mask_enabled or self.mask_coords is None:
            return frame
        if len(self.mask_coords) == 3:
            return self.apply_circular_mask(frame)
        elif len(self.mask_coords) == 4:
            return self.apply_rectangular_mask(frame)
        return frame

    def __call__(self, msg: WorkerResult) -> dict:
        timestamp = msg.timestamp
        frame = msg.data['frame']
        
        if not self.tracking:
            return {
                'frame': frame,
                'points': (),
                'contour': None,
                'orientations': (0.0,),
            }

        masked_frame = self.apply_mask(frame)
        max_value = 255
        inverted_frame = cv2.bitwise_not(masked_frame)
        
        blurred = cv2.GaussianBlur(inverted_frame, (0, 0), self.blur_sigma)
        ret, binary_frame = cv2.threshold(blurred, max_value - self.threshold,
                                          max_value, cv2.THRESH_BINARY)
        
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        binary_frame = cv2.morphologyEx(binary_frame, cv2.MORPH_CLOSE, kernel)
        
        contours, hierarchy = cv2.findContours(binary_frame, cv2.RETR_EXTERNAL,
                                               cv2.CHAIN_APPROX_SIMPLE)
        centroid = (-1, -1)
        orientation = 0
        largest_area = 0
        largest_contour = None

        if contours:
            for indc, cnt in enumerate(contours):
                area = cv2.contourArea(cnt)
                if area > largest_area:
                    largest_area = area
                    largest_contour = cnt
            if largest_contour is not None and largest_area > self.minarea:
                mom = cv2.moments(largest_contour)
                if mom["m00"] != 0:
                    cX = int(mom["m10"] / mom["m00"])
                    cY = int(mom["m01"] / mom["m00"])
                    centroid = (cX, cY)
                    orientation = np.arctan2(2*mom['mu11'], mom['mu20'] - mom['mu02'])/2

        points = (centroid,)
        orientations = (orientation,)

        if self.mode == 'grayscale':
            processed_frame = frame
        elif self.mode == 'binary':
            processed_frame = cv2.bitwise_not(binary_frame)
        else:
            processed_frame = frame

        return {
            'frame': processed_frame,
            'points': points,
            'contour': largest_contour,
            'orientations': orientations,
        }


class ProcessWorker:
    """Generic video-pipeline worker subscribing to ResultBus and writing to SharedBuffer."""
    def __init__(
        self,
        strategy: Callable,
        result_buffer: SharedBuffer,
        *,
        name: str = 'worker',
        bus: ResultBus,
        subscribe_to: str,
        publish_to_bus: Optional[ResultBus] = None,
        on_start: Optional[Callable] = None,
        on_stop: Optional[Callable] = None,
        latest_only: bool = False,
    ):
        self.strategy = strategy
        self.result_buffer = result_buffer
        self.name = name
        self.running: bool = True
        self.is_processing: bool = False
        self.processed_count: int = 0
        self.latest_only: bool = latest_only
        self.timing_history = {}
        self.data_history = {}
        self.raw_buffer = None

        self._subscription_queue = bus.subscribe(subscribe_to)
        self._publish_bus = publish_to_bus
        self._on_start = on_start
        self._on_stop = on_stop

    def run(self):
        if self._on_start is not None:
            self._on_start()

        while self.running:
            try:
                msg = self._subscription_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            if self.latest_only:
                while True:
                    try:
                        msg = self._subscription_queue.get_nowait()
                    except queue.Empty:
                        break

            self.is_processing = True
            recv_time = time.time()
            try:
                result_data = self.strategy(msg)
            finally:
                self.is_processing = False

            timestamp = msg.timestamp
            emit_time = time.time()
            self.timing_history[timestamp] = (recv_time, emit_time)

            if result_data is not None:
                self.data_history[timestamp] = {
                    k: v for k, v in result_data.items() if k not in ('frame', 'contour')
                }
                self.processed_count += 1
                result = WorkerResult(
                    timestamp=timestamp,
                    data=result_data,
                    worker_name=self.name,
                )
                self.result_buffer.try_write_result(result)
                if self._publish_bus is not None:
                    self._publish_bus.publish(result)

        if self._on_stop is not None:
            self._on_stop()

    def stop(self):
        self.running = False


class RecordWorker:
    """Reads from a subscription queue, writes frames via FFMPEG subprocess."""
    def __init__(
        self,
        bus: ResultBus,
        subscribe_to: str,
        name: str = 'recorder',
        queue_size: int = 128
    ):
        self.name = name
        self.running: bool = True
        self.recording: bool = False
        self._ffmpeg_process: Optional[subprocess.Popen] = None
        self._frame_size = None
        self.recorded_count: int = 0
        
        self.filepath: Optional[str] = None
        self.fps: float = 30.0
        self.encoder: str = 'h264_nvenc'

        self._subscription_queue = bus.subscribe(subscribe_to, maxsize=queue_size)
        self._thread_started = False
        self._thread_ident = None

    def initialize_writer(self, filepath, fps, frame_size, encoder='h264_nvenc'):
        self._frame_size = frame_size
        width, height = frame_size
        
        cmd = [
            'ffmpeg',
            '-y',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{width}x{height}',
            '-pix_fmt', 'gray',
            '-r', str(fps),
            '-thread_queue_size', '2048',
            '-i', '-',
            '-c:v', encoder,
            '-bufsize', '6M',
            '-pix_fmt', 'yuv420p',
            filepath
        ]
        
        try:
            self._ffmpeg_process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception as e:
            print(f"Failed to start ffmpeg with {encoder}: {e}")
            cmd[cmd.index(encoder)] = 'libx264'
            try:
                self._ffmpeg_process = subprocess.Popen(
                    cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except Exception as e:
                print(f"Failed to start ffmpeg fallback: {e}")
                self._ffmpeg_process = None

    def release_writer(self):
        if self._thread_started and threading.get_ident() != self._thread_ident:
            return
            
        proc = self._ffmpeg_process
        if proc is not None:
            self._ffmpeg_process = None
            if proc.stdin:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def terminate_writer(self):
        proc = self._ffmpeg_process
        if proc is not None:
            self._ffmpeg_process = None
            try:
                proc.kill()
                proc.wait()
            except Exception:
                pass

    def start_recording(self, filepath, fps, encoder='h264_nvenc'):
        self.filepath = filepath
        self.fps = fps
        self.encoder = encoder
        self.recording = True

    def stop_recording(self):
        self.recording = False
        self.release_writer()

    def write_frame(self, timestamp, frame):
        if self._ffmpeg_process is None and self.filepath is not None:
            height, width = frame.shape[:2]
            self.initialize_writer(self.filepath, self.fps, (width, height), self.encoder)
            
        if self._ffmpeg_process is not None and self._ffmpeg_process.stdin is not None:
            try:
                self._ffmpeg_process.stdin.write(frame.tobytes())
                self.recorded_count += 1
            except Exception as e:
                print(f"Error writing to ffmpeg: {e}")
                pass

    def run(self):
        self._thread_started = True
        self._thread_ident = threading.get_ident()
        
        try:
            while self.running:
                try:
                    msg = self._subscription_queue.get(timeout=0.01)
                    if self.recording:
                        frame = msg.data.get('frame')
                        if frame is not None:
                            self.write_frame(msg.timestamp, frame)
                except queue.Empty:
                    continue
        finally:
            self.release_writer()

    def stop(self):
        self.running = False
