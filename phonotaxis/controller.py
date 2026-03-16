"""
Controller for behavioral paradigms with simplified architecture.

This module provides a streamlined architecture for behavioral experiments
with state machines, separating GUI from business logic:

- SessionController: Combined business logic and coordination (single control point)
- ControllerGUI: Pure view layer for user interface

This design ensures:
- Single point of control for start/stop operations (eliminates race conditions)
- Clean separation between business logic and GUI
- Simplified, maintainable code
- Still testable (controller can be used without GUI)
"""

import time
import numpy as np
import pandas as pd
from typing import List, Optional, Any, Union, Callable
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, Qt
from PyQt6.QtWidgets import QWidget, QGroupBox, QLabel, QPushButton, QGridLayout
from PyQt6.QtGui import QFont
from phonotaxis.statemachine import StateMachine
from phonotaxis.statematrix import StateMatrix
from phonotaxis import config

# Default values
DEFAULT_POLLING_INTERVAL = 0.1  # Timer interval in seconds

# GUI styling
BUTTON_COLORS = {
    'start': '#32CD32',  # LimeGreen
    'stop': '#FF4444'    # Red
}

class SessionController(QObject):
    """
    Controller for behavioral session management.
    
    Provides a single point of control for trial-based behavioral experiments,
    combining business logic with state machine coordination. Handles trial
    management, event logging, timing, data persistence, and GUI communication.
    
    This combines what was previously split between SessionModel and SessionController
    into a single, simpler class that's easier to understand and debug.
    
    Args:
        parent: Parent QObject
        polling_interval: Status update interval (seconds)
        create_gui: Whether to create GUI
        debug: Enable debug output for state machine event processing (default False)
    
    Signals:
        status_update: Emitted when session status changes
                      (time, state, event_count, trial)
        prepare_next_trial: Emitted when ready for next trial
                           (next_trial_number)  
        log_message: Emitted for user notifications
                    (message_string)
        session_started: Emitted when session starts successfully
        session_stopped: Emitted when session stops (manually or due to duration)
    """
    
    # Signals for GUI communication
    status_update = pyqtSignal(float, int, int, int)  # time, state, events, trial
    prepare_next_trial = pyqtSignal(int)  # next trial number
    log_message = pyqtSignal(str)  # log message
    session_started = pyqtSignal()  # session started successfully
    session_stopped = pyqtSignal()  # session stopped (manual or due to duration)
    
    def __init__(self, 
                 parent: Optional[QObject] = None,
                 polling_interval: float = DEFAULT_POLLING_INTERVAL,
                 create_gui: bool = True,
                 debug: bool = False) -> None:
        """
        Initialize the session controller.
        
        Args:
            parent: Parent QObject
            polling_interval: Status update interval (seconds)
            create_gui: Whether to create GUI
            debug: Enable debug output for state machine (default False)
        
        Raises:
            ValueError: If polling_interval is not a positive number
        """
        super().__init__(parent)
        
        # Validate parameters
        if not isinstance(polling_interval, (int, float)) or polling_interval <= 0:
            raise ValueError(f'polling_interval must be a positive number, got {polling_interval}')
        
        # Configuration
        self.polling_interval = polling_interval
        self.session_duration = None
        self.debug = debug
        
        # Trial structure
        self.prepare_next_trial_states: List[int] = []
        self.preparing_next_trial = False
        
        # Session state
        self.is_running = False
        self.start_time = 0.0
        self.current_time = 0.0
        self.current_state = 0
        self.event_count = 0
        self.current_trial = -1  # First trial will be 0
        
        # Event data storage
        self.timestamps: List[float] = []
        self.events: List[int] = []
        self.next_states: List[int] = []
        self.trials: List[int] = []
        
        # State machine
        self.state_machine = StateMachine(debug=self.debug)
        self.state_matrix = StateMatrix(inputs=[], outputs=[])
        self.set_state_matrix(self.state_matrix)
        
        # Connect state machine signals
        self.state_machine.stateChanged.connect(self._on_state_changed)
        self.state_machine.eventProcessed.connect(self._on_event_processed)
        
        # Timer for status updates
        self.timer_tick = QTimer(self)
        self.timer_tick.timeout.connect(self._on_timer_tick)
        
        # Create GUI if requested
        self.gui: Optional[ControllerGUI] = None
        if create_gui:
            self.gui = ControllerGUI(controller=self)
            
    def set_state_matrix(self, state_matrix: StateMatrix) -> None:
        """
        Set the state matrix for the session.
        
        Args:
            state_matrix: StateMatrix object with complete state machine definition
        
        Raises:
            TypeError: If state_matrix is not a StateMatrix instance
        """
        if not isinstance(state_matrix, StateMatrix):
            raise TypeError(f'Expected StateMatrix instance, got {type(state_matrix).__name__}')
            
        try:
            self.state_matrix = state_matrix
            self.prepare_next_trial_states = [state_matrix.get_end_state_index()]

            # Update state machine
            self.state_machine.set_state_matrix(state_matrix.get_matrix(),
                                                state_matrix.get_timer_event_index())
            self.state_machine.set_state_timers(state_matrix.get_state_timers())
            self.state_machine.set_state_outputs(state_matrix.get_outputs())
            self.state_machine.set_integer_outputs(state_matrix.get_integer_outputs())
            
            # Set extra timers if any are defined
            extra_timers_durations = state_matrix.get_extra_timers()
            extra_timers_triggers = state_matrix.get_extra_triggers()
            if len(extra_timers_durations) > 0:
                self.state_machine.set_extra_timers(extra_timers_durations, extra_timers_triggers)
            
            self.log_message.emit('State matrix updated successfully')
            
        except Exception as e:
            self.log_message.emit(f'Error setting state matrix: {str(e)}')
            raise
            
    def set_session_duration(self, duration: Optional[float]) -> None:
        """
        Set the session duration.
        
        Args:
            duration: Maximum session duration in seconds (None for unlimited)
        
        Raises:
            ValueError: If duration is not None and not a positive number
        """
        if duration is not None:
            if not isinstance(duration, (int, float)) or duration <= 0:
                raise ValueError(f'session_duration must be None or a positive number, got {duration}')
        
        self.session_duration = duration
        if duration is not None:
            self.log_message.emit(f'Session duration set to {duration} seconds')
        else:
            self.log_message.emit('Session duration set to unlimited')
            
    def start(self) -> None:
        """
        Start the session (single point of control).
        
        Initializes time tracking, starts the status update timer, and emits
        prepare_next_trial signal for the paradigm to prepare trial 0.
        The paradigm should call ready_to_start_trial() when preparation is complete.
        
        Note:
            Does nothing if session is already running (logs message).
            
        Raises:
            Exception: Re-raises any exception after logging via log_message signal
        """
        if self.is_running:
            self.log_message.emit('Session already running')
            return
            
        try:
            # Initialize time tracking
            if self.current_time == 0.0:
                self.start_time = time.time()
                
            self.is_running = True
            
            # Start status updates
            timer_interval_ms = int(self.polling_interval * 1000)
            self.timer_tick.start(timer_interval_ms)
            
            # Prepare first trial (paradigm will call ready_to_start_trial when ready)
            self.preparing_next_trial = True
            self.prepare_next_trial.emit(self.current_trial + 1)

            self.log_message.emit('Session started')
            self._emit_status_update()
            
            # Notify application and GUI
            self.session_started.emit()  # For application initialization
            
        except Exception as e:
            self.log_message.emit(f'Error starting session: {str(e)}')
            raise
            
    def stop(self) -> None:
        """
        Stop the session (single point of control).
        
        Stops the status timer, forces state machine to END state, stops the
        state machine, and emits session_stopped signal for cleanup.
        
        Raises:
            Exception: Re-raises any exception after logging via log_message signal
        """
        try:
            # Stop timer
            self.timer_tick.stop()
            
            # Update session state BEFORE forcing state change
            # This prevents _on_state_changed from triggering next trial preparation
            self.is_running = False
            
            # Stop state machine
            end_state_index = self.state_matrix.get_end_state_index()
            self.state_machine.force_state(end_state_index)
            self.state_machine.stop()
            
            self.log_message.emit('Session stopped')
            self._emit_status_update()
            
            # Notify application and GUI
            self.session_stopped.emit()  # For application cleanup
            
        except Exception as e:
            self.log_message.emit(f'Error stopping session: {str(e)}')
            raise
            
    def ready_to_start_trial(self) -> None:
        """
        Signal that next trial is ready to start.
        
        Called by the paradigm/task after preparing the trial in response to
        the prepare_next_trial signal. Increments trial counter, resumes the
        state machine (processing any queued events), and forces transition
        to first user state (state 1).
        
        Note:
            Only proceeds if session is running and preparing_next_trial flag is set.
            This prevents race conditions from multiple calls.
            
            Events that occurred during trial preparation will be processed in the
            order they occurred before transitioning to the first user state.
        """
        if self.is_running and self.preparing_next_trial:
            self.current_trial += 1
            self.preparing_next_trial = False
            if len(self.state_matrix.states) > 1:
                # If the state machine has not yet been started, start it.
                # Otherwise, resume processing of queued events (if suspended).
                try:
                    if not getattr(self.state_machine, 'is_active', False):
                        self.state_machine.start()
                    else:
                        # Only resume if processing is suspended; resume will
                        # process any queued events if present.
                        if not getattr(self.state_machine, 'is_processing', True):
                            self.state_machine.resume(process_queued=True)

                    # Move into first user state for the trial
                    self.state_machine.force_state(1)  # Go to first user state
                    self.log_message.emit(f'Started trial {self.current_trial}')
                    self._emit_status_update()
                except Exception as e:
                    # Log and re-raise to surface any unexpected errors
                    self.log_message.emit(f'Error starting trial {self.current_trial}: {e}')
                    raise
            
    def _on_state_changed(self, new_state: int) -> None:
        """
        Handle state machine state changes.
        
        Args:
            new_state: New state index
        """
        self.current_state = new_state
        
        # Check if we need to prepare next trial
        if (self.current_state in self.prepare_next_trial_states and 
            not self.preparing_next_trial and self.is_running):
            self.state_machine.pause()  # Suspend event processing during trial preparation
            self.preparing_next_trial = True
            self.prepare_next_trial.emit(self.current_trial + 1)
            
        self._emit_status_update()
        
    def _on_event_processed(self, event_index: int, timestamp: float, next_state: int) -> None:
        """
        Handle events from the state machine.
        
        Args:
            event_index: Index of the event that was processed
            timestamp: Timestamp when event was processed
            next_state: State that will be entered
        """
        # Calculate relative time
        relative_time = timestamp - self.start_time if self.start_time > 0 else 0.0
        
        # Update event count and lists
        self.event_count += 1
        self.timestamps.append(relative_time)
        self.events.append(event_index)
        self.next_states.append(next_state)
        self.trials.append(self.current_trial)
        
        self._emit_status_update()
        
    def _on_timer_tick(self) -> None:
        """
        Handle status timer - update current time and emit status.
        
        Called periodically based on polling_interval. Updates current_time
        and checks if session_duration has been reached. If duration limit
        is reached, automatically stops the session.
        """
        if self.is_running and self.start_time > 0:
            self.current_time = time.time() - self.start_time
            # Check if session duration has been reached
            if (self.session_duration is not None and 
                self.current_time >= self.session_duration):
                self.log_message.emit(f'Session completed after {self.session_duration} seconds')
                self.stop()  # Stop the session (will emit session_stopped signal)
                return  # Exit to avoid emitting status twice
            self._emit_status_update()
            
    def _emit_status_update(self) -> None:
        """
        Emit status update signal for GUI.
        
        Emits the status_update signal with current session state including
        time, state index, event count, and trial number.
        """
        self.status_update.emit(
            self.current_time,
            self.current_state,
            self.event_count,
            self.current_trial
        )
        
    def get_events(self, use_names=False) -> pd.DataFrame:
        """
        Return DataFrame with all events.
        
        Args:
            use_names: If True, include string names for events and states
        
        Returns:
            DataFrame with event data
        """
        dframe = pd.DataFrame({
            'timestamp': self.timestamps,
            'event': self.events,
            'next_state': self.next_states,
            'trial': self.trials
        })
        if use_names:
            dframe = self._add_event_str_columns(dframe)
        return dframe
        
    def _add_event_str_columns(self, dframe: pd.DataFrame) -> pd.DataFrame:
        """
        Add string columns for event and state names to DataFrame.
        
        Args:
            dframe: DataFrame with event data
            
        Returns:
            DataFrame with added 'events_str' and 'next_state_str' columns
        """
        evdict = self.state_matrix.events.inverse
        stdict = self.state_matrix.get_states().inverse
        evstr = [evdict[ev] for ev in self.events]
        ststr = [stdict[st] for st in self.next_states]
        dframe['event_str'] = evstr
        dframe['next_state_str'] = ststr
        return dframe

    def get_events_one_trial(self, trial_id: int, use_names: bool = False) -> pd.DataFrame:
        """
        Get events for specific trial.
        
        Args:
            trial_id: Trial number (0-indexed)
            use_names: If True, include string names for events and states
            
        Returns:
            DataFrame containing only events from the specified trial
        """
        dframe = self.get_events(use_names=use_names)
        trial_events = dframe[dframe['trial'] == trial_id]
        return trial_events

    def append_to_file(self, h5file: Any) -> Any:
        """
        Save session data to HDF5 file.
        
        Creates an '/events' group in the HDF5 file and saves all event data
        as separate datasets: 'timestamp' (float), 'event' (int), 'next_state' (int),
        and 'trial' (int).
        
        Args:
            h5file: Open HDF5 file handle (from h5py)
            
        Returns:
            HDF5 group object containing the events datasets
            
        Raises:
            UserWarning: If no trials have been started (current_trial < 0)
            RuntimeError: If there's an error creating the HDF5 group or datasets
        """
        if self.current_trial < 0:
            raise UserWarning('No completed trials found. No events were saved.')
            
        try:
            events_group = h5file.create_group('/events')
            events_df = self.get_events()
            for colname, vals in events_df.items():
                events_group.create_dataset(colname, data=np.array(vals))
            return events_group
            
        except Exception as e:
            raise RuntimeError(f'Error saving events to file: {str(e)}')
            
    def cleanup(self) -> None:
        """
        Clean up resources and reset hardware outputs.
        
        Stops the session and resets all state machine outputs to False (off).
        Should be called before closing the application to ensure hardware
        is in a safe state.
        
        Note:
            Catches and logs any exceptions during cleanup to prevent application
            crashes during shutdown.
        """
        try:
            self.stop()
            if self.state_machine:
                # Reset outputs to safe state
                for output_idx in range(self.state_machine.num_outputs):
                    self.state_machine.force_output(output_idx, False)
                    
            self.log_message.emit('Session cleanup completed')
            
        except Exception as e:
            self.log_message.emit(f'Error during cleanup: {str(e)}')


class ControllerGUI(QGroupBox):
    """
    View component for the session controller (pure GUI).
    
    Provides a clean user interface for manual session control and real-time
    status display. Contains no business logic - only UI presentation and
    user interaction capture.
    
    All business logic is handled by the SessionController.
    """
    
    def __init__(self, 
                 parent: Optional[QWidget] = None,
                 controller: Optional[SessionController] = None,
                 min_width: int = 220) -> None:
        """
        Initialize the controller GUI.
        
        Args:
            parent: Parent widget
            controller: SessionController instance to interact with
            min_width: Minimum width of the GUI widget
        """
        super().__init__(parent)
        
        self.controller = controller
        self.is_running = False
        self.last_event_name = '--'
        
        # Display formats
        self._time_format = 'Time: {:.1f} s'
        self._state_format = 'State: [{}] {}'
        self._event_format = 'Events: {}'
        self._trial_format = 'Trial: {}'
        self._last_event_format = 'Last event: {}'
        
        self._setup_ui(min_width)
        self._connect_signals()
        self._update_display(0.0, 0, 0, -1)  # Initial state
        
    def _setup_ui(self, min_width: int) -> None:
        """
        Create and layout the user interface elements.
        
        Sets up status labels, control button, and grid layout for the
        controller GUI widget.
        
        Args:
            min_width: Minimum width in pixels for the widget
        """
        self.setTitle('Session control')
        self.setMinimumWidth(min_width)
        
        # Status labels
        self.time_label = QLabel()
        self.event_count_label = QLabel()
        self.trial_label = QLabel()
        self.last_event_label = QLabel()
        self.state_label = QLabel()
        
        # Set fixed widths for consistent layout
        label_fixed_width = 120
        self.time_label.setFixedWidth(label_fixed_width)
        self.event_count_label.setFixedWidth(label_fixed_width)
        self.trial_label.setFixedWidth(label_fixed_width)
        self.last_event_label.setFixedWidth(label_fixed_width)
        self.state_label.setFixedWidth(2*label_fixed_width)
        
        # Left-align all labels
        alignment = Qt.AlignmentFlag.AlignLeft
        self.time_label.setAlignment(alignment)
        self.event_count_label.setAlignment(alignment)
        self.trial_label.setAlignment(alignment)
        self.last_event_label.setAlignment(alignment)
        self.state_label.setAlignment(alignment)

        # Control button
        self.start_stop_button = QPushButton('')
        self.start_stop_button.setCheckable(False)
        self.start_stop_button.setMinimumHeight(80)
        
        # Style the button
        button_font = QFont()
        button_font.setPointSize(12)
        button_font.setBold(True)
        self.start_stop_button.setFont(button_font)
        
        # Layout - Three rows of status information
        layout = QGridLayout()
        layout.addWidget(self.time_label, 0, 0)
        layout.addWidget(self.trial_label, 0, 1)
        layout.addWidget(self.last_event_label, 1, 0)
        layout.addWidget(self.event_count_label, 1, 1)
        layout.addWidget(self.state_label, 2, 0, 1, 2)  # Span 2 columns
        layout.addWidget(self.start_stop_button, 3, 0, 1, 2)  # Span 2 columns
        
        self.setLayout(layout)
        
        # Initialize to stopped state
        self._set_stopped_appearance()
        
    def _connect_signals(self) -> None:
        """
        Connect signals between GUI and controller.
        
        Connects button clicks to start/stop handler and connects controller
        signals (status_update, session_started, session_stopped) to GUI
        update methods.
        """
        # Button click
        self.start_stop_button.clicked.connect(self._on_start_stop_clicked)
        
        # Connect to controller if provided
        if self.controller:
            # Connect status updates  
            self.controller.status_update.connect(self._update_display)
            # Connect session state changes to update button appearance
            self.controller.session_started.connect(self._set_running_appearance)
            self.controller.session_stopped.connect(self._set_stopped_appearance)
            
    def _on_start_stop_clicked(self) -> None:
        """
        Handle start/stop button clicks.
        
        Calls controller.stop() if running, controller.start() if stopped.
        Does nothing if no controller is connected.
        """
        if not self.controller:
            return
            
        if self.is_running:
            self.controller.stop()
        else:
            self.controller.start()
            
    def _set_running_appearance(self) -> None:
        """
        Set GUI appearance for running state.
        
        Changes button to red 'STOP' appearance and updates internal state flag.
        """
        self.start_stop_button.setText('STOP')
        self.start_stop_button.setStyleSheet(
            f'QPushButton {{ background-color: {BUTTON_COLORS["stop"]}; '
            f'color: white; border: 2px solid #333; border-radius: 5px; }}'
        )
        self.is_running = True
        
    def _set_stopped_appearance(self) -> None:
        """
        Set GUI appearance for stopped state.
        
        Changes button to green 'START' appearance and updates internal state flag.
        """
        self.start_stop_button.setText('START')
        self.start_stop_button.setStyleSheet(
            f'QPushButton {{ background-color: {BUTTON_COLORS["start"]}; '
            f'color: white; border: 2px solid #333; border-radius: 5px; }}'
        )
        self.is_running = False

    @pyqtSlot(float, int, int, int)
    def _update_display(self, 
                       server_time: float, 
                       current_state: int, 
                       event_count: int, 
                       current_trial: int) -> None:
        """
        Update the status display.
        
        Updates all status labels with current session information including
        time, state (with name if available), event count, last event name,
        and trial number.
        
        Args:
            server_time: Current session time in seconds
            current_state: Current state index
            event_count: Total number of events processed
            current_trial: Current trial number (-1 if no trials started)
        """
        self.time_label.setText(self._time_format.format(server_time))
        
        # Get state name from state matrix if available
        state_name = '--'
        if (self.controller and self.controller.state_matrix and 
            current_state in self.controller.state_matrix.states.inverse):
            state_name = self.controller.state_matrix.states.inverse[current_state]
            
        self.state_label.setText(self._state_format.format(current_state, state_name))
        self.event_count_label.setText(self._event_format.format(event_count))
        
        # Get last event name if available
        if (self.controller and len(self.controller.events) > 0 and 
            self.controller.state_matrix and self.controller.state_matrix.events):
            last_event_idx = self.controller.events[-1]
            if last_event_idx in self.controller.state_matrix.events.inverse:
                self.last_event_name = self.controller.state_matrix.events.inverse[last_event_idx]
            else:
                self.last_event_name = str(last_event_idx)
        else:
            self.last_event_name = '--'
        
        self.last_event_label.setText(self._last_event_format.format(self.last_event_name))
        
        if current_trial >= 0:
            self.trial_label.setText(self._trial_format.format(current_trial))
        else:
            self.trial_label.setText('Trial: --')


if __name__ == '__main__':
    """Example usage of the simplified Session Controller."""
    import sys
    from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget
    
    app = QApplication(sys.argv)
    
    # Create main window
    main_window = QWidget()
    main_window.setWindowTitle('Session Controller Example')
    main_window.resize(300, 200)
    
    # Create session controller with GUI
    controller = SessionController(create_gui=True)
    
    # Layout
    layout = QVBoxLayout()
    layout.addWidget(controller.gui)
    main_window.setLayout(layout)
    
    # Show window
    main_window.show()

    # controller.start()
    
    # Connect cleanup
    app.aboutToQuit.connect(controller.cleanup)
    
    sys.exit(app.exec())