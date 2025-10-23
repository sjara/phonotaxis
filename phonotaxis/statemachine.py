"""
State machine.

This module implements a state machine using PyQt. The transitions are defined
in a state matrix, and the machine can handle inputs, outputs, and timers.
"""

import time
import numpy as np
from PyQt6 import QtCore, QtWidgets
from typing import List, Dict, Optional, Any
import warnings


DEBUG = False


class StateMachine(QtCore.QObject):
    """
    PyQt-based state machine that handles inputs via signals and outputs via signals.
    
    The state machine operates based on NumPy arrays where:
    - Each row represents a state
    - Each column represents an input event
    - Matrix values indicate the next state for each event
    
    Signals:
        stateChanged(int): Emitted when state changes. Args: newStateIndex.
        outputChanged(int, bool): Emitted when an output changes.
        integerOutput(int): Emitted when entering a state with an integer output.
        forceStateTransition(int): Signal to force a transition to stateIndex.
        eventProcessed(int, float, int): eventIndex, timestamp, newState
        stateTimerExpired(): Internal signal for state timer expiration (typically not used externally)
    
    Public Methods (to send events/control):
        process_input(input_event: int): Process an input event.
        connect_input_signal(signal: QtCore.pyqtSignal, input_event: int): Connect a PyQt
            signal to an input event, so when the signal is emitted, the input event is
            automatically processed
        force_state(state_index: int): Force a transition to a specific state, bypassing
            the state matrix. Use -1 to force transition to the last (END) state
        force_output(output: int, value: bool): Force an output to a specific value,
            bypassing normal state-based output control
        start(): Start the state machine (begins in END state)
        stop(): Stop the state machine
    
    Public Methods (to query state/events):
        get_current_state() -> int: Returns the current state index
        get_state_info() -> Dict: Returns comprehensive state machine information including
            current_state, is_running, is_configured, num_states, num_inputs, num_outputs,
            output_states, and state_timers
        get_output_state(output: int) -> bool: Returns current state of a specific output
        get_transitions_from_state(state: int) -> np.ndarray: Returns all possible next states
            from a given state for each input event
        get_transitions_for_input(input_event: int) -> np.ndarray: Returns next states for a
            specific input across all states
        find_states_with_output(output: int, value: bool) -> np.ndarray: Returns array of
            state indices that have a specific output value
    
    The state machine can handle:
    - Input events (from external PyQt signals via connect_input_signal())
    - State timers (automatic transitions after timeout)
    - State outputs (signals emitted when entering states)
    - Forced state transitions (via force_state() or forceStateTransition signal)
    """
    
    # Signals
    stateChanged = QtCore.pyqtSignal(int)  # newStateIndex
    outputChanged = QtCore.pyqtSignal(int, bool)  # outputIndex, value
    integerOutput = QtCore.pyqtSignal(int)   # integer output value
    forceStateTransition = QtCore.pyqtSignal(int)  # stateIndex - for external forced transitions
    eventProcessed = QtCore.pyqtSignal(int, float, int)  # eventIndex, timestamp, newState
    _stateTimerExpired = QtCore.pyqtSignal()  # stateTimer expiration internal signal
    
    def __init__(self):
        """
        Initialize an empty state machine.
        
        Use set_state_matrix(), set_state_outputs(), and set_state_timers() 
        to configure the state machine before starting.
        """
        super().__init__()
        
        # Initialize empty state machine
        self.state_matrix = None
        self.state_timers = None
        self.state_outputs = None
        self.integer_outputs = None
        self.timer_event_index = None
        
        self.num_states = 0
        self.num_inputs = 0
        self.num_outputs = 0
        
        # State machine state
        self.current_state = 0
        self.is_running = False
        self.output_states = []
        
        # Timer for state timeouts
        self.state_timer = QtCore.QTimer()
        self.state_timer.setSingleShot(True)
        self.state_timer.timeout.connect(self._stateTimerExpired.emit)
        self._stateTimerExpired.connect(self._on_state_timer_expired)
        
        # Connect force state transition signal
        self.forceStateTransition.connect(self._on_force_state_transition)
        
    def set_state_matrix(self, state_matrix: np.ndarray, timer_event_index: Optional[int] = None):
        """
        Set the state matrix for the state machine.
        
        Args:
            state_matrix: 2D NumPy array where each row is a state and each column is an input event.
                         Values are the next state indices for each event.
            timer_event_index: Index of the timer expiration event column in the state matrix.
                              If None, assumes the last column is the timer event.
        """
        if self.is_running:
            raise RuntimeError("Cannot modify state matrix while state machine is running")
            
        # Validate that input is a NumPy array
        if not isinstance(state_matrix, np.ndarray):
            raise TypeError("state_matrix must be a NumPy array")
            
        # Store array with proper dtype
        self.state_matrix = state_matrix.astype(np.int32)
        
        # Validate inputs
        if self.state_matrix.size == 0:
            raise ValueError("State matrix cannot be empty")
        if self.state_matrix.ndim != 2:
            raise ValueError("State matrix must be 2-dimensional")
            
        self.num_states, self.num_inputs = self.state_matrix.shape
        
        # Validate state matrix values are valid state indices
        if np.any(self.state_matrix < 0) or np.any(self.state_matrix >= self.num_states):
            raise ValueError(f"State matrix contains invalid state indices. Must be 0 to {self.num_states-1}")
        
        # Set timer event index for handling timer expiration
        if timer_event_index is None:
            # Default: assume timer event is the last column
            self.timer_event_index = self.num_inputs - 1
        else:
            if not (0 <= timer_event_index < self.num_inputs):
                raise ValueError(f"Timer event index must be between 0 and {self.num_inputs-1}")
            self.timer_event_index = timer_event_index
            
        # Initialize state timers if not already set
        if self.state_timers is None:
            self.state_timers = np.full(self.num_states, float('inf'), dtype=np.float64)
        elif len(self.state_timers) != self.num_states:
            # Resize state timers to match new state count
            old_timers = self.state_timers
            self.state_timers = np.full(self.num_states, float('inf'), dtype=np.float64)
            # Copy over existing timers up to the minimum of old and new sizes
            copy_size = min(len(old_timers), self.num_states)
            self.state_timers[:copy_size] = old_timers[:copy_size]
            
    def set_state_timers(self, state_timers: np.ndarray):
        """
        Set the state timers for the state machine.
        
        Args:
            state_timers: 1D NumPy array of timer durations for each state (seconds).
        """
        if self.is_running:
            raise RuntimeError("Cannot modify state timers while state machine is running")
            
        # Validate that input is a NumPy array
        if not isinstance(state_timers, np.ndarray):
            raise TypeError("state_timers must be a NumPy array")
            
        if state_timers.ndim != 1:
            raise ValueError("State timers must be 1-dimensional")
        if self.state_matrix is not None and len(state_timers) != self.num_states:
            raise ValueError("State timers must have same length as number of states")
            
        self.state_timers = state_timers.astype(np.float64)
        
    def set_state_outputs(self, state_outputs: np.ndarray):
        """
        Set the state outputs for the state machine.
        
        Args:
            state_outputs: 2D NumPy array where each row contains output values for a state.
                          Values: 0 (off), 1 (on), -1 (no change)
        """
        if self.is_running:
            raise RuntimeError("Cannot modify state outputs while state machine is running")
            
        # Validate that input is a NumPy array
        if not isinstance(state_outputs, np.ndarray):
            raise TypeError("state_outputs must be a NumPy array")
            
        # Store array with proper dtype
        self.state_outputs = state_outputs.astype(np.int32)
        
        # Validate inputs
        if self.state_outputs.ndim != 2:
            raise ValueError("State outputs must be 2-dimensional")
        if self.state_matrix is not None and self.state_outputs.shape[0] != self.state_matrix.shape[0]:
            raise ValueError("State outputs must have same number of rows as state matrix")
            
        self.num_outputs = self.state_outputs.shape[1] if self.state_outputs.size > 0 else 0
        
        # Validate output values
        valid_outputs = np.isin(self.state_outputs, [-1, 0, 1])
        if not np.all(valid_outputs):
            raise ValueError("State outputs must contain only -1 (no change), 0 (off), or 1 (on)")
            
        # Initialize output states
        self.output_states = [False] * self.num_outputs
        
    def set_integer_outputs(self, integer_outputs: np.ndarray):
        """
        Set the state integer outputs for the state machine.
        """
        self.integer_outputs = integer_outputs
    
    def reset(self):
        """
        Reset the state machine to empty state.
        
        This clears all configuration (state matrix, outputs, timers) and stops
        the state machine if it's running.
        """
        # Stop the state machine if running
        if self.is_running:
            self.stop()
            
        # Reset all configuration
        self.state_matrix = None
        self.state_outputs = None
        self.state_timers = None
        self.timer_event_index = None
        
        self.num_states = 0
        self.num_inputs = 0
        self.num_outputs = 0
        
        # Reset state machine state
        self.current_state = 0
        self.output_states = []
        
    def is_configured(self) -> bool:
        """
        Check if the state machine is fully configured and ready to start.
        
        Returns:
            True if state matrix and outputs are set, False otherwise
        """
        return (self.state_matrix is not None and 
                self.state_outputs is not None and 
                self.state_timers is not None)
        
    def start(self):
        """
        Start the state machine.
        
        The state machine always starts in the END state (last state), which is the
        standard initialization pattern. Use force_state()
        to move to the first behavioral state after starting.
            
        Raises:
            RuntimeError: If state machine is not fully configured
        """
        if not self.is_configured():
            raise RuntimeError("State machine must be configured before starting. "
                             "Use set_state_matrix() and set_state_outputs() first.")
            
        self.is_running = True
        # Always start at the END state (-1) to ensure consistent initialization
        # but don't emit state change or outputs yet
        # self.force_state(-1)
        # self._enter_state(self.num_states - 1)
        self.current_state = self.num_states - 1
        
    def stop(self):
        """Stop the state machine."""
        self.is_running = False
        self.state_timer.stop()
                   
    def process_input(self, input_event: int):
        """
        Process an input event and potentially transition to a new state.
        
        Args:
            input_event: Input event index
        """
        if not self.is_running:
            return
            
        if not self.is_configured():
            raise RuntimeError("State machine is not configured")
            
        if not (0 <= input_event < self.num_inputs):
            raise ValueError(f"Invalid input index: {input_event}")
            
        if DEBUG:
            print(f"Processing input event {input_event} in state {self.current_state}")
            
        # Delegate to unified event processing method
        self._process_event(input_event)
            
    def connect_input_signal(self, signal: QtCore.pyqtSignal, input_event: int):
        """
        Connect a PyQt signal to an input event.
        
        Args:
            signal: PyQt signal to connect
            input_event: Input event index to trigger when signal is emitted
        """
        signal.connect(lambda: self.process_input(input_event))
        
    def get_current_state(self) -> int:
        """Get current state index."""
        return self.current_state
        
    def get_output_state(self, output: int) -> bool:
        """
        Get current state of an output.
        
        Args:
            output: Output index
            
        Returns:
            Current output state (True=on, False=off)
        """
        if not (0 <= output < self.num_outputs):
            raise ValueError(f"Invalid output index: {output}")
            
        return self.output_states[output]
        
    def set_state_timer(self, state: int, duration: float):
        """
        Set the timer duration for a state.
        
        Args:
            state: State index
            duration: Timer duration in seconds
        """
        if not self.is_configured():
            raise RuntimeError("State machine is not configured")
            
        if not (0 <= state < self.num_states):
            raise ValueError(f"Invalid state index: {state}")
            
        self.state_timers[state] = duration
        
        # If we're currently in this state, restart the timer
        if state == self.current_state and self.is_running:
            self._start_state_timer()
            
    def force_state(self, state_index: int):
        """
        Force a transition to a specific state, bypassing the state matrix.
        
        This method allows external control to override normal state machine
        transitions, useful for initialization, error recovery, or external
        processing completion.
        
        Args:
            state_index: Index of state to force transition to. Use -1 to force
                        transition to the last (END) state.
            
        Raises:
            ValueError: If state_index is invalid
            RuntimeError: If state machine is not configured
        """
        if not self.is_configured():
            warnings.warn("State machine is not configured. No state was forced.")
            return
            #raise RuntimeError("State machine is not configured")
            
        # Handle -1 as last state
        if state_index == -1:
            state_index = self.num_states - 1
            
        if not (0 <= state_index < self.num_states):
            raise ValueError(f"Invalid state index: {state_index}")
            
        # Only transition if we're running and it's a different state
        if self.is_running and state_index != self.current_state:
            # Emit eventProcessed signal for forced transitions with event ID -1
            timestamp = time.time()
            self.eventProcessed.emit(-1, timestamp, state_index)
            self._enter_state(state_index)

    def force_output(self, output: int, value: bool):
        """
        Force an output to a specific value, bypassing normal state-based output control.
        
        This method allows external control to override output states independently
        of the current state configuration. The forced output value will persist
        until the state machine transitions to a new state that explicitly sets
        this output, or until force_output() is called again.
        
        Args:
            output: Output index to force
            value: Output value to force (True=on, False=off)
            
        Raises:
            ValueError: If output index is invalid
            RuntimeError: If state machine is not configured
        """
        if not self.is_configured():
            warnings.warn("State machine is not configured. No output was forced.")
            return
            #raise RuntimeError("State machine is not configured")
            
        if not (0 <= output < self.num_outputs):
            raise ValueError(f"Invalid output index: {output}")
            
        # Only change and emit signal if the value is actually different
        if self.output_states[output] != value:
            self.output_states[output] = value
            self.outputChanged.emit(output, value)

    def _enter_state(self, state_index: int):
        """
        Enter a new state, handling outputs and timers.
        
        Args:
            state_index: Index of state to enter
        """
        if not (0 <= state_index < self.num_states):
            raise ValueError(f"Invalid state index: {state_index}")
            
        old_state = self.current_state
        self.current_state = state_index
        
        # Stop current timer
        self.state_timer.stop()
         
        # Process outputs for new state
        self._process_state_outputs()

        # Process integer output for new state
        self._process_integer_outputs()        

        # Start new state timer
        self._start_state_timer()
        
        # Emit state change signal
        self.stateChanged.emit(self.current_state)
        
    def _process_state_outputs(self):
        """Process output changes for the current state."""
        if self.state_outputs is None:
            return
            
        state_output_config = self.state_outputs[self.current_state]
        
        for ind, output_value in enumerate(state_output_config):
            if output_value == 0:  # Turn off
                if self.output_states[ind]:  # Only change if currently on
                    self.output_states[ind] = False
                    self.outputChanged.emit(ind, False)
            elif output_value == 1:  # Turn on
                if not self.output_states[ind]:  # Only change if currently off
                    self.output_states[ind] = True
                    self.outputChanged.emit(ind, True)
            # output_value == -1 means no change, so we do nothing
            
    def _process_integer_outputs(self):
        """Process output changes for the current state."""
        if self.integer_outputs is None:
            return
        iout = self.integer_outputs[self.current_state]
        if iout != 0:
            self.integerOutput.emit(iout)
            
    def _start_state_timer(self):
        """Start the timer for the current state."""
        if self.state_timers is None:
            return
        timer_duration = self.state_timers[self.current_state]
        if timer_duration != float('inf') and timer_duration >= 0:
            self.state_timer.start(int(timer_duration * 1000))  # Convert to milliseconds
            
    def _on_state_timer_expired(self):
        """Handle state timer expiration as a special input event."""
        if not self.is_running or not self.is_configured():
            return
        # Delegate to unified event processing method using timer event index
        self._process_event(self.timer_event_index)
        
    def _process_event(self, event_index: int):
        """
        Unified method to process any event (input or timer) and potentially transition to a new state.
        
        This method handles the common logic for all event types:
        - Records timestamp
        - Looks up next state from state matrix
        - Emits eventProcessed signal
        - Transitions to new state if different
        
        Args:
            event_index: Index of the event (input or timer) being processed
        """
        # Record the timestamp when event is processed
        timestamp = time.time()
        
        # Get next state from state matrix
        next_state = self.state_matrix[self.current_state, event_index]
        
        # Emit signal for event processing (regardless of whether state changes)
        self.eventProcessed.emit(event_index, timestamp, next_state)
        
        # Transition to next state if it's different
        if next_state != self.current_state:
            self._enter_state(next_state)
            
    def _on_force_state_transition(self, state_index: int):
        """Handle forced state transition via signal."""
        if not self.is_configured():
            return
            
        if not (0 <= state_index < self.num_states):
            return  # Silently ignore invalid states when called via signal
            
        if self.is_running and state_index != self.current_state:
            self._enter_state(state_index)
        
    def get_state_info(self) -> Dict[str, Any]:
        """
        Get comprehensive information about the current state machine.
        
        Returns:
            Dictionary with state machine information
        """
        return {
            'current_state': self.current_state,
            'is_running': self.is_running,
            'is_configured': self.is_configured(),
            'num_states': self.num_states,
            'num_inputs': self.num_inputs,
            'num_outputs': self.num_outputs,
            'output_states': self.output_states.copy() if self.output_states else [],
            'state_timers': self.state_timers.copy() if self.state_timers is not None else None
        }
        
    def get_transitions_from_state(self, state: int) -> np.ndarray:
        """
        Get all possible transitions from a given state.
        
        Args:
            state: State index
            
        Returns:
            NumPy array of next states for each input event
            
        Raises:
            RuntimeError: If state machine is not configured
        """
        if not self.is_configured():
            raise RuntimeError("State machine is not configured")
            
        if not (0 <= state < self.num_states):
            raise ValueError(f"Invalid state index: {state}")
            
        return self.state_matrix[state].copy()
        
    def get_transitions_for_input(self, input_event: int) -> np.ndarray:
        """
        Get transitions for a specific input across all states.
        
        Args:
            input_event: Input event index
            
        Returns:
            NumPy array of next states for this input from each state
            
        Raises:
            RuntimeError: If state machine is not configured
        """
        if not self.is_configured():
            raise RuntimeError("State machine is not configured")
            
        if not (0 <= input_event < self.num_inputs):
            raise ValueError(f"Invalid input index: {input_event}")
            
        return self.state_matrix[:, input_event].copy()
        
    def find_states_with_output(self, output: int, value: bool) -> np.ndarray:
        """
        Find all states that have a specific output value.
        
        Args:
            output: Output index
            value: Output value to search for (True=on, False=off)
            
        Returns:
            NumPy array of state indices that have the specified output value
            
        Raises:
            RuntimeError: If state machine is not configured
        """
        if not self.is_configured():
            raise RuntimeError("State machine is not configured")
            
        if not (0 <= output < self.num_outputs):
            raise ValueError(f"Invalid output index: {output}")
            
        target_value = 1 if value else 0
        return np.where(self.state_outputs[:, output] == target_value)[0]
        
    def __str__(self) -> str:
        """String representation of the state machine."""
        if not self.is_configured():
            return f"StateMachine: Not configured (use set_state_matrix() and set_state_outputs())"
            
        lines = [
            f"StateMachine: {self.num_states} states, {self.num_inputs} inputs, {self.num_outputs} outputs",
            f"Current state: {self.current_state}",
            f"Running: {self.is_running}",
            "",
            "State Matrix:"
        ]
        
        # Header with input indices
        header = "State".ljust(15) + " | " + " ".join(f"In_{i:>3}" for i in range(self.num_inputs))
        lines.append(header)
        lines.append("-" * len(header))
        
        # State matrix rows
        for i, row in enumerate(self.state_matrix):
            current_marker = "*" if i == self.current_state else " "
            row_str = f"{current_marker}State_{i}".ljust(15) + " | " + " ".join(f"{val:>6}" for val in row)
            lines.append(row_str)
            
        lines.append("")
        lines.append("State Outputs:")
        header = "State".ljust(15) + " | " + " ".join(f"Out_{i:>3}" for i in range(self.num_outputs))
        lines.append(header)
        lines.append("-" * len(header))
        
        for i, outputs in enumerate(self.state_outputs):
            current_marker = "*" if i == self.current_state else " "
            output_str = []
            for j, val in enumerate(outputs):
                if val == 1:
                    output_str.append("ON")
                elif val == 0:
                    output_str.append("OFF")
                else:
                    output_str.append("-")
            row_str = f"{current_marker}State_{i}".ljust(15) + " | " + " ".join(f"{s:>6}" for s in output_str)
            lines.append(row_str)
            
        return "\n".join(lines)

