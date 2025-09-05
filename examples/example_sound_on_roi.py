"""
Examples task where sound is presented when an object enters INITZONE.
User must indicate with arrow keys whether sound came from left or right.
"""

import os
import time
import numpy as np
import pandas as pd
from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from phonotaxis import gui
from phonotaxis import videomodule
from phonotaxis import soundmodule
from phonotaxis import config

subject = 'test000'

# --- Configuration ---
DISPLAY_MODE = 'binary'  # It can be 'grayscale' or 'binary'
FEEDBACK_DURATION = 1000  # In milliseconds

# -- Settings for object tracking --
BLACK_THRESHOLD = 50  # Theshold for binarizing the video frame
MIN_AREA = 4000  # Minimum area of the object to be considered valid for tracking
DEFAULT_INITZONE = [320, 240, 80]  # [center_x, center_y, radius] of the region of interest (INITZONE)
DEFAULT_MASK = [320, 240, 240]  # [center_x, center_y, radius] of the region to mask (MASK)

# --- Application States ---
STATE_MONITORING = 0
STATE_SOUND_PLAYING = 1
STATE_WAITING_FOR_INPUT = 2
STATE_FEEDBACK = 3

class Task(gui.MainWindow):
    #object_in_initzone = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.initzone = DEFAULT_INITZONE
        self.mask = DEFAULT_MASK

        # -- Additional GUI --
        self.threshold_slider = gui.SliderWidget(maxvalue=255, label="Threshold", value=BLACK_THRESHOLD)
        self.minarea_slider = gui.SliderWidget(maxvalue=16000, label="Min area", value=MIN_AREA)
        self.initzone_radius_slider = gui.SliderWidget(maxvalue=300, label="IZ radius", value=self.initzone[2])
        self.mask_radius_slider = gui.SliderWidget(maxvalue=300, label="Mask radius", value=self.mask[2])
        self.status_label = gui.StatusWidget()
        self.session_control = gui.SessionControlWidget()

        self.params = gui.Container()
        self.params['subject'] = gui.StringParam('Subject', value='test000', group='Session info')
        self.params['sessionDuration'] = gui.NumericParam('Duration', value=60, units='s',
                                                        group='Session info')
        self.params['sessionTime'] = gui.NumericParam('Session time', value=0, enabled=False,
                                                      units='s', decimals=1, group='Session info')
        self.sessionInfo = self.params.layout_group('Session info')

        self.layout.addWidget(self.threshold_slider)
        self.layout.addWidget(self.minarea_slider)
        self.layout.addWidget(self.initzone_radius_slider)
        self.layout.addWidget(self.mask_radius_slider)
        self.layout.addWidget(self.status_label)
        hbox = gui.QHBoxLayout()
        hbox.addWidget(self.session_control)
        hbox.addWidget(self.sessionInfo)
        self.layout.addLayout(hbox)

        self.session_start_time = None  # To store the start time of the session
        self.session_running = False
        self.current_state = STATE_MONITORING
        self.correct_channel = None
        self.inside_initzone = False

        self.start_video_thread()
        self.sound_player = soundmodule.SoundPlayer()
        self.frame_data = {'timestamp': [], 'centroid_x': [], 'centroid_y': []}  # To store frame data
        self.trial_data = []  # To store trial data for later analysis

        self.feedback_timer = QTimer(self)
        self.feedback_timer.setSingleShot(True)
        self.feedback_timer.timeout.connect(self.reset_to_monitoring)

        # -- Connect signals from GUI --
        self.threshold_slider.value_changed.connect(self.update_threshold)
        self.minarea_slider.value_changed.connect(self.update_minarea)
        self.initzone_radius_slider.value_changed.connect(self.update_initzone)
        self.mask_radius_slider.value_changed.connect(self.update_mask)
        self.session_control.resume.connect(self.start_session)
        self.session_control.pause.connect(self.stop_session)

        # -- Set paths for video and data saving --
        self.video_filepath = os.path.join(config.VIDEO_PATH, subject, f"{subject}_output.mp4")
        self.data_filepath = os.path.join(config.DATA_PATH, subject, f"{subject}_data.csv")

    def start_session(self):
        if not self.session_running:
            self.session_start_time = time.time()  # Record the start time
            self.video_thread.start_recording(self.video_filepath)
            self.session_running = True

    def stop_session(self):
        if self.session_running:
            self.session_running = False
            self.save_data()
            self.status_label.setText("Session stopped. Data saved.")
            self.video_thread.stop_recording()

    def save_data(self):
        """
        Save the session data to a CSV file.
        This can include timestamps, object positions, and subject responses.
        """
        # Create the directory if it does not exist
        dir_path = os.path.dirname(self.data_filepath)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
        # Create pandas DataFrame from the frame data and save to CSV
        df = pd.DataFrame(self.frame_data)
        df.to_csv(self.data_filepath, index=False)
        print(f"Data saved to {self.data_filepath}")

    def update_threshold(self, value):
        self.video_thread.set_threshold(value)

    def update_minarea(self, value):
        self.video_thread.set_minarea(value)

    def update_initzone(self, radius):
        self.initzone[2] = radius

    def update_mask(self, radius):
        self.mask[2] = radius
        self.video_thread.set_circular_mask(self.mask)

    def start_video_thread(self):
        """Starts the video capture thread and connects its signals."""
        self.video_thread = videomodule.VideoThread(config.CAMERA_INDEX, mode=DISPLAY_MODE,
                                                    tracking=True)
        self.video_thread.set_threshold(self.threshold_slider.value)
        self.video_thread.set_minarea(self.minarea_slider.value)
        self.video_thread.set_circular_mask(self.mask)
        self.video_thread.frame_processed.connect(self.update_image)
        self.video_thread.start()

    def update_image(self, timestamp, frame, points):
        """Updates the video display label with new frames and points."""
        if self.session_running:
            self.check_initzone(points[0])  # Send first point: centroid
            self.frame_data['timestamp'].append(timestamp)
            # FIXME: is the centroid point (x, y) or (row, col)?
            self.frame_data['centroid_x'].append(points[0][0])
            self.frame_data['centroid_y'].append(points[0][1])
        self.video_widget.display_frame(frame, points, self.initzone, self.mask)
        if self.session_running:
            self.params['sessionTime'].set_value(timestamp - self.session_start_time)
            if timestamp - self.session_start_time >= self.params['sessionDuration'].get_value():
                self.session_control.stop()

    def check_initzone(self, point):
        """
        Slot to receive the object's center and check if it's in the INITZONE.
        """
        distance = np.sqrt((point[0] - self.initzone[0])**2 +
                           (point[1] - self.initzone[1])**2)

        if distance <= self.initzone[2]:
            # The object is inside the INITZONE, handle the event (or emit signal)
            #print('Object in INITZONE detected:', point)
            #self.object_in_initzone.emit()
            if not self.inside_initzone:
                self.inside_initzone = True
                self.handle_entered_initzone()
        else:
            self.inside_initzone = False

    def handle_entered_initzone(self):
        """
        Called when object enters the INITZONE. Triggers sound playback
        and transitions the application state.
        """
        if self.current_state == STATE_MONITORING:
            #print("Object in INITZONE detected. Playing sound.")
            self.current_state = STATE_SOUND_PLAYING
            self.status_label.setText("Sound playing... Listen carefully!")
            self.play_random_sound()
            # After sound plays, transition to waiting for input
            self.current_state = STATE_WAITING_FOR_INPUT
            # self.status_label.setText("Press '1' for LEFT or '3' for RIGHT " +
            #                           "to indicate sound source.")
            self.status_label.setText("Press LEFT or RIGHT arrow key " +
                                      "to indicate sound source.")

    def reset_to_monitoring(self):
        """Resets the application state back to video monitoring."""
        self.current_state = STATE_MONITORING
        self.status_label.reset("Monitoring video feed...")
        
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
        key_left = Qt.Key.Key_Left
        key_right = Qt.Key.Key_Right
        #key_left = Qt.Key.Key_1  # '<'
        #key_right = Qt.Key.Key_3  # '>'
        
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
