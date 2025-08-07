"""
Record video and trigger events from video.
"""

import sys
import os
import time
import cv2
import numpy as np
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import QThread, pyqtSignal, Qt

# --- Configuration ---
#FOURCC_CODEC = cv2.VideoWriter_fourcc(*'XVID')  # Codec for AVI files. 'MP4V' for .mp4
FOURCC_CODEC = cv2.VideoWriter_fourcc(*'MP4V')  # Codec for AVI files. 'MP4V' for .mp4
RECORDING_FPS = 60  # Desired FPS for the output video. Can be adjusted or derived from camera.
DEFAULT_BLACK_THRESHOLD = 128  # Trigger sound when average pixel intensity is less than this
DEFAULT_MINIMUM_AREA = 4000  # Minimum area of the largest contour to consider it significant

class VideoThread(QThread):
    """
    A QThread subclass for handling video capture and processing in a separate thread.
    This prevents the GUI from freezing during video operations.

    Signals:
        camera_error_signal (str): Emitted when there is an error with the camera.
        frame_processed (float, np.ndarray, tuple): Emits the timestamp, processed frame,
                                                    and (x,y) of points of interest.
    """
    #new_frame_signal = pyqtSignal(np.ndarray)
    camera_error_signal = pyqtSignal(str)
    frame_processed = pyqtSignal(float, np.ndarray, tuple) # Emits frame and object centroid (x,y)

    def __init__(self, camera_index=0, mode='grayscale', tracking=False, debug=False):
        """
        Args:
            camera_index (int): Index of the camera to use.
            mode (str): Type of image emitted: ['grayscale', 'binary']
                        Note that this does not affect the saved video.
            tracking (bool): Whether to track the largest dark object in the video.
            debug (bool): If True, prints debug information to console.
        """
        super().__init__()
        self.camera_index = camera_index
        self._run_flag = True
        self.cap = None
        self.out = None # Initialize video writer to None
        self.fps = None
        self.mode = mode
        self.tracking = tracking
        self.recording_status = False  # Whether video recording is active
        self.filepath = None  # Path to save the video output, if any
        self.threshold = DEFAULT_BLACK_THRESHOLD  # Default threshold for detecting dark objects
        self.minarea = DEFAULT_MINIMUM_AREA  # Default minimum area of object to track
        self.debug = debug
        self.initialize_camera()
        #if self.save_to is not None:
        #    if not os.path.exists(os.path.dirname(self.save_to)):
        #        os.makedirs(os.path.dirname(self.save_to))
        #self.initialize_video_writer()

    def set_threshold(self, threshold):
        self.threshold = threshold
        
    def set_minarea(self, minarea):
        self.minarea = minarea

    def set_mode(self, mode):
        if mode not in ['grayscale', 'binary']:
            raise ValueError("Mode must be 'grayscale' or 'binary'.")
        self.mode = mode
                
    def initialize_camera(self):
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            self.camera_error_signal.emit(f"Could not open camera at index {self.camera_index}. " +
                                          "Please check if the camera is connected and not " +
                                          "in use by another application.")
            self._run_flag = False
            return

    def start_recording(self, filepath=None):
        """
        Starts the video recording. This should be called after setting the output file.
        """
        if filepath is not None:
            self.filepath = filepath
            self.initialize_video_writer(self.filepath)
            self.recording_status = True
            print(f"Video recording started: {self.filepath}")
        else:
            print("Video recording not started: No output file set or writer not initialized.")
        
    def stop_recording(self):
        """
        Stops the video recording and releases the video writer.
        """
        self.recording_status = False
        print("Video recording stopped.")
            
    def initialize_video_writer(self, filepath):
        # Create the directory if it does not exist
        self.filepath = filepath
        dir_path = os.path.dirname(self.filepath)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        # Get video properties for saving
        frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        # Use a fixed FPS for recording, or try self.cap.get(cv2.CAP_PROP_FPS) if reliable
        # If camera FPS is very low or variable, a fixed RECORDING_FPS is better.
        #fps = RECORDING_FPS
        # fps = self.cap.get(cv2.CAP_PROP_FPS)
        # if fps <= 0:  # If FPS is not set or invalid, use a default value
        #     fps = RECORDING_FPS

        # Initialize VideoWriter
        try:
            self.out = cv2.VideoWriter(self.filepath, FOURCC_CODEC, self.fps,
                                        (frame_width, frame_height))
            if not self.out.isOpened():
                raise IOError(f"Could not open video writer for {self.filepath}." +
                                "Check codec or file path.")
            print(f"Recording video to {self.filepath} at {self.fps} FPS, " +
                    f"resolution {frame_width}x{frame_height}")
        except Exception as e:
            self.camera_error_signal.emit(f"Error initializing video writer: {e}")
            self._run_flag = False
            self.cap.release() # Release camera if writer fails
            return
        
    def run(self):
        """
        Main loop for the thread. Captures video frames, processes them,
        and emits signals for display.
        """

        # Calculate proper frame interval based on desired FPS
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.fps <= 0:  # If FPS is not set or invalid, use a default value
            self.fps = RECORDING_FPS
            print('Warning: The camera did not return a valid FPS. ')
            print('The FPS of the video file will not be accurate. Using default FPS:', self.fps)
        else:
            print('Camera reported FPS:', self.fps)
        frame_interval = 1.0 / self.fps  # seconds between frames
        last_timestamp = 0

        while self._run_flag:
            ret, frame = self.cap.read()
            timestamp = time.time() # A float in seconds.

            if ret:
                if self.recording_status:
                    self.out.write(frame)

                # Convert frame to grayscale for black detection
                gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                # Process video (tracking, detection, etc)
                processed_frame, points = self.process_frame(gray_frame)

                # Emit signal with the new frame (e.g., to show video in GUI)
                self.frame_processed.emit(timestamp, processed_frame, points)
                #self.new_frame_signal.emit(gray_frame)
            else:
                # If frame reading fails, emit an error and stop
                self.camera_error_signal.emit("Failed to read frame from camera. " +
                                              "The camera might have been disconnected.")
                self._run_flag = False

            QThread.msleep(1)  # Small delay to reduce CPU usage

        # Release the camera and video writer when the thread stops
        if self.cap:
            self.cap.release()
        if self.out:
            self.out.release()
        print("Video thread stopped and resources released.")

    def process_frame(self, frame):
        """
        Here is where you will perform tracking and detection of elements in video.
        You want this function to be fast, so avoid heavy processing here.
        """
        if not self.tracking:
            return (frame, ())
        
        max_value = 255  # Assumes 8-bit grayscale images
        inverted_frame = cv2.bitwise_not(frame)
        #inverted_frame = cv2.blur(inverted_frame, (5, 5))  # Optional: blur to reduce noise
        ret, binary_frame = cv2.threshold(inverted_frame, max_value-self.threshold,
                                          max_value, cv2.THRESH_BINARY) # + cv2.THRESH_OTSU)
        contours, hierarchy = cv2.findContours(binary_frame, cv2.RETR_EXTERNAL,
                                               cv2.CHAIN_APPROX_SIMPLE)
        centroid = (-1,-1)  # Default centroid if no contours found
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
        points = (centroid,)  # A tuple of points of interest
        if self.mode == 'grayscale':
            processed_frame = frame
        elif self.mode == 'binary':
            processed_frame = cv2.bitwise_not(binary_frame)
        if self.debug:
            print(f"Centroid: {centroid} \t Largest area: {largest_area}")
        return (processed_frame, points)
        
    def stop(self):
        """Stops the video capture thread gracefully."""
        self._run_flag = False
        self.wait()


# -- For testing purposes --
class VideoThreadBlackDetect(VideoThread):
    """
    A specialized video thread that detects black screens and triggers a signal.
    Inherits from VideoThread to reuse camera handling and video processing.
    """
    black_screen_detected_signal = pyqtSignal()
    
    def __init__(self, camera_index=0, save_to=None, threshold=DEFAULT_BLACK_THRESHOLD):
        super().__init__(camera_index, save_to)
        self.black_threshold = threshold

    def process_frame(self, frame):
        # Check if the screen is mostly black
        avg_intensity = np.mean(frame)
        if avg_intensity < self.black_threshold:
            self.black_screen_detected_signal.emit()
        return (frame, ())  # Return the frame and an empty tuple for points of interest


def count_video_frames(video_path):
    """
    Manually count frames by reading through the entire video.
    This is slower but works with any video format.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return 0
    
    frame_count = 0
    while True:
        ret, _ = cap.read()
        if not ret:
            break
        frame_count += 1
    
    cap.release()
    return frame_count