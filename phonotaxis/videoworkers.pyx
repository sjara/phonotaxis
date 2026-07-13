import time
import queue
import cv2
import numpy as np
import subprocess
cimport numpy as cnp

from .sharedbuffer cimport SharedFrameBuffer, ResultBuffer
from .resultbus cimport WorkerResult, ResultBus

cdef class CaptureWorker:
    """Reads frames from cv2.VideoCapture, fans out to multiple buffers."""
    def __init__(self, object cap,
                 list process_buffers,
                 SharedFrameBuffer record_buffer):
        self.cap = cap
        self.process_buffers = process_buffers
        self.record_buffer = record_buffer
        self.running = True
        self.recording = False

    def _ensure_grayscale(self, cnp.ndarray frame):
        if frame.ndim == 3:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame

    def run(self):
        cdef bint ret
        cdef cnp.ndarray frame
        cdef double timestamp
        cdef cnp.ndarray gray
        cdef SharedFrameBuffer buf

        while self.running:
            ret, frame = self.cap.read()
            timestamp = time.time()
            if ret:
                gray = self._ensure_grayscale(frame)
                
                for buf in self.process_buffers:
                    buf.try_write(timestamp, gray)
                
                if self.recording and self.record_buffer is not None:
                    self.record_buffer.try_write(timestamp, gray)
            else:
                # To prevent tight loop on failure, sleep briefly
                time.sleep(0.001)

    def stop(self):
        self.running = False


cdef class FileCaptureWorker:
    """Reads frames from a video file cv2.VideoCapture, fans out to multiple buffers at a controlled rate."""
    def __init__(self, object cap,
                 list process_buffers,
                 SharedFrameBuffer record_buffer = None,
                 object fps_limit = None,
                 bint loop = False,
                 bint paused = False):
        self.cap = cap
        self.process_buffers = process_buffers
        self.record_buffer = record_buffer
        self.fps_limit = fps_limit
        self.loop = loop
        self.running = True
        self.recording = False
        self.paused = paused
        
        # Get properties
        self.file_fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.file_fps <= 0:
            self.file_fps = 30.0  # Fallback
            
        self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
    def _ensure_grayscale(self, cnp.ndarray frame):
        if frame.ndim == 3:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame

    def run(self):
        cdef double fps
        cdef double frame_interval
        cdef double last_frame_time
        cdef double elapsed
        cdef double sleep_dur
        cdef bint any_full
        cdef SharedFrameBuffer buf
        cdef bint ret
        cdef cnp.ndarray frame
        cdef double timestamp
        cdef cnp.ndarray gray
        
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
                    
            timestamp = time.time()
            gray = self._ensure_grayscale(frame)
            
            for buf in self.process_buffers:
                buf.try_write(timestamp, gray)
                
            if self.recording and self.record_buffer is not None:
                self.record_buffer.try_write(timestamp, gray)
                
    def stop(self):
        self.running = False


cdef class ContourTracker:
    """
    Stateful strategy for contour-based dark-object tracking.

    Extracted from the original ProcessWorker.process_frame logic.
    Implements ``__call__`` so it can be injected into a generic
    ``ProcessWorker``.

    Call signature: ``(timestamp, frame) -> dict``
    """

    def __init__(self, int threshold, int minarea, bint tracking = True):
        self.threshold = threshold
        self.minarea = minarea
        self.tracking = tracking
        self.mask_enabled = False
        self.mask_coords = None
        self.mode = 'grayscale'

    # -- Mask helpers ------------------------------------------------

    def set_circular_mask(self, list coords):
        self.mask_coords = coords
        self.mask_enabled = True

    def set_rectangular_mask(self, list coords):
        self.mask_coords = coords
        self.mask_enabled = True

    def disable_mask(self):
        self.mask_enabled = False
        self.mask_coords = None

    def apply_circular_mask(self, cnp.ndarray frame):
        if not self.mask_enabled or self.mask_coords is None or len(self.mask_coords) != 3:
            return frame
        cdef cnp.ndarray masked_frame = frame.copy()
        cdef int height = frame.shape[0]
        cdef int width = frame.shape[1]
        cdef int center_x = self.mask_coords[0]
        cdef int center_y = self.mask_coords[1]
        cdef int radius = self.mask_coords[2]
        if radius <= 0:
            return frame
        y_coords, x_coords = np.ogrid[:height, :width]
        distance_from_center = np.sqrt((x_coords - center_x)**2 + (y_coords - center_y)**2)
        mask_outside_circle = distance_from_center > radius
        masked_frame[mask_outside_circle] = 255
        return masked_frame

    def apply_rectangular_mask(self, cnp.ndarray frame):
        if not self.mask_enabled or self.mask_coords is None or len(self.mask_coords) != 4:
            return frame
        cdef cnp.ndarray masked_frame = frame.copy()
        cdef int height = frame.shape[0]
        cdef int width = frame.shape[1]
        cdef object x1_obj = self.mask_coords[0]
        cdef object y1_obj = self.mask_coords[1]
        cdef object x2_obj = self.mask_coords[2]
        cdef object y2_obj = self.mask_coords[3]
        
        cdef int x1 = max(0, x1_obj)
        cdef int y1 = max(0, y1_obj)
        cdef int x2 = min(width, x2_obj) if x2_obj is not None else width
        cdef int y2 = min(height, y2_obj) if y2_obj is not None else height
        if x1 >= x2 or y1 >= y2:
            return frame
        mask = np.ones_like(frame) * 255
        mask[y1:y2, x1:x2] = 0
        masked_frame[mask == 255] = 255
        return masked_frame

    def apply_mask(self, cnp.ndarray frame):
        if not self.mask_enabled or self.mask_coords is None:
            return frame
        if len(self.mask_coords) == 3:
            return self.apply_circular_mask(frame)
        elif len(self.mask_coords) == 4:
            return self.apply_rectangular_mask(frame)
        return frame

    # -- Core processing ---------------------------------------------

    def __call__(self, double timestamp, cnp.ndarray frame) -> dict:
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

        cdef cnp.ndarray masked_frame = self.apply_mask(frame)

        cdef int max_value = 255
        cdef cnp.ndarray inverted_frame = cv2.bitwise_not(masked_frame)
        
        # Apply Gaussian Blur to smooth pixel-level noise
        cdef cnp.ndarray blurred = cv2.GaussianBlur(inverted_frame, (15, 15), 0)
        
        cdef cnp.ndarray binary_frame
        _, binary_frame = cv2.threshold(blurred, max_value - self.threshold,
                                        max_value, cv2.THRESH_BINARY)
        
        # Apply Morphological Closing to fill gaps and holes in the binary region
        cdef cnp.ndarray kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        binary_frame = cv2.morphologyEx(binary_frame, cv2.MORPH_CLOSE, kernel)
        
        contours, hierarchy = cv2.findContours(binary_frame, cv2.RETR_EXTERNAL,
                                               cv2.CHAIN_APPROX_SIMPLE)
        cdef tuple centroid = (-1, -1)
        cdef double orientation = 0
        cdef double largest_area = 0
        cdef object largest_contour = None
        cdef double area
        cdef int cX, cY
        cdef dict mom

        if contours:
            for cnt in contours:
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

        cdef tuple points = (centroid,)
        cdef tuple orientations = (orientation,)
        cdef cnp.ndarray processed_frame

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


cdef class ProcessWorker:
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
        object strategy,
        ResultBuffer result_buffer,
        *,
        str name = 'worker',
        # Frame mode (mutually exclusive with bus subscription)
        SharedFrameBuffer raw_buffer = None,
        # Bus mode
        ResultBus bus = None,
        str subscribe_to = None,
        # Optional: publish own results to a bus
        ResultBus publish_to_bus = None,
        # Lifecycle hooks
        object on_start = None,
        object on_stop = None,
    ):
        self.strategy = strategy
        self.result_buffer = result_buffer
        self.name = name
        self.raw_buffer = raw_buffer
        self.running = True
        self.is_processing = False

        # Bus subscription setup
        self._subscription_queue = None
        if bus is not None and subscribe_to is not None:
            self._subscription_queue = bus.subscribe(subscribe_to)

        # Publishing setup
        self._publish_bus = publish_to_bus

        # Lifecycle hooks
        self._on_start = on_start
        self._on_stop = on_stop

    def run(self):
        """Main loop — reads input, calls strategy, writes output."""
        cdef object item
        cdef double timestamp
        cdef cnp.ndarray frame
        cdef object msg
        cdef dict result_data
        cdef WorkerResult result

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


cdef class RecordWorker:
    """Reads from record_buffer, writes frames via FFMPEG subprocess (GPU-accelerated)."""
    def __init__(self, SharedFrameBuffer record_buffer):
        self.record_buffer = record_buffer
        self.running = True
        self._ffmpeg_process = None
        self._frame_size = None

    def initialize_writer(self, str filepath, double fps, tuple frame_size, str encoder='h264_nvenc'):
        self._frame_size = frame_size
        cdef int width = frame_size[0]
        cdef int height = frame_size[1]
        
        # Build ffmpeg command
        cmd = [
            'ffmpeg',
            '-y', # Overwrite
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{width}x{height}',
            '-pix_fmt', 'gray', # Mono camera
            '-r', str(fps),
            '-i', '-', # Read from stdin
            '-c:v', encoder,
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

    def run(self):
        cdef object item
        cdef double timestamp
        cdef cnp.ndarray frame
        while self.running:
            item = self.record_buffer.read_blocking(timeout=0.05)
            if item is None:
                continue
            timestamp, frame = item
            if self._ffmpeg_process is not None and self._ffmpeg_process.stdin is not None:
                try:
                    self._ffmpeg_process.stdin.write(frame.tobytes())
                except Exception as e:
                    print(f"Error writing to ffmpeg: {e}")
                    # stop recording if writing fails?
                    pass

    def stop(self):
        self.running = False
        self.release_writer()
