"""
Unit tests for statematrix module.

Tests cover:
- StateMatrix initialization
- State construction and transitions
- Input validation
- Getter methods and data retrieval
- Extra timers functionality
- Utility methods
"""

import pytest
import numpy as np
import tempfile
import h5py
from phonotaxis import statematrix


class TestStateMatrixInit:
    """Tests for StateMatrix initialization."""
    
    def test_init_empty(self):
        """Test initialization with no inputs or outputs."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[])
        
        assert len(sm.inputs) == 0
        assert len(sm.outputs) == 0
        assert sm.n_outputs == 0
        assert len(sm.extra_timers_names) == 0
        
    def test_init_with_inputs(self):
        """Test initialization with input names."""
        sm = statematrix.StateMatrix(inputs=['C', 'L', 'R'], outputs=[])
        
        assert len(sm.inputs) == 3
        assert sm.inputs['C'] == 0
        assert sm.inputs['L'] == 1
        assert sm.inputs['R'] == 2
        
    def test_init_with_outputs(self):
        """Test initialization with output names."""
        sm = statematrix.StateMatrix(inputs=[], outputs=['valve', 'led'])
        
        assert len(sm.outputs) == 2
        assert sm.outputs['valve'] == 0
        assert sm.outputs['led'] == 1
        assert sm.n_outputs == 2
        
    def test_init_creates_end_state(self):
        """Test that END state is automatically created at index 0."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[])
        
        assert 'END' in sm.states
        assert sm.states['END'] == 0
        assert sm.get_end_state_index() == 0
        
    def test_end_state_outputs_off(self):
        """Test that END state has all outputs set to OFF."""
        sm = statematrix.StateMatrix(inputs=[], outputs=['valve', 'led', 'buzzer'])
        
        outputs = sm.get_outputs()
        end_state_idx = sm.get_end_state_index()
        
        # END state should have all outputs OFF (0)
        assert np.all(outputs[end_state_idx] == 0)
        
    def test_init_creates_events(self):
        """Test that events dictionary is properly created from inputs."""
        sm = statematrix.StateMatrix(inputs=['C', 'L'], outputs=[])
        
        # Should have Cin, Cout, Lin, Lout, Tup, and Forced
        assert 'Cin' in sm.events
        assert 'Cout' in sm.events
        assert 'Lin' in sm.events
        assert 'Lout' in sm.events
        assert 'Tup' in sm.events
        assert 'Forced' in sm.events
        
        # Check correct indices
        assert sm.events['Cin'] == 0
        assert sm.events['Cout'] == 1
        assert sm.events['Lin'] == 2
        assert sm.events['Lout'] == 3
        assert sm.events['Forced'] == -1
        
    def test_init_with_extratimers(self):
        """Test initialization with extra timers."""
        sm = statematrix.StateMatrix(
            inputs=['C'], 
            outputs=[], 
            extratimers=['timer1', 'timer2']
        )
        
        assert len(sm.extra_timers_names) == 2
        assert 'timer1' in sm.extra_timers_names
        assert 'timer2' in sm.extra_timers_names
        # Extra timers should appear in events dict
        assert 'timer1' in sm.events
        assert 'timer2' in sm.events


class TestStateMatrixConstruction:
    """Tests for building state matrices."""
    
    def test_add_simple_state(self):
        """Test adding a simple state with no transitions."""
        sm = statematrix.StateMatrix(inputs=['C'], outputs=[])
        sm.add_state(name='state1', statetimer=1.0)
        
        assert 'state1' in sm.states
        assert sm.states['state1'] == 1  # END is 0, so state1 is 1
        
    def test_add_state_with_transition(self):
        """Test adding state with a transition."""
        sm = statematrix.StateMatrix(inputs=['C'], outputs=[])
        sm.add_state(name='state1', statetimer=1.0, 
                    transitions={'Cin': 'state2'})
        
        assert 'state1' in sm.states
        assert 'state2' in sm.states
        
        matrix = sm.get_matrix()
        state1_idx = sm.states['state1']
        state2_idx = sm.states['state2']
        cin_idx = sm.events['Cin']
        
        assert matrix[state1_idx, cin_idx] == state2_idx
        
    def test_add_state_with_timer(self):
        """Test that state timer is set correctly."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[])
        sm.add_state(name='wait', statetimer=5.0)
        
        timers = sm.get_state_timers()
        wait_idx = sm.states['wait']
        assert timers[wait_idx] == 5.0
        
    def test_add_state_with_infinite_timer(self):
        """Test state with infinite timer."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[])
        sm.add_state(name='wait', statetimer=float('inf'))
        
        timers = sm.get_state_timers()
        wait_idx = sm.states['wait']
        assert np.isinf(timers[wait_idx])
        
    def test_add_state_with_outputs_on(self):
        """Test turning outputs on."""
        sm = statematrix.StateMatrix(inputs=[], outputs=['led', 'valve'])
        sm.add_state(name='reward', outputsOn=['led', 'valve'])
        
        outputs = sm.get_outputs()
        reward_idx = sm.states['reward']
        assert outputs[reward_idx, 0] == 1  # led on
        assert outputs[reward_idx, 1] == 1  # valve on
        
    def test_add_state_with_outputs_off(self):
        """Test turning outputs off."""
        sm = statematrix.StateMatrix(inputs=[], outputs=['led', 'valve'])
        sm.add_state(name='iti', outputsOff=['led', 'valve'])
        
        outputs = sm.get_outputs()
        iti_idx = sm.states['iti']
        assert outputs[iti_idx, 0] == 0  # led off
        assert outputs[iti_idx, 1] == 0  # valve off
        
    def test_add_state_with_mixed_outputs(self):
        """Test turning some outputs on and others off."""
        sm = statematrix.StateMatrix(inputs=[], outputs=['led', 'valve'])
        sm.add_state(name='state1', outputsOn=['led'], outputsOff=['valve'])
        
        outputs = sm.get_outputs()
        state1_idx = sm.states['state1']
        assert outputs[state1_idx, 0] == 1   # led on
        assert outputs[state1_idx, 1] == 0   # valve off
        
    def test_add_state_with_integer_output(self):
        """Test integer output."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[])
        sm.add_state(name='stim', integerOut=42)
        
        int_outputs = sm.get_integer_outputs()
        stim_idx = sm.states['stim']
        assert int_outputs[stim_idx] == 42
        
    def test_update_existing_state(self):
        """Test that adding a state with existing name updates it."""
        sm = statematrix.StateMatrix(inputs=['C'], outputs=[])
        sm.add_state(name='state1', statetimer=1.0)
        original_idx = sm.states['state1']
        
        sm.add_state(name='state1', statetimer=2.0, 
                    transitions={'Cin': 'state2'})
        
        # Should keep same index
        assert sm.states['state1'] == original_idx
        # Timer should be updated
        timers = sm.get_state_timers()
        assert timers[original_idx] == 2.0
        
    def test_multiple_transitions(self):
        """Test state with multiple transitions."""
        sm = statematrix.StateMatrix(inputs=['C', 'L', 'R'], outputs=[])
        sm.add_state(name='choice', 
                    transitions={'Lin': 'left_reward', 
                                'Rin': 'right_reward',
                                'Tup': 'timeout'})
        
        matrix = sm.get_matrix()
        choice_idx = sm.states['choice']
        
        assert matrix[choice_idx, sm.events['Lin']] == sm.states['left_reward']
        assert matrix[choice_idx, sm.events['Rin']] == sm.states['right_reward']
        assert matrix[choice_idx, sm.events['Tup']] == sm.states['timeout']
        
    def test_self_transition(self):
        """Test state that transitions to itself."""
        sm = statematrix.StateMatrix(inputs=['C'], outputs=[])
        sm.add_state(name='loop', transitions={'Cin': 'loop'})
        
        matrix = sm.get_matrix()
        loop_idx = sm.states['loop']
        assert matrix[loop_idx, sm.events['Cin']] == loop_idx


class TestStateMatrixValidation:
    """Tests for input validation."""
    
    def test_invalid_event_name(self):
        """Test that invalid event names raise ValueError."""
        sm = statematrix.StateMatrix(inputs=['C'], outputs=[])
        
        with pytest.raises(ValueError, match="Invalid event name"):
            sm.add_state(name='state1', 
                        transitions={'invalid_event': 'state2'})
            
    def test_invalid_output_name_on(self):
        """Test that invalid output names in outputsOn raise ValueError."""
        sm = statematrix.StateMatrix(inputs=[], outputs=['led'])
        
        with pytest.raises(ValueError, match="Invalid output name"):
            sm.add_state(name='state1', outputsOn=['invalid_output'])
            
    def test_invalid_output_name_off(self):
        """Test that invalid output names in outputsOff raise ValueError."""
        sm = statematrix.StateMatrix(inputs=[], outputs=['led'])
        
        with pytest.raises(ValueError, match="Invalid output name"):
            sm.add_state(name='state1', outputsOff=['invalid_output'])
            
    def test_invalid_extratimer_name(self):
        """Test that invalid timer names in trigger raise ValueError."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[], 
                                     extratimers=['timer1'])
        
        with pytest.raises(ValueError, match="Invalid extra timer name"):
            sm.add_state(name='state1', trigger=['invalid_timer'])
            
    def test_duplicate_extratimer_raises_exception(self):
        """Test that adding duplicate extra timer raises exception."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[])
        sm._add_extratimer('timer1')
        
        with pytest.raises(Exception, match="already been defined"):
            sm._add_extratimer('timer1')
            
    def test_set_nonexistent_extratimer_raises_exception(self):
        """Test that setting non-existent extra timer raises exception."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[])
        
        with pytest.raises(Exception, match="has no extratimer"):
            sm.set_extratimer('nonexistent', 1.0)
            
    def test_extratimer_multiple_states_raises_error(self):
        """Test that assigning same extra timer to multiple states raises error."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[], 
                                     extratimers=['timer1'])
        sm.add_state(name='state1', trigger=['timer1'])
        
        # Trying to assign the same timer to a different state should raise error
        with pytest.raises(ValueError, match="already triggered by state"):
            sm.add_state(name='state2', trigger=['timer1'])
            
    def test_extratimer_same_state_reentry_allowed(self):
        """Test that updating same state with same timer is allowed."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[], 
                                     extratimers=['timer1'])
        sm.add_state(name='state1', trigger=['timer1'])
        
        # Updating the same state should not raise error
        sm.add_state(name='state1', trigger=['timer1'], statetimer=5.0)
        
        triggers = sm.get_extra_triggers()
        assert triggers[0] == sm.states['state1']


class TestStateMatrixGetters:
    """Tests for getter methods."""
    
    def test_get_matrix_shape(self):
        """Test that get_matrix returns correct shape."""
        sm = statematrix.StateMatrix(inputs=['C', 'L'], outputs=[])
        sm.add_state(name='state1')
        sm.add_state(name='state2')
        
        matrix = sm.get_matrix()
        # Should have END + state1 + state2 = 3 states
        # Should have Cin, Cout, Lin, Lout, Tup = 5 events
        assert matrix.shape == (3, 5)
        
    def test_get_matrix_dtype(self):
        """Test that get_matrix returns int32 array."""
        sm = statematrix.StateMatrix(inputs=['C'], outputs=[])
        matrix = sm.get_matrix()
        
        assert isinstance(matrix, np.ndarray)
        assert matrix.dtype == np.int32
        
    def test_get_state_timers_shape(self):
        """Test that get_state_timers returns correct shape."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[])
        sm.add_state(name='state1')
        
        timers = sm.get_state_timers()
        assert len(timers) == 2  # END + state1
        
    def test_get_state_timers_dtype(self):
        """Test that get_state_timers returns float64 array."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[])
        timers = sm.get_state_timers()
        
        assert isinstance(timers, np.ndarray)
        assert timers.dtype == np.float64
        
    def test_get_outputs_shape(self):
        """Test that get_outputs returns correct shape."""
        sm = statematrix.StateMatrix(inputs=[], outputs=['led', 'valve'])
        sm.add_state(name='state1')
        
        outputs = sm.get_outputs()
        assert outputs.shape == (2, 2)  # 2 states, 2 outputs
        
    def test_get_outputs_dtype(self):
        """Test that get_outputs returns int32 array."""
        sm = statematrix.StateMatrix(inputs=[], outputs=['led'])
        outputs = sm.get_outputs()
        
        assert isinstance(outputs, np.ndarray)
        assert outputs.dtype == np.int32
        
    def test_get_outputs_nochange_default(self):
        """Test that outputs default to NOCHANGE (-1)."""
        sm = statematrix.StateMatrix(inputs=[], outputs=['led', 'valve'])
        sm.add_state(name='state1')  # No outputs specified
        
        outputs = sm.get_outputs()
        state1_idx = sm.states['state1']
        assert outputs[state1_idx, 0] == statematrix.NOCHANGE
        assert outputs[state1_idx, 1] == statematrix.NOCHANGE
        
    def test_get_integer_outputs_dtype(self):
        """Test that get_integer_outputs returns int32 array."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[])
        int_outputs = sm.get_integer_outputs()
        
        assert isinstance(int_outputs, np.ndarray)
        assert int_outputs.dtype == np.int32
        
    def test_get_extra_timers_dtype(self):
        """Test that get_extra_timers returns float64 array."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[], 
                                     extratimers=['timer1'])
        extra_timers = sm.get_extra_timers()
        
        assert isinstance(extra_timers, np.ndarray)
        assert extra_timers.dtype == np.float64
        
    def test_get_extra_triggers_dtype(self):
        """Test that get_extra_triggers returns int32 array."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[], 
                                     extratimers=['timer1'])
        extra_triggers = sm.get_extra_triggers()
        
        assert isinstance(extra_triggers, np.ndarray)
        assert extra_triggers.dtype == np.int32
        
    def test_get_timer_event_index(self):
        """Test that timer event index is correct."""
        sm = statematrix.StateMatrix(inputs=['C', 'L'], outputs=[])
        tup_idx = sm.get_timer_event_index()
        
        assert tup_idx == sm.events['Tup']
        # Should be last regular event (before extra timers)
        assert tup_idx == 4  # Cin, Cout, Lin, Lout, Tup
        
    def test_get_states(self):
        """Test that get_states returns bidirectional mapping."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[])
        sm.add_state(name='state1')
        
        states = sm.get_states()
        assert states['END'] == 0
        assert states['state1'] == 1
        assert states.inverse[0] == 'END'
        assert states.inverse[1] == 'state1'


class TestStateMatrixExtraTimers:
    """Tests for extra timer functionality."""
    
    def test_add_extratimer(self):
        """Test adding an extra timer."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[])
        sm._add_extratimer('punishment', 5.0)
        
        assert 'punishment' in sm.extra_timers_names
        assert 'punishment' in sm.events
        
    def test_extratimer_in_events(self):
        """Test that extra timers appear in events dict."""
        sm = statematrix.StateMatrix(inputs=['C'], outputs=[], 
                                     extratimers=['timer1'])
        
        # Timer should be after all input events
        assert sm.events['timer1'] == 3  # After Cin, Cout, Tup
        
    def test_set_extratimer_duration(self):
        """Test setting extra timer duration."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[], 
                                     extratimers=['timer1'])
        sm.set_extratimer('timer1', 10.0)
        
        extra_timers = sm.get_extra_timers()
        assert extra_timers[0] == 10.0
        
    def test_extratimer_trigger(self):
        """Test that extra timer trigger is set by state."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[], 
                                     extratimers=['timer1'])
        sm.add_state(name='state1', trigger=['timer1'])
        
        triggers = sm.get_extra_triggers()
        state1_idx = sm.states['state1']
        assert triggers[0] == state1_idx
        
    def test_extratimer_default_trigger(self):
        """Test that extra timer without trigger returns -1."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[], 
                                     extratimers=['timer1'])
        
        # Should return -1 for timers without assigned triggers
        triggers = sm.get_extra_triggers()
        assert triggers[0] == -1
            
    def test_extratimer_trigger_assigned(self):
        """Test that extra timer trigger works after being assigned."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[], 
                                     extratimers=['timer1'])
        sm.add_state(name='state1', trigger=['timer1'])
        
        # Should not raise error after trigger is assigned
        triggers = sm.get_extra_triggers()
        state1_idx = sm.states['state1']
        assert triggers[0] == state1_idx
        
    def test_multiple_extratimers(self):
        """Test multiple extra timers."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[], 
                                     extratimers=['timer1', 'timer2', 'timer3'])
        
        assert len(sm.extra_timers_names) == 3
        assert len(sm.get_extra_timers()) == 3
        assert len(sm.get_extra_triggers()) == 3


class TestStateMatrixUtilities:
    """Tests for utility methods."""
    
    def test_reset_transitions(self):
        """Test that reset_transitions clears all transitions."""
        sm = statematrix.StateMatrix(inputs=['C'], outputs=['led'])
        sm.add_state(name='state1', statetimer=1.0, 
                    transitions={'Cin': 'state2'}, 
                    outputsOn=['led'])
        
        sm.reset_transitions()
        
        # All transitions should be self-loops
        matrix = sm.get_matrix()
        for i in range(matrix.shape[0]):
            assert np.all(matrix[i] == i)
            
        # Timers should be infinite
        timers = sm.get_state_timers()
        assert np.all(np.isinf(timers))
        
        # Outputs: END state (0) should be OFF, other states should be NOCHANGE
        outputs = sm.get_outputs()
        assert np.all(outputs[0] == 0)  # END state outputs are OFF
        for ind in range(1, outputs.shape[0]):
            assert np.all(outputs[ind] == statematrix.NOCHANGE)  # Other states are NOCHANGE

    def test_analyze_matrix_properties(self):
        """Test matrix property analysis."""
        sm = statematrix.StateMatrix(inputs=['C'], outputs=[])
        sm.add_state(name='state1', transitions={'Cin': 'state2'})
        sm.add_state(name='state2', transitions={'Cin': 'state1'})
        
        props = sm.analyze_matrix_properties()
        
        assert 'n_states' in props
        assert 'n_events' in props
        assert 'reachable_states' in props
        assert 'unreachable_states' in props
        assert 'dead_end_states' in props
        assert 'is_fully_connected' in props
        
        assert props['n_states'] == 3  # END + state1 + state2
        
    def test_analyze_unreachable_states(self):
        """Test detection of unreachable states."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[])
        sm.add_state(name='state1')
        sm.add_state(name='state2')  # Not reachable from any state
        
        props = sm.analyze_matrix_properties()
        
        # state2 should be unreachable
        assert len(props['unreachable_states']) > 0
        
    def test_analyze_dead_end_states(self):
        """Test detection of dead-end states."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[])
        sm.add_state(name='dead_end')  # Only self-transitions (default)
        
        props = sm.analyze_matrix_properties()
        
        # Should detect states with only self-transitions
        assert len(props['dead_end_states']) > 0
        
    def test_str_representation(self):
        """Test string representation."""
        sm = statematrix.StateMatrix(inputs=['C'], outputs=['led'])
        sm.add_state(name='state1', statetimer=1.0, 
                    transitions={'Cin': 'state2'},
                    outputsOn=['led'])
        
        str_repr = str(sm)
        
        # Should contain state names
        assert 'END' in str_repr
        assert 'state1' in str_repr
        assert 'state2' in str_repr
        
    def test_append_to_hdf5_file(self):
        """Test saving to HDF5 file."""
        sm = statematrix.StateMatrix(inputs=['C'], outputs=['led'])
        sm.add_state(name='state1')
        
        with tempfile.NamedTemporaryFile(suffix='.h5', delete=False) as tmp:
            with h5py.File(tmp.name, 'w') as h5file:
                sm.append_to_file(h5file)
                
                # Check that stateMatrix group was created
                assert 'stateMatrix' in h5file
                assert 'eventsNames' in h5file['stateMatrix']
                assert 'outputsNames' in h5file['stateMatrix']
                assert 'statesNames' in h5file['stateMatrix']


class TestStateMatrixEdgeCases:
    """Tests for edge cases and error conditions."""
    
    def test_empty_state_matrix(self):
        """Test state matrix with only END state."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[])
        
        matrix = sm.get_matrix()
        assert matrix.shape[0] == 1  # Only END state
        
    def test_no_inputs_valid(self):
        """Test that state matrix works with no inputs."""
        sm = statematrix.StateMatrix(inputs=[], outputs=['led'])
        sm.add_state(name='state1', outputsOn=['led'])
        
        # Should only have 'Tup' and 'Forced' events
        assert 'Tup' in sm.events
        assert 'Forced' in sm.events
        
    def test_no_outputs_valid(self):
        """Test that state matrix works with no outputs."""
        sm = statematrix.StateMatrix(inputs=['C'], outputs=[])
        sm.add_state(name='state1', transitions={'Cin': 'state2'})
        
        outputs = sm.get_outputs()
        assert outputs.shape[1] == 0  # No output columns
        
    def test_matrix_validation_invalid_indices(self):
        """Test that get_matrix validates state indices."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[])
        sm.add_state(name='state1')
        
        # Manually corrupt the state matrix
        sm.state_matrix[0][0] = 999  # Invalid state index
        
        with pytest.raises(ValueError, match="invalid state indices"):
            sm.get_matrix()
            
    def test_output_validation_invalid_values(self):
        """Test that get_outputs validates output values."""
        sm = statematrix.StateMatrix(inputs=[], outputs=['led'])
        sm.add_state(name='state1')
        
        # Manually corrupt outputs
        sm.state_outputs[0][0] = 5  # Invalid value (not -1, 0, or 1)
        
        with pytest.raises(ValueError, match="must contain only"):
            sm.get_outputs()
            
    def test_large_state_matrix(self):
        """Test with many states to ensure scalability."""
        sm = statematrix.StateMatrix(inputs=['C'], outputs=[])
        
        # Add 100 states
        for i in range(100):
            sm.add_state(name=f'state{i}')
            
        matrix = sm.get_matrix()
        assert matrix.shape[0] == 101  # 100 states + END
        
    def test_zero_timer(self):
        """Test state with zero duration timer."""
        sm = statematrix.StateMatrix(inputs=[], outputs=[])
        sm.add_state(name='instant', statetimer=0.0)
        
        timers = sm.get_state_timers()
        instant_idx = sm.states['instant']
        assert timers[instant_idx] == 0.0


class TestStateMatrixIntegration:
    """Integration tests for complete workflows."""
    
    def test_simple_two_choice_task(self):
        """Test a simple two-choice task state matrix."""
        sm = statematrix.StateMatrix(
            inputs=['C', 'L', 'R'],
            outputs=['centerLED', 'leftLED', 'rightLED', 'leftValve', 'rightValve']
        )
        
        # Wait for center poke
        sm.add_state(name='wait_for_cpoke', statetimer=float('inf'),
                    transitions={'Cin': 'play_stimulus'},
                    outputsOn=['centerLED'])
        
        # Play stimulus
        sm.add_state(name='play_stimulus', statetimer=0.5,
                    transitions={'Tup': 'wait_for_choice'},
                    integerOut=1)
        
        # Wait for choice
        sm.add_state(name='wait_for_choice', statetimer=5.0,
                    transitions={'Lin': 'left_reward', 
                               'Rin': 'right_reward',
                               'Tup': 'END'},
                    outputsOn=['leftLED', 'rightLED'])
        
        # Left reward
        sm.add_state(name='left_reward', statetimer=0.2,
                    transitions={'Tup': 'END'},
                    outputsOn=['leftValve'])
        
        # Right reward
        sm.add_state(name='right_reward', statetimer=0.2,
                    transitions={'Tup': 'END'},
                    outputsOn=['rightValve'])
        
        # Verify structure
        matrix = sm.get_matrix()
        assert matrix.shape[0] == 6  # 5 states + END
        
        # Verify transitions work
        choice_idx = sm.states['wait_for_choice']
        left_reward_idx = sm.states['left_reward']
        right_reward_idx = sm.states['right_reward']
        
        assert matrix[choice_idx, sm.events['Lin']] == left_reward_idx
        assert matrix[choice_idx, sm.events['Rin']] == right_reward_idx
        
    def test_state_matrix_with_extratimer(self):
        """Test state matrix with extra timer for punishment."""
        sm = statematrix.StateMatrix(
            inputs=['C'],
            outputs=['led'],
            extratimers=['punishment']
        )
        
        sm.set_extratimer('punishment', 10.0)
        
        sm.add_state(name='correct', 
                    transitions={'Tup': 'END'})
        
        sm.add_state(name='error', 
                    transitions={'Tup': 'timeout'},
                    trigger=['punishment'])
        
        sm.add_state(name='timeout',
                    transitions={'punishment': 'END'},
                    outputsOff=['led'])
        
        # Verify timer is set correctly
        extra_timers = sm.get_extra_timers()
        assert extra_timers[0] == 10.0
        
        # Verify trigger is set
        triggers = sm.get_extra_triggers()
        error_idx = sm.states['error']
        assert triggers[0] == error_idx


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
