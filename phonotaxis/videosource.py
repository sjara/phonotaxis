import cv2
import numpy as np
from typing import Optional, Tuple, Union

class VideoSource:
    """Abstract interface for video sources (OpenCV, PySpin, Aravis, etc.)."""
    
    def __init__(self):
        self._target_fps: Optional[float] = None
        self._target_exposure: Optional[float] = None
        self._target_gain: Optional[float] = None
    
    def open(self) -> bool:
        """Open the video source. Returns True if successful."""
        raise NotImplementedError

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read a frame from the source. Returns (success, frame)."""
        raise NotImplementedError

    def release(self) -> None:
        """Release the video source resources."""
        raise NotImplementedError

    @property
    def fps(self) -> float:
        """Get the frame rate of the video source."""
        raise NotImplementedError

    @property
    def frame_width(self) -> int:
        """Get the width of the frames."""
        raise NotImplementedError

    @property
    def frame_height(self) -> int:
        """Get the height of the frames."""
        raise NotImplementedError

    @property
    def exposure(self) -> float:
        """Get the current exposure time (typically in microseconds)."""
        raise NotImplementedError

    @property
    def gain(self) -> float:
        """Get the current gain (typically in dB)."""
        raise NotImplementedError

    def set_fps(self, fps: float) -> bool:
        """Set the frame rate of the video source. Returns True if successful."""
        raise NotImplementedError

    def set_exposure(self, exposure: float) -> bool:
        """Set the exposure time (typically in microseconds). Returns True if successful."""
        raise NotImplementedError

    def set_gain(self, gain: float) -> bool:
        """Set the gain (typically in dB). Returns True if successful."""
        raise NotImplementedError

    def set_position(self, frame_index: int) -> bool:
        """Set the playback position (primarily for video files)."""
        return False


class CV2VideoSource(VideoSource):
    """OpenCV-based video source implementation."""
    
    def __init__(self, camera_index_or_path: Union[int, str] = 0):
        super().__init__()
        self.target = camera_index_or_path
        self.cap: Optional[cv2.VideoCapture] = None

    def open(self) -> bool:
        if self.cap is None:
            self.cap = cv2.VideoCapture(self.target)
            if self.cap.isOpened():
                if self._target_fps is not None:
                    self.cap.set(cv2.CAP_PROP_FPS, self._target_fps)
                if self._target_exposure is not None:
                    self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)  # 1 = manual mode
                    self.cap.set(cv2.CAP_PROP_EXPOSURE, self._target_exposure)
                if self._target_gain is not None:
                    self.cap.set(cv2.CAP_PROP_GAIN, self._target_gain)
        return self.cap.isOpened()

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self.cap is None:
            return False, None
        return self.cap.read()

    def release(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    @property
    def fps(self) -> float:
        if self.cap is None:
            self.open()
        if self.cap is None:
            return 0.0
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        return fps if fps > 0.0 else 30.0

    @property
    def frame_width(self) -> int:
        if self.cap is None:
            self.open()
        if self.cap is None:
            return 0
        return int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))

    @property
    def frame_height(self) -> int:
        if self.cap is None:
            self.open()
        if self.cap is None:
            return 0
        return int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    @property
    def exposure(self) -> float:
        if self.cap is None:
            self.open()
        if self.cap is None:
            return 0.0
        return self.cap.get(cv2.CAP_PROP_EXPOSURE)

    @property
    def gain(self) -> float:
        if self.cap is None:
            self.open()
        if self.cap is None:
            return 0.0
        return self.cap.get(cv2.CAP_PROP_GAIN)

    def set_fps(self, fps: float) -> bool:
        self._target_fps = fps
        if self.cap is None:
            return False
        return self.cap.set(cv2.CAP_PROP_FPS, fps)

    def set_exposure(self, exposure: float) -> bool:
        self._target_exposure = exposure
        if self.cap is None:
            return False
        self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)  # 1 = manual mode
        return self.cap.set(cv2.CAP_PROP_EXPOSURE, exposure)

    def set_gain(self, gain: float) -> bool:
        self._target_gain = gain
        if self.cap is None:
            return False
        return self.cap.set(cv2.CAP_PROP_GAIN, gain)

    def set_position(self, frame_index: int) -> bool:
        if self.cap is None:
            return False
        return self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
