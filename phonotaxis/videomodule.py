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
FOURCC_CODEC = cv2.VideoWriter_fourcc(*'XVID')  # Codec for AVI files. 'MP4V' for .mp4
RECORDING_FPS = 20  # Desired FPS for the output video. Can be adjusted or derived from camera.
DEFAULT_BLACK_THRESHOLD = 40  # Trigger sound when average pixel intensity is less than this
AREA_THRESHOLD = 4000  # Minimum area of the largest contour to consider it significant

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

    def __init__(self, camera_index=0, save_to=None, mode='grayscale', tracking=False):
        """
        Args:
            camera_index (int): Index of the camera to use.
            save_to (str): Path to save the video output. If None, no saving occurs.
            mode (str): Type of image emitted: ['grayscale', 'binary']
                        Note that this does not affect the saved video.
            tracking (bool): Whether to track the largest dark object in the video.
        """
        super().__init__()
        self.camera_index = camera_index
        self._run_flag = True
        self.cap = None
        self.out = None # Initialize video writer to None
        self.mode = mode
        self.tracking = tracking
        self.save_to = save_to
        self.initialize_camera()

    def set_threshold(self, threshold):
        self.threshold = threshold
        
    def set_tracking_params(self, threshold=DEFAULT_BLACK_THRESHOLD,
                            min_area=AREA_THRESHOLD):
        """
        Args:
            threshold (int): Threshold for detecting dark objects in grayscale.
            min_area (int): Minimum area of the largest contour to consider it significant.
        """
        self.threshold = threshold
        self.min_area = min_area
        
    def initialize_camera(self):
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            self.camera_error_signal.emit(f"Could not open camera at index {self.camera_index}. " +
                                          "Please check if the camera is connected and not " +
                                          "in use by another application.")
            self._run_flag = False
            return

        # Get video properties for saving
        frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        # Use a fixed FPS for recording, or try self.cap.get(cv2.CAP_PROP_FPS) if reliable
        # If camera FPS is very low or variable, a fixed RECORDING_FPS is better.
        fps = RECORDING_FPS

        # Initialize VideoWriter
        try:
            if self.save_to is not None:
                self.out = cv2.VideoWriter(self.save_to, FOURCC_CODEC, fps,
                                           (frame_width, frame_height))
                if not self.out.isOpened():
                    raise IOError(f"Could not open video writer for {self.save_to}." +
                                  "Check codec or file path.")
                print(f"Recording video to {self.save_to} at {fps} FPS, " +
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
        while self._run_flag:
            ret, frame = self.cap.read()
            timestamp = time.time() # A float in seconds.

            if ret:
                # Write the frame to the output video file
                if self.save_to is not None:
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

            QThread.msleep(30)  # Small delay to reduce CPU usage

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
        #self.frame_processed.emit(frame, ())
        #    return
        
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
            if largest_contour is not None and largest_area > AREA_THRESHOLD:
                mom = cv2.moments(largest_contour)
                if mom["m00"] != 0:
                    cX = int(mom["m10"] / mom["m00"])
                    cY = int(mom["m01"] / mom["m00"])
                    centroid = (cX, cY)
        # Emit the processed frame and the centroid coordinates
        # if self.mode == 'grayscale':
        #     self.frame_processed.emit(frame, centroid)
        # elif self.mode == 'binary':
        #     self.frame_processed.emit(cv2.bitwise_not(binary_frame), centroid)
        points = (centroid,)  # A tuple of points of interest
        if self.mode == 'grayscale':
            processed_frame = frame
        elif self.mode == 'binary':
            processed_frame = cv2.bitwise_not(binary_frame)
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


#DEFAULT_BLACK_THRESHOLD = 60  # Trigger sound when average pixel intensity is less than this
#AREA_THRESHOLD = 4000
class OLD_VideoThreadTracking(VideoThread):
    """
    A specialized video thread for tracking the darkest object.
    Inherits from VideoThread to reuse camera handling and video processing.
    """
    #frame_processed = pyqtSignal(tuple) # Emits the centroid (x,y)
    frame_processed = pyqtSignal(np.ndarray, tuple) # Emits the frame and centroid (x,y)
    
    def __init__(self, camera_index=0, save_to=None, threshold=DEFAULT_BLACK_THRESHOLD,
                 mode='grayscale'):
        """
        Args:
            camera_index (int): Index of the camera to use.
            save_to (str): Path to save the video output. If None, no saving occurs.
            threshold (int): Threshold for detecting dark objects in grayscale.
            mode (str): Type of image emitted: ['grayscale', 'binary']
                        Note that this does not affect the saved video.
        """
        super().__init__(camera_index, save_to)
        self.threshold = threshold
        self.mode = mode

    def process_frame(self, frame):
        max_value = 255
        inverted_frame = cv2.bitwise_not(frame)
        #inverted_frame = cv2.blur(inverted_frame, (5, 5))
        ret, binary_frame = cv2.threshold(inverted_frame, max_value-self.threshold,
                                          max_value, cv2.THRESH_BINARY) # + cv2.THRESH_OTSU)
        contours, hierarchy = cv2.findContours(binary_frame, cv2.RETR_EXTERNAL,
                                               cv2.CHAIN_APPROX_SIMPLE)
        centroid = ()
        largest_area = 0
        largest_contour = None

        if contours:
            #print('----------------------------------')
            for indc, cnt in enumerate(contours):
                area = cv2.contourArea(cnt)
                #cv2.drawContours(frame, [cnt], -1, (255, 255, 255), 2) # White contour
                #print(f"{indc}: {area}")
                if area > largest_area:
                    largest_area = area
                    largest_contour = cnt
            if largest_contour is not None and largest_area > AREA_THRESHOLD:
                mom = cv2.moments(largest_contour)
                if mom["m00"] != 0:
                    cX = int(mom["m10"] / mom["m00"])
                    cY = int(mom["m01"] / mom["m00"])
                    centroid = (cX, cY)

                    # Optional: Draw the contour and centroid
                    #if self.mode == 'grayscale':
                    #    cv2.drawContours(frame, [largest_contour], -1, (255, 255, 255), 2)
                    #cv2.drawContours(frame, [largest_contour], -1, (255, 255, 255), 4)
                    #cv2.circle(frame, centroid, 5, (255, 255, 255), -1) # Red centroid
                    #cv2.putText(frame, f"({cX},{cY}: {largest_area})",
                    #            (cX + 10, cY + 10),
                    #            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                #print(f"*{indc}* : {largest_area}")
        # Emit the processed frame and the centroid coordinates
        if self.mode == 'grayscale':
            self.frame_processed.emit(frame, centroid)
        elif self.mode == 'binary':
            self.frame_processed.emit(cv2.bitwise_not(binary_frame), centroid)
        
