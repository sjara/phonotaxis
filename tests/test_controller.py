"""
Unit tests for controller module.

Tests cover:
- SessionController initialization
- Parameter validation
- State matrix configuration
- Session lifecycle (start/stop)
- Trial management
- Event logging and retrieval
- Session duration handling
- Signal emissions
- Data persistence (HDF5)
- Cleanup procedures
- ControllerGUI initialization and display
- GUI-controller interaction
"""

import pytest
from pytestqt.qtbot import QtBot
import numpy as np
import pandas as pd
import tempfile
import h5py
from unittest.mock import MagicMock, Mock, patch, PropertyMock
from PyQt6 import QtCore
from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import QApplication
from phonotaxis import controller
from phonotaxis.statematrix import StateMatrix
from phonotaxis.statemachine import StateMachine


@pytest.fixture
def qapp():
    """Create QApplication instance for testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def qtbot(qapp):
    """Fixture to provide qtbot for signal testing."""
    return QtBot(qapp)


@pytest.fixture
def basic_state_matrix():
    """Create a basic state matrix for testing."""
    sm = StateMatrix(inputs=['L', 'R'], outputs=['ValveL', 'ValveR'])
    sm.add_state(name='wait', statetimer=1.0,
                transitions={'Lin': 'reward'},
                outputsOff=['ValveL'])
    sm.add_state(name='reward', statetimer=0.5,
                transitions={'Tup': 'END'},
                outputsOn=['ValveL'])
    return sm


class TestSessionControllerInit:
    """Tests for SessionController initialization."""
    
    def test_init_default(self, qapp):
        """Test default initialization."""
        ctrl = controller.SessionController(create_gui=False)
        
        assert ctrl.polling_interval == controller.DEFAULT_POLLING_INTERVAL
        assert ctrl.session_duration is None
        assert ctrl.debug is False
        assert ctrl.is_running is False
        assert ctrl.start_time == 0.0
        assert ctrl.current_time == 0.0
        assert ctrl.current_state == 0
        assert ctrl.event_count == 0
        assert ctrl.current_trial == -1
        assert ctrl.preparing_next_trial is False
        assert ctrl.timestamps == []
        assert ctrl.events == []
        assert ctrl.next_states == []
        assert ctrl.trials == []
        assert ctrl.gui is None
        
    def test_init_with_gui(self, qapp):
        """Test initialization with GUI creation."""
        ctrl = controller.SessionController(create_gui=True)
        
        assert ctrl.gui is not None
        assert isinstance(ctrl.gui, controller.ControllerGUI)
        assert ctrl.gui.controller is ctrl
        
    def test_init_with_debug(self, qapp):
        """Test initialization with debug enabled."""
        ctrl = controller.SessionController(create_gui=False, debug=True)
        
        assert ctrl.debug is True
        assert ctrl.state_machine.debug is True
        
    def test_init_custom_polling_interval(self, qapp):
        """Test initialization with custom polling interval."""
        ctrl = controller.SessionController(create_gui=False, polling_interval=0.5)
        
        assert ctrl.polling_interval == 0.5
        
    def test_init_invalid_polling_interval_negative(self, qapp):
        """Test that negative polling interval raises ValueError."""
        with pytest.raises(ValueError, match='polling_interval must be a positive number'):
            controller.SessionController(create_gui=False, polling_interval=-0.1)
            
    def test_init_invalid_polling_interval_zero(self, qapp):
        """Test that zero polling interval raises ValueError."""
        with pytest.raises(ValueError, match='polling_interval must be a positive number'):
            controller.SessionController(create_gui=False, polling_interval=0)
            
    def test_init_invalid_polling_interval_string(self, qapp):
        """Test that string polling interval raises ValueError."""
        with pytest.raises(ValueError, match='polling_interval must be a positive number'):
            controller.SessionController(create_gui=False, polling_interval='invalid')


class TestSetStateMatrix:
    """Tests for set_state_matrix method."""
    
    def test_set_state_matrix_valid(self, qapp, basic_state_matrix):
        """Test setting a valid state matrix."""
        ctrl = controller.SessionController(create_gui=False)
        
        ctrl.set_state_matrix(basic_state_matrix)
        
        assert ctrl.state_matrix is basic_state_matrix
        assert ctrl.prepare_next_trial_states == [0]  # END state
        
    def test_set_state_matrix_invalid_type(self, qapp):
        """Test that invalid state matrix type raises TypeError."""
        ctrl = controller.SessionController(create_gui=False)
        
        with pytest.raises(TypeError, match='Expected StateMatrix instance'):
            ctrl.set_state_matrix("not a state matrix")
            
    def test_set_state_matrix_emits_log_message(self, qapp, basic_state_matrix):
        """Test that setting state matrix emits log message."""
        ctrl = controller.SessionController(create_gui=False)
        spy = QSignalSpy(ctrl.log_message)
        
        ctrl.set_state_matrix(basic_state_matrix)
        
        assert len(spy) == 1
        assert 'State matrix updated successfully' in spy[0][0]


class TestSetSessionDuration:
    """Tests for set_session_duration method."""
    
    def test_set_session_duration_valid(self, qapp):
        """Test setting valid session duration."""
        ctrl = controller.SessionController(create_gui=False)
        
        ctrl.set_session_duration(60.0)
        
        assert ctrl.session_duration == 60.0
        
    def test_set_session_duration_none(self, qapp):
        """Test setting session duration to None (unlimited)."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.session_duration = 60.0  # Set initially
        
        ctrl.set_session_duration(None)
        
        assert ctrl.session_duration is None
        
    def test_set_session_duration_invalid_negative(self, qapp):
        """Test that negative duration raises ValueError."""
        ctrl = controller.SessionController(create_gui=False)
        
        with pytest.raises(ValueError, match='session_duration must be None or a positive number'):
            ctrl.set_session_duration(-10.0)
            
    def test_set_session_duration_invalid_zero(self, qapp):
        """Test that zero duration raises ValueError."""
        ctrl = controller.SessionController(create_gui=False)
        
        with pytest.raises(ValueError, match='session_duration must be None or a positive number'):
            ctrl.set_session_duration(0)
            
    def test_set_session_duration_emits_log_message(self, qapp):
        """Test that setting duration emits log message."""
        ctrl = controller.SessionController(create_gui=False)
        spy = QSignalSpy(ctrl.log_message)
        
        ctrl.set_session_duration(120.0)
        
        assert len(spy) == 1
        assert '120.0 seconds' in spy[0][0]


class TestSessionLifecycle:
    """Tests for session start/stop lifecycle."""
    
    def test_start_session(self, qapp, basic_state_matrix):
        """Test starting a session."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        
        ctrl.start()
        
        assert ctrl.is_running is True
        assert ctrl.start_time > 0
        assert ctrl.preparing_next_trial is True
        
    def test_start_emits_signals(self, qapp, basic_state_matrix):
        """Test that start emits expected signals."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        
        started_spy = QSignalSpy(ctrl.session_started)
        prepare_spy = QSignalSpy(ctrl.prepare_next_trial)
        status_spy = QSignalSpy(ctrl.status_update)
        
        ctrl.start()
        
        assert len(started_spy) == 1
        assert len(prepare_spy) == 1
        assert prepare_spy[0][0] == 0  # Trial 0
        assert len(status_spy) == 1
        
    def test_start_already_running(self, qapp, basic_state_matrix):
        """Test that starting already running session does nothing."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.start()
        
        started_spy = QSignalSpy(ctrl.session_started)
        ctrl.start()  # Try to start again
        
        assert len(started_spy) == 0  # No new signal
        
    def test_stop_session(self, qapp, basic_state_matrix):
        """Test stopping a session."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.start()
        
        ctrl.stop()
        
        assert ctrl.is_running is False
        
    def test_stop_emits_signals(self, qapp, basic_state_matrix):
        """Test that stop emits expected signals."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.start()
        
        stopped_spy = QSignalSpy(ctrl.session_stopped)
        status_spy = QSignalSpy(ctrl.status_update)
        
        ctrl.stop()
        
        assert len(stopped_spy) == 1
        assert len(status_spy) == 1
        
    def test_stop_sets_end_state(self, qapp, basic_state_matrix):
        """Test that stopping forces state machine to END state."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.start()
        ctrl.ready_to_start_trial()  # Start trial 0, goes to state 1
        
        # Verify we're in a non-END state
        assert ctrl.current_state != 0
        
        ctrl.stop()
        
        # After stopping, should be in END state (state 0)
        assert ctrl.current_state == 0
        
    def test_stop_does_not_trigger_prepare_next_trial(self, qapp, basic_state_matrix):
        """Test that stopping does not emit prepare_next_trial signal.
        
        This is a regression test for the bug where stopping would trigger
        prepare_next_trial because is_running was set to False AFTER forcing
        the state change to END.
        """
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.start()
        ctrl.ready_to_start_trial()  # Start trial 0
        
        # Clear the prepare_next_trial signal from start
        prepare_spy = QSignalSpy(ctrl.prepare_next_trial)
        
        ctrl.stop()
        
        # Should NOT emit prepare_next_trial when stopping
        assert len(prepare_spy) == 0
        
    def test_stop_start_does_not_create_empty_trial(self, qapp, basic_state_matrix):
        """Test that stopping and restarting doesn't create an empty trial.
        
        This is a regression test for the bug where:
        1. stop() would force to END state while is_running=True
        2. _on_state_changed would see END state + is_running=True
        3. This would emit prepare_next_trial(N+1)
        4. start() would also emit prepare_next_trial(N+1)
        5. Result: trial counter incremented twice, creating empty trial
        """
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        
        # Start and run trial 0
        ctrl.start()
        assert ctrl.current_trial == -1  # Before starting any trial
        ctrl.ready_to_start_trial()
        assert ctrl.current_trial == 0
        
        # Stop the session
        ctrl.stop()
        assert ctrl.current_trial == 0  # Should still be 0
        
        # Start again - should prepare trial 1 (not trial 2)
        prepare_spy = QSignalSpy(ctrl.prepare_next_trial)
        ctrl.start()
        
        assert len(prepare_spy) == 1
        assert prepare_spy[0][0] == 1  # Should be preparing trial 1
        
        # Complete trial 1
        ctrl.ready_to_start_trial()
        assert ctrl.current_trial == 1  # Should be 1, not 2
        
        # Verify no empty trial was created by checking events
        # Trial 0 had 1 forced event, trial 1 had 1 forced event
        df = ctrl.get_events()
        assert len(df[df['trial'] == 0]) >= 1  # Trial 0 has events
        assert len(df[df['trial'] == 1]) >= 1  # Trial 1 has events
        # No trial 2 should exist yet
        assert len(df[df['trial'] == 2]) == 0


class TestTrialManagement:
    """Tests for trial management."""
    
    def test_ready_to_start_trial(self, qapp, basic_state_matrix):
        """Test ready_to_start_trial increments trial counter."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.start()
        
        ctrl.ready_to_start_trial()
        
        assert ctrl.current_trial == 0
        assert ctrl.preparing_next_trial is False
        
    def test_ready_to_start_trial_requires_preparing_flag(self, qapp, basic_state_matrix):
        """Test that ready_to_start_trial only works when preparing_next_trial is True."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.start()
        ctrl.ready_to_start_trial()  # Start trial 0
        
        # Try to call again without preparing flag
        ctrl.ready_to_start_trial()
        
        assert ctrl.current_trial == 0  # Should not increment
        
    def test_ready_to_start_trial_not_running(self, qapp, basic_state_matrix):
        """Test that ready_to_start_trial does nothing if not running."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.preparing_next_trial = True  # Manually set flag
        
        ctrl.ready_to_start_trial()
        
        assert ctrl.current_trial == -1  # Should not start
        
    def test_prepare_next_trial_signal_on_end_state(self, qapp, basic_state_matrix):
        """Test that reaching END state triggers prepare_next_trial signal."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.start()
        ctrl.ready_to_start_trial()
        
        prepare_spy = QSignalSpy(ctrl.prepare_next_trial)
        
        # Simulate reaching END state (state 0)
        ctrl._on_state_changed(0)
        
        assert len(prepare_spy) == 1
        assert prepare_spy[0][0] == 1  # Next trial is 1
        assert ctrl.preparing_next_trial is True


class TestEventLogging:
    """Tests for event logging."""
    
    def test_on_event_processed_logs_event(self, qapp, basic_state_matrix):
        """Test that events are logged when processed."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.start()
        ctrl.ready_to_start_trial()  # Generates 1 forced event
        
        # Simulate event
        timestamp = ctrl.start_time + 1.5
        ctrl._on_event_processed(event_index=2, timestamp=timestamp, next_state=1)
        
        # Should have 2 events total: forced (-1) + manual (2)
        assert ctrl.event_count == 2
        assert len(ctrl.timestamps) == 2
        # Check the manually added event (second one)
        assert ctrl.timestamps[1] == pytest.approx(1.5, abs=0.01)
        assert ctrl.events[1] == 2
        assert ctrl.next_states[1] == 1
        assert ctrl.trials[1] == 0
        
    def test_multiple_events_logging(self, qapp, basic_state_matrix):
        """Test logging multiple events."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.start()
        ctrl.ready_to_start_trial()  # Generates 1 forced event
        
        # Simulate multiple events
        for i in range(5):
            ctrl._on_event_processed(event_index=i, 
                                    timestamp=ctrl.start_time + i * 0.1, 
                                    next_state=i % 2)
        
        # Should have 6 events: 1 forced + 5 manual
        assert ctrl.event_count == 6
        assert len(ctrl.timestamps) == 6
        assert len(ctrl.events) == 6


class TestGetEvents:
    """Tests for get_events methods."""
    
    def test_get_events_empty(self, qapp):
        """Test get_events with no events."""
        ctrl = controller.SessionController(create_gui=False)
        
        df = ctrl.get_events()
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert list(df.columns) == ['timestamp', 'event', 'next_state', 'trial']
        
    def test_get_events_with_data(self, qapp, basic_state_matrix):
        """Test get_events with logged events."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.start()
        ctrl.ready_to_start_trial()  # This triggers a forced transition event (event=-1)
        
        # Add some events
        ctrl._on_event_processed(1, ctrl.start_time + 0.5, 1)
        ctrl._on_event_processed(2, ctrl.start_time + 1.0, 2)
        
        df = ctrl.get_events()
        
        # Should have 3 events: forced transition (-1) + 2 manual events
        assert len(df) == 3
        assert df['event'].tolist() == [-1, 1, 2]
        assert df['trial'].tolist() == [0, 0, 0]
        
    def test_get_events_one_trial(self, qapp, basic_state_matrix):
        """Test get_events_one_trial filtering."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.start()
        
        # Trial 0 - ready_to_start_trial generates forced event (-1)
        ctrl.ready_to_start_trial()
        ctrl._on_event_processed(1, ctrl.start_time + 0.5, 1)
        
        # Trial 1 - ready_to_start_trial generates forced event (-1)
        ctrl.preparing_next_trial = True
        ctrl.ready_to_start_trial()
        ctrl._on_event_processed(2, ctrl.start_time + 1.5, 2)
        
        df_trial0 = ctrl.get_events_one_trial(0)
        df_trial1 = ctrl.get_events_one_trial(1)
        
        # Each trial has forced event + manual event
        assert len(df_trial0) == 2
        assert df_trial0['event'].tolist() == [-1, 1]
        assert len(df_trial1) == 2
        assert df_trial1['event'].tolist() == [-1, 2]


class TestSessionDuration:
    """Tests for session duration handling."""
    
    def test_session_stops_at_duration(self, qapp, basic_state_matrix, qtbot):
        """Test that session stops when duration is reached."""
        ctrl = controller.SessionController(create_gui=False, polling_interval=0.05)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.set_session_duration(0.2)  # 200ms
        
        stopped_spy = QSignalSpy(ctrl.session_stopped)
        ctrl.start()
        
        # Wait for session to complete
        qtbot.wait(300)  # Wait 300ms
        
        assert ctrl.is_running is False
        assert len(stopped_spy) >= 1
        
    def test_session_unlimited_duration(self, qapp, basic_state_matrix, qtbot):
        """Test that session continues without duration limit."""
        ctrl = controller.SessionController(create_gui=False, polling_interval=0.05)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.set_session_duration(None)  # Unlimited
        
        ctrl.start()
        qtbot.wait(200)  # Wait 200ms
        
        assert ctrl.is_running is True
        ctrl.stop()


class TestAppendToFile:
    """Tests for HDF5 file saving."""
    
    def test_append_to_file_no_trials(self, qapp):
        """Test that append_to_file raises error with no trials."""
        ctrl = controller.SessionController(create_gui=False)
        
        with tempfile.NamedTemporaryFile(suffix='.h5', delete=False) as f:
            with h5py.File(f.name, 'w') as h5file:
                with pytest.raises(UserWarning, match='No completed trials'):
                    ctrl.append_to_file(h5file)
                    
    def test_append_to_file_with_events(self, qapp, basic_state_matrix):
        """Test saving events to HDF5 file."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.start()
        ctrl.ready_to_start_trial()  # Generates 1 forced event
        
        # Add some events
        ctrl._on_event_processed(1, ctrl.start_time + 0.5, 1)
        ctrl._on_event_processed(2, ctrl.start_time + 1.0, 2)
        
        with tempfile.NamedTemporaryFile(suffix='.h5', delete=False) as f:
            with h5py.File(f.name, 'w') as h5file:
                events_group = ctrl.append_to_file(h5file)
                
                assert 'timestamp' in events_group
                assert 'event' in events_group
                assert 'next_state' in events_group
                assert 'trial' in events_group
                # Should have 3 events: forced + 2 manual
                assert len(events_group['timestamp']) == 3
                
    def test_append_to_file_data_types(self, qapp, basic_state_matrix):
        """Test that HDF5 datasets have correct dtypes."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.start()
        ctrl.ready_to_start_trial()
        ctrl._on_event_processed(1, ctrl.start_time + 0.5, 1)
        
        with tempfile.NamedTemporaryFile(suffix='.h5', delete=False) as f:
            with h5py.File(f.name, 'w') as h5file:
                events_group = ctrl.append_to_file(h5file)
                
                assert events_group['timestamp'].dtype == np.float64
                assert events_group['event'].dtype == np.int64
                assert events_group['next_state'].dtype == np.int64
                assert events_group['trial'].dtype == np.int64


class TestCleanup:
    """Tests for cleanup method."""
    
    def test_cleanup_stops_session(self, qapp, basic_state_matrix):
        """Test that cleanup stops the session."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.start()
        
        ctrl.cleanup()
        
        assert ctrl.is_running is False
        
    def test_cleanup_resets_outputs(self, qapp, basic_state_matrix):
        """Test that cleanup resets state machine outputs."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        
        # Mock force_output to verify it's called
        ctrl.state_machine.force_output = Mock()
        
        ctrl.cleanup()
        
        # Should call force_output for each output
        assert ctrl.state_machine.force_output.call_count == ctrl.state_machine.num_outputs


class TestControllerGUIInit:
    """Tests for ControllerGUI initialization."""
    
    def test_gui_init_without_controller(self, qapp):
        """Test GUI initialization without controller."""
        gui = controller.ControllerGUI(controller=None)
        
        assert gui.controller is None
        assert gui.is_running is False
        assert gui.last_event_name == '--'
        
    def test_gui_init_with_controller(self, qapp, basic_state_matrix):
        """Test GUI initialization with controller."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        gui = controller.ControllerGUI(controller=ctrl)
        
        assert gui.controller is ctrl
        
    def test_gui_initial_appearance(self, qapp):
        """Test GUI starts in stopped appearance."""
        gui = controller.ControllerGUI(controller=None)
        
        assert gui.start_stop_button.text() == 'START'
        assert gui.is_running is False


class TestControllerGUIInteraction:
    """Tests for ControllerGUI interaction with controller."""
    
    def test_gui_button_starts_session(self, qapp, basic_state_matrix):
        """Test that clicking START button starts session."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        gui = controller.ControllerGUI(controller=ctrl)
        
        # Simulate button click
        gui._on_start_stop_clicked()
        
        assert ctrl.is_running is True
        
    def test_gui_button_stops_session(self, qapp, basic_state_matrix):
        """Test that clicking STOP button stops session."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        gui = controller.ControllerGUI(controller=ctrl)
        
        ctrl.start()
        gui._on_start_stop_clicked()
        
        assert ctrl.is_running is False
        
    def test_gui_updates_on_status_signal(self, qapp):
        """Test that GUI updates when status_update signal is emitted."""
        ctrl = controller.SessionController(create_gui=False)
        gui = controller.ControllerGUI(controller=ctrl)
        
        # Emit status update
        ctrl.status_update.emit(10.5, 2, 15, 3)
        
        assert 'Time: 10.5' in gui.time_label.text()
        assert 'Events: 15' in gui.event_count_label.text()
        assert 'Trial: 3' in gui.trial_label.text()
        
    def test_gui_appearance_changes_on_session_started(self, qapp, basic_state_matrix):
        """Test that GUI appearance changes when session starts."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        gui = controller.ControllerGUI(controller=ctrl)
        
        ctrl.start()
        
        assert gui.start_stop_button.text() == 'STOP'
        assert gui.is_running is True
        
    def test_gui_appearance_changes_on_session_stopped(self, qapp, basic_state_matrix):
        """Test that GUI appearance changes when session stops."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        gui = controller.ControllerGUI(controller=ctrl)
        
        ctrl.start()
        ctrl.stop()
        
        assert gui.start_stop_button.text() == 'START'
        assert gui.is_running is False


class TestSignalEmissions:
    """Tests for signal emissions."""
    
    def test_log_message_signal(self, qapp):
        """Test that log_message signal is emitted."""
        ctrl = controller.SessionController(create_gui=False)
        spy = QSignalSpy(ctrl.log_message)
        
        ctrl.set_session_duration(60.0)
        
        assert len(spy) == 1
        
    def test_status_update_signal(self, qapp, basic_state_matrix):
        """Test that status_update signal is emitted."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        spy = QSignalSpy(ctrl.status_update)
        
        ctrl.start()
        
        assert len(spy) >= 1
        
    def test_prepare_next_trial_signal(self, qapp, basic_state_matrix):
        """Test that prepare_next_trial signal is emitted."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        spy = QSignalSpy(ctrl.prepare_next_trial)
        
        ctrl.start()
        
        assert len(spy) == 1
        assert spy[0][0] == 0  # First trial


class TestEdgeCases:
    """Tests for edge cases and error conditions."""
    
    def test_get_events_with_names_requires_state_matrix(self, qapp, basic_state_matrix):
        """Test that get_events with use_names=True requires configured state matrix."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        ctrl.start()
        ctrl.ready_to_start_trial()
        ctrl._on_event_processed(1, ctrl.start_time + 0.5, 1)
        
        # This should work with state matrix
        df = ctrl.get_events(use_names=True)
        assert 'events_str' in df.columns
        assert 'next_state_str' in df.columns
        
    def test_stop_before_start(self, qapp, basic_state_matrix):
        """Test that stopping before starting doesn't crash."""
        ctrl = controller.SessionController(create_gui=False)
        ctrl.set_state_matrix(basic_state_matrix)
        
        # Should not raise
        ctrl.stop()
        
    def test_timer_tick_before_start(self, qapp):
        """Test that timer tick before start does nothing."""
        ctrl = controller.SessionController(create_gui=False)
        
        # Should not raise
        ctrl._on_timer_tick()
        
        assert ctrl.current_time == 0.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
