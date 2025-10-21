"""
Useful widgets for phonotaxis applications
"""

from typing import Dict, Optional
from PyQt6 import QtCore, QtWidgets, QtGui

# Define styles for Arduino control widget
OUTPUT_BUTTON_STYLE_LOW = """
    QPushButton {
        background-color: #808080;
        border: 2px solid #606060;
        border-radius: 8px;
        padding: 8px;
        font-size: 12px;
        font-weight: bold;
        color: white;
        min-height: 30px;
        min-width: 100px;
    }
    QPushButton:hover {
        background-color: #909090;
        border-color: #707070;
    }
"""

OUTPUT_BUTTON_STYLE_HIGH = """
    QPushButton {
        background-color: #2196F3;
        border: 2px solid #1976D2;
        border-radius: 8px;
        padding: 8px;
        font-size: 12px;
        font-weight: bold;
        color: white;
        min-height: 30px;
        min-width: 100px;
    }
    QPushButton:hover {
        background-color: #42A5F5;
        border-color: #1E88E5;
    }
"""

INPUT_INDICATOR_STYLE_BELOW = """
    QLabel {
        background-color: #404040;
        border: 1px solid #606060;
        border-radius: 4px;
        padding: 8px;
        font-size: 11px;
        font-weight: bold;
        color: white;
        text-align: center;
        min-height: 30px;
        min-width: 80px;
    }
"""

INPUT_INDICATOR_STYLE_ABOVE = """
    QLabel {
        background-color: #4CAF50;
        border: 2px solid #45a049;
        border-radius: 4px;
        padding: 8px;
        font-size: 11px;
        font-weight: bold;
        color: white;
        text-align: center;
        min-height: 30px;
        min-width: 80px;
    }
"""


class ArduinoControlWidget(QtWidgets.QWidget):
    """
    Widget for controlling Arduino outputs and monitoring inputs.
    
    Features:
    - One button per digital output to toggle HIGH/LOW
    - Real-time analog input value display
    - Threshold setting for each analog input
    - Visual indicator (color rectangle) showing threshold state
    
    The widget connects to an ArduinoThread instance and uses its signals to update
    the display and control outputs.

    Usage:
        widget = ArduinoControlWidget()
        widget.connect_arduino(arduino_thread)
        widget.show()
    """
    
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        """
        Initialize the Arduino control widget.
        
        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        
        # Arduino thread reference
        self.arduino_thread: Optional[object] = None
        
        # Track output states
        self.output_states: Dict[str, bool] = {}
        
        # Track input values and thresholds
        self.input_values: Dict[int, float] = {}
        self.input_thresholds: Dict[int, float] = {}
        
        # Monitoring state
        self.monitoring_enabled: bool = True
        
        # GUI elements
        self.output_buttons: Dict[str, QtWidgets.QPushButton] = {}
        self.input_indicators: Dict[int, QtWidgets.QLabel] = {}
        self.input_value_labels: Dict[int, QtWidgets.QLabel] = {}
        self.input_threshold_spinboxes: Dict[int, QtWidgets.QDoubleSpinBox] = {}
        self.status_label: Optional[QtWidgets.QLabel] = None
        self.monitoring_button: Optional[QtWidgets.QPushButton] = None
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Set up the user interface."""
        self.setWindowTitle("Arduino Control Panel")
        self.setMinimumSize(480, 240)
        
        # Main layout
        main_layout = QtWidgets.QVBoxLayout()
        
        # Status section (single line with monitoring toggle button)
        status_layout = QtWidgets.QHBoxLayout()
        
        self.status_label = QtWidgets.QLabel("Not connected to Arduino")
        self.status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            QLabel {
                padding: 4px;
                font-size: 11px;
                color: #666666;
            }
        """)
        
        self.monitoring_button = QtWidgets.QPushButton("Monitoring: ON")
        self.monitoring_button.setCheckable(True)
        self.monitoring_button.setChecked(True)
        self.monitoring_button.setMaximumWidth(120)
        self.monitoring_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                border: 2px solid #45a049;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 10px;
                font-weight: bold;
                color: white;
            }
            QPushButton:hover {
                background-color: #5DBF60;
            }
            QPushButton:checked {
                background-color: #4CAF50;
            }
            QPushButton:!checked {
                background-color: #808080;
                border-color: #606060;
            }
        """)
        self.monitoring_button.clicked.connect(self._toggle_monitoring)
        
        status_layout.addStretch()
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.monitoring_button)
        
        # Combined inputs/outputs section
        controls_group = QtWidgets.QGroupBox("Arduino Controls")
        self.controls_layout = QtWidgets.QGridLayout()
        self.controls_layout.setSpacing(10)
        
        controls_group.setLayout(self.controls_layout)
        
        # Create controls immediately based on config
        self._create_control_widgets()
        
        # Add sections to main layout
        main_layout.addLayout(status_layout)
        main_layout.addWidget(controls_group)
        main_layout.addStretch()
        
        self.setLayout(main_layout)
        
    def connect_arduino(self, arduino_thread):
        """
        Connect the widget to an ArduinoThread instance.
        
        Args:
            arduino_thread: ArduinoThread instance to connect to
        """
        self.arduino_thread = arduino_thread
        
        # Connect signals
        if hasattr(arduino_thread, 'arduino_ready'):
            arduino_thread.arduino_ready.connect(self._on_arduino_ready)
        if hasattr(arduino_thread, 'arduino_error'):
            arduino_thread.arduino_error.connect(self._on_arduino_error)
        if hasattr(arduino_thread, 'analog_value_acquired'):
            arduino_thread.analog_value_acquired.connect(self._on_analog_value)
        if hasattr(arduino_thread, 'threshold_crossed'):
            arduino_thread.threshold_crossed.connect(self._on_threshold_crossed)
        
        # Update status
        self.status_label.setText("Waiting for connection to Arduino...")
    
    def disconnect_arduino(self):
        """Disconnect from the current Arduino thread."""
        if self.arduino_thread:
            # Disconnect signals
            try:
                if hasattr(self.arduino_thread, 'arduino_ready'):
                    self.arduino_thread.arduino_ready.disconnect(self._on_arduino_ready)
                if hasattr(self.arduino_thread, 'arduino_error'):
                    self.arduino_thread.arduino_error.disconnect(self._on_arduino_error)
                if hasattr(self.arduino_thread, 'analog_value_acquired'):
                    self.arduino_thread.analog_value_acquired.disconnect(self._on_analog_value)
                if hasattr(self.arduino_thread, 'threshold_crossed'):
                    self.arduino_thread.threshold_crossed.disconnect(self._on_threshold_crossed)
            except TypeError:
                pass  # Signal not connected
                
        self.arduino_thread = None
        self.status_label.setText("Disconnected from Arduino")
    
    def _create_control_widgets(self):
        """Create control widgets based on config (called during UI setup)."""
        from phonotaxis import config
        
        # Add header labels
        header_font = QtGui.QFont()
        header_font.setBold(True)
        
        # Column headers
        input_header = QtWidgets.QLabel("Input")
        input_header.setFont(header_font)
        self.controls_layout.addWidget(input_header, 0, 0)
        
        value_header = QtWidgets.QLabel("Value")
        value_header.setFont(header_font)
        value_header.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.controls_layout.addWidget(value_header, 0, 1)
        
        threshold_header = QtWidgets.QLabel("Threshold")
        threshold_header.setFont(header_font)
        threshold_header.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.controls_layout.addWidget(threshold_header, 0, 2)
        
        # Add spacing column
        self.controls_layout.setColumnMinimumWidth(3, 20)
        
        output_header = QtWidgets.QLabel("Output")
        output_header.setFont(header_font)
        output_header.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.controls_layout.addWidget(output_header, 0, 4)
        
        # Get inputs and outputs from config
        n_inputs = len(config.INPUT_PINS)
        output_items = list(config.OUTPUT_PINS.items())
        
        # Create rows - one per input, paired with corresponding output
        max_rows = max(n_inputs, len(output_items))
        
        for ind in range(max_rows):
            row = ind + 1
            
            # --- INPUT COLUMN ---
            if ind < n_inputs:
                pin_num = ind
                
                # Find pin name
                pin_name = None
                for name, num in config.INPUT_PINS.items():
                    if num == pin_num:
                        pin_name = name
                        break
                
                # Input indicator label (replaces separate pin label and status indicator)
                indicator_label = QtWidgets.QLabel(f"{pin_name} (A{pin_num})" if pin_name else f"A{pin_num}")
                indicator_label.setStyleSheet(INPUT_INDICATOR_STYLE_BELOW)
                indicator_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self.controls_layout.addWidget(indicator_label, row, 0)
                self.input_indicators[pin_num] = indicator_label
                
                # Value display
                value_label = QtWidgets.QLabel("0.000")
                value_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | 
                                       QtCore.Qt.AlignmentFlag.AlignVCenter)
                value_label.setStyleSheet("font-family: monospace; padding: 5px;")
                self.controls_layout.addWidget(value_label, row, 1)
                self.input_value_labels[pin_num] = value_label
                
                # Threshold spinbox
                threshold_spinbox = QtWidgets.QDoubleSpinBox()
                threshold_spinbox.setRange(0.0, 1.0)
                threshold_spinbox.setSingleStep(0.01)
                threshold_spinbox.setDecimals(3)
                threshold_spinbox.setValue(0.5)
                threshold_spinbox.valueChanged.connect(
                    lambda value, p=pin_num: self._set_threshold(p, value)
                )
                self.controls_layout.addWidget(threshold_spinbox, row, 2)
                self.input_threshold_spinboxes[pin_num] = threshold_spinbox
                
                # Initialize values
                self.input_values[pin_num] = 0.0
                self.input_thresholds[pin_num] = 0.5
            else:
                # Empty cells if no more inputs
                for col in [0, 1, 2]:
                    empty_label = QtWidgets.QLabel("")
                    self.controls_layout.addWidget(empty_label, row, col)
            
            # --- OUTPUT COLUMN ---
            if ind < len(output_items):
                output_name, pin_num = output_items[ind]
                
                button = QtWidgets.QPushButton(f"{output_name} (D{pin_num})")
                button.setStyleSheet(OUTPUT_BUTTON_STYLE_LOW)
                button.clicked.connect(lambda checked, name=output_name: self._toggle_output(name))
                self.controls_layout.addWidget(button, row, 4)
                
                self.output_buttons[output_name] = button
                self.output_states[output_name] = False
            else:
                # Empty cell if no more outputs
                empty_label = QtWidgets.QLabel("")
                self.controls_layout.addWidget(empty_label, row, 4)
    
    def _setup_controls(self):
        """Initialize Arduino-specific settings after connection is established."""
        if not self.arduino_thread:
            return
        
        # Set initial thresholds in Arduino
        for pin_num, threshold in self.input_thresholds.items():
            try:
                self.arduino_thread.set_threshold(pin_num, threshold)
            except Exception as e:
                print(f"Warning: Could not set threshold for pin {pin_num}: {e}")
    
    def _toggle_output(self, output_name: str):
        """Toggle the state of a digital output."""
        if not self.arduino_thread:
            return
        
        try:
            # Toggle state
            current_state = self.output_states.get(output_name, False)
            new_state = not current_state
            
            # Send command to Arduino
            self.arduino_thread.set_digital_output(output_name, new_state)
            
            # Update UI
            self.output_states[output_name] = new_state
            button = self.output_buttons[output_name]
            if new_state:
                button.setStyleSheet(OUTPUT_BUTTON_STYLE_HIGH)
            else:
                button.setStyleSheet(OUTPUT_BUTTON_STYLE_LOW)
            
        except Exception as e:
            self.status_label.setText(f"Error toggling {output_name}: {str(e)}")
    
    def _set_threshold(self, pin_num: int, threshold: float):
        """Set the threshold for an analog input."""
        # Always update local threshold value
        self.input_thresholds[pin_num] = threshold
        
        # Update indicator based on current value
        current_value = self.input_values.get(pin_num, 0.0)
        self._update_input_indicator(pin_num, current_value)
        
        # Send to Arduino if connected
        if not self.arduino_thread:
            return
        
        try:
            self.arduino_thread.set_threshold(pin_num, threshold)
        except Exception as e:
            self.status_label.setText(f"Error setting threshold for A{pin_num}: {str(e)}")
    
    def _toggle_monitoring(self):
        """Toggle input monitoring on/off."""
        self.monitoring_enabled = self.monitoring_button.isChecked()
        
        if self.monitoring_enabled:
            self.monitoring_button.setText("Monitoring: ON")
            self.status_label.setText("Input monitoring enabled")
        else:
            self.monitoring_button.setText("Monitoring: OFF")
            self.status_label.setText("Input monitoring disabled")
    
    def _on_arduino_ready(self):
        """Handle Arduino ready signal."""
        self._setup_controls()
        self.status_label.setText("Arduino connected and ready")
    
    def _on_arduino_error(self, error_msg: str):
        """Handle Arduino error signal."""
        self.status_label.setText(f"Arduino error: {error_msg}")
    
    def _on_analog_value(self, pin_num: int, value: float):
        """Handle analog value update."""
        # Only update if monitoring is enabled
        if not self.monitoring_enabled:
            return
        
        self.input_values[pin_num] = value
        
        # Update value display
        if pin_num in self.input_value_labels:
            self.input_value_labels[pin_num].setText(f"{value:.3f}")
        
        # Update indicator
        self._update_input_indicator(pin_num, value)
    
    def _update_input_indicator(self, pin_num: int, value: float):
        """Update the visual indicator for an input based on threshold."""
        if pin_num not in self.input_indicators:
            return
        
        indicator = self.input_indicators[pin_num]
        threshold = self.input_thresholds.get(pin_num, 0.5)
        
        # Just change color, no text update needed
        if value >= threshold:
            indicator.setStyleSheet(INPUT_INDICATOR_STYLE_ABOVE)
        else:
            indicator.setStyleSheet(INPUT_INDICATOR_STYLE_BELOW)
    
    def _on_threshold_crossed(self, pin_num: int, value: float, is_rising: bool):
        """Handle threshold crossing event."""
        # Only update status if monitoring is enabled
        if not self.monitoring_enabled:
            return
        
        edge_type = "rising" if is_rising else "falling"
        self.status_label.setText(f"A{pin_num}: {edge_type} edge at {value:.3f}")



