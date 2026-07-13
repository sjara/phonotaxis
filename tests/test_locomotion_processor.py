import pytest
import numpy as np
import sys
sys.path.append('/home/jaralab/src')
from ptparadigms.locomotion_processor import LocomotionProcessor

def test_locomotion_processor_init():
    proc = LocomotionProcessor(buffer_size=10)
    assert proc.buffer_size == 10
    assert proc.prev_x == -1.0
    assert proc.prev_y == -1.0
    assert proc.prev_orientation == 0.0

def test_locomotion_processor_velocity_and_heading():
    proc = LocomotionProcessor(buffer_size=10, smoothing_window=1)
    proc.update_contingency_params(
        velocity_threshold=10.0,
        angular_velocity_min=0.0,
        angular_velocity_max=10.0,
        point_threshold=100
    )
    
    # First frame (initializes prev_values)
    state1 = proc.process_frame(timestamp=0.0, centroid=(100, 100), orientation=0.0)
    assert state1.velocity == 0.0
    assert state1.heading == 0.0
    assert state1.angular_velocity == 0.0
    
    # Second frame (moving right, no orientation change)
    state2 = proc.process_frame(timestamp=1.0, centroid=(120, 100), orientation=0.0)
    assert state2.velocity == 20.0  # 20 pixels / 1 sec
    assert abs(state2.heading - 0.0) < 1e-5  # Moving along positive x axis
    assert state2.angular_velocity == 0.0

def test_locomotion_processor_in_place_rotation():
    proc = LocomotionProcessor(buffer_size=10, smoothing_window=1)
    proc.update_contingency_params(
        velocity_threshold=0.0,
        angular_velocity_min=1.0,
        angular_velocity_max=5.0,
        point_threshold=100
    )
    
    # First frame (initializes prev_values)
    proc.process_frame(timestamp=0.0, centroid=(100, 100), orientation=0.0)
    
    # Second frame (stationary position, rotating in place by 0.5 radians)
    state = proc.process_frame(timestamp=0.5, centroid=(100, 100), orientation=0.5)
    
    # Distance moved is 0.0, so velocity should be 0.0
    assert state.velocity == 0.0
    # Rotation rate: 0.5 rad / 0.5 sec = 1.0 rad/s
    assert abs(state.angular_velocity - 1.0) < 1e-5
    assert proc.prev_orientation == 0.5

def test_locomotion_processor_orientation_wrapping():
    proc = LocomotionProcessor(buffer_size=10, smoothing_window=1)
    
    # First frame (initializes prev_values near the boundary)
    proc.process_frame(timestamp=0.0, centroid=(100, 100), orientation=np.pi/2 - 0.1)
    
    # Second frame (wraps across the pi/2 boundary to -pi/2 + 0.1)
    state = proc.process_frame(timestamp=1.0, centroid=(100, 100), orientation=-np.pi/2 + 0.1)
    
    # Total change should be 0.2 rad (wrapped to [-pi/2, pi/2])
    # Rate: 0.2 rad / 1.0 sec = 0.2 rad/s
    assert abs(state.angular_velocity - 0.2) < 1e-5

def test_locomotion_processor_smoothing():
    proc = LocomotionProcessor(buffer_size=20, smoothing_window=10)
    for i in range(10):
        state = proc.process_frame(timestamp=float(i), centroid=(100, 100), orientation=0.0)
    assert state.velocity == 0.0
    
    state11 = proc.process_frame(timestamp=10.0, centroid=(110, 100), orientation=0.0)
    assert state11.velocity < 2.0
