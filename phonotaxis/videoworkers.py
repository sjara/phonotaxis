import time
import cv2
import numpy as np
import subprocess
from typing import List, Optional
from .sharedbuffer import SharedFrameBuffer, ResultBuffer

class CaptureWorker:
    """Reads frames from cv2.VideoCapture, fans out to multiple buffers."""
    def __init__(self, cap: cv2.VideoCapture,
                 process_buffers: List[SharedFrameBuffer],
                 record_buffer: SharedFrameBuffer):
        self.cap = cap
        self.process_buffers = process_buffers
        self.record_buffer = record_buffer
        self.running: bool = True
        self.recording: bool = False

    def _ensure_grayscale(self, frame):
        if len(frame.shape) == 3:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame

    def run(self):
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


class ProcessWorker:
    """Reads from raw_buffer, runs process_frame logic, writes to result_buffer."""
    def __init__(self, raw_buffer: SharedFrameBuffer, result_buffer: ResultBuffer,
                 threshold: int, minarea: int, tracking: bool = True):
        self.raw_buffer = raw_buffer
        self.result_buffer = result_buffer
        
        self.threshold: int = threshold
        self.minarea: int = minarea
        self.tracking: bool = tracking
        self.mask_enabled: bool = False
        self.mask_coords: Optional[list] = None
        self.mode: str = 'grayscale'
        
        self.running: bool = True
        
    def set_circular_mask(self, coords):
        self.mask_coords = coords
        self.mask_enabled = True

    def set_rectangular_mask(self, coords):
        self.mask_coords = coords
        self.mask_enabled = True

    def disable_mask(self):
        self.mask_enabled = False
        self.mask_coords = None

    def run(self):
        while self.running:
            item = self.raw_buffer.read_blocking(timeout=0.05)
            if item is None:
                continue
            timestamp, frame = item
            processed_frame, points, contour = self.process_frame(frame)
            self.result_buffer.try_write_result(timestamp, processed_frame, points, contour)

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

    def process_frame(self, frame):
        if not self.tracking:
            return (frame, (), None)
        
        masked_frame = self.apply_mask(frame)
        
        max_value = 255
        inverted_frame = cv2.bitwise_not(masked_frame)
        ret, binary_frame = cv2.threshold(inverted_frame, max_value-self.threshold,
                                          max_value, cv2.THRESH_BINARY)
        contours, hierarchy = cv2.findContours(binary_frame, cv2.RETR_EXTERNAL,
                                               cv2.CHAIN_APPROX_SIMPLE)
        centroid = (-1,-1)
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
        points = (centroid,)
        if self.mode == 'grayscale':
            processed_frame = frame
        elif self.mode == 'binary':
            processed_frame = cv2.bitwise_not(binary_frame)
        else:
            processed_frame = frame
            
        return (processed_frame, points, largest_contour)

    def stop(self):
        self.running = False


class RecordWorker:
    """Reads from record_buffer, writes frames via FFMPEG subprocess (GPU-accelerated)."""
    def __init__(self, record_buffer: SharedFrameBuffer):
        self.record_buffer = record_buffer
        self.running: bool = True
        self._ffmpeg_process: Optional[subprocess.Popen] = None
        self._frame_size = None

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
