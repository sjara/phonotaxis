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

        # MASK masking parameters
        self.mask_enabled = False  # Whether to apply MASK masking
        self.mask_coords = None  # List of coordinates: [x1,y1,x2,y2] for rectangular or [cx,cy,radius] for circular

        # Store tracking
        self.timestamps = []
        self.points = []  # List where each element is a list of (x,y) coordinates for one point across time

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

    def set_circular_mask(self, coords):
        """
        Set circular region of interest for masking.
        Only pixels inside this circle will be considered for object detection.
        
        Args:
            coords (list): [center_x, center_y, radius] - center coordinates and radius of the circular mask
        """
        if len(coords) != 3:
            raise ValueError("Circular mask requires exactly 3 coordinates: [center_x, center_y, radius]")
        
        self.mask_coords = coords
        self.mask_enabled = True
        if self.debug:
            center_x, center_y, radius = coords
            print(f"Circular MASK set: center ({center_x}, {center_y}), radius {radius}")

    def set_rectangular_mask(self, coords):
        """
        Set rectangular region of interest for masking.
        Only pixels inside this rectangle will be considered for object detection.
        
        Args:
            coords (list): [x1, y1, x2, y2] - top-left and bottom-right coordinates of the rectangle
        """
        if len(coords) != 4:
            raise ValueError("Rectangular mask requires exactly 4 coordinates: [x1, y1, x2, y2]")
        
        self.mask_coords = coords
        self.mask_enabled = True
        if self.debug:
            x1, y1, x2, y2 = coords
            print(f"Rectangular MASK set: ({x1}, {y1}) to ({x2}, {y2})")

    def set_rectangular_mask_from_center(self, center_x, center_y, width, height):
        """
        Set rectangular MASK from center point and dimensions.
        
        Args:
            center_x (int): Center x coordinate
            center_y (int): Center y coordinate
            width (int): Width of the rectangle
            height (int): Height of the rectangle
        """
        half_width = width // 2
        half_height = height // 2
        x1 = max(0, center_x - half_width)
        y1 = max(0, center_y - half_height)
        x2 = center_x + half_width
        y2 = center_y + half_height
        self.set_rectangular_mask([x1, y1, x2, y2])

    def disable_mask(self):
        """Disable MASK masking - use the full frame for object detection."""
        self.mask_enabled = False
        self.mask_coords = None
        if self.debug:
            print("MASK masking disabled")

    def get_mask(self):
        """
        Get current MASK settings.
        
        Returns:
            dict: Dictionary with MASK parameters or None if disabled
        """
        if not self.mask_enabled or self.mask_coords is None:
            return None
        
        if len(self.mask_coords) == 3:
            # Circular mask
            center_x, center_y, radius = self.mask_coords
            return {
                'type': 'circular',
                'coords': self.mask_coords,
                'center_x': center_x,
                'center_y': center_y,
                'radius': radius,
                'enabled': self.mask_enabled
            }
        elif len(self.mask_coords) == 4:
            # Rectangular mask
            x1, y1, x2, y2 = self.mask_coords
            return {
                'type': 'rectangular',
                'coords': self.mask_coords,
                'x1': x1,
                'y1': y1,
                'x2': x2,
                'y2': y2,
                'enabled': self.mask_enabled
            }
        else:
            return None

    def set_mode(self, mode):
        if mode not in ['grayscale', 'binary']:
            raise ValueError("Mode must be 'grayscale' or 'binary'.")
        self.mode = mode

    def store_tracking_data(self, timestamp, points):
        """
        Appends timestamp and points to the tracking lists, but only if video recording is active.
        
        Args:
            timestamp (float): The timestamp of the frame.
            points (tuple): The points of interest detected in the frame.
        """
        if self.recording_status:
            self.timestamps.append(timestamp)
            
            # Ensure we have enough point lists for all detected points
            while len(self.points) < len(points):
                self.points.append([])
            
            # Append coordinates to each point's list
            for i, point in enumerate(points):
                self.points[i].append(point)
                
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

                # Store tracking data if recording
                self.store_tracking_data(timestamp, points)

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

    def apply_circular_mask(self, frame):
        """
        Apply circular masking to the frame by setting pixels outside the circular mask to white (255).

        Args:
            frame (np.ndarray): Grayscale frame to mask
            
        Returns:
            np.ndarray: Masked frame
        """
        if not self.mask_enabled or self.mask_coords is None or len(self.mask_coords) != 3:
            return frame
            
        # Create a copy of the frame to avoid modifying the original
        masked_frame = frame.copy()
        height, width = frame.shape
        
        # Get circle parameters
        center_x, center_y, radius = self.mask_coords
        
        if radius <= 0:
            print("Warning: Invalid circular mask radius, using full frame")
            return frame
            
        # Create coordinate grids
        y_coords, x_coords = np.ogrid[:height, :width]
        
        # Calculate distance from center for each pixel
        distance_from_center = np.sqrt((x_coords - center_x)**2 + (y_coords - center_y)**2)
        
        # Create mask: pixels outside the circle are set to white (255)
        mask_outside_circle = distance_from_center > radius
        masked_frame[mask_outside_circle] = 255
        
        return masked_frame

    def apply_mask(self, frame):
        """
        Apply masking to the frame based on the current mask coordinates.
        
        Args:
            frame (np.ndarray): Grayscale frame to mask
            
        Returns:
            np.ndarray: Masked frame
        """
        if not self.mask_enabled or self.mask_coords is None:
            return frame
            
        if len(self.mask_coords) == 3:
            # Circular mask: [center_x, center_y, radius]
            return self.apply_circular_mask(frame)
        elif len(self.mask_coords) == 4:
            # Rectangular mask: [x1, y1, x2, y2]
            return self.apply_rectangular_mask(frame)
        else:
            print(f"Warning: Invalid mask coordinates length ({len(self.mask_coords)}), using full frame")
            return frame

    def apply_rectangular_mask(self, frame):
        """
        Apply rectangular masking to the frame by setting pixels outside the mask to white (255).

        Args:
            frame (np.ndarray): Grayscale frame to mask
            
        Returns:
            np.ndarray: Masked frame
        """
        if not self.mask_enabled or self.mask_coords is None or len(self.mask_coords) != 4:
            return frame
            
        # Create a copy of the frame to avoid modifying the original
        masked_frame = frame.copy()
        height, width = frame.shape
        
        # Get rectangle parameters
        x1, y1, x2, y2 = self.mask_coords
        
        # Set default bounds if not specified and validate
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(width, x2) if x2 is not None else width
        y2 = min(height, y2) if y2 is not None else height
        
        # Ensure coordinates are valid
        if x1 >= x2 or y1 >= y2:
            print("Warning: Invalid MASK coordinates, using full frame")
            return frame
            
        # Create mask: 0 inside MASK, 255 outside MASK
        mask = np.ones_like(frame) * 255
        mask[y1:y2, x1:x2] = 0
        
        # Set pixels outside MASK to white (255)
        masked_frame[mask == 255] = 255
        
        return masked_frame

    def process_frame(self, frame):
        """
        Here is where you will perform tracking and detection of elements in video.
        You want this function to be fast, so avoid heavy processing here.
        """
        if not self.tracking:
            return (frame, ())
        
        # Apply MASK masking if enabled
        masked_frame = self.apply_mask(frame)
        
        max_value = 255  # Assumes 8-bit grayscale images
        inverted_frame = cv2.bitwise_not(masked_frame)
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
            # Return the original frame for display, but use masked frame for processing
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