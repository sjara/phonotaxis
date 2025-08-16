#!/usr/bin/env python3
"""
Test script for the new dispatcher implementation.

This script tests the basic functionality of the new Dispatcher class
to ensure it works correctly with the modern StateMachine and StateMatrix.
"""

import sys
import time
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget
from PyQt6.QtCore import QTimer

from phonotaxis.dispatcher import Dispatcher
from phonotaxis.statematrix import StateMatrix


# Create a simple state matrix
sm = StateMatrix(inputs={'C':0, 'L':1, 'R':2},
                outputs={'centerLED':0, 'leftLED':1, 'rightLED':2})

# Add states
sm.add_state(name='wait_for_cpoke', statetimer=2,
            transitions={'Cin':'stim_on', 'Tup':'stim_on'},
            outputsOff=['centerLED'])
sm.add_state(name='stim_on', statetimer=0.5,
            transitions={'Tup':'stim_off'},
            outputsOn=['centerLED'])
sm.add_state(name='stim_off', statetimer=0.5,
            transitions={'Tup':'END'},
            outputsOff=['centerLED'])

print(sm)

"""Test dispatcher with GUI in a Qt application."""
print("\nTesting Dispatcher with GUI")
print("=" * 30)

app = QApplication([])

# Create dispatcher with GUI
dispatcher = Dispatcher(create_gui=True)
# Connect log_message signal to print function
dispatcher.log_message.connect(lambda message: print(f"Dispatcher: {message}"))

assert dispatcher.gui is not None, "GUI should be created"
print("✓ Dispatcher GUI created")

# Set state matrix in dispatcher
dispatcher.set_state_matrix(sm)
print("✓ State matrix set in dispatcher")

# Create main window
main_window = QWidget()
main_window.setWindowTitle('Dispatcher Test')
main_window.resize(300, 200)

layout = QVBoxLayout()
layout.addWidget(dispatcher.gui)
main_window.setLayout(layout)

print("✓ GUI integrated into main window")

# Test start/stop functionality
if 0:
    dispatcher.gui.start()
    assert dispatcher.is_running, " Should be running after start"
    print("✓ Start functionality works")

if 0:
    dispatcher.gui.stop()
    assert not dispatcher.is_running, "Should be stopped after stop"
    print("✓ Stop functionality works")

# Show window briefly for visual verification
main_window.show()

if 0:
    # Auto-close after 2 seconds for automated testing
    close_timer = QTimer()
    close_timer.timeout.connect(app.quit)
    close_timer.setSingleShot(True)
    close_timer.start(2000)  # 2 seconds
    print("✓ GUI displayed successfully (closing in 2 seconds)")

if 1:
    # New trial every 10 seconds
    close_timer = QTimer(main_window)
    close_timer.timeout.connect(dispatcher.ready_to_start_trial)
    close_timer.setInterval(5000)  # In ms
    close_timer.start()
    print("✓ New trial timer started (every N seconds)")

# Run event loop briefly
app.exec()

print("✓ GUI test completed")



# if __name__ == '__main__':
#     try:
#         # Test without GUI first
#         test_dispatcher_basic_functionality()
        
#         # Test with GUI
#         test_dispatcher_with_gui()
        
#         print("\n🎉 All tests passed! The new Dispatcher is working correctly.")
        
#     except Exception as e:
#         print(f"\n❌ Test failed with error: {str(e)}")
#         import traceback
#         traceback.print_exc()
#         sys.exit(1)
