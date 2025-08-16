"""
Classes for assembling a state transition matrix, timers and outputs.

NOTES:

* The state matrix is represented by Python lists during construction for flexibility,
  then converted to NumPy arrays for efficient runtime use via get_matrix().
* The state timers are represented by a Python list during construction,
  then converted to NumPy arrays for runtime use via get_state_timers().
* The state outputs are represented by Python lists during construction,
  then converted to NumPy arrays for runtime use via get_outputs().
  Each element contains the outputs for each state as a list of 0 (off), 1 (on) 
  or -1 (NOCHANGE) which indicates the output should not be changed from its previous value.

Input format:
sma.add_state(name='STATENAME', statetimer=3,
             transitions={'EVENT':NEXTSTATE},
             outputsOn=[], outputsOff=[])

Output (NumPy array from get_matrix()):
#       Ci  Co  Li  Lo  Ri  Ro  Tup
mat = [  0,  0,  0,  0,  0,  0,  2  ]

Key attributes:
- states_name_to_index: Dictionary mapping state names to their indices
- events_dict: Dictionary mapping event names to their column indices in the matrix
"""

from typing import Dict, List, Optional, Any, Union
import numpy as np
from bidict import bidict

from phonotaxis import utils

# Use float('inf') for states that should never timeout
INFINITE_TIME = float('inf')  # For states that should never timeout automatically
NOCHANGE = -1  # Output value that means "do not change output from previous state"

class StateMatrix():
    """
    State transition matrix for behavioral control systems.

    This class manages a state machine with transitions based on input events,
    timers, and outputs. It uses Python lists during construction for flexibility,
    then provides NumPy arrays for efficient runtime use through getter methods.

    The default state transition matrix without extra timers has the following columns:
    [ Cin  Cout  Lin  Lout  Rin  Rout  Tup]

    Where the first six are for center, left and right ports, and the
    next column for the state timer.

    State Structure:
        - START state: Always state 0, created automatically during initialization
        - END state: Always the last state, created automatically when matrices are requested
        - User-defined states: Created between START and END states

    Main Methods:
        get_matrix(): Returns state transition matrix as NumPy array (adds END state)
        get_outputs(): Returns output configurations as NumPy array  
        get_state_timers(): Returns timer durations as NumPy array

    Attributes:
        inputs_dict: Dictionary mapping input names to their indices
        outputs_dict: Dictionary mapping output names to their indices  
        state_matrix: Internal list of lists for building (use get_matrix() for NumPy access)
        state_timers: Internal list of timer durations (use get_state_timers() for NumPy access)
        state_outputs: Internal list of output configs (use get_outputs() for NumPy access)
        serial_outputs: List of serial output values for each state
        states: Bidirectional dictionary mapping state names to indices and vice versa
        events_dict: Dictionary mapping event names to column indices
        extra_timers_names: List of extra timer names
        extra_timers_duration: List of extra timer durations
        extra_timers_triggers: List of states that trigger extra timers
        
    Note:
        Internal data structures use Python lists for construction flexibility.
        Use get_*() methods to obtain validated NumPy arrays for runtime efficiency.
        The START state (state 0) and END state (last state) are managed automatically.
    """
    def __init__(self, inputs: Optional[Dict[str, int]] = None, 
                 outputs: Optional[Dict[str, int]] = None,
                 extratimers: Optional[List[str]] = None) -> None:
        """
        Initialize StateMatrix.
        
        Args:
            inputs: Dictionary mapping input names to their integer indices.
                   Used to define available input events (e.g., port entries/exits).
            outputs: Dictionary mapping output names to their integer indices.
                    Used to define available outputs (e.g., valves, LEDs).
            extratimers: List of extra timer names. These timers can be triggered
                        by specific states and continue running across state transitions.

        Note:
            The state matrix automatically creates a START state as state 0 and
            an END state as the last state when get_matrix() is called.

        Example:
            >>> sm = StateMatrix(
            ...     inputs={'center': 0, 'left': 1, 'right': 2},
            ...     outputs={'valve': 0, 'led': 1},
            ...     extratimers=['punishment_timer']
            ... )
        """
        # Handle mutable default arguments
        if inputs is None:
            inputs = {}
        if outputs is None:
            outputs = {}
        if extratimers is None:
            extratimers = []
            
        self.inputs_dict = inputs
        self.outputs_dict = outputs

        # Initialize lists that will grow as needed
        self.state_matrix = []
        self.state_timers = []
        self.state_outputs = []
        self.serial_outputs = []

        self.states = bidict()

        self._next_state_ind = 0

        #self.extraTimersIndexToName = {}
        #self.extraTimersNameToIndex = {}
        self.extra_timers_names = []
        #self._nextExtraTimerInd = 0
        self.extra_timers_duration = []
        self.extra_timers_triggers = []

        # This dictionary is modified if ExtraTimers are used.
        self.events_dict = {}
        for key,val in self.inputs_dict.items():
            self.events_dict[key+'in'] = 2*val
            self.events_dict[key+'out'] = 2*val+1
        self.events_dict['Tup'] = len(self.events_dict)

        self.n_input_events = len(self.events_dict)
        self.events_dict['Forced'] = -1
        self.n_outputs = len(self.outputs_dict)

        for onetimer in extratimers:
            self._add_extratimer(onetimer)

        self._init_mat()

    def append_to_file(self, h5file: Any, current_trial: int) -> None:
        """
        Append state matrix definitions to an open HDF5 file.
        
        Saves the events dictionary, outputs dictionary, and states dictionary
        to the HDF5 file under a '/stateMatrix' group.
        
        Args:
            h5file: Open HDF5 file handle where data will be written
            current_trial: Current trial number (parameter is ignored but kept
                         for compatibility)
                         
        Note:
            The current_trial parameter is currently ignored but maintained
            for backward compatibility.
        """
        statemat_group = h5file.create_group('/stateMatrix')
        utils.append_dict_to_HDF5(statemat_group,'eventsNames',self.events_dict)
        utils.append_dict_to_HDF5(statemat_group,'outputsNames',self.outputs_dict)
        utils.append_dict_to_HDF5(statemat_group,'statesNames',dict(self.states))

        #TODO: save names of extratimers and index corresponding to the event for each.
        #      note that you have to add nInputEvents to the index of each timer.
        #utils.append_dict_to_HDF5(statemat_group,'extraTimersNames',self.extraTimersNameToIndex)

    def _make_default_row(self, state_ind: int) -> List[int]:
        """
        Create a default transition row for a state.
        
        Creates a row where all events transition back to the same state,
        effectively creating a self-loop for all events until explicitly
        overridden.
        
        Args:
            state_ind: Index of the state for which to create the default row
            
        Returns:
            List of integers representing state transitions, where each position
            corresponds to an event and the value is the target state index
        """
        n_extra_timers = len(self.extra_timers_names)
        new_row = (self.n_input_events+n_extra_timers)*[state_ind]    # Input events
        return new_row

    def _init_mat(self) -> None:
        """
        Initialize state transition matrix with the START state.
        
        Creates the initial state matrix with a START state (state 0)
        that has a very long timer. This state serves as the starting point
        for the state machine in every trial.
        
        Raises:
            Exception: If called when the state matrix already has more than
                      one state, indicating that extra timers should be created
                      before any states.
        """
        if len(self.state_matrix)>1:
            raise Exception('You need to create all extra timers before creating any state.')
        self.add_state(name='START', statetimer=0)
        # Set START state to transition to state 1 on timeout
        self._force_transition(0, 1)

    def _force_transition(self, origin_state_id: int, destination_state_id: int) -> None:
        """
        Set a timeout transition between two states using state IDs.
        
        Directly modifies the state matrix to create a transition on the 'Tup'
        (timeout) event from the origin state to the destination state.
        
        Args:
            origin_state_id: Index of the state to transition from
            destination_state_id: Index of the state to transition to
            
        Note:
            This method bypasses the normal state name resolution and works
            directly with state indices for efficiency.
        """
        self.state_matrix[origin_state_id][self.events_dict['Tup']] = destination_state_id

    def _append_state_to_list(self, state_name: str) -> None:
        """
        Add a new state to the available states list.
        
        Assigns the next available index to the named state, updates
        the state dictionaries, and creates the corresponding matrix row.
        This method manages the automatic assignment of state indices
        and ensures matrix consistency.
        
        Args:
            state_name: Name of the state to add
        """
        state_ind = self._next_state_ind
        self.states[state_name] = state_ind
        self._next_state_ind += 1
        
        # Extend lists if needed to accommodate this state
        while len(self.state_matrix) <= state_ind:
            self.state_matrix.append([])
            self.state_timers.append(INFINITE_TIME)  # Default to infinite timer
            self.state_outputs.append(self.n_outputs*[NOCHANGE])
            self.serial_outputs.append(0)
            
        # Create default row for this state (all events transition to itself)
        self.state_matrix[state_ind] = self._make_default_row(state_ind)

    def add_state(self, name: str = '', statetimer: float = INFINITE_TIME, 
                  transitions: Optional[Dict[str, str]] = None,
                  outputsOn: Optional[List[str]] = None, 
                  outputsOff: Optional[List[str]] = None, 
                  trigger: Optional[List[str]] = None, 
                  serialOut: int = 0) -> None:
        """
        Add a state to the transition matrix.
        
        Creates or updates a state with the specified timer, transitions,
        outputs, and triggers. This is the main method for building the
        state machine structure.
        
        Args:
            name: Name of the state. If empty string, a default name will be used.
            statetimer: Duration in seconds that the state will last before
                       timing out (triggering a 'Tup' event). Use float('inf')
                       for states that should never timeout automatically.
            transitions: Dictionary mapping event names to target state names.
                        Events include input events (e.g., 'centerin', 'centerout')
                        and timer events (e.g., 'Tup').
            outputsOn: List of output names to turn ON when entering this state.
            outputsOff: List of output names to turn OFF when entering this state.
            trigger: List of extra timer names to start/trigger when entering
                    this state.
            serialOut: Integer (1-255) to send through serial port when entering
                      this state. A value of 0 means no serial output.
                      
        Example:
            >>> sm.add_state(
            ...     name='wait_for_poke',
            ...     statetimer=10.0,
            ...     transitions={'centerin': 'reward_state'},
            ...     outputsOn=['led'],
            ...     outputsOff=['valve'],
            ...     serialOut=1
            ... )
        """
        # Handle mutable default arguments
        if transitions is None:
            transitions = {}
        if outputsOn is None:
            outputsOn = []
        if outputsOff is None:
            outputsOff = []
        if trigger is None:
            trigger = []

        n_extra_timers = len(self.extra_timers_names)

        # -- Find index for this state (create if necessary) --
        if name not in self.states:
            self._append_state_to_list(name)
        this_state_ind = self.states[name]

        # -- Add target states from specified events --
        new_row = self._make_default_row(this_state_ind)
        for (event_name, target_state_name) in transitions.items():
            if target_state_name not in self.states:
                self._append_state_to_list(target_state_name)
            target_state_ind = self.states[target_state_name]
            new_row[self.events_dict[event_name]] = target_state_ind

        # -- Update state properties --
        # Matrix row already exists from _append_state_to_list, just update it
        self.state_matrix[this_state_ind] = new_row
        self.state_timers[this_state_ind] = statetimer
        
        # Reset outputs to default, then apply specified outputs
        self.state_outputs[this_state_ind] = self.n_outputs*[NOCHANGE]
        for one_output in outputsOn:
            output_ind = self.outputs_dict[one_output]
            self.state_outputs[this_state_ind][output_ind] = 1
        for one_output in outputsOff:
            output_ind = self.outputs_dict[one_output]
            self.state_outputs[this_state_ind][output_ind] = 0
        self.serial_outputs[this_state_ind] = serialOut

        # -- Add this state to the list of triggers for extra timers --
        for one_extra_timer in trigger:
            extra_timer_ind = self.extra_timers_names.index(one_extra_timer)
            self.extra_timers_triggers[extra_timer_ind] = this_state_ind

    def _add_extratimer(self, name: str, duration: float = 0) -> None:
        """
        Add an extra timer to the state matrix.
        
        Extra timers are independent timers that can be triggered by specific
        states but continue running even after state transitions. They generate
        their own events when they expire.
        
        Args:
            name: Name of the extra timer
            duration: Initial duration in seconds (can be changed later with
                     set_extratimer)
                     
        Raises:
            Exception: If a timer with the same name already exists
            
        Note:
            Extra timers must be added before creating any states, as they
            modify the structure of the transition matrix.
        """
        if name not in self.extra_timers_names:
            self.extra_timers_names.append(name)
        else:
            raise Exception(f'Extra timer ({name}) has already been defined.')
        extra_timer_event_col = self.n_input_events + len(self.extra_timers_names)-1
        self.events_dict[name] = extra_timer_event_col
        #self._init_mat() # Initialize again with different number of columns
        self.extra_timers_duration.append(duration)
        #self.extraTimersTriggers.append(None) # This will be filled by add_state
        # The default trigger for extratimers is state 0. The state machine requires a trigger.
        self.extra_timers_triggers.append(0) # This will be updated by add_state

    def set_extratimer(self, name: str, duration: float) -> None:
        """
        Set the duration of an existing extra timer.
        
        Updates the duration of a previously defined extra timer. This allows
        for dynamic adjustment of timer durations between trials.
        
        Args:
            name: Name of the extra timer to modify
            duration: New duration in seconds
            
        Raises:
            Exception: If no extra timer with the specified name exists
        """
        if name not in self.extra_timers_names:
            raise Exception(f'The state matrix has no extratimer called {name}.')
        self.extra_timers_duration[self.extra_timers_names.index(name)] = duration

    def _ensure_end_state(self) -> None:
        """
        Ensure an END state exists as the last state.
        
        Creates an END state with infinite timer if it doesn't already exist.
        The END state serves as a waiting state where the machine can wait
        until it is forced to transition to the START state for the next trial.
        """
        if 'END' not in self.states:
            # Add END state with infinite timer that loops back to itself
            self.add_state(name='END', statetimer=INFINITE_TIME)

    def get_matrix(self) -> np.ndarray:
        """
        Get the state transition matrix as a NumPy array.
        
        Validates the matrix for consistency (ensuring all referenced states exist),
        adds an END state as the last state if not already present, and converts
        from the internal Python list representation to a NumPy array for efficient
        runtime use.
        
        Returns:
            NumPy array of shape (n_states, n_events) with state transition matrix.
            Each element [i,j] represents the target state when state i receives event j.
            The END state is automatically added as the final state and serves as
            a waiting state for the next trial.
            
        Raises:
            ValueError: If matrix is empty, has invalid dimensions, or contains
                       state indices outside the valid range [0, n_states-1].
        """
        # Ensure END state exists as the last state
        self._ensure_end_state()
        
        # Remove any empty rows at the end
        #actual_matrix = [row for row in self.state_matrix if row]
        
        #if not actual_matrix:
        #    raise ValueError("State matrix is empty")
            
        # Convert to numpy array
        matrix_array = np.array(self.state_matrix, dtype=np.int32)

        # Validate array shape consistency
        if matrix_array.ndim != 2:
            raise ValueError("State matrix must be 2-dimensional")
            
        # Validate state indices
        n_states = matrix_array.shape[0]
        if np.any(matrix_array < 0) or np.any(matrix_array >= n_states):
            raise ValueError(f"State matrix contains invalid state indices. Must be 0 to {n_states-1}")
            
        return matrix_array

    def get_outputs(self) -> np.ndarray:
        """
        Get the state outputs matrix as a NumPy array.
        
        Ensures the END state exists, then filters and validates the outputs list
        to include only outputs for states that actually exist in the state matrix.
        Validates that all output values are within the allowed range.
        
        Returns:
            NumPy array of shape (n_states, n_outputs) with output configurations.
            Values are: 0 (off), 1 (on), or -1 (unchanged from previous state).
            
        Raises:
            ValueError: If any output values are outside the valid range [-1, 0, 1].
        """
        # Ensure END state exists
        self._ensure_end_state()
        
        if not self.state_outputs:
            return np.empty((0, self.n_outputs), dtype=np.int32)
            return np.empty((0, self.n_outputs), dtype=np.int32)
            
        # Remove any empty rows and ensure consistent length
        actual_outputs = []
        for i, outputs in enumerate(self.state_outputs):
            if i < len(self.state_matrix) and self.state_matrix[i]:  # Only include if state exists
                actual_outputs.append(outputs)
                
        if not actual_outputs:
            return np.empty((0, self.n_outputs), dtype=np.int32)
            
        outputs_array = np.array(actual_outputs, dtype=np.int32)
        
        # Validate output values
        valid_outputs = np.isin(outputs_array, [-1, 0, 1])
        if not np.all(valid_outputs):
            raise ValueError("State outputs must contain only -1 (no change), 0 (off), or 1 (on)")
            
        return outputs_array

    def get_state_timers(self) -> np.ndarray:
        """
        Get the state timers as a NumPy array.
        
        Ensures the END state exists, then filters and validates the timer list
        to include only timers for states that actually exist in the state matrix.
        
        Returns:
            NumPy array of timer durations for each state in seconds.
            Array length matches the number of valid states.
        """
        # Ensure END state exists
        self._ensure_end_state()
        
        if not self.state_timers:
            return np.empty(0, dtype=np.float64)
            
        # Only include timers for states that actually exist
        actual_timers = []
        for i, timer in enumerate(self.state_timers):
            if i < len(self.state_matrix) and self.state_matrix[i]:
                actual_timers.append(timer)
                
        return np.array(actual_timers, dtype=np.float64)

    def get_timer_event_index(self) -> int:
        """
        Get the index of the timer event ('Tup') in the state matrix.
        
        Returns:
            Integer index of the 'Tup' event column in the state matrix.
            This is useful when creating a StateMachine instance.
        """
        return self.events_dict['Tup']

    def analyze_matrix_properties(self) -> Dict[str, Any]:
        """
        Analyze matrix properties using NumPy for insights.
        
        Returns:
            Dictionary with analysis results including connectivity,
            dead ends, cycles, etc.
        """
        try:
            matrix = self.get_matrix()
            n_states, n_events = matrix.shape
            
            # Find reachable states
            reachable = set([0])  # Assume state 0 is always reachable
            for state in range(n_states):
                reachable.update(matrix[state])
            
            all_states = set(range(n_states))
            unreachable = all_states - reachable
            
            # Find dead-end states (only self-transitions)
            dead_ends = []
            for state in range(n_states):
                if np.all(matrix[state] == state):
                    dead_ends.append(state)
            
            # Calculate connectivity metrics
            unique_transitions = len(np.unique(matrix))
            
            return {
                'n_states': n_states,
                'n_events': n_events,
                'reachable_states': sorted(reachable),
                'unreachable_states': sorted(unreachable),
                'dead_end_states': dead_ends,
                'connectivity_ratio': unique_transitions / n_states,
                'is_fully_connected': len(unreachable) == 0,
                'matrix_density': np.count_nonzero(matrix != np.arange(n_states)[:, None]) / matrix.size
            }
            
        except Exception as e:
            return {'error': str(e), 'valid': False}

    def reset_transitions(self) -> None:
        """
        Reset all state transitions to default values.
        
        Resets all states to have self-transitions for all events, very long
        timers, and unchanged output configurations. This effectively clears
        all custom transitions while preserving the state structure.
        
        Note:
            This method preserves the states themselves but removes all
            custom transition logic, timers, and output configurations.
        """
        for state_ind in self.states.inverse.keys():
            self.state_matrix[state_ind] = self._make_default_row(state_ind)
            self.state_timers[state_ind] = INFINITE_TIME
            self.state_outputs[state_ind] = self.n_outputs*[NOCHANGE]

    def get_serial_outputs(self) -> List[int]:
        """
        Get the serial output values for all states.
        
        Returns:
            List of integers representing serial output values for each state.
            0 means no serial output, 1-255 are valid output codes.
        """
        return self.serial_outputs

    def get_extra_timers(self) -> List[float]:
        """
        Get the durations of all extra timers.
        
        Returns:
            List of floats representing the duration in seconds of each
            extra timer.
        """
        return self.extra_timers_duration

    def get_extra_triggers(self) -> List[int]:
        """
        Get the trigger states for all extra timers.
        
        Returns:
            List of integers representing which state index triggers each
            extra timer.
        """
        return self.extra_timers_triggers

    def get_states_dict(self) -> bidict:
        """
        Get the bidirectional mapping between state names and indices.
        
        Returns:
            Bidirectional dictionary where you can access:
            - Forward mapping: states['state_name'] -> index
            - Reverse mapping: states.inverse[index] -> 'state_name'
        """
        return self.states

    def __str__(self) -> str:
        """
        Create a human-readable string representation of the state matrix.
        
        Formats the state matrix as a table showing:
        - Extra timer information
        - Column headers for events
        - Each state with its transitions, timers, outputs, and serial codes
        
        Returns:
            Multi-line string representation of the complete state matrix
            suitable for debugging and visualization.
        """
        mat_str = '\n'
        rev_events_dict = {}
        mat_str += self._extratimers_as_str()
        for key in self.events_dict:
            if key!='Forced':
                rev_events_dict[self.events_dict[key]] = key
        mat_str += '\t\t\t'
        mat_str += '\t'.join([rev_events_dict[k][0:4] for k in sorted(rev_events_dict.keys())])
        mat_str += '\t\tTimers\tOutputs\tSerialOut'
        mat_str += '\n'
        sm = self.get_matrix()
        for (index, one_row) in enumerate(sm):
            mat_str += f'{self.states.inverse[index].ljust(16)} [{index}] \t'
            mat_str += '\t'.join(str(e) for e in one_row)
            mat_str += f'\t|\t{self.state_timers[index]:0.2f}'
            mat_str += f'\t{self._output_as_str(self.state_outputs[index])}'
            mat_str += f'\t{self.serial_outputs[index]}'
            mat_str += '\n'
        return mat_str

    def _extratimers_as_str(self) -> str:
        """
        Format extra timers information as a string.
        
        Returns:
            String representation of all extra timers showing their names,
            durations, and which states trigger them.
        """
        et_str = ''
        for ind_t, one_extratimer in enumerate(self.extra_timers_names):
            if self.extra_timers_triggers[ind_t] is not None:
                this_trigger = self.states.inverse[self.extra_timers_triggers[ind_t]]
            else:
                this_trigger = '[nothing]'
            et_str += f'{one_extratimer}:\t{self.extra_timers_duration[ind_t]:0.2f} triggered by {this_trigger}\n'
        return et_str

    def _output_as_str(self, output_vec: List[int]) -> str:
        """
        Convert an output vector to a string representation.
        
        Args:
            outputVec: List of integers representing output states
            
        Returns:
            String where '1' = on, '0' = off, '-' = unchanged from previous state
        """
        #outputStr = '-'*len(outputVec)
        output_str = ''
        for ind_o, output_value in enumerate(output_vec):
            if output_value==1:
                output_str += '1'
            elif output_value==0:
                output_str += '0'
            else:
                output_str += '-'
        return output_str