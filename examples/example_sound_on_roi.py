"""
Examples task where sound is presented when an object enters ROI.
User must indicate with arrow keys whether sound came from left or right.
"""

import numpy as np
from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from phonotaxis import gui
from phonotaxis import videomodule
from phonotaxis import soundmodule
from phonotaxis import config

# --- Configuration ---
#SAVE_VIDEO_TO = None #'/tmp/output.avi' #None
DISPLAY_MODE = 'binary'  # It can be 'grayscale' or 'binary'
FEEDBACK_DURATION = 1000  # In milliseconds

# -- Settings for object tracking --
BLACK_THRESHOLD = 50  # Theshold for binarizing the video frame
MIN_AREA = 4000  # Minimum area of the object to be considered valid for tracking
ROI = (320, 240, 40)  # (center_x, center_y, radius) of the region of interest (ROI)

# --- Application States ---
STATE_MONITORING = 0
STATE_SOUND_PLAYING = 1
STATE_WAITING_FOR_INPUT = 2
STATE_FEEDBACK = 3

class Task(gui.MainWindow):
    #object_in_roi = pyqtSignal()

    def __init__(self):
        super().__init__()
        # -- Additional GUI --
        self.threshold_slider = gui.SliderWidget(maxvalue=255, label="Threshold")
        self.minarea_slider = gui.SliderWidget(maxvalue=16000, label="Minimum area")
        self.status_label = gui.StatusWidget()
        self.layout.addWidget(self.threshold_slider)
        self.layout.addWidget(self.minarea_slider)
        self.layout.addWidget(self.status_label)

        self.current_state = STATE_MONITORING
        self.correct_channel = None

        self.start_video_thread()
        self.sound_player = soundmodule.SoundPlayer()
        
        self.feedback_timer = QTimer(self)
        self.feedback_timer.setSingleShot(True)
        self.feedback_timer.timeout.connect(self.reset_to_monitoring)

        # -- Connect signals from GUI --
        self.threshold_slider.value_changed.connect(self.update_threshold)
        self.minarea_slider.value_changed.connect(self.update_minarea)
        
    def update_threshold(self, value):
        self.video_thread.set_threshold(value)

    def update_minarea(self, value):
        self.video_thread.set_minarea(value)
        
    def start_video_thread(self):
        """Starts the video capture thread and connects its signals."""
        self.video_thread = videomodule.VideoThread(config.CAMERA_INDEX, mode=DISPLAY_MODE,
                                                    tracking=True)
        self.video_thread.set_threshold(BLACK_THRESHOLD)
        self.video_thread.set_minarea(MIN_AREA)
        #self.video_thread.set_tracking_params(threshold=BLACK_THRESHOLD,
        #                                      min_area=MIN_AREA)
        self.video_thread.frame_processed.connect(self.update_image)
        self.video_thread.start()

    def update_image(self, timestamp, frame, points):
        """Updates the video display label with new frames and points."""
        self.check_roi(points[0])  # Send first point: centroid
        self.video_widget.display_frame(frame, points, ROI)

    def check_roi(self, point):
        """
        Slot to receive the object's center and check if it's in the ROI.
        """
        distance = np.sqrt((point[0] - ROI[0])**2 +
                           (point[1] - ROI[1])**2)

        if distance <= ROI[2]:
            # The object is inside the ROI, handle the event (or emit signal)
            #print('Object in ROI detected:', point)
            #self.object_in_roi.emit()
            self.handle_object_in_roi()

    def reset_to_monitoring(self):
        """Resets the application state back to video monitoring."""
        self.current_state = STATE_MONITORING
        self.status_label.reset("Monitoring video feed...")
        
    def handle_object_in_roi(self):
        """
        Called when object enters the ROI. Triggers sound playback
        and transitions the application state.
        """
        if self.current_state == STATE_MONITORING:
            #print("Object in ROI detected. Playing sound.")
            self.current_state = STATE_SOUND_PLAYING
            self.status_label.setText("Sound playing... Listen carefully!")
            self.play_random_sound()
            # After sound plays, transition to waiting for input
            self.current_state = STATE_WAITING_FOR_INPUT
            self.status_label.setText("Press '1' for LEFT or '3' for RIGHT " +
                                      "to indicate sound source.")

    def play_random_sound(self):
        """Plays a sound to either the left or right speaker randomly."""
        channel_names = ['left', 'right']
        self.correct_channel = str(np.random.choice(channel_names))
        # NOTE: the code here is a little backwards. I should find the index first.
        index_correct_channel = channel_names.index(self.correct_channel)
        print(f"Playing sound to: {self.correct_channel} channel")
        #self.sound_player.play_noise()
        self.sound_player.play_tone(index_correct_channel)

    def keyPressEvent(self, event):
        """Handles key press events for user input."""
        #key_left_key = Qt.Key.Key_Left
        #key_right_key = Qt.Key.Key_Right
        key_left = Qt.Key.Key_1  # '<'
        key_right = Qt.Key.Key_3  # '>'
        
        if self.current_state == STATE_WAITING_FOR_INPUT:
            user_channel = None
            if event.key() == key_left:
                user_channel = 'left'
            elif event.key() == key_right:
                user_channel = 'right'

            if user_channel:
                self.current_state = STATE_FEEDBACK
                if user_channel == self.correct_channel:
                    style = ("font-size: 20px; font-weight: bold; padding: 10px;" +
                             "border-radius: 8px; background-color: #4CAF50; color: #fff;")
                    self.status_label.setStyleSheet(style) # Green for correct
                    self.status_label.setText("Correct!")
                    print("User was CORRECT!")
                else:
                    style = ("font-size: 20px; font-weight: bold; padding: 10px; " +
                             "border-radius: 8px; background-color: #F44336; color: #fff;")
                    self.status_label.setStyleSheet(style) # Red for incorrect
                    self.status_label.setText("Incorrect! It was "+
                                              f"{self.correct_channel.capitalize()}.")
                    print(f"User was INCORRECT! Correct was: {self.correct_channel}")

                self.feedback_timer.start(FEEDBACK_DURATION) # Start timer for feedback

    def closeEvent(self, event):
        """Handles the close event to stop the video thread."""
        self.video_thread.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    (app,paradigm) = gui.create_app(Task)
