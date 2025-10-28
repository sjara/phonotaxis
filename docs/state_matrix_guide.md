# State Matrix Guide

This guide explains how to define state matrices for behavioral paradigms in the phonotaxis framework. State matrices are the core mechanism for controlling trial logic, managing hardware outputs, and responding to hardware/video inputs.

## Table of Contents
1. [Overview](#overview)
2. [Input Events](#input-events)
3. [Adding States](#adding-states)
4. [The 'Tup' Event](#the-tup-event)
5. [Controlling Outputs](#controlling-outputs)
6. [Resetting Transitions](#resetting-transitions)
7. [Example State Matrix Output](#example-state-matrix-output)

---

## Overview

A state matrix defines a finite state machine that controls behavioral experiments. Each state specifies:
- **Transitions**: Which state to move to when specific events occur
- **Timers**: How long to remain in the state before timing out
- **Outputs**: Which hardware outputs (valves, LEDs, etc.) to turn on or off
- **Integer outputs**: Numeric codes that can trigger sounds or other actions

The state matrix is created using the `StateMatrix` class from the `statematrix` module and passed to the session controller to execute trials.

---

## Input Events

### Hardware and Video Inputs Become Two Events Each

Every input you define (whether from hardware like Arduino ports or from video tracking zones) automatically generates **two events**:
- An **"in" event** (triggered when entering/activating)
- An **"out" event** (triggered when exiting/deactivating)

For example:
```python
# Define inputs
VIDEO_INPUTS = ['IZ']        # Initiation Zone
ARDUINO_INPUTS = ['L', 'R']  # Left, Right

# These create the following events automatically:
# From Video:   'IZin', 'IZout'
# From Arduino: 'Lin', 'Lout', 'Rin', 'Rout'
```

### How Events Are Created

When you initialize a `StateMatrix`:
```python
sm = StateMatrix(inputs=INPUTS, outputs=OUTPUTS)
```

For each input name in the list, the state matrix creates:
- `{input_name}in` - triggered when the input activates
- `{input_name}out` - triggered when the input deactivates

These event names are used in the `transitions` parameter when adding states.

### Event Ordering

Generally, events are indexed in the following order:
1. **Video events** come first (in the order zones are defined)
2. **Arduino/Hardware events** come next (in the order defined in `ARDUINO_INPUTS`)
3. **'Tup' event** (state timer timeout) comes last
4. **Extra timer events** (if defined) come after 'Tup'

---

## Adding States

States are added using the `add_state()` method of the `StateMatrix` class. Here's the anatomy of a state definition:

### Basic State Structure

```python
sm.add_state(
    name='state_name',           # Unique identifier for this state
    statetimer=duration,         # How long to stay in state (seconds)
    transitions={                # Dictionary of event -> next_state
        'event_name': 'next_state_name'
    },
    outputsOn=['output1'],       # List of outputs to turn ON
    outputsOff=['output2'],      # List of outputs to turn OFF
    integerOut=1                 # Numeric code (e.g., for sound playback)
)
```

For an example of a full state matrix, see `examples/example_initzone_and_ports.py`.


### State Parameters Explained

**`name`** (str): 
- Unique identifier for the state
- Used in transition definitions to refer to this state
- Should be descriptive (e.g., 'wait_for_poke', 'reward_on_L')

**`statetimer`** (float):
- Duration in seconds before the state times out
- Use `np.inf` for states that should never timeout automatically
- Use `0` for immediate transitions to next state
- When timer expires, triggers the 'Tup' event

**`transitions`** (dict):
- Maps event names to target state names
- Events not listed will cause the state to stay in itself (self-transition)
- Common event names: 'IZin', 'IZout', 'Lin', 'Lout', 'Rin', 'Rout', 'Tup'

**`outputsOn`** (list):
- Names of outputs to turn ON when entering this state
- Must match output names defined when creating StateMatrix
- Example: `['ValveL', 'LED1']`

**`outputsOff`** (list):
- Names of outputs to turn OFF when entering this state
- Explicitly turns outputs off regardless of previous state
- Example: `['ValveR', 'ValveL']`

**`integerOut`** (int):
- Numeric code emitted when entering this state
- Often used to trigger sound playback via `SoundPlayer`
- Default is 0 (no numeric output)
- Example: `integerOut=3` triggers a specific sound

---

## The 'Tup' Event

The **'Tup' event** (short for "Timer Up") is a special built-in event that occurs when a state's timer expires.

### Key Characteristics

1. **Automatically created**: Every state matrix has a 'Tup' event column
2. **Triggered by timeout**: Fires when `statetimer` duration elapses
3. **Common for sequential logic**: Used to move through predetermined sequences

### Common Usage Patterns

**Immediate transition** (statetimer=0): This example state immediately turns off valves and transitions to END.

```python
sm.add_state(name='reward_off', statetimer=0,
             transitions={'Tup':'END'},
             outputsOff=['ValveL', 'ValveR'])
```

**Timeout condition** (wait with timeout): This example state waits for left poke up to 10 seconds, transitions to timeout if no poke.
```python
sm.add_state(name='wait_for_poke', statetimer=10.0,
             transitions={'Lin':'reward', 'Tup':'timeout_state'})
```


**Infinite wait** (no timeout): This example state waits indefinitely for left or right poke (no 'Tup' transition needed).
```python
sm.add_state(name='wait_for_poke', statetimer=np.inf,
             transitions={'Lin':'reward', 'Rin':'reward'})
```


---

## Controlling Outputs

Outputs represent physical devices like valves, LEDs, or other actuators connected to your hardware interface.

### Defining Outputs

Outputs are defined when creating the state matrix:
```python
OUTPUTS = ['ValveL', 'ValveR', 'LED1', 'LED2']
sm = StateMatrix(inputs=INPUTS, outputs=OUTPUTS)
```

### Three Ways to Control Outputs

**1. Turn outputs ON**:
```python
sm.add_state(name='reward', statetimer=0.1,
             outputsOn=['ValveL'])
```
Explicitly turns on the left valve. Other outputs remain unchanged.

**2. Turn outputs OFF**:
```python
sm.add_state(name='end_reward', statetimer=0,
             outputsOff=['ValveL', 'ValveR'])
```
Explicitly turns off both valves. Other outputs remain unchanged.

**3. Leave outputs unchanged** (default):
```python
sm.add_state(name='wait', statetimer=5.0)
```
All outputs maintain their previous state.

### Output State Persistence

Outputs maintain their state across transitions unless explicitly changed:
```python
sm.add_state(name='valve_on', statetimer=0.1,
             outputsOn=['ValveL'])             # Valve turns ON

sm.add_state(name='middle_state', statetimer=1.0,
             transitions={'Tup':'valve_off'})  # Valve STAYS ON

sm.add_state(name='valve_off', statetimer=0,
             outputsOff=['ValveL'])            # Valve turns OFF
```

### Integer Outputs for Sound Playback

The `integerOut` parameter is commonly used to trigger pre-loaded sounds:

```python
# Sound IDs (defined earlier)
SOUND_ID_LEFT = 1
SOUND_ID_RIGHT = 2

# Trigger sounds in states
sm.add_state(name='play_left_sound', statetimer=0.5,
             integerOut=SOUND_ID_LEFT)

sm.add_state(name='play_right_sound', statetimer=0.5,
             integerOut=SOUND_ID_RIGHT)
```

The `SoundPlayer` module listens for these integer outputs and plays the corresponding sound.

**NOTE:** The value `integerOut=0` is reserved for turning sounds off.

---

## Resetting Transitions

### When to use `reset_transitions()`

The `reset_transitions()` method clears all custom transitions and resets the state matrix to a default state. **You should call this when preparing a new trial** (e.g., in  `prepare_next_trial()`, before defining the state matrix for the next trial.

### Why Reset?

State matrices are reused across trials. If you don't reset:
- Old transitions from previous trials persist
- State definitions accumulate and can cause unexpected behavior
- Memory usage grows unnecessarily

### Typical Usage Pattern

```python
def prepare_next_trial(self, next_trial):
    """Prepare the state matrix for the next trial."""
    
    # Reset the state matrix to defaults
    self.sm.reset_transitions()
    
    # Now define states for this trial
    self.sm.add_state(name='wait_for_poke', statetimer=np.inf,
                      transitions={'Lin':'reward_on_L', 'Rin':'reward_on_R'})
    
    self.sm.add_state(name='reward_on_L', statetimer=valve_duration,
                      transitions={'Tup':'reward_off'},
                      outputsOn=['ValveL'])
    
    # ... more states ...
    
    # Send the state matrix to the controller
    self.controller.set_state_matrix(self.sm)
    self.controller.ready_to_start_trial()
```

### What `reset_transitions()` does

1. Resets all state transitions to self-loops (every event returns to the same state)
2. Sets all state timers to `INFINITE_TIME`
3. Sets all outputs to `NOCHANGE`
4. **Does NOT** delete states - the state structure remains. This is useful for keeping a consistent mapping between states and state IDs across trials.

After resetting, you rebuild only the states needed for the current trial.

---

## Example State Matrix Output

When you print a state matrix (using `print(sm)`), you get a formatted table showing the complete structure. Here's an example from `example_initzone_and_ports.py`, with:
- Six states (one per row, from 0 to 5)
- One video input (IZ) and two arduino inputs ('L', 'R'). This yields a total of 6 input events + 1 timer event.
- A state timer for each state 
- Two binary outputs
- And one (default) integer output

```
                     IZin  IZout  Lin  Lout  Rin  Rout  Tup  |  Timers  Outputs  integerOut
END              [0]    0     0    0     0    0     0    0   |    inf     --       0
wait_for_poke    [1]    2     1    3     1    4     1    1   |    inf     00       0
play_sound       [2]    1     2    2     2    2     2    1   |   0.40     --       3
reward_on_L      [3]    5     3    3     3    3     3    5   |   0.10     10       2
reward_on_R      [4]    5     4    4     4    4     4    5   |   0.10     01       3
reward_off       [5]    0     5    5     5    5     5    0   |   0.00     00       0
```

### Reading the Table

**Header Row**:
- **Event columns**: IZin, IZout, Lin, Lout, Rin, Rout, Tup
  - These are the possible events that can occur
  - Each abbreviated to 5 characters in the display
- **Timers**: Duration the state will last
- **Outputs**: State of each output (see below)
- **integerOut**: Numeric code emitted

**State Rows**:
- **State name and index**: e.g., `wait_for_poke [1]`
- **Transition columns**: Numbers indicate target state index
  - Example: Under 'IZin' for state 1, value is `2` → transitions to state 2 (play_sound)
  - Value matching own index means self-transition (stay in same state)
- **Timers**: Duration in seconds (`inf` means infinite)
- **Outputs**: Character per output
  - `1` = ON
  - `0` = OFF
  - `-` = NOCHANGE (maintains previous state)
- **integerOut**: Numeric value (0 = none)

### Example Analysis

Looking at state `wait_for_poke [1]`:
- **IZin → 2**: When entering initiation zone, go to `play_sound`
- **IZout → 1**: When leaving initiation zone, stay in `wait_for_poke`
- **Lin → 3**: When left poke detected, go to `reward_on_L`
- **Rin → 4**: When right poke detected, go to `reward_on_R`
- **Tup → 1**: Timer never expires (inf), but would stay here if it did
- **Timer: inf**: Never times out
- **Outputs: 00**: Both valves OFF
- **integerOut: 0**: No numeric output

Looking at state `reward_on_L [3]`:
- **All events → self except Tup**: Ignores all pokes/zone events while delivering reward
- **Tup → 5**: After timer expires, go to `reward_off`
- **Timer: 0.10**: Lasts 0.1 seconds
- **Outputs: 10**: Left valve ON, right valve OFF
- **integerOut: 2**: Triggers sound ID 2

### The END State

The `END` state (always state 0) is special:
- Automatically created when initializing StateMatrix
- Serves as a waiting state between trials
- All events self-transition (stay in END)
- Typically reached at the end of each trial
- The controller uses forced transitions to move from END to state 1 to start trials

---

## Complete Example

Here's a complete example putting it all together:

```python
import numpy as np
from phonotaxis import statematrix

# Define inputs and outputs
VIDEO_INPUTS = ['IZ']  # Initiation zone
ARDUINO_INPUTS = ['L', 'R']  # Left and right ports
INPUTS = VIDEO_INPUTS + ARDUINO_INPUTS
OUTPUTS = ['ValveL', 'ValveR']

# Create state matrix
sm = statematrix.StateMatrix(inputs=INPUTS, outputs=OUTPUTS)

# Sound IDs for integer outputs
SOUND_ID_INITZONE = 1
SOUND_ID_LEFT = 2
SOUND_ID_RIGHT = 3

def prepare_state_matrix(sm, valve_duration=0.1, sound_duration=0.4):
    """Build the state matrix for a trial."""
    
    # Reset from previous trial
    sm.reset_transitions()
    
    # Wait for animal to enter initiation zone or poke
    sm.add_state(name='wait_for_poke', statetimer=np.inf,
                 transitions={'IZin':'play_sound', 
                              'Lin':'reward_on_L', 
                              'Rin':'reward_on_R'},
                 outputsOff=['ValveL', 'ValveR'])
    
    # Play sound when entering initiation zone
    sm.add_state(name='play_sound', statetimer=sound_duration,
                 transitions={'Tup':'wait_for_poke'},
                 integerOut=SOUND_ID_INITZONE)
    
    # Deliver left reward
    sm.add_state(name='reward_on_L', statetimer=valve_duration,
                 transitions={'Tup':'reward_off'},
                 outputsOn=['ValveL'], 
                 integerOut=SOUND_ID_LEFT)
    
    # Deliver right reward
    sm.add_state(name='reward_on_R', statetimer=valve_duration,
                 transitions={'Tup':'reward_off'},
                 outputsOn=['ValveR'], 
                 integerOut=SOUND_ID_RIGHT)
    
    # Turn off valves and end trial
    sm.add_state(name='reward_off', statetimer=0,
                 transitions={'Tup':'END'},
                 outputsOff=['ValveL', 'ValveR'])
    
    return sm

# Prepare and view the state matrix
prepare_state_matrix(sm)
print(sm)
```

This creates a complete trial structure where:
1. Animal waits in the chamber
2. Entering initiation zone triggers a sound
3. Poking left or right port delivers water reward with associated sound
4. Valves turn off and trial ends

---

## Summary

- **Input events**: Every input (hardware/video) creates two events: `{name}in` and `{name}out`
- **Adding states**: Use `add_state()` with name, timer, transitions, and outputs
- **'Tup' event**: Special event triggered when state timer expires
- **Outputs**: Control with `outputsOn`, `outputsOff`; unchanged outputs maintain previous state
- **Integer outputs**: Numeric codes for triggering sounds or other actions
- **Reset**: Always call `sm.reset_transitions()` at the start of `prepare_next_trial()`
- **Printing**: Use `print(sm)` to view complete state matrix structure

For more examples, see:
- `examples/example_initzone_and_ports.py`
- `examples/example_water_on_poke.py`
- `examples/example_statemachine.py`
