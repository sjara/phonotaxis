# Behavioral Paradigm Guide

This guide explains how to build and structure **behavioral paradigms** (experimental tasks) using the `phonotaxis` framework. 

A paradigm is a standalone Python script containing a PyQt6 GUI that orchestrates a trial-by-trial finite state machine, hardware inputs/outputs (digital pins/valves), real-time video tracking, sound playback, and data saving.

---

## Table of Contents
1. [Concepts](#concepts)
2. [Paradigm Architecture Overview](#paradigm-architecture-overview)
3. [Structure of a Paradigm File](#structure-of-a-paradigm-file)
4. [Lifecycle Methods](#lifecycle-methods)
5. [Defining GUI Parameters & Widgets](#defining-gui-parameters--widgets)
6. [Setting Up Hardware & Video Interfaces](#setting-up-hardware--video-interfaces)
7. [Managing Trials and the State Matrix](#managing-trials-and-the-state-matrix)
8. [Integrating Custom Video/Analysis Workers](#integrating-custom-videoanalysis-workers)
9. [Data Persistence & HDF5 Saving](#data-persistence--hdf5-saving)
10. [Complete Annotated Example](#complete-annotated-example)

---

## Concepts

| Term | Meaning |
|------|---------|
| **Paradigm** | A single Python file (or class) that defines one experiment type |
| **Trial** | The smallest repeatable unit of an experiment |
| **State matrix** | A table that encodes which state to jump to for every possible event |
| **State** | A named moment in time (e.g., `wait_for_poke`, `reward_left`) |
| **Event** | Something that can change the state — an animal entering a zone, poking a port, or a timer expiring |
| **Output** | Something the computer controls — a water valve, an LED, a speaker |
| **Integer output** | A numeric code emitted when entering a state, used to trigger sounds |

---

## Paradigm Architecture Overview

The `phonotaxis` framework uses a unified coordinator/model layout. A paradigm script defines a class subclassing `QMainWindow` which interacts with the `SessionController` (`phonotaxis.controller.SessionController`). 

The `SessionController` coordinates the real-time execution of the state machine, hardware interfaces, and logs. Your paradigm class is responsible for defining *what* happens in each trial and presenting parameters/plots to the user in a GUI.

### The Session Lifecycle and Trial Loop

```
start_session() [User clicks Start]
  │
  ├──► prepare_next_trial(0) ──► Builds StateMatrix for trial 0
  │                                │
  │  ┌─────────────────────────────┴──────────────────────────────┐
  │  ▼                                                            ▼
  │  [Trial Execution]                                            [Real-Time Tracking & I/O]
  │  StateMachine consumes inputs (Arduino, Video Zones, Tup)     Capture/Process/Record
  │  and drives transitions/outputs (Valves, LEDs, Sound codes)   Workers run in parallel
  │  ▲                                                            │
  │  └─────────────────────────────┬──────────────────────────────┘
  │                                │
  ├──► Trial reaches an 'END' state (State 0)
  │
  ├──► process_results(trial_num) ──► Classifies choices / outcomes
  │
  ├──► prepare_next_trial(trial_num + 1) ──► Builds StateMatrix for next trial
  │
... Repeat until Max Trials, Max Duration, or user clicks Stop
  │
  └──► stop_session() ──► Writes data via save_to_file()
```

---

## Structure of a Paradigm File

A standard paradigm script is structured into these consecutive parts:

1. **Imports and Constants**: Framework modules, numpy, and settings (sampling rate, constants).
2. **Sound ID Constants**: Integer codes mapped to sound waves.
3. **Input and Output Name Lists**: Video zones, digital pin inputs, and actuator outputs.
4. **Paradigm Class (`QMainWindow` subclass)**:
   - `__init__`: Set up widgets, layouts, parameters, controllers, and thread initialization.
   - `start_session` / `stop_session`: Initialize or tear down experimental sessions.
   - `prepare_sounds`: Build or update audio waveforms.
   - `prepare_next_trial`: Build the transition matrix for the next trial.
   - `process_results`: Record outcomes from the just-completed trial.
   - `save_to_file`: Write session data, parameters, trial history, and tracking lists to HDF5.
   - `closeEvent`: Handle clean shutdown of threads and hardware when the window is closed.
5. **App Entry Point**: Bootstrap the GUI using `gui.create_app(Paradigm)`.

---

## Lifecycle Methods

When subclassing `QMainWindow` for your paradigm, the framework relies on several lifecycle methods called at specific session transitions:

### `start_session(self)`
Triggered when the user clicks the "Start" button on the controller GUI. 
- Set `self.session_running = True`.
- Retrieve session limits (such as max duration) from GUI inputs and set them on the controller.

### `stop_session(self)`
Triggered when the session is stopped (manually, or via duration/trial limits).
- Set `self.session_running = False`.
- Proactively call `self.save_to_file()` or print a completion summary.

### `prepare_next_trial(self, next_trial)`
Called by the `SessionController` before a trial begins.
- If `next_trial > 0`, run `self.params.update_history(next_trial - 1)` to log parameter histories.
- Run `self.process_results(next_trial - 1)` to process the outcome of the completed trial.
- Call `self.sm.reset_transitions()` to clear the previous trial's state machine.
- Re-add states using `self.sm.add_state(...)` to define the trial structure.
- Call `self.controller.set_state_matrix(self.sm)` followed by `self.controller.ready_to_start_trial()` to begin the trial.

### `process_results(self, trial)`
Called at the end of each trial to extract what choice the animal made (e.g. left vs right poke) by examining state transition histories, and logging it to trial arrays.

### `save_to_file(self)`
Triggered when the user clicks the "Save" button or automatically at the end of a session. Calls the `SaveData` widget to write parameters, results, event tables, and tracking data to a structured HDF5 file.

### `closeEvent(self, event)`
Called when the user closes the PyQt6 application window. You **must** stop the video thread and close the hardware interface here to prevent background threads from hanging.

---

## Defining GUI Parameters & Widgets

`phonotaxis` offers parameter containers that automatically manage GUI layout, validation, and historical logging:

```python
from phonotaxis import gui

self.params = gui.Container()

# Numeric parameter (auto-validated, logs trial-by-trial history if history=True)
self.params['valveDuration'] = gui.NumericParam(
    'Valve duration', value=0.1, units='s', group='Valve settings'
)

# String parameter
self.params['subjectName'] = gui.StringParam(
    'Subject ID', value='mouse01', group='Session settings'
)

# Menu / Dropdown parameter
self.params['rewardType'] = gui.MenuParam(
    'Reward side', options=['random', 'left', 'right'], value='random', group='Session settings'
)

# Retrieve current value in code
duration = self.params['valveDuration'].get_value()

# Add a visually grouped control panel for these parameters to your layout:
valve_panel = self.params.layout_group('Valve settings')
self.layout.addWidget(valve_panel)
```

---

## Setting Up Hardware & Video Interfaces

A typical paradigm needs to map input events and manage output actuators.

### 1. Declaring Inputs & Outputs

```python
# Video tracking initiation zones
VIDEO_INPUTS = ['IZ']

# Input pins on the Arduino (e.g., L = Left Poke, R = Right Poke)
ARDUINO_INPUTS = ['L', 'R']

# Combined inputs for the state matrix constructor
INPUTS = VIDEO_INPUTS + ARDUINO_INPUTS

# Output actuators (e.g., ValveL, ValveR, LED)
OUTPUTS = ['ValveL', 'ValveR', 'LED']
```

### 2. Initializing Hardware and Video

In your paradigm's `__init__` method, configure the hardware interface and video thread:

```python
from phonotaxis import videomodule, arduinomodule, emulator, config

# 1. Start the VideoThread
self.video_thread = videomodule.VideoThread(config.CAMERA_INDEX, tracking=True)
self.video_thread.start()

# 2. Configure VideoInterface (maps zone coordinates to state-machine events)
video_zones = {
    'IZ': ('circular', (320, 240, 80)) # type, (center_x, center_y, radius)
}
self.video_interface = videomodule.VideoInterface(
    video_thread=self.video_thread,
    zones=video_zones
)
self.video_interface.connect_state_machine(self.controller.state_machine)

# 3. Calculate event offset (video events come first; hardware events follow)
video_event_offset = len(self.video_interface.get_events())

# 4. Connect Hardware Interface (Arduino or Emulator GUI)
if config.HARDWARE_INTERFACE == 'arduino':
    self.interface = arduinomodule.ArduinoInterface(
        inputs=ARDUINO_INPUTS,
        outputs=OUTPUTS,
        event_offset=video_event_offset
    )
else:
    self.interface = emulator.EmulatorWidget(
        inputs=ARDUINO_INPUTS,
        outputs=OUTPUTS,
        event_offset=video_event_offset
    )
self.interface.connect_state_machine(self.controller.state_machine)
```

---

## Managing Trials and the State Matrix

You construct the trial logic inside `prepare_next_trial` using declarative state machines. Refer to `docs/state_matrix_guide.md` for a deeper dive into transitions and outputs.

```python
def prepare_next_trial(self, next_trial):
    if next_trial > 0:
        self.params.update_history(next_trial - 1)
        self.process_results(next_trial - 1)

    # 1. Reset state transitions
    self.sm.reset_transitions()

    # Get dynamic parameter values from the GUI
    valve_duration = self.params['valveDuration'].get_value()

    # 2. Add States
    
    # State 1: wait for the mouse to poke left or right port
    self.sm.add_state(
        name='wait_for_poke',
        statetimer=float('inf'),  # Wait indefinitely
        transitions={'Lin': 'reward_left', 'Rin': 'reward_right'},
        outputsOff=['ValveL', 'ValveR']
    )

    # State 2: deliver reward on left
    self.sm.add_state(
        name='reward_left',
        statetimer=valve_duration,  # Elapses after valve duration
        transitions={'Tup': 'trial_end'},
        outputsOn=['ValveL']
    )

    # State 3: deliver reward on right
    self.sm.add_state(
        name='reward_right',
        statetimer=valve_duration,
        transitions={'Tup': 'trial_end'},
        outputsOn=['ValveR']
    )

    # State 4: clean up outputs and transition to END (State 0)
    self.sm.add_state(
        name='trial_end',
        statetimer=0,
        transitions={'Tup': 'END'},
        outputsOff=['ValveL', 'ValveR']
    )

    # 3. Load the matrix and flag ready
    self.controller.set_state_matrix(self.sm)
    self.controller.ready_to_start_trial()
```

---

## Integrating Custom Video/Analysis Workers

If your paradigm needs real-time analysis beyond basic dark-object tracking (e.g. kinematics extraction, zone dwell times, or custom filters), you can register custom workers to run in parallel with the multi-threaded video pipeline.

Subscribing to `'contour_tracker'` routes tracking data directly to your worker. Use `latest_only=True` to prevent slow analysis algorithms from causing backpressure:

```python
from phonotaxis.resultbus import SharedBuffer
from phonotaxis.videoworkers import ProcessWorker

# 1. Define a strategy callable class
class KinematicsStrategy:
    def __init__(self):
        self.last_pos = None

    def __call__(self, msg):
        points = msg.data.get('points', ())
        if not points or points[0] == (-1, -1):
            return {'speed': 0.0}
        
        pos = points[0]
        speed = 0.0
        if self.last_pos is not None:
            speed = float(np.linalg.norm(np.array(pos) - np.array(self.last_pos)))
        
        self.last_pos = pos
        return {'speed': speed}

# 2. Create the worker and register it in __init__
self.kinematics_buffer = SharedBuffer(event=self.video_thread._result_ready_event)
self.kinematics_worker = ProcessWorker(
    strategy=KinematicsStrategy(),
    result_buffer=self.kinematics_buffer,
    name='kinematics',
    bus=self.video_thread.result_bus,
    subscribe_to='contour_tracker',
    latest_only=True
)
self.video_thread.add_process_worker(self.kinematics_worker)
```

In your main thread (e.g., in a GUI update loop or during `process_results`), you can read the latest computed value:
```python
res = self.kinematics_buffer.try_read_result()
if res is not None:
    speed = res.data['speed']
```

---

## Data Persistence & HDF5 Saving

Data is saved via the `SaveData` widget. This class accepts a list of containers and writes all attributes, dictionaries, parameter histories, and state matrix tables to HDF5.

In `save_to_file`:
```python
def save_to_file(self):
    subject = self.session_info.get_value('subject')
    if self.controller.current_trial > 0:
        # Pass all objects containing trial/session variables
        containers = [
            self.params,          # Parameters & histories
            self.controller,      # Trial timings and state logs
            self.sm,              # State machine definitions
            self.results,         # Custom result arrays
            self.video_thread     # Video tracking timestamps & centroids
        ]
        
        self.savedata_widget.to_file(
            containers,
            subject=subject,
            paradigm=PARADIGM_NAME
        )
    else:
        print('No trials completed yet. Saving aborted.')
```

---

## Complete Annotated Example

Below is a complete, runnable paradigm file illustrating how the components integrate:

```python
"""
paradigm_classical_conditioning.py

A simple classical conditioning paradigm:
1. Animal enters the initiation zone (IZ).
2. Sound tone plays immediately.
3. Food valve opens briefly after a delay.
"""

import numpy as np
from bidict import bidict
from PyQt6.QtWidgets import QWidget, QMainWindow, QHBoxLayout, QVBoxLayout
from phonotaxis import gui, widgets, controller, videomodule, arduinomodule, emulator, statematrix, soundmodule, savedata, config

# Paradigm identification used for file naming
PARADIGM_NAME = 'classical_conditioning'

# Sound Configuration
SAMPLING_RATE = 44100
SOUND_ID_CUE = 1

# Video tracking zone settings
DEFAULT_IZ_ZONE = [320, 240, 60]  # [center_x, center_y, radius]
DEFAULT_MASK = [320, 240, 240]

# State Machine Inputs/Outputs
VIDEO_INPUTS = ['IZ']
ARDUINO_INPUTS = ['L_Poke']
INPUTS = VIDEO_INPUTS + ARDUINO_INPUTS
OUTPUTS = ['ValveL', 'CueLED']

class Paradigm(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(PARADIGM_NAME)
        self.setWindowIcon(gui.create_icon())
        
        # 1. Session Controller
        self.controller = controller.SessionController(debug=False)
        self.session_running = False
        
        # 2. GUI widgets
        self.video_widget = widgets.VideoWidget(controls=True, initzone_radius=DEFAULT_IZ_ZONE[2])
        self.savedata_widget = savedata.SaveData(datadir=config.DATA_PATH)
        self.session_info = widgets.SessionInfo()
        self.session_info.set_values({
            'subject': 'mouse01',
            'trainer': 'experimenter',
            'maxSessionDuration': 1800.0,
            'maxTrials': 100
        })
        
        # 3. Parameters
        self.params = gui.Container()
        self.params['cueDuration'] = gui.NumericParam('Cue Tone Duration', value=0.5, units='s', group='Trial Params')
        self.params['delayDuration'] = gui.NumericParam('Trace Delay', value=1.0, units='s', group='Trial Params')
        self.params['valveDuration'] = gui.NumericParam('Valve Open', value=0.1, units='s', group='Trial Params')
        trial_params_panel = self.params.layout_group('Trial Params')
        
        # 4. Custom Results logging
        self.results = utils.EnumContainer()
        self.results.labels['outcome'] = bidict({'rewarded': 1, 'omission': 0})
        self.results['outcome'] = []
        
        # 5. Connect Signal handlers
        self.controller.session_started.connect(self.start_session)
        self.controller.session_stopped.connect(self.stop_session)
        self.controller.prepare_next_trial.connect(self.prepare_next_trial)
        self.savedata_widget.button.clicked.connect(self.save_to_file)
        
        # 6. Layout arrangement
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QHBoxLayout(self.central_widget)
        
        col_left = QVBoxLayout()
        col_right = QVBoxLayout()
        self.layout.addLayout(col_left)
        self.layout.addLayout(col_right)
        
        col_left.addWidget(self.video_widget)
        col_right.addWidget(self.controller.gui)
        col_right.addWidget(self.session_info)
        col_right.addWidget(self.savedata_widget)
        col_right.addWidget(trial_params_panel)
        col_right.addStretch()
        
        # 7. Start Video Thread & Interface
        self.video_thread = videomodule.VideoThread(config.CAMERA_INDEX, mode='grayscale', tracking=True)
        self.video_thread.set_circular_mask(DEFAULT_MASK)
        self.video_thread.frame_processed.connect(self._update_display)
        self.video_thread.start()
        
        self.video_interface = videomodule.VideoInterface(
            video_thread=self.video_thread,
            zones={'IZ': ('circular', tuple(DEFAULT_IZ_ZONE))}
        )
        self.video_interface.connect_state_machine(self.controller.state_machine)
        
        self.video_widget.connect_video_thread(self.video_thread)
        self.video_widget.connect_video_interface(self.video_interface, zone_name='IZ')
        
        # 8. Sound generation & Player
        self.sound_player = soundmodule.SoundPlayer()
        self.sound_player.connect_state_machine(self.controller.state_machine)
        
        # 9. State Machine configuration
        self.sm = statematrix.StateMatrix(inputs=INPUTS, outputs=OUTPUTS)
        
        # 10. Hardware (Arduino or Emulator Widget)
        video_offset = len(self.video_interface.get_events())
        if config.HARDWARE_INTERFACE == 'arduino':
            self.interface = arduinomodule.ArduinoInterface(inputs=ARDUINO_INPUTS, outputs=OUTPUTS, event_offset=video_offset)
        else:
            self.interface = emulator.EmulatorWidget(inputs=ARDUINO_INPUTS, outputs=OUTPUTS, event_offset=video_offset)
            self.interface.show()
        self.interface.connect_state_machine(self.controller.state_machine)

    def _update_display(self, timestamp, frame, points, contour):
        self.video_widget.display_frame(frame, points, contour=contour)

    def start_session(self):
        if not self.session_running:
            self.controller.set_session_duration(self.session_info.get_value('maxSessionDuration'))
            self.session_running = True

    def stop_session(self):
        if self.session_running:
            self.session_running = False

    def prepare_sounds(self):
        cue_dur = self.params['cueDuration'].get_value()
        sound_cue = soundmodule.Sound(duration=cue_dur, srate=SAMPLING_RATE, nchannels=2)
        sound_cue.add_tone(5000, 0.4, channel='all')  # 5 kHz tone
        self.sound_player.set_sound(SOUND_ID_CUE, sound_cue)

    def prepare_next_trial(self, next_trial):
        if next_trial > 0:
            self.params.update_history(next_trial - 1)
            self.process_results(next_trial - 1)
            
        self.prepare_sounds()
        
        # Read parameter values
        cue_dur = self.params['cueDuration'].get_value()
        delay_dur = self.params['delayDuration'].get_value()
        valve_dur = self.params['valveDuration'].get_value()
        
        self.sm.reset_transitions()
        
        # State 1: Wait for animal to enter initiation zone
        self.sm.add_state(
            name='wait_for_init',
            statetimer=float('inf'),
            transitions={'IZin': 'play_cue'},
            outputsOff=['ValveL', 'CueLED']
        )
        
        # State 2: Play sound cue tone
        self.sm.add_state(
            name='play_cue',
            statetimer=cue_dur,
            transitions={'Tup': 'trace_delay'},
            outputsOn=['CueLED'],
            integerOut=SOUND_ID_CUE
        )
        
        # State 3: Trace delay interval
        self.sm.add_state(
            name='trace_delay',
            statetimer=delay_dur,
            transitions={'Tup': 'deliver_reward'},
            outputsOff=['CueLED']
        )
        
        # State 4: Valve open reward delivery
        self.sm.add_state(
            name='deliver_reward',
            statetimer=valve_dur,
            transitions={'Tup': 'trial_end'},
            outputsOn=['ValveL']
        )
        
        # State 5: Turn off valves and complete trial
        self.sm.add_state(
            name='trial_end',
            statetimer=0,
            transitions={'Tup': 'END'},
            outputsOff=['ValveL']
        )
        
        self.controller.set_state_matrix(self.sm)
        self.controller.ready_to_start_trial()

    def process_results(self, trial):
        events_df = self.controller.get_events_one_trial(trial)
        states = events_df.next_state.values
        # Classify as rewarded if reward state was entered
        if self.sm.states['deliver_reward'] in states:
            outcome = self.results.labels['outcome']['rewarded']
        else:
            outcome = self.results.labels['outcome']['omission']
        self.results['outcome'].append(outcome)

    def save_to_file(self):
        subject = self.session_info.get_value('subject')
        if self.controller.current_trial > 0:
            containers = [self.params, self.controller, self.sm, self.results, self.video_thread]
            self.savedata_widget.to_file(containers, subject=subject, paradigm=PARADIGM_NAME)

    def closeEvent(self, event):
        self.interface.close()
        self.video_thread.stop()
        super().closeEvent(event)

if __name__ == '__main__':
    (app, paradigm) = gui.create_app(Paradigm)
```
