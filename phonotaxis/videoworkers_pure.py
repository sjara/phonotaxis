import time
import queue
import cv2
import numpy as np
import subprocess
from typing import Callable, List, Optional
from .sharedbuffer import SharedFrameBuffer, ResultBuffer
from .resultbus import WorkerResult, ResultBus


class CaptureWorker:
    """Reads frames from cv2.VideoCapture, fans out to multiple buffers."""
    def __init__(self, cap: cv2.VideoCapture,
                 process_buffers: List[SharedFrameBuffer],
                 record_worker = None):
        self.cap = cap
        self.process_buffers = process_buffers
        self.record_worker = record_worker
        self.running: bool = True
        self.recording: bool = False
        self.captured_count: int = 0

    def _ensure_grayscale(self, frame):
        if len(frame.shape) == 3:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame

    def run(self):
        while self.running:
            ret, frame = self.cap.read()
            timestamp = time.time()
            if ret:
                self.captured_count += 1
                gray = self._ensure_grayscale(frame)
                
                for buf in self.process_buffers:
                    buf.try_write(timestamp, gray)
                
                if self.recording and self.record_worker is not None:
                    self.record_worker.write_frame(timestamp, gray)
            else:
                # To prevent tight loop on failure, sleep briefly
                time.sleep(0.001)

    def stop(self):
        self.running = False


class FileCaptureWorker:
    """Reads frames from a video file cv2.VideoCapture, fans out to multiple buffers at a controlled rate."""
    def __init__(self, cap: cv2.VideoCapture,
                 process_buffers: List[SharedFrameBuffer],
                 record_worker = None,
                 fps_limit: Optional[float] = None,
                 loop: bool = False,
                 paused: bool = False,
                 wait_on_full: bool = True):
        self.cap = cap
        self.process_buffers = process_buffers
        self.record_worker = record_worker
        self.fps_limit = fps_limit
        self.loop = loop
        self.running: bool = True
        self.recording: bool = False
        self.paused = paused
        self.wait_on_full = wait_on_full
        self.captured_count: int = 0
        
        # Get properties
        self.file_fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.file_fps <= 0:
            self.file_fps = 30.0  # Fallback
            
        self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
    def _ensure_grayscale(self, frame):
        if len(frame.shape) == 3:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame

    def run(self):
        # Determine target frame interval
        fps = self.fps_limit if self.fps_limit is not None else self.file_fps
        frame_interval = 1.0 / fps if fps > 0 else 0.0
        
        last_frame_time = time.time()
        
        while self.running:
            if self.paused:
                time.sleep(0.01)
                continue
            # Control frame rate
            if frame_interval > 0:
                elapsed = time.time() - last_frame_time
                sleep_dur = frame_interval - elapsed
                if sleep_dur > 0:
                    time.sleep(sleep_dur)
            
            # Wait if any process buffer is full to prevent frame drops
            if self.wait_on_full:
                while self.running:
                    any_full = False
                    for buf in self.process_buffers:
                        if buf._items_available >= buf._capacity:
                            any_full = True
                            break
                    if any_full:
                        time.sleep(0.001)
                    else:
                        break

            if not self.running:
                break

            last_frame_time = time.time()
            ret, frame = self.cap.read()
            
            if not ret:
                if self.loop:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self.cap.read()
                    if not ret:
                        break  # Failed to loop/reset
                else:
                    break  # End of file
                    
            self.captured_count += 1
            timestamp = time.time()
            gray = self._ensure_grayscale(frame)
            
            for buf in self.process_buffers:
                buf.try_write(timestamp, gray)
                
            if self.recording and self.record_worker is not None:
                self.record_worker.write_frame(timestamp, gray)
                
    def stop(self):
        self.running = False


class ContourTracker:
    """
    Stateful strategy for contour-based dark-object tracking.

    Extracted from the original ProcessWorker.process_frame logic.
    Implements ``__call__`` so it can be injected into a generic
    ``ProcessWorker``.

    Call signature: ``(timestamp, frame) -> dict``
    """

    def __init__(self, threshold: int, minarea: int, tracking: bool = True):
        self.threshold: int = threshold
        self.minarea: int = minarea
        self.tracking: bool = tracking
        self.mask_enabled: bool = False
        self.mask_coords: Optional[list] = None
        self.mode: str = 'grayscale'

    # -- Mask helpers ------------------------------------------------

    def set_circular_mask(self, coords):
        self.mask_coords = coords
        self.mask_enabled = True

    def set_rectangular_mask(self, coords):
        self.mask_coords = coords
        self.mask_enabled = True

    def disable_mask(self):
        self.mask_enabled = False
        self.mask_coords = None

    def apply_circular_mask(self, frame):
        if not self.mask_enabled or self.mask_coords is None or len(self.mask_coords) != 3:
            return frame
        masked_frame = frame.copy()
        height, width = frame.shape
        center_x, center_y, radius = self.mask_coords
        if radius <= 0:
            return frame
        y_coords, x_coords = np.ogrid[:height, :width]
        distance_from_center = np.sqrt((x_coords - center_x)**2 + (y_coords - center_y)**2)
        mask_outside_circle = distance_from_center > radius
        masked_frame[mask_outside_circle] = 255
        return masked_frame

    def apply_rectangular_mask(self, frame):
        if not self.mask_enabled or self.mask_coords is None or len(self.mask_coords) != 4:
            return frame
        masked_frame = frame.copy()
        height, width = frame.shape
        x1, y1, x2, y2 = self.mask_coords
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(width, x2) if x2 is not None else width
        y2 = min(height, y2) if y2 is not None else height
        if x1 >= x2 or y1 >= y2:
            return frame
        mask = np.ones_like(frame) * 255
        mask[y1:y2, x1:x2] = 0
        masked_frame[mask == 255] = 255
        return masked_frame

    def apply_mask(self, frame):
        if not self.mask_enabled or self.mask_coords is None:
            return frame
        if len(self.mask_coords) == 3:
            return self.apply_circular_mask(frame)
        elif len(self.mask_coords) == 4:
            return self.apply_rectangular_mask(frame)
        return frame

    # -- Core processing ---------------------------------------------

    def __call__(self, timestamp: float, frame: np.ndarray) -> dict:
        """
        Process a single frame.

        Returns:
            dict with keys: processed_frame, points, contour, orientations
        """
        if not self.tracking:
            return {
                'processed_frame': frame,
                'points': (),
                'contour': None,
                'orientations': (0.0,),
            }

        masked_frame = self.apply_mask(frame)

        max_value = 255
        inverted_frame = cv2.bitwise_not(masked_frame)
        
        # Apply Gaussian Blur to smooth pixel-level noise
        blurred = cv2.GaussianBlur(inverted_frame, (15, 15), 0)
        
        ret, binary_frame = cv2.threshold(blurred, max_value - self.threshold,
                                          max_value, cv2.THRESH_BINARY)
        
        # Apply Morphological Closing to fill gaps and holes in the binary region
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
            'processed_frame': processed_frame,
            'points': points,
            'contour': largest_contour,
            'orientations': orientations,
        }


class ProcessWorker:
    """
    Generic video-pipeline worker.

    Handles buffer I/O, lifecycle, and inter-worker notification.
    Domain logic is injected as a *strategy* callable — no subclassing
    required.

    Two input modes (mutually exclusive):

    1. **Frame mode** — reads from a ``SharedFrameBuffer`` (raw frames).
       Strategy signature: ``(timestamp, frame) -> dict``
    2. **Bus mode** — subscribes to a ``ResultBus`` topic.
       Strategy signature: ``(WorkerResult) -> dict``

    Output is always written to a ``ResultBuffer`` and optionally
    published to a ``ResultBus`` for downstream workers.
    """

    def __init__(
        self,
        strategy: Callable,
        result_buffer: ResultBuffer,
        *,
        name: str = 'worker',
        # Frame mode (mutually exclusive with bus subscription)
        raw_buffer: Optional[SharedFrameBuffer] = None,
        # Bus mode
        bus: Optional[ResultBus] = None,
        subscribe_to: Optional[str] = None,
        # Optional: publish own results to a bus
        publish_to_bus: Optional[ResultBus] = None,
        # Lifecycle hooks
        on_start: Optional[Callable] = None,
        on_stop: Optional[Callable] = None,
    ):
        self.strategy = strategy
        self.result_buffer = result_buffer
        self.name = name
        self.raw_buffer = raw_buffer
        self.running: bool = True
        self.is_processing: bool = False
        self.processed_count: int = 0

        # Bus subscription setup
        self._subscription_queue: Optional[queue.Queue] = None
        if bus is not None and subscribe_to is not None:
            self._subscription_queue = bus.subscribe(subscribe_to)

        # Publishing setup
        self._publish_bus = publish_to_bus

        # Lifecycle hooks
        self._on_start = on_start
        self._on_stop = on_stop

    def run(self):
        """Main loop — reads input, calls strategy, writes output."""
        if self._on_start is not None:
            self._on_start()

        while self.running:
            if self.raw_buffer is not None:
                # Frame mode
                item = self.raw_buffer.read_blocking(timeout=0.05)
                if item is None:
                    continue
                timestamp, frame = item
                self.is_processing = True
                try:
                    result_data = self.strategy(timestamp, frame)
                finally:
                    self.is_processing = False
            elif self._subscription_queue is not None:
                # Bus mode
                try:
                    msg = self._subscription_queue.get(timeout=0.05)
                except queue.Empty:
                    continue
                self.is_processing = True
                try:
                    result_data = self.strategy(msg)
                finally:
                    self.is_processing = False
                timestamp = msg.timestamp
            else:
                # No input source — sleep to prevent busy loop
                time.sleep(0.05)
                continue

            if result_data is not None:
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
    """Reads from record_buffer, writes frames via FFMPEG subprocess (GPU-accelerated)."""
    def __init__(self, record_buffer=None):
        self.running: bool = True
        self._ffmpeg_process: Optional[subprocess.Popen] = None
        self._frame_size = None
        self.recorded_count: int = 0

    def initialize_writer(self, filepath, fps, frame_size, encoder='h264_nvenc'):
        self._frame_size = frame_size
        width, height = frame_size
        
        # Build ffmpeg command
        cmd = [
            'ffmpeg',
            '-y', # Overwrite
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{width}x{height}',
            '-pix_fmt', 'gray', # Mono camera
            '-r', str(fps),
            '-thread_queue_size', '2048', # Queue up to 2048 raw frames in ffmpeg internal buffer
            '-i', '-', # Read from stdin
            '-c:v', encoder,
            '-bufsize', '6M', # Set rate control VBV buffer size
            '-pix_fmt', 'yuv420p', # For compatibility
            filepath
        ]
        
        try:
            # We want to see output to stderr for debugging ffmpeg issues
            self._ffmpeg_process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except Exception as e:
            print(f"Failed to start ffmpeg with {encoder}: {e}")
            cmd[cmd.index(encoder)] = 'libx264'
            try:
                self._ffmpeg_process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            except Exception as e:
                print(f"Failed to start ffmpeg fallback: {e}")
                self._ffmpeg_process = None

    def release_writer(self):
        if self._ffmpeg_process is not None:
            if self._ffmpeg_process.stdin:
                self._ffmpeg_process.stdin.close()
            self._ffmpeg_process.wait()
            self._ffmpeg_process = None

    def write_frame(self, timestamp, frame):
        if self._ffmpeg_process is not None and self._ffmpeg_process.stdin is not None:
            try:
                self._ffmpeg_process.stdin.write(frame.tobytes())
                self.recorded_count += 1
            except Exception as e:
                print(f"Error writing to ffmpeg: {e}")
                pass

    def run(self):
        while self.running:
            time.sleep(0.01)

    def stop(self):
        self.running = False
        self.release_writer()
