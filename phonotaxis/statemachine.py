"""
State machine.

This module implements a state machine using PyQt. The transitions are defined
in a state matrix, and the machine can handle inputs, outputs, and timers.

The state machine operates on NumPy arrays that define:
- State transition matrix: which state to move to for each input event
- State timers: how long to stay in each state before timeout
- State outputs: what outputs to activate/deactivate in each state
- Integer outputs: optional integer values to emit when entering states
- Extra timers: optional independent timers triggered by states that persist across transitions

Typical workflow:
    1. Create a StateMachine instance
    2. Configure it using set_state_matrix(), set_state_outputs(), set_state_timers()
    3. Optionally set integer outputs using set_integer_outputs()
    4. Optionally set extra timers using set_extra_timers()
    5. Connect external signals to input events using connect_input_signal()
    6. Connect to output signals (stateChanged, outputChanged, etc.)
    7. Call start() to begin operation
    8. Use force_state() to transition to the first behavioral state
    9. The machine runs until stop() is called or END state is reached

Example:
    >>> sm = StateMachine()
    >>> sm.set_state_matrix(state_matrix, timer_event_index=4)
    >>> sm.set_state_timers(timers)
    >>> sm.set_state_outputs(outputs)
    >>> sm.start()
    >>> sm.force_state(1)  # Move to first behavioral state
"""

import time
import numpy as np
from PyQt6 import QtCore
from typing import Dict, Optional, Any


PREFIX = " StateMachine:"


class StateMachine(QtCore.QObject):
    """
    PyQt-based state machine that handles inputs via signals and outputs via signals.
    
    The state machine operates based on NumPy arrays where:
    - Each row represents a state
    - Each column represents an input event
    - Matrix values indicate the next state for each event
    
    Args:
        debug: Enable debug output for event processing (default False)
    
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
        pause(): Pause event processing while continuing to log events with timestamps
        resume(process_queued: bool): Resume event processing, optionally processing queued events
    
    Public Methods (to query state/events):
        get_current_state() -> int: Returns the current state index
        get_state_info() -> Dict: Returns comprehensive state machine information including
            current_state, is_active, is_processing, is_configured, num_states, num_inputs, 
            num_outputs, output_states, and state_timers
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
    - Extra timers (independent timers triggered by states that persist across transitions)
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
    
    def __init__(self, debug: bool = False):
        """
        Initialize an empty state machine.
        
        Args:
            debug: Enable debug output (default False)
        
        Use set_state_matrix(), set_state_outputs(), and set_state_timers() 
        to configure the state machine before starting.
        """
        super().__init__()
        
        self.debug = debug
        
        # Initialize empty state machine
        self.state_matrix = None
        self.state_timers = None
        self.state_outputs = None
        self.integer_outputs = None
        self.timer_event_index = None
        
        # Extra timers (independent timers that persist across state transitions)
        self.extra_timers_durations = None  # Duration for each extra timer
        self.extra_timers_triggers = None   # Which state triggers each extra timer
        self.extra_timers = []  # List of QTimer objects for extra timers
        self.num_extra_timers = 0
        
        self.num_states = 0
        self.num_inputs = 0
        self.num_outputs = 0
        
        # State machine state
        self.current_state = 0
        self.is_active = False  # State machine is started/operational vs stopped
        self.is_processing = False  # Events are being processed vs suspended (default False until started)
        self.suspended_events = []  # Store (event_index, timestamp) tuples during suspension
        self.output_states = []
        
        # Timer for state timeouts
        self.state_timer = QtCore.QTimer()
        self.state_timer.setSingleShot(True)
        self.state_timer.timeout.connect(self._stateTimerExpired.emit)
        self._stateTimerExpired.connect(self._on_state_timer_expired)
        
        # Connect force state transition signal
        self.forceStateTransition.connect(self._on_force_state_transition)
        
    def set_state_matrix(self, state_matrix: np.ndarray, timer_event_index: Optional[int] = None) -> None:
        """
        Set the state matrix for the state machine.
        
        The state matrix defines all possible state transitions. Each row represents
        a state, and each column represents an input event. The matrix values are
        the indices of the next state to transition to when that event occurs.
        
        Args:
            state_matrix: 2D NumPy array where each row is a state and each column is an input event.
                         Values are the next state indices for each event.
            timer_event_index: Index of the timer expiration event column in the state matrix.
                              If None, assumes the last column is the timer event.
        
        Raises:
            RuntimeError: If state machine is currently processing events
            TypeError: If state_matrix is not a NumPy array
            ValueError: If state_matrix is empty, not 2D, or contains invalid state indices
        """
        if self.is_processing:
            raise RuntimeError("Cannot modify state matrix while state machine is processing events")
            
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
            
    def set_state_timers(self, state_timers: np.ndarray) -> None:
        """
        Set the state timers for the state machine.
        
        State timers define how long the state machine will wait in each state
        before triggering a timeout event. Use float('inf') for states that
        should wait indefinitely (no timeout).
        
        Args:
            state_timers: 1D NumPy array of timer durations for each state (seconds).
        
        Raises:
            RuntimeError: If state machine is currently active
            TypeError: If state_timers is not a NumPy array
            ValueError: If state_timers is not 1D or length doesn't match number of states
        
        Note:
            Timer precision is limited to approximately 1 millisecond due to Qt's
            QTimer implementation. Timer durations are converted to milliseconds and
            rounded to the nearest integer. For sub-millisecond precision, consider
            alternative timing mechanisms.
        """
        if self.is_processing:
            raise RuntimeError("Cannot modify state timers while state machine is processing events")
            
        # Validate that input is a NumPy array
        if not isinstance(state_timers, np.ndarray):
            raise TypeError("state_timers must be a NumPy array")
            
        if state_timers.ndim != 1:
            raise ValueError("State timers must be 1-dimensional")
        if self.state_matrix is not None and len(state_timers) != self.num_states:
            raise ValueError("State timers must have same length as number of states")
            
        self.state_timers = state_timers.astype(np.float64)
        
    def set_state_outputs(self, state_outputs: np.ndarray) -> None:
        """
        Set the state outputs for the state machine.
        
        State outputs define which outputs should be turned on, off, or left unchanged
        when entering each state. When a state is entered, only outputs with explicit
        on (1) or off (0) values will change; outputs with -1 (no change) will maintain
        their current state. All outputs are initialized to False (off) when this method
        is called.
        
        Args:
            state_outputs: 2D NumPy array where each row contains output values for a state.
                          Values: 0 (off), 1 (on), -1 (no change)
        
        Raises:
            RuntimeError: If state machine is currently processing events
            TypeError: If state_outputs is not a NumPy array
            ValueError: If state_outputs is not 2D, has mismatched rows with state matrix,
                       or contains values other than -1, 0, or 1
        """
        if self.is_processing:
            raise RuntimeError("Cannot modify state outputs while state machine is processing events")
            
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
        
    def set_integer_outputs(self, integer_outputs: np.ndarray) -> None:
        """
        Set the state integer outputs for the state machine.
        
        Integer outputs are emitted via the integerOutput signal when entering
        a state. This can be used to trigger external actions with parameters
        (e.g., selecting which sound to play, controlling external devices).
        
        The interpretation of integer values is defined by the module connected
        to the integerOutput signal. By convention, 0 typically means "no action"
        and non-zero values trigger specific actions.
        
        Args:
            integer_outputs: 1D NumPy array of integer values for each state.
                           A value of 0 means no integer output signal is emitted.
        
        Raises:
            RuntimeError: If state machine is processing events
            TypeError: If integer_outputs is not a NumPy array
            ValueError: If integer_outputs dimension or size is invalid
        """
        if self.is_processing:
            raise RuntimeError("Cannot modify integer outputs while state machine is processing events")
            
        # Validate that input is a NumPy array
        if not isinstance(integer_outputs, np.ndarray):
            raise TypeError("integer_outputs must be a NumPy array")
            
        if integer_outputs.ndim != 1:
            raise ValueError("Integer outputs must be 1-dimensional")
        if self.state_matrix is not None and len(integer_outputs) != self.num_states:
            raise ValueError("Integer outputs must have same length as number of states")
            
        self.integer_outputs = integer_outputs.astype(np.int32)
        
    def set_extra_timers(self, extra_timers_durations: np.ndarray, 
                        extra_timers_triggers: np.ndarray) -> None:
        """
        Set the extra timers for the state machine.
        
        Extra timers are independent timers that can be triggered by specific states
        and continue running across state transitions (unlike state timers which reset
        on each state entry). When an extra timer expires, it generates an event that
        can cause state transitions.
        
        Each extra timer can only be triggered by one specific state. When that state
        is entered, the timer starts. The timer continues running even after leaving
        that state, and when it expires, it generates an event based on its position
        in the events dictionary (after the standard input events and state timer event).
        
        Args:
            extra_timers_durations: 1D NumPy array of timer durations in seconds.
            extra_timers_triggers: 1D NumPy array of state indices that trigger each timer.
        
        Raises:
            RuntimeError: If state machine is processing events
            TypeError: If inputs are not NumPy arrays
            ValueError: If arrays are not 1D, have different lengths, or contain invalid values
        
        Example:
            >>> # Two extra timers: timer1 triggered by state 2, timer2 by state 3
            >>> sm.set_extra_timers(
            ...     extra_timers_durations=np.array([5.0, 10.0]),
            ...     extra_timers_triggers=np.array([2, 3])
            ... )
        """
        if self.is_processing:
            raise RuntimeError("Cannot modify extra timers while state machine is processing events")
            
        # Validate that inputs are NumPy arrays
        if not isinstance(extra_timers_durations, np.ndarray):
            raise TypeError("extra_timers_durations must be a NumPy array")
        if not isinstance(extra_timers_triggers, np.ndarray):
            raise TypeError("extra_timers_triggers must be a NumPy array")
            
        # Validate dimensions
        if extra_timers_durations.ndim != 1:
            raise ValueError("Extra timers durations must be 1-dimensional")
        if extra_timers_triggers.ndim != 1:
            raise ValueError("Extra timers triggers must be 1-dimensional")
            
        # Validate matching lengths
        if len(extra_timers_durations) != len(extra_timers_triggers):
            raise ValueError("Extra timers durations and triggers must have the same length")
            
        # Store with proper dtypes
        self.extra_timers_durations = extra_timers_durations.astype(np.float64)
        self.extra_timers_triggers = extra_timers_triggers.astype(np.int32)
        self.num_extra_timers = len(extra_timers_durations)
        
        # Validate trigger state indices
        if self.state_matrix is not None:
            # if np.any(self.extra_timers_triggers < 0) or np.any(self.extra_timers_triggers >= self.num_states):
            if np.any(self.extra_timers_triggers >= self.num_states):
                raise ValueError(f"Extra timer triggers contain invalid state indices. Must be 0 to {self.num_states-1}")
        
        # Create QTimer objects for each extra timer
        self._create_extra_timer_objects()
    
    def _create_extra_timer_objects(self) -> None:
        """
        Create QTimer objects for each extra timer.
        
        This internal method creates one QTimer per extra timer and connects
        each to its corresponding expiration handler. All timers are single-shot.
        """
        # Stop and delete any existing extra timers
        for timer in self.extra_timers:
            timer.stop()
            timer.deleteLater()
        self.extra_timers = []
        
        # Create new timer objects
        for i in range(self.num_extra_timers):
            timer = QtCore.QTimer()
            timer.setSingleShot(True)
            # Use lambda with default argument to capture current index
            timer.timeout.connect(lambda idx=i: self._on_extra_timer_expired(idx))
            self.extra_timers.append(timer)
    
    def reset(self) -> None:
        """
        Reset the state machine to empty state.
        
        This clears all configuration (state matrix, outputs, timers) and stops
        the state machine if it's active.
        """
        # Stop the state machine if active
        if self.is_active:
            self.stop()
            
        # Reset all configuration
        self.state_matrix = None
        self.state_outputs = None
        self.state_timers = None
        self.integer_outputs = None
        self.timer_event_index = None
        
        # Reset extra timers
        for timer in self.extra_timers:
            timer.stop()
            timer.deleteLater()
        self.extra_timers = []
        self.extra_timers_durations = None
        self.extra_timers_triggers = None
        self.num_extra_timers = 0
        
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
        
    def start(self) -> None:
        """
        Start the state machine.
        
        The state machine always starts in state 0 (typically the END/waiting state),
        which is the standard initialization pattern. Use force_state() to transition
        to the first behavioral state after starting.
            
        Raises:
            RuntimeError: If state machine is not fully configured
        """
        if not self.is_configured():
            raise RuntimeError("State machine must be configured before starting. "
                             "Use set_state_matrix() and set_state_outputs() first.")
            
        self.is_active = True
        self.is_processing = True
        # Always start at state 0 (END/waiting state)
        self.current_state = 0
        
    def stop(self) -> None:
        """
        Stop the state machine.
        
        Stops the state machine from processing events and cancels any active state timer
        and all extra timers. The current state and output values are preserved and can
        be inspected after stopping. The state machine can be restarted with start().
        """
        self.is_active = False
        self.is_processing = False  # Reset to default (not processing when stopped)
        self.suspended_events.clear()
        self.state_timer.stop()
        # Stop all extra timers
        for timer in self.extra_timers:
            timer.stop()
            
    def pause(self) -> None:
        """
        Suspend event processing while continuing to log events.
        
        When processing is suspended, the state machine continues to log events (via 
        eventProcessed signal) with accurate timestamps, but defers state transitions. 
        Events are stored and will be processed in order when resume() is called.
        
        Useful for temporarily suspending state transitions while maintaining event logging,
        such as during trial preparation in behavioral experiments.
        
        Raises:
            RuntimeError: If state machine is not active
            
        Note:
            State and extra timers continue running during suspension. If a timer expires 
            while suspended, it will be queued like any other event.
        """
        if not self.is_active:
            raise RuntimeError("Cannot pause: state machine is not active")
        self.is_processing = False
        
    def resume(self, process_queued: bool = True) -> None:
        """
        Resume event processing after suspension.
        
        Args:
            process_queued: If True (default), process all events that occurred during
                          suspension in the order they occurred. If False, discard queued events.
        
        Raises:
            RuntimeError: If state machine is not active or already processing
        """
        if not self.is_active:
            raise RuntimeError("Cannot resume: state machine is not active")
        if self.is_processing:
            raise RuntimeError("Cannot resume: state machine is already processing events")
            
        self.is_processing = True
        
        if process_queued:
            # Process all queued events in order
            for event_idx, original_timestamp in self.suspended_events:
                # Process the event with its original timestamp preserved
                self._process_event(event_idx, original_timestamp)
        
        self.suspended_events.clear()
                   
    def process_input(self, input_event: int) -> None:
        """
        Process an input event and potentially transition to a new state.
        
        Looks up the next state from the state matrix based on the current state
        and input event, then transitions to that state if it's different from
        the current state. If the state machine is not active, this method
        returns immediately without doing anything.
        
        If event processing is suspended, the event is logged with its timestamp
        and queued for processing when resume() is called.
        
        Args:
            input_event: Input event index
        
        Raises:
            RuntimeError: If state machine is not configured
            ValueError: If input_event index is invalid
        
        Note:
            This method is a no-op if the state machine is not active (i.e., 
            before start() is called or after stop() is called).
        """
        if not self.is_active:
            return
            
        if not self.is_configured():
            raise RuntimeError("State machine is not configured")
            
        if not (0 <= input_event < self.num_inputs):
            raise ValueError(f"Invalid input index: {input_event}")
            
        if self.debug:
            print(f"{PREFIX} Processing input event {input_event} in state {self.current_state}")
        
        # If processing is suspended, queue the event for later processing
        if not self.is_processing:
            timestamp = time.time()
            self.suspended_events.append((input_event, timestamp))
            # Still emit signal so event is logged
            next_state = self.state_matrix[self.current_state, input_event]
            self.eventProcessed.emit(input_event, timestamp, next_state)
            if self.debug:
                print(f"{PREFIX} Event {input_event} queued during suspension (would go to state {next_state})")
            return
            
        # Delegate to unified event processing method
        self._process_event(input_event)
            
    def connect_input_signal(self, signal: QtCore.pyqtSignal, input_event: int) -> None:
        """
        Connect a PyQt signal to an input event.
        
        When the connected signal is emitted, the specified input event will be
        automatically processed. The connection persists until the signal or
        state machine is destroyed. This method does not validate the input_event
        index; validation occurs when the signal is actually emitted.
        
        Args:
            signal: PyQt signal to connect
            input_event: Input event index to trigger when signal is emitted
        
        Note:
            Multiple signals can be connected to the same input event, and one
            signal can trigger multiple input events by calling this method
            multiple times with different input_event values.
        """
        signal.connect(lambda: self.process_input(input_event))
        
    def get_current_state(self) -> int:
        """
        Get current state index.
        
        Returns:
            Index of the state the machine is currently in.
        """
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
        
    def set_state_timer(self, state: int, duration: float) -> None:
        """
        Set the timer duration for a state.
        
        Updates the timer duration for a specific state. If the state machine is
        currently in the specified state and running, the timer will be restarted
        with the new duration.
        
        Args:
            state: State index
            duration: Timer duration in seconds
        
        Raises:
            RuntimeError: If state machine is not configured
            ValueError: If state index is invalid
        
        Note:
            If currently in the specified state, the timer is automatically restarted
            with the new duration. Use float('inf') for no timeout.
        """
        if not self.is_configured():
            raise RuntimeError("State machine is not configured")
            
        if not (0 <= state < self.num_states):
            raise ValueError(f"Invalid state index: {state}")
            
        self.state_timers[state] = duration
        
        # If we're currently in this state, restart the timer
        if state == self.current_state and self.is_active:
            self._start_state_timer()
            
    def force_state(self, state_index: int) -> None:
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
            raise RuntimeError("State machine is not configured")
            
        # Handle -1 as last state
        if state_index == -1:
            state_index = self.num_states - 1
            
        if not (0 <= state_index < self.num_states):
            raise ValueError(f"Invalid state index: {state_index}")
            
        # Only transition if we're active and it's a different state
        if self.is_active and state_index != self.current_state:
            # Emit eventProcessed signal for forced transitions with event ID -1
            timestamp = time.time()
            self.eventProcessed.emit(-1, timestamp, state_index)
            self._enter_state(state_index)

    def force_output(self, output: int, value: bool) -> None:
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
            raise RuntimeError("State machine is not configured")
            
        if not (0 <= output < self.num_outputs):
            raise ValueError(f"Invalid output index: {output}")
            
        # Only change and emit signal if the value is actually different
        if self.output_states[output] != value:
            self.output_states[output] = value
            self.outputChanged.emit(output, value)

    def _enter_state(self, state_index: int) -> None:
        """
        Enter a new state, handling outputs and timers.
        
        Args:
            state_index: Index of state to enter
        """
        if not (0 <= state_index < self.num_states):
            raise ValueError(f"Invalid state index: {state_index}")
            
        self.current_state = state_index
        
        # Stop current state timer
        self.state_timer.stop()
         
        # Process outputs for new state
        self._process_state_outputs()

        # Process integer output for new state
        self._process_integer_outputs()        

        # Start new state timer
        self._start_state_timer()
        
        # Start any extra timers triggered by this state
        self._start_extra_timers_for_state(state_index)
        
        # Emit state change signal
        self.stateChanged.emit(self.current_state)
        
    def _process_state_outputs(self) -> None:
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
            
    def _process_integer_outputs(self) -> None:
        """
        Process integer output for the current state.
        
        Emits the integerOutput signal with the value for the current state,
        unless the value is 0 (which means no signal is emitted).
        """
        if self.integer_outputs is None:
            return
        iout = self.integer_outputs[self.current_state]
        # Emit signal for all non-zero values
        if iout != 0:
            self.integerOutput.emit(iout)
            
    def _start_state_timer(self) -> None:
        """Start the timer for the current state."""
        if self.state_timers is None:
            return
        timer_duration = self.state_timers[self.current_state]
        if timer_duration != float('inf') and timer_duration >= 0:
            self.state_timer.start(round(timer_duration * 1000))  # Convert to milliseconds
            
    def _on_state_timer_expired(self) -> None:
        """Handle state timer expiration as a special input event."""
        if not self.is_active or not self.is_configured():
            return
        
        # If processing is suspended, queue the timer event just like input events
        if not self.is_processing:
            timestamp = time.time()
            self.suspended_events.append((self.timer_event_index, timestamp))
            # Still emit signal so event is logged
            next_state = self.state_matrix[self.current_state, self.timer_event_index]
            self.eventProcessed.emit(self.timer_event_index, timestamp, next_state)
            if self.debug:
                print(f"{PREFIX} State timer event queued during suspension (would go to state {next_state})")
            return
            
        # Delegate to unified event processing method using timer event index
        self._process_event(self.timer_event_index)
        
    def _start_extra_timers_for_state(self, state_index: int) -> None:
        """
        Start any extra timers that are triggered by the given state.
        
        Args:
            state_index: State that was just entered
        """
        if self.extra_timers_triggers is None:
            return
            
        # Find which extra timers are triggered by this state
        for timer_idx in range(self.num_extra_timers):
            if self.extra_timers_triggers[timer_idx] == state_index:
                duration = self.extra_timers_durations[timer_idx]
                if duration >= 0 and duration != float('inf'):
                    # Start this extra timer
                    self.extra_timers[timer_idx].start(round(duration * 1000))
                    if self.debug:
                        print(f"{PREFIX} Started extra timer {timer_idx} with duration {duration}s")
                        
    def _on_extra_timer_expired(self, timer_idx: int) -> None:
        """
        Handle extra timer expiration.
        
        When an extra timer expires, it generates an event whose index is calculated
        based on the timer's position: n_input_events + timer_idx. This follows the
        convention from statematrix where extra timer events come after all input
        events and the state timer event.
        
        Args:
            timer_idx: Index of the extra timer that expired
        """
        if not self.is_active or not self.is_configured():
            return
            
        # Calculate the event index for this extra timer
        # Extra timer events come after all regular input events (including state timer)
        # In statematrix: n_input_events includes input events + 'Tup'
        # So extra timer i has event index: n_input_events + i
        # Since timer_event_index points to 'Tup', and extra timers come after:
        extra_timer_event_index = self.timer_event_index + 1 + timer_idx
        
        if self.debug:
            print(f"{PREFIX} Extra timer {timer_idx} expired, processing event {extra_timer_event_index}")
        
        # If processing is suspended, queue the extra timer event just like other events
        if not self.is_processing:
            timestamp = time.time()
            self.suspended_events.append((extra_timer_event_index, timestamp))
            # Still emit signal so event is logged
            next_state = self.state_matrix[self.current_state, extra_timer_event_index]
            self.eventProcessed.emit(extra_timer_event_index, timestamp, next_state)
            if self.debug:
                print(f"{PREFIX} Extra timer {timer_idx} event queued during suspension (would go to state {next_state})")
            return
            
        # Process this as an event
        self._process_event(extra_timer_event_index)
        
    def _process_event(self, event_index: int, timestamp: Optional[float] = None) -> None:
        """
        Unified method to process any event (input or timer) and potentially transition to a new state.
        
        This method handles the common logic for all event types:
        - Records timestamp
        - Looks up next state from state matrix
        - Emits eventProcessed signal
        - Transitions to new state if different
        
        Args:
            event_index: Index of the event (input or timer) being processed
            timestamp: Optional timestamp to use (for replaying queued events). If None,
                      uses current time.
        """
        # Record the timestamp when event is processed (or use provided timestamp)
        if timestamp is None:
            timestamp = time.time()
        
        # Get next state from state matrix
        next_state = self.state_matrix[self.current_state, event_index]
        
        # Emit signal for event processing (regardless of whether state changes)
        self.eventProcessed.emit(event_index, timestamp, next_state)
        
        # Transition to next state if it's different
        if next_state != self.current_state:
            self._enter_state(next_state)
            
    def _on_force_state_transition(self, state_index: int) -> None:
        """Handle forced state transition via signal."""
        if not self.is_configured():
            return
            
        if not (0 <= state_index < self.num_states):
            return  # Silently ignore invalid states when called via signal
            
        if self.is_active and state_index != self.current_state:
            self._enter_state(state_index)
        
    def get_state_info(self) -> Dict[str, Any]:
        """
        Get comprehensive information about the current state machine.
        
        Returns:
            Dictionary with state machine information containing:
                - 'current_state' (int): Index of the current state
                - 'is_active' (bool): Whether the state machine is active
                - 'is_processing' (bool): Whether events are being processed
                - 'is_configured' (bool): Whether the state machine is fully configured
                - 'num_states' (int): Total number of states
                - 'num_inputs' (int): Total number of input events
                - 'num_outputs' (int): Total number of outputs
                - 'output_states' (list): Current state of each output (True=on, False=off)
                - 'state_timers' (np.ndarray or None): Copy of state timers array, or None if not set
        """
        return {
            'current_state': self.current_state,
            'is_active': self.is_active,
            'is_processing': self.is_processing,
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
            ValueError: If state index is invalid
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
            ValueError: If input_event index is invalid
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
            f"Active: {self.is_active}, Processing: {self.is_processing}",
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

