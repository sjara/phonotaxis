"""
Interface emulator to test the phonotaxis controller without hardware.

This module provides a graphical emulator that allows testing state machine input/output behavior
without requiring actual hardware. It provides:

- Input simulation via clickable buttons
- Output visualization via colored rectangles
- Real-time output updates via Qt signals
- Automatic event mapping (each input creates 'in' and 'out' events)

The emulator takes lists of input and output names and creates appropriate UI elements.
Each input button generates two events: '{input}in' when pressed and '{input}out' when released.
"""

import sys
from typing import Dict, List, Optional, Callable, Tuple
from PyQt6 import QtCore, QtWidgets, QtGui
import numpy as np

# Define default colors
BUTTON_STYLE_NORMAL = """
    QPushButton {
        background-color: #E0E0E0;
        border: 2px solid #A0A0A0;
        border-radius: 8px;
        padding: 8px;
        font-size: 12px;
        font-weight: bold;
        color: black;
        min-height: 40px;
        min-width: 80px;
    }
    QPushButton:hover {
        background-color: #F0F0F0;
        border-color: #808080;
        color: black;
    }
    QPushButton:pressed {
        background-color: #D0D0D0;
        border-color: #606060;
        color: black;
    }
"""

BUTTON_STYLE_ACTIVE = """
    QPushButton {
        background-color: #4CAF50;
        border: 2px solid #45a049;
        border-radius: 8px;
        padding: 8px;
        font-size: 12px;
        font-weight: bold;
        color: white;
        min-height: 40px;
        min-width: 80px;
    }
"""

OUTPUT_STYLE_INACTIVE = """
    QLabel {
        background-color: #808080;
        border: 2px solid #606060;
        border-radius: 8px;
        padding: 8px;
        font-size: 12px;
        font-weight: bold;
        color: white;
        text-align: center;
        min-height: 40px;
        min-width: 80px;
    }
"""

OUTPUT_STYLE_ACTIVE = """
    QLabel {
        background-color: #2196F3;
        border: 2px solid #1976D2;
        border-radius: 8px;
        padding: 8px;
        font-size: 12px;
        font-weight: bold;
        color: white;
        text-align: center;
        min-height: 40px;
        min-width: 80px;
    }
"""


class EmulatorWidget(QtWidgets.QWidget):
    """
    Emulator widget for testing state machine inputs and outputs without hardware.
    
    Provides a graphical interface with:
    - Input buttons (clickable to simulate hardware inputs)
    - Output indicators (colored rectangles showing output states)
    - Automatic event generation: each input creates 'in' and 'out' events
    
    The widget creates a mapping of events to indices based on the input/output lists:
    - Each input generates two events: '{input}in' and '{input}out'
    - Output indices correspond directly to the output list order
    
    Usage:
        1. Create emulator: emulator = EmulatorWidget(inputs=['center', 'left'], outputs=['valve'])
        2. Connect: emulator.connect_state_machine(state_machine, event_mapping)
        3. Button press sends '{input}in' event, button release sends '{input}out' event
    
    Note: This emulator only handles input simulation and output visualization.
    State tracking should be handled by external components.
    """
    
    def __init__(self, 
                 inputs: List[str],
                 outputs: List[str],
                 parent: Optional[QtWidgets.QWidget] = None):
        """
        Initialize the emulator widget.
        
        Args:
            inputs: List of input names (e.g., ['center', 'left', 'right'])
            outputs: List of output names (e.g., ['valve', 'led'])
            parent: Parent widget
        """
        super().__init__(parent)
        
        # Configuration
        self.input_names = inputs.copy()
        self.output_names = outputs.copy()
        
        # Create event mapping: each input gets 'in' and 'out' events
        self.events = {}
        event_index = 0
        for input_name in self.input_names:
            self.events[input_name + 'in'] = event_index
            event_index += 1
            self.events[input_name + 'out'] = event_index
            event_index += 1
        
        # Output mapping: direct correspondence to output list
        self.output_mapping = {name: idx for idx, name in enumerate(self.output_names)}
        
        # State machine reference
        self.state_machine: Optional[object] = None
        self.event_mapping: Dict[str, int] = {}  # Maps our events to state machine events
        
        # GUI elements
        self.input_buttons: Dict[str, QtWidgets.QPushButton] = {}
        self.output_indicators: Dict[str, QtWidgets.QLabel] = {}
        self.info_label: Optional[QtWidgets.QLabel] = None
        
        # Button press state tracking
        self.button_timers: Dict[str, QtCore.QTimer] = {}
        self.button_press_duration = 100  # ms
        
        self._setup_ui()
        
    def get_events(self) -> Dict[str, int]:
        """
        Get the event mapping created by this emulator.
        
        Returns:
            Dictionary mapping event names to sequential indices.
            Each input creates two events: '{input}in' and '{input}out'.
        """
        return self.events.copy()
    
    def get_outputs(self) -> Dict[str, int]:
        """
        Get the output mapping for this emulator.
        
        Returns:
            Dictionary mapping output names to sequential indices.
        """
        return self.output_mapping.copy()
        
    def _setup_ui(self):
        """Set up the user interface."""
        self.setWindowTitle("State Machine Emulator")
        self.setMinimumSize(400, 300)
        
        # Main layout
        main_layout = QtWidgets.QVBoxLayout()
        
        # Info section
        info_group = QtWidgets.QGroupBox("Emulator Status")
        info_layout = QtWidgets.QVBoxLayout()
        
        self.info_label = QtWidgets.QLabel("Connect a state machine to start testing")
        self.info_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.info_label.setWordWrap(True)
        self.info_label.setFixedHeight(20)
        self.info_label.setStyleSheet("""
            QLabel {
                border-radius: 4px;
                padding: 2px;
                font-size: 14px;
                color: #CCCCCC;
            }
        """)
        # self.info_label.setStyleSheet("""
        #     QLabel {
        #         background-color: #F5F5F5;
        #         border: 1px solid #CCCCCC;
        #         border-radius: 4px;
        #         padding: 8px;
        #         font-size: 12px;
        #         color: black;
        #     }
        # """)
        
        info_layout.addWidget(self.info_label)
        info_group.setLayout(info_layout)
        
        # Inputs section
        inputs_group = QtWidgets.QGroupBox("Inputs (Click to simulate)")
        inputs_layout = QtWidgets.QGridLayout()
        
        for i, input_name in enumerate(self.input_names):
            button = QtWidgets.QPushButton(input_name)
            button.setStyleSheet(BUTTON_STYLE_NORMAL)
            button.pressed.connect(lambda name=input_name: self._on_input_pressed(name))
            button.released.connect(lambda name=input_name: self._on_input_released(name))
            
            # Arrange buttons in a grid (3 columns max)
            row = i // 3
            col = i % 3
            inputs_layout.addWidget(button, row, col)
            
            self.input_buttons[input_name] = button
            
            # Create timer for this button
            timer = QtCore.QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(lambda name=input_name: self._reset_button_style(name))
            self.button_timers[input_name] = timer
        
        if not self.input_names:
            no_inputs_label = QtWidgets.QLabel("No inputs configured")
            no_inputs_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            no_inputs_label.setStyleSheet("color: #666666; font-style: italic;")
            inputs_layout.addWidget(no_inputs_label, 0, 0)
            
        inputs_group.setLayout(inputs_layout)
        
        # Outputs section
        outputs_group = QtWidgets.QGroupBox("Outputs")
        outputs_layout = QtWidgets.QGridLayout()
        
        for i, output_name in enumerate(self.output_names):
            indicator = QtWidgets.QLabel(output_name)
            indicator.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            indicator.setStyleSheet(OUTPUT_STYLE_INACTIVE)
            
            # Arrange indicators in a grid (3 columns max)
            row = i // 3
            col = i % 3
            outputs_layout.addWidget(indicator, row, col)
            
            self.output_indicators[output_name] = indicator
            
        if not self.output_names:
            no_outputs_label = QtWidgets.QLabel("No outputs configured")
            no_outputs_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            no_outputs_label.setStyleSheet("color: #666666; font-style: italic;")
            outputs_layout.addWidget(no_outputs_label, 0, 0)
            
        outputs_group.setLayout(outputs_layout)
        
        # Add sections to main layout
        main_layout.addWidget(info_group)
        main_layout.addWidget(inputs_group)
        main_layout.addWidget(outputs_group)
        main_layout.addStretch()  # Push everything to top
        
        self.setLayout(main_layout)
        
    def connect_state_machine(self, state_machine): #, event_mapping: Dict[str, int]):
        """
        Connect the emulator to a state machine.
        
        Args:
            state_machine: StateMachine instance to connect to
            event_mapping: Dictionary mapping emulator event names to state machine event indices.
                          Should include mappings for the events returned by get_events().
                          Example: {'centerin': 0, 'centerout': 1, 'leftin': 2, 'leftout': 3}
        """
        self.state_machine = state_machine
        #self.event_mapping = event_mapping.copy()
        self.event_mapping = self.get_events()  # Assume direct mapping for simplicity
        
        # Connect state machine signals for output changes
        if hasattr(state_machine, 'outputChanged'):
            state_machine.outputChanged.connect(self._on_output_changed)
            
        # Update UI status
        self._update_connection_status()

    def disconnect_state_machine(self):
        """Disconnect from the current state machine."""
        if self.state_machine:
            # Disconnect signals
            if hasattr(self.state_machine, 'outputChanged'):
                self.state_machine.outputChanged.disconnect(self._on_output_changed)
                
        self.state_machine = None
        self.event_mapping.clear()
        
        # Reset UI
        self._update_connection_status()
        self._reset_all_outputs()
            
    def _on_input_pressed(self, input_name: str):
        """Handle input button press - sends 'in' event."""
        if not self.state_machine:
            return
            
        # Visual feedback
        button = self.input_buttons[input_name]
        button.setStyleSheet(BUTTON_STYLE_ACTIVE)
        
        # Send 'in' event to state machine
        in_event_key = input_name + 'in'
        if in_event_key in self.event_mapping:
            state_machine_event_index = self.event_mapping[in_event_key]
            try:
                self.state_machine.process_input(state_machine_event_index)
                self.info_label.setText(f"Sent event: {in_event_key} → SM index {state_machine_event_index}")
            except Exception as e:
                self.info_label.setText(f"Error sending {in_event_key}: {str(e)}")
        else:
            self.info_label.setText(f"Event {in_event_key} not mapped to state machine")
            
    def _on_input_released(self, input_name: str):
        """Handle input button release - sends 'out' event."""
        # Send 'out' event to state machine
        if self.state_machine:
            out_event_key = input_name + 'out'
            if out_event_key in self.event_mapping:
                state_machine_event_index = self.event_mapping[out_event_key]
                try:
                    self.state_machine.process_input(state_machine_event_index)
                    self.info_label.setText(f"Sent event: {out_event_key} → SM index {state_machine_event_index}")
                except Exception as e:
                    self.info_label.setText(f"Error sending {out_event_key}: {str(e)}")
        
        # Start timer to reset button style after short delay
        if input_name in self.button_timers:
            self.button_timers[input_name].start(self.button_press_duration)
            
    def _reset_button_style(self, input_name: str):
        """Reset button style to normal."""
        if input_name in self.input_buttons:
            self.input_buttons[input_name].setStyleSheet(BUTTON_STYLE_NORMAL)
            
    def _on_output_changed(self, output_index: int, value: bool):
        """Handle state machine output change."""
        # Find output name from mapping
        output_name = None
        for name, index in self.output_mapping.items():
            if index == output_index:
                output_name = name
                break
                
        if output_name and output_name in self.output_indicators:
            indicator = self.output_indicators[output_name]
            if value:
                indicator.setStyleSheet(OUTPUT_STYLE_ACTIVE)
                self.info_label.setText(f"Output {output_name} turned ON")
            else:
                indicator.setStyleSheet(OUTPUT_STYLE_INACTIVE)
                self.info_label.setText(f"Output {output_name} turned OFF")
        else:
            self.info_label.setText(f"Output index {output_index} changed to {value}")
            
    def _update_connection_status(self):
        """Update the connection status display."""
        if self.state_machine:
            if hasattr(self.state_machine, 'is_configured') and self.state_machine.is_configured():
                self.info_label.setText("State machine connected and ready for testing")
            else:
                self.info_label.setText("State machine connected but not configured")
        else:
            self.info_label.setText("No state machine connected")
            
    def _reset_all_outputs(self):
        """Reset all output indicators to inactive state."""
        for indicator in self.output_indicators.values():
            indicator.setStyleSheet(OUTPUT_STYLE_INACTIVE)


def create_emulator_from_state_matrix(state_matrix):
    """
    Create an EmulatorWidget from a StateMatrix object.
    
    This is a convenience function that extracts input/output names from a StateMatrix
    and creates an appropriate EmulatorWidget. It also returns the event mapping
    needed to connect to a state machine.
    
    Args:
        state_matrix: StateMatrix object with inputs_dict and outputs_dict
        
    Returns:
        Tuple of (EmulatorWidget, event_mapping) where event_mapping maps
        emulator events to state matrix events
    """
    # Extract input and output names
    inputs = list(state_matrix.inputs_dict.keys()) if hasattr(state_matrix, 'inputs_dict') else []
    outputs = list(state_matrix.outputs_dict.keys()) if hasattr(state_matrix, 'outputs_dict') else []
    
    # Create emulator
    emulator = EmulatorWidget(inputs=inputs, outputs=outputs)
    
    # Create event mapping from emulator events to state matrix events
    event_mapping = {}
    if hasattr(state_matrix, 'events_dict'):
        emulator_events = emulator.get_events()
        for event_name, emulator_index in emulator_events.items():
            if event_name in state_matrix.events_dict:
                event_mapping[event_name] = state_matrix.events_dict[event_name]
    
    return emulator, event_mapping


def create_emulator_app(inputs: List[str], 
                       outputs: List[str]) -> Tuple[QtWidgets.QApplication, EmulatorWidget]:
    """
    Create a standalone emulator application.
    
    Args:
        inputs: List of input names for buttons
        outputs: List of output names for indicators
        
    Returns:
        Tuple of (QApplication, EmulatorWidget)
    """
    app = QtWidgets.QApplication(sys.argv)
        
    emulator = EmulatorWidget(inputs=inputs, outputs=outputs)
    emulator.show()
    
    return app, emulator


if __name__ == '__main__':
    """Example usage of the emulator."""
    
    # Example 1: Create emulator directly with input/output lists
    print("=== Example 1: Direct creation ===")
    inputs = ['center', 'left', 'right']
    outputs = ['valve', 'led']
    
    app, emulator = create_emulator_app(inputs=inputs, outputs=outputs)
    
    # Show the event mapping that this emulator creates
    print("Emulator event mapping:")
    for event, index in emulator.get_events().items():
        print(f"  {event}: {index}")
    
    print("\nEmulator output mapping:")
    for output, index in emulator.get_outputs().items():
        print(f"  {output}: {index}")
    
    print("\nTo connect to a state machine:")
    print("1. Create a StateMachine instance")
    print("2. Get the emulator's event mapping with emulator.get_events()")
    print("3. Create a mapping from emulator events to your state machine events")
    print("4. Call: emulator.connect_state_machine(state_machine, event_mapping)")
    print("5. Start the state machine")
    print("6. Click buttons to simulate inputs")
    
    # # Example 2: Create emulator from StateMatrix
    # print("\n=== Example 2: From StateMatrix ===")
    # try:
    #     from phonotaxis.statematrix import StateMatrix
    #     state_matrix = StateMatrix(inputs=['IZ', 'L', 'R'], outputs=['ValveL', 'ValveR'])
        
    #     emulator2, event_mapping = create_emulator_from_state_matrix(state_matrix)
        
    #     print("StateMatrix-based emulator created")
    #     print("Event mapping from emulator to StateMatrix:")
    #     for event, sm_index in event_mapping.items():
    #         print(f"  {event}: {sm_index}")
    #     print("Use this mapping when calling emulator.connect_state_machine(state_machine, event_mapping)")
    # except ImportError:
    #     print("StateMatrix not available for this example")
    
    sys.exit(app.exec())

