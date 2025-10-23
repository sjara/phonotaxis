"""
Example task: water reward and sound playback triggered by a poke on either port.
"""

import numpy as np
from bidict import bidict
from PyQt6.QtWidgets import QWidget, QMainWindow, QHBoxLayout, QVBoxLayout
from phonotaxis import gui
from phonotaxis import soundmodule
from phonotaxis import controller
from phonotaxis import arduinomodule
from phonotaxis import statematrix
from phonotaxis import utils
from phonotaxis import emulator
from phonotaxis import config


# --- Sound settings ---
SAMPLING_RATE = 44100

# --- Sound IDs for state machine integer outputs ---
SOUND_ID_LEFT = 1
SOUND_ID_RIGHT = 2

# --- State machine inputs and outputs ---
INPUTS = list(config.INPUT_PINS.keys()) 
OUTPUTS = list(config.OUTPUT_PINS.keys())

class Task(QMainWindow):
    def __init__(self):
        super().__init__()
        self.name = 'example'  # Paradigm name
        self.setWindowTitle("Water and sound on poke")
        #self.setGeometry(100, 100, 800, 600)
        self.setWindowIcon(gui.create_icon())

        # -- Connect messenger --
        self.messagebar = gui.Messenger()
        self.messagebar.timed_message.connect(self._show_message)
        self.messagebar.collect('Created window')

        # -- Main widgets --
        self.session_running = False
        self.controller = controller.SessionController()

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
        self.layout.addWidget(self.controller.gui)
        self.layout.addWidget(self.sessionInfo)
        self.layout.addWidget(self.otherParams)

        # -- Sound player --
        self.sound_player = soundmodule.SoundPlayer()
        self.sound_player.connect_state_machine(self.controller.state_machine)

        # -- State machine --
        self.sm = statematrix.StateMatrix(inputs=INPUTS, outputs=OUTPUTS)

        # -- Hardware interface --
        if config.HARDWARE_INTERFACE == 'arduino':
            self.interface = arduinomodule.ArduinoInterface(inputs=INPUTS, outputs=OUTPUTS, 
                                                            debug=True)
            self.messagebar.collect("Connecting to Arduino...")
            self.interface.arduino_ready.connect(lambda: self.messagebar.collect("Arduino ready."))
            self.interface.arduino_error.connect(
                lambda err: self.messagebar.collect(f"Arduino error: {err}"))
        elif config.HARDWARE_INTERFACE == 'emulator':
            self.interface = emulator.EmulatorWidget(inputs=INPUTS, outputs=OUTPUTS)
            self.interface.show()  # Show emulator window
        self.interface.connect_state_machine(self.controller.state_machine)

    def _show_message(self, msg):
        self.statusBar().showMessage(str(msg))
        print(msg)

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
        
        self.sound_player.set_sound(SOUND_ID_LEFT, soundL)
        self.sound_player.set_sound(SOUND_ID_RIGHT, soundR)

    def prepare_next_trial(self, next_trial):
        """Process results from last trials and prepare the next one."""
        if next_trial > 0:
            self.params.update_history(next_trial-1)
            self.process_results(next_trial-1)
            #print(self.controller.get_events_for_trial(use_names=True))

        self.prepare_sounds()

        valve_duration = self.params['valveDuration'].get_value()

        self.sm.reset_transitions()
        self.sm.add_state(name='wait_for_poke', statetimer=np.inf,
                          transitions={'Lin':'rewardOnL', 'Rin':'rewardOnR'},
                          outputsOff=['ValveL', 'ValveR'])
        self.sm.add_state(name='rewardOnL', statetimer=valve_duration,
                          transitions={'Tup':'rewardOff'},
                          outputsOn=['ValveL'], integerOut=SOUND_ID_LEFT)
        self.sm.add_state(name='rewardOnR', statetimer=valve_duration,
                          transitions={'Tup':'rewardOff'},
                          outputsOn=['ValveR'], integerOut=SOUND_ID_RIGHT)
        self.sm.add_state(name='rewardOff', statetimer=0,
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
        super().closeEvent(event)


if __name__ == "__main__":
    (app, paradigm) = gui.create_app(Task)
