"""
Unit tests for statemachine module.

Tests cover:
- StateMachine initialization
- State matrix, timers, and outputs configuration
- State machine lifecycle (start/stop)
- Input event processing
- State transitions
- Output handling
- Timer functionality
- Forced state transitions
- Signal connections
- Query methods (getters)
- Error handling and validation
"""

import pytest
import numpy as np
import time
from unittest.mock import MagicMock, Mock
from PyQt6 import QtCore
from PyQt6.QtTest import QSignalSpy
from phonotaxis import statemachine


@pytest.fixture
def qtbot(qapp):
    """Fixture to provide qtbot for signal testing."""
    from pytestqt.qtbot import QtBot
    return QtBot(qapp)


@pytest.fixture
def qapp():
    """Create QApplication instance for testing."""
    app = QtCore.QCoreApplication.instance()
    if app is None:
        app = QtCore.QCoreApplication([])
    return app


class TestStateMachineInit:
    """Tests for StateMachine initialization."""
    
    def test_init_default(self):
        """Test default initialization."""
        sm = statemachine.StateMachine()
        
        assert sm.debug is False
        assert sm.state_matrix is None
        assert sm.state_timers is None
        assert sm.state_outputs is None
        assert sm.integer_outputs is None
        assert sm.timer_event_index is None
        assert sm.num_states == 0
        assert sm.num_inputs == 0
        assert sm.num_outputs == 0
        assert sm.current_state == 0
        assert sm.is_active is False
        assert sm.is_processing is False
        assert sm.output_states == []
        
    def test_init_with_debug(self):
        """Test initialization with debug enabled."""
        sm = statemachine.StateMachine(debug=True)
        assert sm.debug is True
        
    def test_is_configured_false_initially(self):
        """Test is_configured returns False when not configured."""
        sm = statemachine.StateMachine()
        assert sm.is_configured() is False


class TestSetStateMatrix:
    """Tests for set_state_matrix method."""
    
    def test_set_state_matrix_basic(self):
        """Test basic state matrix setting."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        
        sm.set_state_matrix(matrix)
        
        assert sm.num_states == 2
        assert sm.num_inputs == 2
        assert np.array_equal(sm.state_matrix, matrix)
        assert sm.timer_event_index == 1  # Default to last column
        
    def test_set_state_matrix_with_timer_index(self):
        """Test state matrix with explicit timer event index."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0, 0],
                          [1, 2, 0],
                          [2, 0, 1]], dtype=np.int32)
        
        sm.set_state_matrix(matrix, timer_event_index=1)
        
        assert sm.timer_event_index == 1
        
    def test_set_state_matrix_initializes_timers(self):
        """Test that state timers are initialized when not set."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        
        sm.set_state_matrix(matrix)
        
        assert sm.state_timers is not None
        assert len(sm.state_timers) == 2
        assert np.all(sm.state_timers == float('inf'))
        
    def test_set_state_matrix_not_numpy_array(self):
        """Test that non-NumPy arrays are rejected."""
        sm = statemachine.StateMachine()
        with pytest.raises(TypeError):
            sm.set_state_matrix([[0, 1], [1, 0]])
            
    def test_set_state_matrix_empty(self):
        """Test that empty matrix is rejected."""
        sm = statemachine.StateMachine()
        with pytest.raises(ValueError, match="cannot be empty"):
            sm.set_state_matrix(np.array([]))
            
    def test_set_state_matrix_wrong_dimensions(self):
        """Test that non-2D matrix is rejected."""
        sm = statemachine.StateMachine()
        with pytest.raises(ValueError, match="must be 2-dimensional"):
            sm.set_state_matrix(np.array([0, 1, 2]))
            
    def test_set_state_matrix_invalid_indices(self):
        """Test that invalid state indices are rejected."""
        sm = statemachine.StateMachine()
        # Matrix with invalid state index (3 when only 2 states exist)
        matrix = np.array([[0, 0],
                          [1, 3]], dtype=np.int32)
        with pytest.raises(ValueError, match="invalid state indices"):
            sm.set_state_matrix(matrix)
            
    def test_set_state_matrix_negative_indices(self):
        """Test that negative state indices are rejected."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, -1]], dtype=np.int32)
        with pytest.raises(ValueError, match="invalid state indices"):
            sm.set_state_matrix(matrix)
            
    def test_set_state_matrix_while_running(self):
        """Test that matrix cannot be changed while running."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), 1.0])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        new_matrix = np.array([[0]], dtype=np.int32)
        with pytest.raises(RuntimeError, match="processing events"):
            sm.set_state_matrix(new_matrix)
            
        sm.stop()
        
    def test_set_state_matrix_invalid_timer_index(self):
        """Test that invalid timer event index is rejected."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        with pytest.raises(ValueError, match="Timer event index"):
            sm.set_state_matrix(matrix, timer_event_index=5)
            

class TestSetStateTimers:
    """Tests for set_state_timers method."""
    
    def test_set_state_timers_basic(self):
        """Test basic state timers setting."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        sm.set_state_matrix(matrix)
        
        timers = np.array([float('inf'), 1.5])
        sm.set_state_timers(timers)
        
        assert np.array_equal(sm.state_timers, timers)
        
    def test_set_state_timers_not_numpy_array(self):
        """Test that non-NumPy arrays are rejected."""
        sm = statemachine.StateMachine()
        with pytest.raises(TypeError):
            sm.set_state_timers([1.0, 2.0])
            
    def test_set_state_timers_wrong_dimensions(self):
        """Test that non-1D timers are rejected."""
        sm = statemachine.StateMachine()
        with pytest.raises(ValueError, match="must be 1-dimensional"):
            sm.set_state_timers(np.array([[1.0, 2.0]]))
            
    def test_set_state_timers_wrong_length(self):
        """Test that timers with wrong length are rejected."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        sm.set_state_matrix(matrix)
        
        with pytest.raises(ValueError, match="same length"):
            sm.set_state_timers(np.array([1.0, 2.0, 3.0]))
            
    def test_set_state_timers_while_running(self):
        """Test that timers cannot be changed while running."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), 1.0])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        with pytest.raises(RuntimeError, match="processing events"):
            sm.set_state_timers(np.array([2.0, 3.0]))
            
        sm.stop()


class TestSetStateOutputs:
    """Tests for set_state_outputs method."""
    
    def test_set_state_outputs_basic(self):
        """Test basic state outputs setting."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        sm.set_state_matrix(matrix)
        
        outputs = np.array([[0, 0, 0],
                           [0, 1, -1]], dtype=np.int32)
        sm.set_state_outputs(outputs)
        
        assert sm.num_outputs == 3
        assert np.array_equal(sm.state_outputs, outputs)
        assert sm.output_states == [False, False, False]
        
    def test_set_state_outputs_not_numpy_array(self):
        """Test that non-NumPy arrays are rejected."""
        sm = statemachine.StateMachine()
        with pytest.raises(TypeError):
            sm.set_state_outputs([[1, 0], [0, 1]])
            
    def test_set_state_outputs_wrong_dimensions(self):
        """Test that non-2D outputs are rejected."""
        sm = statemachine.StateMachine()
        with pytest.raises(ValueError, match="must be 2-dimensional"):
            sm.set_state_outputs(np.array([1, 0, -1]))
            
    def test_set_state_outputs_wrong_rows(self):
        """Test that outputs with wrong number of rows are rejected."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        sm.set_state_matrix(matrix)
        
        outputs = np.array([[0, 0],
                           [0, 1],
                           [1, 1]], dtype=np.int32)
        with pytest.raises(ValueError, match="same number of rows"):
            sm.set_state_outputs(outputs)
            
    def test_set_state_outputs_invalid_values(self):
        """Test that invalid output values are rejected."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        sm.set_state_matrix(matrix)
        
        outputs = np.array([[0, 0],
                           [0, 2]], dtype=np.int32)  # 2 is invalid
        with pytest.raises(ValueError, match="must contain only -1"):
            sm.set_state_outputs(outputs)
            
    def test_set_state_outputs_while_running(self):
        """Test that outputs cannot be changed while running."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), 1.0])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        new_outputs = np.array([[0, 0],
                               [1, 0]], dtype=np.int32)
        with pytest.raises(RuntimeError, match="processing events"):
            sm.set_state_outputs(new_outputs)
            
        sm.stop()


class TestSetIntegerOutputs:
    """Tests for set_integer_outputs method."""
    
    def test_set_integer_outputs_basic(self):
        """Test basic integer outputs setting."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        sm.set_state_matrix(matrix)
        
        int_outputs = np.array([0, 5])
        sm.set_integer_outputs(int_outputs)
        
        assert np.array_equal(sm.integer_outputs, int_outputs)
        
    def test_set_integer_outputs_not_numpy_array(self):
        """Test that non-NumPy arrays are rejected."""
        sm = statemachine.StateMachine()
        with pytest.raises(TypeError):
            sm.set_integer_outputs([0, 5])
            
    def test_set_integer_outputs_wrong_dimensions(self):
        """Test that non-1D integer outputs are rejected."""
        sm = statemachine.StateMachine()
        with pytest.raises(ValueError, match="must be 1-dimensional"):
            sm.set_integer_outputs(np.array([[0, 5]]))
            
    def test_set_integer_outputs_wrong_length(self):
        """Test that integer outputs with wrong length are rejected."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        sm.set_state_matrix(matrix)
        
        with pytest.raises(ValueError, match="same length"):
            sm.set_integer_outputs(np.array([0, 5, 10]))
            
    def test_set_integer_outputs_while_running(self):
        """Test that integer outputs cannot be changed while running."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), 1.0])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        with pytest.raises(RuntimeError, match="processing events"):
            sm.set_integer_outputs(np.array([0, 5]))
            
        sm.stop()


class TestStartStop:
    """Tests for start and stop methods."""
    
    def test_start_unconfigured(self):
        """Test that starting unconfigured machine raises error."""
        sm = statemachine.StateMachine()
        with pytest.raises(RuntimeError, match="must be configured"):
            sm.start()
            
    def test_start_configured(self):
        """Test starting a properly configured state machine."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), 1.0])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        assert sm.is_active is True
        assert sm.is_processing is True
        assert sm.current_state == 0  # Always starts at state 0
        
        sm.stop()
        
    def test_stop(self):
        """Test stopping the state machine."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), 1.0])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        sm.stop()
        
        assert sm.is_active is False
        assert sm.is_processing is False
        
    def test_is_configured(self):
        """Test is_configured method."""
        sm = statemachine.StateMachine()
        assert sm.is_configured() is False
        
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        sm.set_state_matrix(matrix)
        # After setting matrix, timers are auto-initialized, so still not fully configured
        # (missing outputs)
        assert sm.is_configured() is False
        
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        sm.set_state_outputs(outputs)
        # After setting outputs, now we have matrix, outputs, and auto-initialized timers
        # so it's configured
        assert sm.is_configured() is True


class TestReset:
    """Tests for reset method."""
    
    def test_reset_clears_configuration(self):
        """Test that reset clears all configuration."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), 1.0])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.reset()
        
        assert sm.state_matrix is None
        assert sm.state_outputs is None
        assert sm.state_timers is None
        assert sm.integer_outputs is None
        assert sm.num_states == 0
        assert sm.num_inputs == 0
        assert sm.num_outputs == 0
        assert sm.current_state == 0
        assert sm.output_states == []
        
    def test_reset_stops_machine(self):
        """Test that reset stops running machine."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), 1.0])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        assert sm.is_active is True
        sm.reset()
        assert sm.is_active is False


class TestProcessInput:
    """Tests for process_input method."""
    
    def test_process_input_basic(self, qapp):
        """Test basic input processing and state transition."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        # Create signal spy to monitor state changes
        spy = QSignalSpy(sm.stateChanged)
        
        # Force to state 1 first, then process input to transition back to state 0
        sm.force_state(1)
        qapp.processEvents()
        spy.clear() if hasattr(spy, 'clear') else None  # Clear initial transition
        
        # Process input event 1 from state 1, should transition to state 0
        sm.process_input(1)
        qapp.processEvents()
        
        assert sm.current_state == 0
        # Note: Can't use len(spy) reliably without clear(), but we verify final state
        
        sm.stop()
        
    def test_process_input_not_running(self):
        """Test that input processing does nothing when not running."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        # Don't start the machine
        
        sm.process_input(1)
        
        # Should still be at state 0
        assert sm.current_state == 0
        
    def test_process_input_unconfigured(self):
        """Test that processing input on unconfigured machine raises error."""
        sm = statemachine.StateMachine()
        sm.is_active = True  # Force active state
        
        with pytest.raises(RuntimeError, match="not configured"):
            sm.process_input(0)
            
    def test_process_input_invalid_index(self):
        """Test that invalid input index raises error."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        with pytest.raises(ValueError, match="Invalid input index"):
            sm.process_input(5)
            
        sm.stop()
        
    def test_process_input_no_transition(self, qapp):
        """Test input that doesn't cause state transition."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 1]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        spy = QSignalSpy(sm.stateChanged)
        
        # Process input 0, should stay in state 0
        sm.process_input(0)
        qapp.processEvents()
        
        assert sm.current_state == 0
        assert len(spy) == 0  # No state change signal
        
        sm.stop()


class TestOutputHandling:
    """Tests for output handling."""
    
    def test_output_changed_on_state_entry(self, qapp):
        """Test that outputs change when entering a new state."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        # Machine starts at state 0 (all outputs off), force to state 1
        # State 1 has outputs [0, 1] -> output 1 turns on
        sm.force_state(1)
        qapp.processEvents()
        
        # Now create spy and transition back to state 0 which has [0, 0]
        # This should turn off output 1
        spy = QSignalSpy(sm.outputChanged)
        sm.process_input(1)  # From state 1, input 1 goes to state 0
        qapp.processEvents()
        
        # Should have 1 output change (output 1 off)
        assert len(spy) == 1
        assert spy[0][0] == 1  # output index
        assert spy[0][1] is False  # turned off
        
        sm.stop()
        
    def test_output_no_change(self, qapp):
        """Test that outputs with -1 don't change."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0, 0],
                          [1, 2, 0],
                          [2, 0, 1]], dtype=np.int32)
        outputs = np.array([[0, 0, 0],
                           [0, 1, -1],
                           [-1, -1, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        # Start by forcing to state 1 to set up initial outputs
        # State 1 has outputs [0, 1, -1] -> output 1 turns on
        sm.force_state(1)
        qapp.processEvents()
        
        assert sm.output_states[0] is False
        assert sm.output_states[1] is True
        assert sm.output_states[2] is False
        
        # Transition to state 2: [-1, -1, 1] -> [False, True, True]
        # Outputs 0 and 1 should remain unchanged (due to -1)
        sm.process_input(1)
        qapp.processEvents()
        
        assert sm.output_states[0] is False  # Should remain False (no change)
        assert sm.output_states[1] is True   # Should remain True (no change)
        assert sm.output_states[2] is True   # Should turn on
        
        sm.stop()
        
    def test_get_output_state(self):
        """Test get_output_state method."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        
        assert sm.get_output_state(0) is False
        assert sm.get_output_state(1) is False
        
    def test_get_output_state_invalid_index(self):
        """Test get_output_state with invalid index."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        
        with pytest.raises(ValueError, match="Invalid output index"):
            sm.get_output_state(5)


class TestForceState:
    """Tests for force_state method."""
    
    def test_force_state_basic(self, qapp):
        """Test forcing a state transition."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        spy = QSignalSpy(sm.stateChanged)
        
        sm.force_state(1)
        qapp.processEvents()
        
        assert sm.current_state == 1
        assert len(spy) == 1
        
        sm.stop()
        
    def test_force_state_to_end(self, qapp):
        """Test forcing transition to END state using -1."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        sm.force_state(1)
        qapp.processEvents()
        
        sm.force_state(-1)
        qapp.processEvents()
        
        assert sm.current_state == 1  # Last state (index 1)
        
        sm.stop()
        
    def test_force_state_unconfigured(self):
        """Test force_state on unconfigured machine raises error."""
        sm = statemachine.StateMachine()
        with pytest.raises(RuntimeError, match="not configured"):
            sm.force_state(0)
            
    def test_force_state_invalid_index(self):
        """Test force_state with invalid index."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        with pytest.raises(ValueError, match="Invalid state index"):
            sm.force_state(5)
            
        sm.stop()
        
    def test_force_state_same_state(self, qapp):
        """Test forcing to same state doesn't trigger transition."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        spy = QSignalSpy(sm.stateChanged)
        
        sm.force_state(0)  # Already at state 0
        qapp.processEvents()
        
        assert len(spy) == 0  # No state change
        
        sm.stop()


class TestForceOutput:
    """Tests for force_output method."""
    
    def test_force_output_basic(self, qapp):
        """Test forcing an output value."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        spy = QSignalSpy(sm.outputChanged)
        
        sm.force_output(1, True)
        qapp.processEvents()
        
        assert sm.output_states[1] is True
        assert len(spy) == 1
        
        sm.stop()
        
    def test_force_output_same_value(self, qapp):
        """Test forcing output to same value doesn't emit signal."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        spy = QSignalSpy(sm.outputChanged)
        
        sm.force_output(0, False)  # Already False
        qapp.processEvents()
        
        assert len(spy) == 0
        
        sm.stop()
        
    def test_force_output_unconfigured(self):
        """Test force_output on unconfigured machine raises error."""
        sm = statemachine.StateMachine()
        with pytest.raises(RuntimeError, match="not configured"):
            sm.force_output(0, True)
            
    def test_force_output_invalid_index(self):
        """Test force_output with invalid index."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        with pytest.raises(ValueError, match="Invalid output index"):
            sm.force_output(5, True)
            
        sm.stop()


class TestIntegerOutputs:
    """Tests for integer outputs functionality."""
    
    def test_integer_output_emitted(self, qapp):
        """Test that integer output signal is emitted."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        int_outputs = np.array([0, 42])  # State 1 has integer output 42
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.set_integer_outputs(int_outputs)
        sm.start()
        
        spy = QSignalSpy(sm.integerOutput)
        
        sm.force_state(1)
        qapp.processEvents()
        
        assert len(spy) == 1
        assert spy[0][0] == 42
        
        sm.stop()
        
    def test_integer_output_zero_not_emitted(self, qapp):
        """Test that zero integer output is not emitted."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        int_outputs = np.array([0, 0])  # Both states have no integer output
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.set_integer_outputs(int_outputs)
        sm.start()
        
        spy = QSignalSpy(sm.integerOutput)
        
        sm.force_state(1)
        qapp.processEvents()
        
        assert len(spy) == 0  # No integer output emitted
        
        sm.stop()


class TestStateTimers:
    """Tests for state timer functionality."""
    
    def test_state_timer_expiration(self, qapp):
        """Test that state timer causes transition."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), 0.1])  # State 1 timeout after 0.1s
        
        sm.set_state_matrix(matrix, timer_event_index=1)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        spy = QSignalSpy(sm.stateChanged)
        
        # Force to state 1, should timeout and return to state 0
        sm.force_state(1)
        qapp.processEvents()
        
        # Wait for timer
        QtCore.QThread.msleep(150)
        qapp.processEvents()
        
        assert sm.current_state == 0
        assert len(spy) >= 2  # Transition to state 1, then back to 0
        
        sm.stop()
        
    def test_set_state_timer_updates_current(self, qapp):
        """Test that set_state_timer updates timer if in that state."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix, timer_event_index=1)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        sm.force_state(1)
        qapp.processEvents()
        
        # Now update the timer for state 1
        sm.set_state_timer(1, 0.1)
        qapp.processEvents()
        
        spy = QSignalSpy(sm.stateChanged)
        
        # Wait for timer
        QtCore.QThread.msleep(150)
        qapp.processEvents()
        
        # Should have transitioned back to state 0
        assert sm.current_state == 0
        assert len(spy) >= 1
        
        sm.stop()
        
    def test_set_state_timer_invalid_state(self):
        """Test set_state_timer with invalid state index."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        with pytest.raises(ValueError, match="Invalid state index"):
            sm.set_state_timer(5, 1.0)
            
        sm.stop()


class TestSignalConnections:
    """Tests for signal connection functionality."""
    
    def test_connect_input_signal(self, qapp):
        """Test connecting external signal to input event."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        
        # Create external signal - need to create it on the class, not instance
        class SignalEmitter(QtCore.QObject):
            signal = QtCore.pyqtSignal()
        
        emitter = SignalEmitter()
        
        # Connect to input event 1
        sm.connect_input_signal(emitter.signal, 1)
        sm.start()
        
        # Force to state 1 so the input signal can trigger a transition
        sm.force_state(1)
        qapp.processEvents()
        
        spy = QSignalSpy(sm.stateChanged)
        
        # Emit the signal - from state 1, input 1 goes to state 0
        emitter.signal.emit()
        qapp.processEvents()
        
        assert sm.current_state == 0
        assert len(spy) == 1
        
        sm.stop()
        
    def test_event_processed_signal(self, qapp):
        """Test that eventProcessed signal is emitted."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        spy = QSignalSpy(sm.eventProcessed)
        
        # Force to state 1, then process input to transition back to state 0
        sm.force_state(1)
        qapp.processEvents()
        spy.clear() if hasattr(spy, 'clear') else None
        
        sm.process_input(1)
        qapp.processEvents()
        
        assert len(spy) >= 1
        # Check the last event processed
        last_event = spy[len(spy)-1] if len(spy) > 0 else spy[0]
        assert last_event[0] == 1  # event index
        assert isinstance(last_event[1], float)  # timestamp
        assert last_event[2] == 0  # next state (back to 0)
        
        sm.stop()
        
    def test_force_state_transition_signal(self, qapp):
        """Test forcing state via signal."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        spy = QSignalSpy(sm.stateChanged)
        
        sm.forceStateTransition.emit(1)
        qapp.processEvents()
        
        assert sm.current_state == 1
        assert len(spy) == 1
        
        sm.stop()


class TestQueryMethods:
    """Tests for query/getter methods."""
    
    def test_get_current_state(self):
        """Test get_current_state method."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        assert sm.get_current_state() == 0
        
        sm.force_state(1)
        assert sm.get_current_state() == 1
        
        sm.stop()
        
    def test_get_state_info(self):
        """Test get_state_info method."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), 1.5])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        info = sm.get_state_info()
        
        assert info['current_state'] == 0
        assert info['is_active'] is True
        assert info['is_processing'] is True
        assert info['is_configured'] is True
        assert info['num_states'] == 2
        assert info['num_inputs'] == 2
        assert info['num_outputs'] == 2
        assert info['output_states'] == [False, False]
        assert np.array_equal(info['state_timers'], timers)
        
        sm.stop()
        
    def test_get_transitions_from_state(self):
        """Test get_transitions_from_state method."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 2],
                          [2, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1],
                           [1, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        
        transitions = sm.get_transitions_from_state(1)
        assert np.array_equal(transitions, np.array([1, 2]))
        
    def test_get_transitions_from_state_invalid(self):
        """Test get_transitions_from_state with invalid state."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        
        with pytest.raises(ValueError, match="Invalid state index"):
            sm.get_transitions_from_state(5)
            
    def test_get_transitions_for_input(self):
        """Test get_transitions_for_input method."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 2],
                          [2, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1],
                           [1, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        
        transitions = sm.get_transitions_for_input(1)
        # State 0 has self-transition, state 1->2, state 2->0
        assert np.array_equal(transitions, np.array([0, 2, 0]))
        
    def test_get_transitions_for_input_invalid(self):
        """Test get_transitions_for_input with invalid input."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        
        with pytest.raises(ValueError, match="Invalid input index"):
            sm.get_transitions_for_input(5)
            
    def test_find_states_with_output(self):
        """Test find_states_with_output method."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 2],
                          [2, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1],
                           [1, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        
        # Find states where output 0 is on - only state 2 has it on
        states = sm.find_states_with_output(0, True)
        assert np.array_equal(states, np.array([2]))
        
        # Find states where output 1 is on
        states = sm.find_states_with_output(1, True)
        assert np.array_equal(states, np.array([1, 2]))
        
    def test_find_states_with_output_invalid(self):
        """Test find_states_with_output with invalid output."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        
        with pytest.raises(ValueError, match="Invalid output index"):
            sm.find_states_with_output(5, True)


class TestStringRepresentation:
    """Tests for __str__ method."""
    
    def test_str_unconfigured(self):
        """Test string representation of unconfigured machine."""
        sm = statemachine.StateMachine()
        s = str(sm)
        assert "Not configured" in s
        
    def test_str_configured(self):
        """Test string representation of configured machine."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        
        s = str(sm)
        assert "2 states" in s
        assert "2 inputs" in s
        assert "2 outputs" in s
        assert "State Matrix:" in s
        assert "State Outputs:" in s


class TestPauseResume:
    """Tests for pause and resume methods."""

    def test_pause_suspends_processing(self, qapp):
        """Test that pause suspends event processing."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])

        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        sm.force_state(1)
        qapp.processEvents()

        sm.pause()
        assert sm.is_active is True
        assert sm.is_processing is False

        # Events sent while paused should not cause a state transition
        sm.process_input(1)  # Would go to state 0 if processing
        qapp.processEvents()
        assert sm.current_state == 1  # Still in state 1

        sm.stop()

    def test_pause_queues_events(self, qapp):
        """Test that events received while paused are queued."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])

        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        sm.force_state(1)
        qapp.processEvents()

        sm.pause()
        sm.process_input(1)
        assert len(sm.suspended_events) == 1
        assert sm.suspended_events[0][0] == 1  # event index

        sm.stop()

    def test_resume_processes_queued_events(self, qapp):
        """Test that resume processes events queued during pause."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])

        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        sm.force_state(1)
        qapp.processEvents()

        sm.pause()
        sm.process_input(1)  # queued: would transition to state 0
        assert sm.current_state == 1  # not yet processed

        sm.resume()
        qapp.processEvents()
        assert sm.current_state == 0  # now processed
        assert sm.is_processing is True

        sm.stop()

    def test_resume_discard_queued_events(self, qapp):
        """Test that resume with process_queued=False discards queued events."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])

        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        sm.force_state(1)
        qapp.processEvents()

        sm.pause()
        sm.process_input(1)  # queued

        sm.resume(process_queued=False)
        qapp.processEvents()
        assert sm.current_state == 1  # event discarded, still in state 1
        assert sm.is_processing is True

        sm.stop()

    def test_pause_not_active_raises(self):
        """Test that pausing an inactive machine raises RuntimeError."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])

        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)

        with pytest.raises(RuntimeError, match="not active"):
            sm.pause()

    def test_resume_not_active_raises(self):
        """Test that resuming an inactive machine raises RuntimeError."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])

        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)

        with pytest.raises(RuntimeError, match="not active"):
            sm.resume()

    def test_resume_already_processing_raises(self):
        """Test that resuming while already processing raises RuntimeError."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])

        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()

        with pytest.raises(RuntimeError, match="already processing"):
            sm.resume()

        sm.stop()


class TestComplexScenarios:
    """Tests for complex state machine scenarios."""
    
    def test_multi_state_transitions(self, qapp):
        """Test multiple state transitions in sequence."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0, 0],
                          [1, 2, 1],
                          [2, 0, 2]], dtype=np.int32)
        outputs = np.array([[0, 0, 0],
                           [0, 1, 0],
                           [0, 0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        assert sm.current_state == 0
        
        # Force to state 1 to begin the sequence
        sm.force_state(1)
        qapp.processEvents()
        assert sm.current_state == 1
        
        sm.process_input(1)
        qapp.processEvents()
        assert sm.current_state == 2
        
        sm.process_input(1)
        qapp.processEvents()
        assert sm.current_state == 0
        
        sm.stop()
        
    def test_output_persistence_across_states(self, qapp):
        """Test that outputs persist when marked as no-change (-1)."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0, 0],
                          [1, 2, 0],
                          [2, 0, 1]], dtype=np.int32)
        outputs = np.array([[0, 0, 0],
                           [-1, 1, 0],  # Keep output 0 from previous state
                           [-1, -1, 1]], dtype=np.int32)  # Keep outputs 0 and 1
        timers = np.array([float('inf'), float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        # Force to state 1 first. State 1 has [-1, 1, 0] so output 1 turns on,
        # output 0 stays at its default (False), output 2 turns off
        sm.force_state(1)
        qapp.processEvents()
        assert sm.output_states[0] is False  # -1 kept it at default False
        assert sm.output_states[1] is True   # Turned on
        assert sm.output_states[2] is False  # Turned off
        
        # Transition to state 2: [-1, -1, 1] keeps outputs 0 and 1, turns on output 2
        sm.process_input(1)
        qapp.processEvents()
        assert sm.output_states[0] is False  # -1 keeps it False
        assert sm.output_states[1] is True   # -1 keeps it True
        assert sm.output_states[2] is True   # Turned on
        
        sm.stop()
        
    def test_forced_output_override(self, qapp):
        """Test that forced outputs override state-based outputs."""
        sm = statemachine.StateMachine()
        matrix = np.array([[0, 0],
                          [1, 0]], dtype=np.int32)
        outputs = np.array([[0, 0],
                           [0, 1]], dtype=np.int32)
        timers = np.array([float('inf'), float('inf')])
        
        sm.set_state_matrix(matrix)
        sm.set_state_outputs(outputs)
        sm.set_state_timers(timers)
        sm.start()
        
        # Force output 1 to on (state 0 normally has it off)
        sm.force_output(1, True)
        qapp.processEvents()
        assert sm.output_states[1] is True
        
        # Force transition to state 1, which sets output 1 to on (same value)
        sm.force_state(1)
        qapp.processEvents()
        assert sm.output_states[1] is True
        
        # Transition back to state 0 via input, which sets output 1 to off
        sm.process_input(1)
        qapp.processEvents()
        assert sm.output_states[1] is False
        
        sm.stop()
