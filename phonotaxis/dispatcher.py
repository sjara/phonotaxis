"""
Dispatcher for behavioral paradigms.

Provides an interface between a trial-structured paradigm and the state
machine. It will for example halt the state machine until the next trial
has been prepared and ready to start.

This module provides:
- Dispatcher: Core logic for trial-based state machine control
- DispatcherGUI: Optional graphical interface for the dispatcher
- Integration with the new StateMachine and StateMatrix classes
"""

import time
import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Any, Union
from PyQt6 import QtCore, QtWidgets, QtGui

from phonotaxis.statemachine import StateMachine
from phonotaxis.statematrix import StateMatrix
from phonotaxis import config

# Default values
DEFAULT_PREPARE_NEXT_STATE = 0  # State to prepare next trial
DEFAULT_POLLING_INTERVAL = 0.1  # Timer interval in seconds

# GUI styling
BUTTON_COLORS = {
    'start': '#32CD32',  # LimeGreen
    'stop': '#FF4444'    # Red
}

N_INPUTS = 3
N_OUTPUTS = 2

class Dispatcher(QtCore.QObject):
    """
    Dispatcher is the trial controller for behavioral experiments.
    
    It provides an interface between a trial-structured paradigm and the state
    machine, managing trial preparation, execution, and data collection.
    
    Key features:
    - Trial-based control with prepare-next-trial states
    - Event logging and data collection
    - Timer-based polling of state machine status
    - Integration with modern StateMachine and StateMatrix classes
    - Optional GUI for manual control
    
    Signals:
        timer_tick: Emitted at each timer interval with current status
                   (server_time, current_state, event_count, current_trial)
        prepare_next_trial: Emitted when ready for next trial preparation
                           (next_trial_number)
        log_message: Emitted when important events occur (message_string)
    """
    
    # Signals - using snake_case for PEP8 compliance
    timer_tick = QtCore.pyqtSignal(float, int, int, int)  # time, state, events, trial
    prepare_next_trial = QtCore.pyqtSignal(int)  # next trial number
    log_message = QtCore.pyqtSignal(str)  # log message
    
    def __init__(self, 
                 parent: Optional[QtCore.QObject] = None,
                 server_type: str = 'dummy',
                 polling_interval: float = DEFAULT_POLLING_INTERVAL,
                 n_inputs: Optional[int] = N_INPUTS,
                 n_outputs: Optional[int] = N_OUTPUTS,
                 create_gui: bool = True) -> None:
        """
        Initialize the Dispatcher.
        
        Args:
            parent: Parent QObject
            server_type: Type of state machine server ('arduino_due', 'emulator', 'dummy')
            polling_interval: How often to poll state machine status (seconds)
            n_inputs: Number of system inputs (uses config default if None)
            n_outputs: Number of system outputs (uses config default if None) 
            create_gui: Whether to create a graphical interface
        """
        super().__init__(parent)
        
        # Server configuration
        self.server_type = server_type
        self.polling_interval = polling_interval
        
        # Trial structure variables
        self.prepare_next_trial_states: List[int] = [DEFAULT_PREPARE_NEXT_STATE]
        self.preparing_next_trial = False
        
        # State machine variables
        self.state_matrix = None
        self.state_machine = StateMachine()
        self.n_inputs = n_inputs
        self.n_outputs = n_outputs
        self.is_running = False
        self.state_machine.stateChanged.connect(self._on_state_changed)
        self.state_machine.eventProcessed.connect(self._on_event_processed)

        # Data collection variables
        self.initial_time = 0.0
        self.current_time = 0.0
        self.current_state = 0
        self.event_count = 0
        self.current_trial = -1  # First trial will be 0
        self.events_log: List[List[Union[float, int]]] = []
        self.trial_end_indices: List[int] = []
        
        # Lists to store events        
        self.timestamps = []
        self.events = []
        self.next_states = []
        self.trials = []

        # Timer for polling
        self.polling_timer = QtCore.QTimer(self)
        self.polling_timer.timeout.connect(self._on_timer_tick)
        
        # Create GUI if requested
        self.gui: Optional[DispatcherGUI] = None
        if create_gui:
            self.gui = DispatcherGUI(model=self)
            
    def set_state_matrix(self, state_matrix: StateMatrix) -> None:
        """
        Set the state transition matrix from a StateMatrix object.
        
        Args:
            state_matrix: StateMatrix object containing the complete state machine definition
        """
        self.state_matrix = state_matrix
        try:
            # Update the state machine
            self.state_machine.set_state_matrix(state_matrix.get_matrix(),
                                                state_matrix.get_timer_event_index())
            self.state_machine.set_state_outputs(state_matrix.get_outputs())
            self.state_machine.set_state_timers(state_matrix.get_state_timers())
            
            self.log_message.emit('State matrix updated successfully')
        except Exception as e:
            self.log_message.emit(f'Error setting state matrix: {str(e)}')
            raise
                            
    def ready_to_start_trial(self) -> None:
        """
        Signal that the next trial is prepared and ready to start.
        
        This transitions the state machine to state 1 (first behavioral state)
        and increments the trial counter.
        """
        if not self.state_machine:
            self.log_message.emit('Error: No state machine available')
            return
            
        try:
            print(self.get_events())  # DEBUG
            self.current_trial += 1
            self.state_machine.force_state(0)
            self.preparing_next_trial = False
            self.log_message.emit(f'Started trial {self.current_trial}')
        except Exception as e:
            self.log_message.emit(f'Error starting trial: {str(e)}')
            raise
            
    def start(self) -> None:
        """Start the dispatcher and state machine."""
        if not self.state_machine:
            self.log_message.emit('Error: No state machine to start')
            return
            
        try:
            # Initialize time tracking
            if self.current_time == 0.0:
                self.initial_time = time.time()

            # Start polling timer
            timer_interval_ms = int(self.polling_interval * 1000)
            self.polling_timer.start(timer_interval_ms)
            
            # Start state machine
            self.state_machine.start()
            self.is_running = True
            self.ready_to_start_trial()  # Prepare first trial
            
            # Trigger initial status update
            self._on_timer_tick()
            
            self.log_message.emit('Dispatcher started')
            
        except Exception as e:
            self.log_message.emit(f'Error starting dispatcher: {str(e)}')
            
    def stop(self) -> None:
        """Stop the dispatcher and state machine."""
        try:
            # Stop polling timer
            self.polling_timer.stop()
            
            # Stop state machine
            if self.state_machine:
                self.state_machine.force_state(-1)  # Go to END state
                self.state_machine.stop()
                self._on_timer_tick()

            self.is_running = False
            self.log_message.emit('Dispatcher stopped')

        except Exception as e:
            self.log_message.emit(f'Error stopping dispatcher: {str(e)}')
            raise
            
    def _on_timer_tick(self) -> None:
        """Handle timer tick events - poll state machine and update status."""
        if not self.state_machine:
            return
            
        try:
            # Update current status
            self.current_time = time.time() - self.initial_time
            # self._query_state_machine()
            
            # Emit status signal
            self.timer_tick.emit(
                self.current_time, 
                self.current_state, 
                self.event_count, 
                self.current_trial
            )
            
            # Check if we need to prepare next trial
            if (self.current_state in self.prepare_next_trial_states and 
                not self.preparing_next_trial):
                self.preparing_next_trial = True
                # self._update_trial_boundaries()
                self.prepare_next_trial.emit(self.current_trial + 1)
                
        except Exception as e:
            self.log_message.emit(f'Error in timer tick: {str(e)}')
            raise

    # def _query_state_machine(self) -> None:
    #     """Query the state machine for current status and events."""
    #     if not self.state_machine:
    #         return
            
    #     # For the new StateMachine class, we get status directly
    #     self.current_time = time.time()  # Use system time for now
    #     # Connect to state machine signals if not already connected
        
    #     # For now, we don't have a direct events interface in the new StateMachine
    #     # This would need to be implemented when connecting to real hardware
    #     # self.event_count += 1  # Placeholder
        
    def _on_event_processed(self, event_index: int, timestamp: float, next_state: int) -> None:
        """
        Handle events from the state machine.
        
        This is called for every event (input or timer) regardless of whether
        it causes a state change. This is where we increment the event count.
        
        Args:
            event_index: Index of the event that was processed
            timestamp: Timestamp when the event was processed
            next_state: The state that will be entered (may be same as current)
        """
        # Update event log - use relative time from start
        relative_time = timestamp - self.initial_time if self.initial_time > 0 else 0.0
        self.events_log.append([relative_time, event_index, next_state])
        self.event_count += 1
        
        # Update events lists
        #self.timestamps.append(timestamp)
        self.timestamps.append(relative_time)
        self.events.append(event_index)
        self.next_states.append(next_state)
        self.trials.append(self.current_trial)

        # Emit timer tick signal with updated status
        self.timer_tick.emit(
            self.current_time, 
            self.current_state, 
            self.event_count, 
            self.current_trial
        )
        
    def _on_state_changed(self, new_state: int) -> None:
        """
        Handle state changes from the state machine.
        
        Args:
            new_state: The new state index after a transition
        """
        self.current_state = new_state
        
        # Log the state change
        self.log_message.emit(f'State changed to {new_state}')
        
    # def _update_trial_boundaries(self) -> None:
    #     """Update the record of where each trial ends in the events log."""
    #     if self.current_trial >= 0 and self.event_count > 0:
    #         # Find the last occurrence of a prepare-next-trial state
    #         for i in range(len(self.events_log) - 1, -1, -1):
    #             if len(self.events_log[i]) > 2 and self.events_log[i][2] in self.prepare_next_trial_states:
    #                 self.trial_end_indices.append(i)
    #                 break
                    
    def get_events_for_trial(self, trial_id: int) -> np.ndarray:
        """
        Get events for a specific trial.
        
        Args:
            trial_id: Trial number to retrieve events for
            
        Returns:
            NumPy array with events for the specified trial
        """
        if trial_id < 0 or trial_id >= len(self.trial_end_indices):
            return np.empty((0, 3), dtype=float)
            
        # Determine start and end indices
        end_idx = self.trial_end_indices[trial_id]
        start_idx = self.trial_end_indices[trial_id - 1] + 1 if trial_id > 0 else 0
        
        # Extract events for this trial
        trial_events = self.events_log[start_idx:end_idx + 1]
        return np.array(trial_events, dtype=float)
    
    def get_events(self):
        """
        Return data about all events so far.
        """
        events_dframe = pd.DataFrame({'timestamp':self.timestamps,
                         'event': self.events,
                         'next_state': self.next_states,
                         'trial': self.trials})
        # return (np.array(self.timestamps, dtype='float'),
        #         np.array(self.events, dtype='int'),
        #         np.array(self.next_states, dtype='int'),
        #         np.array(self.trials, dtype='int'))
        return events_dframe
        
    def get_current_status(self) -> Dict[str, Any]:
        """
        Get comprehensive status information.
        
        Returns:
            Dictionary with current dispatcher and state machine status
        """
        return {
            'is_running': self.is_running,
            'server_time': self.current_time,
            'current_state': self.current_state,
            'current_trial': self.current_trial,
            'event_count': self.event_count,
            'preparing_next_trial': self.preparing_next_trial,
            'n_completed_trials': len(self.trial_end_indices),
            'state_machine_info': self.state_machine.get_state_info() if self.state_machine else None
        }
        
    def append_to_file(self, h5file: Any, current_trial: Optional[int] = None) -> Any:
        """
        Add events information to an HDF5 file.
        
        Args:
            h5file: Open HDF5 file handle
            current_trial: Current trial number (ignored for compatibility)
            
        Returns:
            HDF5 group containing the events data
        """
        if not self.trial_end_indices:
            raise UserWarning('No completed trials found. No events were saved.')
            
        try:
            # Create events group
            events_group = h5file.create_group('/events')
            
            # Convert events log to numpy array
            if self.events_log:
                events_array = np.array(self.events_log, dtype=float)
                events_group.create_dataset('eventTime', data=events_array[:, 0])
                events_group.create_dataset('eventCode', data=events_array[:, 1])
                events_group.create_dataset('nextState', data=events_array[:, 2])
            else:
                # Create empty datasets
                events_group.create_dataset('eventTime', data=np.array([], dtype=float))
                events_group.create_dataset('eventCode', data=np.array([], dtype=int))
                events_group.create_dataset('nextState', data=np.array([], dtype=int))
                
            # Save trial boundaries
            events_group.create_dataset('indexLastEventEachTrial', 
                                      data=np.array(self.trial_end_indices, dtype=int))
                                      
            return events_group
            
        except Exception as e:
            raise RuntimeError(f'Error saving events to file: {str(e)}')
            
            
    def cleanup(self) -> None:
        """Clean up resources when closing the dispatcher."""
        try:
            self.stop()
            if self.state_machine:
                # Reset all outputs to safe state
                for output_idx in range(self.state_machine.num_outputs):
                    self.state_machine.force_output(output_idx, False)
                    
            self.log_message.emit('Dispatcher cleanup completed')
            
        except Exception as e:
            self.log_message.emit(f'Error during cleanup: {str(e)}')
            raise

class DispatcherGUI(QtWidgets.QGroupBox):
    """
    Graphical interface for the Dispatcher.
    
    Provides manual control buttons and real-time status display for the
    dispatcher and state machine. Follows modern PyQt6 conventions and
    PEP8 styling guidelines.
    """
    
    # Signals for controlling the dispatcher
    start_requested = QtCore.pyqtSignal()
    stop_requested = QtCore.pyqtSignal()
    
    def __init__(self, 
                 parent: Optional[QtWidgets.QWidget] = None,
                 model: Optional[Dispatcher] = None,
                 min_width: int = 220) -> None:
        """
        Initialize the dispatcher GUI.
        
        Args:
            parent: Parent widget
            model: Dispatcher instance to control and monitor
            min_width: Minimum width of the GUI widget
        """
        super().__init__(parent)
        
        self.model = model
        self.is_running = False
        
        # String formats for display
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
        
        # Set fixed widths to prevent any movement
        label_fixed_width = 120  # Adjust this value as needed
        self.time_label.setFixedWidth(label_fixed_width)
        self.state_label.setFixedWidth(label_fixed_width)
        self.event_count_label.setFixedWidth(label_fixed_width)
        self.trial_label.setFixedWidth(label_fixed_width)
        
        # Set text alignment to ensure consistent left alignment
        self.time_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.state_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.event_count_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.trial_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        
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
        """Connect signals between GUI and model."""
        # Button click
        self.start_stop_button.clicked.connect(self._on_start_stop_clicked)
        
        # Connect to model if provided
        if self.model:
            # Connect control signals
            self.start_requested.connect(self.model.start)
            self.stop_requested.connect(self.model.stop)
            
            # Connect status updates
            self.model.timer_tick.connect(self._update_display)
            
    def _on_start_stop_clicked(self) -> None:
        """Handle start/stop button clicks."""
        if self.is_running:
            self.stop()
        else:
            self.start()
            
    def start(self) -> None:
        """Request to start the dispatcher."""
        self._set_running_appearance()
        self.start_requested.emit()
        
    def stop(self) -> None:
        """Request to stop the dispatcher."""
        self._set_stopped_appearance()
        self.stop_requested.emit()
        
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
            server_time: Current time from state machine
            current_state: Current state index
            event_count: Total number of events
            current_trial: Current trial number
        """
        self.time_label.setText(self._time_format.format(server_time))
        
        # Get state name from state matrix if available
        if (self.model and self.model.state_matrix and 
            current_state in self.model.state_matrix.states.inverse):
            state_name = self.model.state_matrix.states.inverse[current_state]
            self.state_label.setText(self._state_format.format(current_state, state_name))
        else:
            self.state_label.setText(self._state_format.format(current_state, '--'))
        
        self.event_count_label.setText(self._event_format.format(event_count))
        
        if current_trial >= 0:
            self.trial_label.setText(self._trial_format.format(current_trial))
        else:
            self.trial_label.setText('Trial: --')


if __name__ == '__main__':
    """Example usage of the Dispatcher."""
    import sys
    from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget
    
    app = QApplication(sys.argv)
    
    # Create main window
    main_window = QWidget()
    main_window.setWindowTitle('Dispatcher Example')
    main_window.resize(300, 200)
    
    # Create dispatcher with GUI
    dispatcher = Dispatcher(create_gui=True)
    
    # Layout
    layout = QVBoxLayout()
    if dispatcher.gui:
        layout.addWidget(dispatcher.gui)
    main_window.setLayout(layout)
    
    # Show window
    main_window.show()
    
    # Connect cleanup
    app.aboutToQuit.connect(dispatcher.cleanup)
    
    sys.exit(app.exec())