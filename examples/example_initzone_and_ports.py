"""
Example task: play a sound when entering initiation zone and
deliver water reward when poking on either port.
"""

import numpy as np
from bidict import bidict
from PyQt6.QtWidgets import QWidget, QMainWindow, QHBoxLayout, QVBoxLayout
from phonotaxis import gui
from phonotaxis import widgets
from phonotaxis import soundmodule
from phonotaxis import controller
from phonotaxis import arduinomodule
from phonotaxis import videomodule
from phonotaxis import statematrix
from phonotaxis import utils
from phonotaxis import emulator
from phonotaxis import config


# --- Sound settings ---
SAMPLING_RATE = 44100

# --- Sound IDs for state machine integer outputs ---
SOUND_ID_INITZONE = 1
SOUND_ID_LEFT = 2
SOUND_ID_RIGHT = 3

# -- Settings for object tracking --
BLACK_THRESHOLD = 50  # Theshold for binarizing the video frame
MIN_AREA = 4000  # Minimum area of the object to be considered valid for tracking
DEFAULT_INITZONE = [320, 240, 80]  # [center_x, center_y, radius] of the region of interest (INITZONE)
DEFAULT_MASK = [320, 240, 240]  # [center_x, center_y, radius] of the region to mask (MASK)

# --- State machine inputs and outputs ---
VIDEO_INPUTS = ['IZ']  # Inputs from video tracking
ARDUINO_INPUTS = list(config.INPUT_PINS.keys())  # Inputs from Arduino/emulator
INPUTS = VIDEO_INPUTS + ARDUINO_INPUTS  # Combined inputs for state matrix
OUTPUTS = list(config.OUTPUT_PINS.keys())

class Task(QMainWindow):
    def __init__(self):
        super().__init__()
        self.name = 'example'  # Paradigm name
        self.setWindowTitle("Water and sound on poke")
        #self.setGeometry(100, 100, 800, 600)
        self.setWindowIcon(gui.create_icon())

        self.initzone = DEFAULT_INITZONE.copy()
        self.mask = DEFAULT_MASK.copy()

        # -- Connect messenger --
        self.messagebar = gui.Messenger()
        self.messagebar.timed_message.connect(self._show_message)
        self.messagebar.collect('Created window')

        # -- Main widgets --
        self.session_running = False
        self.controller = controller.SessionController(debug=False)
        self.video_widget = widgets.VideoWidget()
        self.video_widget.set_contour_display(True)

        # -- Additional GUI --
        self.threshold_slider = widgets.SliderWidget(maxvalue=255, label="Threshold", value=BLACK_THRESHOLD)
        self.minarea_slider = widgets.SliderWidget(maxvalue=16000, label="Min area", value=MIN_AREA)
        self.initzone_radius_slider = widgets.SliderWidget(maxvalue=300, label="IZ radius", value=self.initzone[2])
        self.mask_radius_slider = widgets.SliderWidget(maxvalue=300, label="Mask radius", value=self.mask[2])

        # -- Connect signals from GUI --
        #self.controller.status_update.connect(self.on_timer_tick)
        self.controller.session_started.connect(self.start_session)
        #self.controller.session_stopped.connect(self.stop_session)
        self.controller.prepare_next_trial.connect(self.prepare_next_trial)

        # -- Connect signals to messenger
        self.controller.log_message.connect(self.messagebar.collect)

        # -- Add container for storing results from each trial --
        self.results = utils.EnumContainer()
        maxNtrials = 4000
        self.results.labels['choice'] = bidict({'left':0, 'right':1, 'none':2})
        self.results['choice'] = np.empty(maxNtrials, dtype=int)

        self.params = gui.Container()
        self.params['subject'] = gui.StringParam('Subject', value='test000', group='Session info')
        self.params['trainer'] = gui.StringParam('Trainer', value='', group='Session info')
        self.params['sessionDuration'] = gui.NumericParam('Duration', value=200, units='s',
                                                        group='Session info')
        self.sessionInfo = self.params.layout_group('Session info')

        self.params['soundDuration'] = gui.NumericParam('Sound duration', value=0.4, units='s',
                                                        group='Other params')
        self.params['valveDuration'] = gui.NumericParam('Valve duration', value=0.1, units='s', 
                                                        group='Other params')
        self.otherParams = self.params.layout_group('Other params')  

        # --- GUI layout ---
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QHBoxLayout(self.central_widget)

        col1 = QVBoxLayout()
        col2 = QVBoxLayout()
        self.layout.addLayout(col1)
        self.layout.addLayout(col2)

        col1.addWidget(self.video_widget)
        col1.addWidget(self.threshold_slider)
        col1.addWidget(self.minarea_slider)
        col1.addWidget(self.initzone_radius_slider)
        col1.addWidget(self.mask_radius_slider)

        # hbox = QHBoxLayout()
        # hbox.addWidget(self.controller.gui)
        # hbox.addWidget(self.sessionInfo)
        # # hbox.addWidget(self.savedata_widget)
        # col1.addLayout(hbox)

        col2.addWidget(self.controller.gui)
        col2.addWidget(self.sessionInfo)
        col2.addWidget(self.otherParams)
        col2.addStretch()

        # -- Initialize video --
        self.start_video_thread()
        self.frame_data = {'timestamp': [], 'centroid_x': [], 'centroid_y': []}  # To store frame data
        self.trial_data = []  # To store trial data for later analysis

        # -- Connect signals from GUI --
        self.threshold_slider.value_changed.connect(self.update_threshold)
        self.minarea_slider.value_changed.connect(self.update_minarea)
        self.initzone_radius_slider.value_changed.connect(self.update_initzone)
        self.mask_radius_slider.value_changed.connect(self.update_mask)

        # -- Sound player --
        self.sound_player = soundmodule.SoundPlayer()
        self.sound_player.connect_state_machine(self.controller.state_machine)

        # -- State machine --
        self.sm = statematrix.StateMatrix(inputs=INPUTS, outputs=OUTPUTS)

        # -- Video interface for zone detection --
        video_zones = {
            'IZ': ('circular', tuple(self.initzone))  # initzone is [cx, cy, radius]
        }
        self.video_interface = videomodule.VideoInterface(
            video_thread=self.video_thread,
            zones=video_zones,
            debug=False
        )
        self.video_interface.connect_state_machine(self.controller.state_machine)
        self.messagebar.collect("Video interface initialized.")

        # Calculate event offset for Arduino/Emulator (video events come first)
        # Each video zone creates 2 events ('in' and 'out')
        video_event_offset = len(self.video_interface.get_events())

        # -- Hardware interface (Arduino or Emulator) --
        if config.HARDWARE_INTERFACE == 'arduino':
            self.interface = arduinomodule.ArduinoInterface(inputs=ARDUINO_INPUTS, outputs=OUTPUTS, 
                                                            event_offset=video_event_offset,
                                                            debug=True)
            self.messagebar.collect("Connecting to Arduino...")
            self.interface.arduino_ready.connect(lambda: self.messagebar.collect("Arduino ready."))
            self.interface.arduino_error.connect(
                lambda err: self.messagebar.collect(f"Arduino error: {err}"))
        elif config.HARDWARE_INTERFACE == 'emulator':
            self.interface = emulator.EmulatorWidget(inputs=ARDUINO_INPUTS, outputs=OUTPUTS,
                                                     event_offset=video_event_offset)
            self.interface.show()  # Show emulator window
        self.interface.connect_state_machine(self.controller.state_machine)

    def _show_message(self, msg):
        self.statusBar().showMessage(str(msg))
        print(msg)

    def update_threshold(self, value):
        self.video_thread.set_threshold(value)

    def update_minarea(self, value):
        self.video_thread.set_minarea(value)

    def update_initzone(self, radius):
        self.initzone[2] = radius
        # Update the video interface zone coordinates
        self.video_interface.add_zone('IZ', 'circular', tuple(self.initzone))

    def update_mask(self, radius):
        self.mask[2] = radius
        self.video_thread.set_circular_mask(self.mask)

    def start_video_thread(self):
        """Starts the video capture thread and connects its signals."""
        self.video_thread = videomodule.VideoThread(config.CAMERA_INDEX, mode='binary',
                                                    tracking=True)
        self.video_thread.set_threshold(self.threshold_slider.value)
        self.video_thread.set_minarea(self.minarea_slider.value)
        self.video_thread.set_circular_mask(self.mask)
        self.video_thread.frame_processed.connect(self.update_image)
        self.video_thread.start()

    def update_image(self, timestamp, frame, points, contour):
        """Updates the video display label with new frames and points."""
        if self.session_running:
            self.frame_data['timestamp'].append(timestamp)
            # FIXME: is the centroid point (x, y) or (row, col)?
            self.frame_data['centroid_x'].append(points[0][0])
            self.frame_data['centroid_y'].append(points[0][1])
        self.video_widget.display_frame(frame, points, self.initzone, self.mask, contour=contour)
            
    def start_session(self):
        """
        Called automatically when SessionController.start() is called.
        """
        if not self.session_running:
            # Set the session duration from the GUI parameter
            session_duration = self.params['sessionDuration'].get_value()
            self.controller.set_session_duration(session_duration)
            self.session_running = True

    def prepare_sounds(self):
        """Prepare possible sounds"""
        duration = self.params['soundDuration'].get_value()
        soundL = soundmodule.Sound(duration=duration, srate=SAMPLING_RATE, nchannels=2)
        soundL.add_tone(440, duration, channel=0)
        soundR = soundmodule.Sound(duration=duration, srate=SAMPLING_RATE, nchannels=2)
        soundR.add_tone(350, duration, channel=1)
        soundIZ = soundmodule.Sound(duration=duration, srate=SAMPLING_RATE, nchannels=2)
        soundIZ.add_tone(294, duration, channel='all')
        
        self.sound_player.set_sound(SOUND_ID_LEFT, soundL)
        self.sound_player.set_sound(SOUND_ID_RIGHT, soundR)
        self.sound_player.set_sound(SOUND_ID_INITZONE, soundIZ)

    def prepare_next_trial(self, next_trial):
        """Process results from last trials and prepare the next one."""
        if next_trial > 0:
            self.params.update_history(next_trial-1)
            self.process_results(next_trial-1)
            #print(self.controller.get_events_for_trial(use_names=True))

        self.prepare_sounds()

        valve_duration = self.params['valveDuration'].get_value()
        sound_duration = self.params['soundDuration'].get_value()

        self.sm.reset_transitions()
        self.sm.add_state(name='wait_for_poke', statetimer=np.inf,
                          transitions={'IZin':'play_sound', 
                                       'Lin':'reward_on_L', 'Rin':'reward_on_R'},
                          outputsOff=['ValveL', 'ValveR'])
        self.sm.add_state(name='play_sound', statetimer=sound_duration,
                          transitions={'Tup':'wait_for_poke'},
                          integerOut=SOUND_ID_INITZONE)
        self.sm.add_state(name='reward_on_L', statetimer=valve_duration,
                          transitions={'Tup':'reward_off'},
                          outputsOn=['ValveL'], integerOut=SOUND_ID_LEFT)
        self.sm.add_state(name='reward_on_R', statetimer=valve_duration,
                          transitions={'Tup':'reward_off'},
                          outputsOn=['ValveR'], integerOut=SOUND_ID_RIGHT)
        self.sm.add_state(name='reward_off', statetimer=0,
                          transitions={'Tup':'END'},
                          outputsOff=['ValveL', 'ValveR'])
        if next_trial == 0:
            print(self.sm)
        self.controller.set_state_matrix(self.sm)
        self.controller.ready_to_start_trial()

    def process_results(self, trial):
        pass

    def closeEvent(self, event):
        self.interface.close()  # Close the emulator window
        self.video_thread.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    (app, paradigm) = gui.create_app(Task)
