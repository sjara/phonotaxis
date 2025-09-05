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
import datetime
from typing import List, Dict, Optional, Any, Union, Callable
from PyQt6 import QtCore, QtWidgets, QtGui
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

N_INPUTS = 3
N_OUTPUTS = 2

class SessionController(QtCore.QObject):
    """
    Controller for behavioral session management.
    
    Provides a single point of control for trial-based behavioral experiments,
    combining business logic with state machine coordination. Handles trial
    management, event logging, timing, data persistence, and GUI communication.
    
    This combines what was previously split between SessionModel and SessionController
    into a single, simpler class that's easier to understand and debug.
    
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
    status_update = QtCore.pyqtSignal(float, int, int, int)  # time, state, events, trial
    prepare_next_trial = QtCore.pyqtSignal(int)  # next trial number
    log_message = QtCore.pyqtSignal(str)  # log message
    session_started = QtCore.pyqtSignal()  # session started successfully
    session_stopped = QtCore.pyqtSignal()  # session stopped (manual or due to duration)
    
    def __init__(self, 
                 parent: Optional[QtCore.QObject] = None,
                 polling_interval: float = DEFAULT_POLLING_INTERVAL,
                 create_gui: bool = True,
                 session_duration: Optional[float] = None) -> None:
        """
        Initialize the session controller.
        
        Args:
            parent: Parent QObject
            polling_interval: Status update interval (seconds)
            create_gui: Whether to create GUI
            session_duration: Maximum session duration in seconds (None for unlimited)
        """
        super().__init__(parent)
        
        # Configuration
        self.polling_interval = polling_interval
        self.session_duration = session_duration
        
        # Trial structure
        self.prepare_next_trial_states: List[int] = [] # [DEFAULT_PREPARE_NEXT_STATE]
        self.preparing_next_trial = False
        
        # Session state
        self.is_running = False
        self.start_time = 0.0
        self.current_time = 0.0
        self.current_state = 0
        self.event_count = 0
        self.current_trial = -1  # First trial will be 0
        
        # Event data storage
        self.events_log: List[List[Union[float, int]]] = []
        self.trial_end_indices: List[int] = []
        self.timestamps: List[float] = []
        self.events: List[int] = []
        self.next_states: List[int] = []
        self.trials: List[int] = []
        
        # State machine
        self.state_machine = StateMachine()
        self.state_matrix = StateMatrix(inputs=[], outputs=[])
        self.set_state_matrix(self.state_matrix)
        
        # Connect state machine signals
        self.state_machine.stateChanged.connect(self._on_state_changed)
        self.state_machine.eventProcessed.connect(self._on_event_processed)
        
        # Timer for status updates
        self.timer_tick = QtCore.QTimer(self)
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
        """
        try:
            self.state_matrix = state_matrix
            self.prepare_next_trial_states = [state_matrix.get_end_state_index()]

            # Update state machine
            self.state_machine.set_state_matrix(state_matrix.get_matrix(),
                                                state_matrix.get_timer_event_index())
            self.state_machine.set_state_timers(state_matrix.get_state_timers())
            self.state_machine.set_state_outputs(state_matrix.get_outputs())
            self.state_machine.set_integer_outputs(state_matrix.get_integer_outputs())
            
            self.log_message.emit('State matrix updated successfully')
            
        except Exception as e:
            self.log_message.emit(f'Error setting state matrix: {str(e)}')
            raise
            
    def set_session_duration(self, duration: Optional[float]) -> None:
        """
        Set the session duration.
        
        Args:
            duration: Maximum session duration in seconds (None for unlimited)
        """
        self.session_duration = duration
        if duration is not None:
            self.log_message.emit(f'Session duration set to {duration} seconds')
        else:
            self.log_message.emit('Session duration set to unlimited')
            
    def start(self) -> None:
        """Start the session (single point of control)."""
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
            
            # Prepare first trial
            #self.ready_to_start_trial()
            self.prepare_next_trial.emit(self.current_trial + 1)

            # Start state machine
            #self.state_machine.start()
            # State will be set to first user state (1) in ready_to_start_trial()

            self.log_message.emit('Session started')
            self._emit_status_update()
            
            # Notify application and GUI
            self.session_started.emit()  # For application initialization
            
        except Exception as e:
            self.log_message.emit(f'Error starting session: {str(e)}')
            raise
            
    def stop(self) -> None:
        """Stop the session (single point of control)."""
        try:
            # Stop timer
            self.timer_tick.stop()
            
            # Stop state machine
            self.state_machine.force_state(0)  # END state (always state 0)
            self.state_machine.stop()
            
            # Update session state
            self.is_running = False
            
            self.log_message.emit('Session stopped')
            self._emit_status_update()
            
            # Notify application and GUI
            self.session_stopped.emit()  # For application cleanup
            
        except Exception as e:
            self.log_message.emit(f'Error stopping session: {str(e)}')
            raise
            
    def ready_to_start_trial(self) -> None:
        """Signal that next trial is ready to start."""
        if self.is_running:
            self.current_trial += 1
            self.preparing_next_trial = False
            if len(self.state_matrix.states) > 1:
                self.state_machine.start()
                self.state_machine.force_state(1)  # Go to first user state
                self.log_message.emit(f'Started trial {self.current_trial}')
                self._emit_status_update()
            
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
            self.state_machine.stop()
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
        
        # Update event log
        self.events_log.append([relative_time, event_index, next_state])
        self.event_count += 1
        
        # Update event lists
        self.timestamps.append(relative_time)
        self.events.append(event_index)
        self.next_states.append(next_state)
        self.trials.append(self.current_trial)
        
        self._emit_status_update()
        
    def _on_timer_tick(self) -> None:
        """Handle status timer - update current time and emit status."""
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
        """Emit status update signal for GUI."""
        self.status_update.emit(
            self.current_time,
            self.current_state,
            self.event_count,
            self.current_trial
        )
        
    def get_events(self, use_names=False) -> pd.DataFrame:
        """
        Return DataFrame with all events.
        
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
        
    def _add_event_str_columns(self, dframe):
        evdict = self.state_matrix.events_dict.inverse
        stdict = self.state_matrix.get_states_dict().inverse
        evstr = [evdict[ev] for ev in self.events]
        ststr = [stdict[st] for st in self.next_states]
        dframe['events_str'] = evstr
        dframe['next_state_str'] = ststr
        return dframe

    def get_events_one_trial(self, trial_id: int) -> np.ndarray:
        """
        Get events for specific trial.
        
        Args:
            trial_id: Trial number
            
        Returns:
            NumPy array with trial events
        """
        if trial_id < 0 or trial_id >= len(self.trial_end_indices):
            return np.empty((0, 3), dtype=float)
            
        end_idx = self.trial_end_indices[trial_id]
        start_idx = self.trial_end_indices[trial_id - 1] + 1 if trial_id > 0 else 0
        
        trial_events = self.events_log[start_idx:end_idx + 1]
        return np.array(trial_events, dtype=float)
        
    # def get_current_status(self) -> Dict[str, Any]:
    #     """
    #     Get comprehensive status information.
        
    #     Returns:
    #         Dictionary with current session status
    #     """
    #     return {
    #         'is_running': self.is_running,
    #         'server_time': self.current_time,
    #         'current_state': self.current_state,
    #         'current_trial': self.current_trial,
    #         'event_count': self.event_count,
    #         'preparing_next_trial': self.preparing_next_trial,
    #         'n_completed_trials': len(self.trial_end_indices)
    #     }

    def append_to_file(self, h5file: Any, current_trial: Optional[int] = None) -> Any:
        """
        Save session data to HDF5 file.
        
        Args:
            h5file: Open HDF5 file handle
            current_trial: Current trial number (ignored for compatibility)
            
        Returns:
            HDF5 group with events data
        """
        
        # if not self.trial_end_indices:
        if self.current_trial < 1:
            raise UserWarning('No completed trials found. No events were saved.')
            
        try:
            events_group = h5file.create_group('/events')
            events_df = self.get_events()
            for colname, vals in events_df.items():
                events_group.create_dataset(colname, data=np.array(vals))
            # if self.events_log:
            #     events_array = np.array(self.events_log, dtype=float)
            #     events_group.create_dataset('eventTime', data=events_array[:, 0])
            #     events_group.create_dataset('eventCode', data=events_array[:, 1])
            #     events_group.create_dataset('nextState', data=events_array[:, 2])
            # else:
            #     events_group.create_dataset('eventTime', data=np.array([], dtype=float))
            #     events_group.create_dataset('eventCode', data=np.array([], dtype=int))
            #     events_group.create_dataset('nextState', data=np.array([], dtype=int))
                
            # events_group.create_dataset('indexLastEventEachTrial', 
            #                           data=np.array(self.trial_end_indices, dtype=int))
            return events_group
            
        except Exception as e:
            raise RuntimeError(f'Error saving events to file: {str(e)}')
            
    def cleanup(self) -> None:
        """Clean up resources."""
        try:
            self.stop()
            if self.state_machine:
                # Reset outputs to safe state
                for output_idx in range(self.state_machine.num_outputs):
                    self.state_machine.force_output(output_idx, False)
                    
            self.log_message.emit('Session cleanup completed')
            
        except Exception as e:
            self.log_message.emit(f'Error during cleanup: {str(e)}')


class ControllerGUI(QtWidgets.QGroupBox):
    """
    View component for the session controller (pure GUI).
    
    Provides a clean user interface for manual session control and real-time
    status display. Contains no business logic - only UI presentation and
    user interaction capture.
    
    All business logic is handled by the SessionController.
    """
    
    def __init__(self, 
                 parent: Optional[QtWidgets.QWidget] = None,
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
        
        # Display formats
        self._time_format = 'Time: {:.1f} s'
        self._state_format = 'State: [{}] {}'
        self._event_format = 'Events: {}'
        self._trial_format = 'Trial: {}'
        
        self._setup_ui(min_width)
        self._connect_signals()
        self._update_display(0.0, 0, 0, -1)  # Initial state
        
    def _setup_ui(self, min_width: int) -> None:
        """Create and layout the user interface elements."""
        self.setTitle('Session control')
        self.setMinimumWidth(min_width)
        
        # Status labels
        self.time_label = QtWidgets.QLabel()
        self.state_label = QtWidgets.QLabel()
        self.event_count_label = QtWidgets.QLabel()
        self.trial_label = QtWidgets.QLabel()
        
        # Set fixed widths for consistent layout
        label_fixed_width = 120
        self.time_label.setFixedWidth(label_fixed_width)
        self.state_label.setFixedWidth(label_fixed_width)
        self.event_count_label.setFixedWidth(label_fixed_width)
        self.trial_label.setFixedWidth(label_fixed_width)
        
        # Left-align all labels
        alignment = QtCore.Qt.AlignmentFlag.AlignLeft
        self.time_label.setAlignment(alignment)
        self.state_label.setAlignment(alignment)
        self.event_count_label.setAlignment(alignment)
        self.trial_label.setAlignment(alignment)
        
        # Control button
        self.start_stop_button = QtWidgets.QPushButton('')
        self.start_stop_button.setCheckable(False)
        self.start_stop_button.setMinimumHeight(80)
        
        # Style the button
        button_font = QtGui.QFont()
        button_font.setPointSize(12)
        button_font.setBold(True)
        self.start_stop_button.setFont(button_font)
        
        # Layout
        layout = QtWidgets.QGridLayout()
        layout.addWidget(self.time_label, 0, 0)
        layout.addWidget(self.state_label, 1, 1)
        layout.addWidget(self.event_count_label, 0, 1)
        layout.addWidget(self.trial_label, 1, 0)
        layout.addWidget(self.start_stop_button, 2, 0, 1, 2)  # Span 2 columns
        
        self.setLayout(layout)
        
        # Initialize to stopped state
        self._set_stopped_appearance()
        
    def _connect_signals(self) -> None:
        """Connect signals between GUI and controller."""
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
        """Handle start/stop button clicks."""
        if not self.controller:
            return
            
        if self.is_running:
            self.controller.stop()
        else:
            self.controller.start()
            
    def _set_running_appearance(self) -> None:
        """Set GUI appearance for running state."""
        self.start_stop_button.setText('STOP')
        self.start_stop_button.setStyleSheet(
            f'QPushButton {{ background-color: {BUTTON_COLORS["stop"]}; '
            f'color: white; border: 2px solid #333; border-radius: 5px; }}'
        )
        self.is_running = True
        
    def _set_stopped_appearance(self) -> None:
        """Set GUI appearance for stopped state."""
        self.start_stop_button.setText('START')
        self.start_stop_button.setStyleSheet(
            f'QPushButton {{ background-color: {BUTTON_COLORS["start"]}; '
            f'color: white; border: 2px solid #333; border-radius: 5px; }}'
        )
        self.is_running = False
        
    @QtCore.pyqtSlot(float, int, int, int)
    def _update_display(self, 
                       server_time: float, 
                       current_state: int, 
                       event_count: int, 
                       current_trial: int) -> None:
        """
        Update the status display.
        
        Args:
            server_time: Current time from session
            current_state: Current state index
            event_count: Total number of events
            current_trial: Current trial number
        """
        self.time_label.setText(self._time_format.format(server_time))
        
        # Get state name from state matrix if available
        state_name = '--'
        if (self.controller and self.controller.state_matrix and 
            current_state in self.controller.state_matrix.states.inverse):
            state_name = self.controller.state_matrix.states.inverse[current_state]
            
        self.state_label.setText(self._state_format.format(current_state, state_name))
        self.event_count_label.setText(self._event_format.format(event_count))
        
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