"""
Interface for Arduino.

This module enables collecting analog signals from an Arduino Mega 2560
which has the standard firmata loaded into it and provides Qt signals
when analog inputs cross configurable thresholds.

It uses the pyfirmata2 package. Note that reading via polling is not supported by this library.

Threading architecture:
- ArduinoThread is a QThread primarily for non-blocking Arduino connection during startup.
- pyfirmata2 internally manages its own background thread for serial communication.
- Callbacks registered with pyfirmata2 run in pyfirmata2's background thread, not in the QThread.
- The QThread's run() loop simply keeps the connection alive; actual data acquisition happens
  independently in pyfirmata2's thread.
- Thread-safe access to shared data (thresholds, values) is protected by threading.Lock.
"""

import threading
from typing import Dict, List, Optional
from PyQt6.QtCore import QThread, pyqtSignal
from pyfirmata2 import Arduino
from phonotaxis import config

PREFIX = " Arduino:"

class ArduinoThread(QThread):
    """
    A QThread subclass for handling Arduino analog input monitoring in a separate thread.
    This prevents the GUI from freezing during Arduino operations.

    Signals:
        arduino_error_signal (str): Emitted when there is an error with the Arduino connection.
        threshold_crossed_signal (int, float, bool): Emitted when an analog input crosses a threshold.
                                                     Parameters: (pin_number, value, is_rising_edge)
        analog_value_signal (int, float): Emitted with current analog values for all monitored pins.
                                         Parameters: (pin_number, value)
    """
    arduino_ready = pyqtSignal()
    arduino_error = pyqtSignal(str)
    threshold_crossed = pyqtSignal(int, float, bool)  # pin, value, is_rising_edge
    #analog_value_acquired = pyqtSignal(int, float)  # pin, value --- IGNORE ---

    def __init__(self, port=None, n_inputs=None, thresholds=None, debug=False):
        """
        Args:
            port (str): Arduino serial port. If None, uses config.ARDUINO_PORT.
            n_inputs (int): Number of analog inputs to monitor. If None, uses len(config.INPUT_PINS).
            thresholds (dict): Dictionary mapping pin numbers to threshold values.
                             Example: {0: 0.5, 1: 0.3} sets thresholds for pins A0 and A1.
                             If None, no thresholds are set (only raw values are emitted).
            debug (bool): If True, prints debug information to console.
        """
        super().__init__()
        self.port = port or config.ARDUINO_PORT
        self.n_inputs = n_inputs or len(config.INPUT_PINS)
        self.thresholds = thresholds or {}
        self.debug = debug
        self._run_flag = True
        self.board = None
        self.analog_pins = []
        self.digital_output_pins = {}  # Store digital output pin objects by name
        self.previous_values = {}
        self.previous_states = {}  # Track whether each pin is above/below threshold
        self._lock = threading.Lock()

    def connect_arduino(self):
        """
        Establish connection to Arduino and set up analog pins.
        
        Returns:
            bool: True if connection successful, False otherwise.
        """
        try:
            if self.debug:
                print(f"{PREFIX} Connecting on port: {self.port}")
            
            self.board = Arduino(self.port)
            self.board.samplingOn(config.ARDUINO_SAMPLING_INTERVAL)  # in ms
            
            # Set up analog pins
            for pin_num in range(self.n_inputs):
                pin = self.board.get_pin(f'a:{pin_num}:i')
                pin.enable_reporting()
                pin.register_callback(self._create_callback(pin_num))
                self.analog_pins.append(pin)
                self.previous_values[pin_num] = 0.0
                
                # Initialize threshold state tracking
                if pin_num in self.thresholds:
                    self.previous_states[pin_num] = False
                
                if self.debug:
                    print(f"{PREFIX} Set up analog pin A{pin_num}")

            # Set up digital output pins
            for pin_name, pin_num in config.OUTPUT_PINS.items():
                pin = self.board.get_pin(f'd:{pin_num}:o')
                self.digital_output_pins[pin_name] = pin
                # Initialize all outputs to LOW
                pin.write(0)
                
                if self.debug:
                    print(f"{PREFIX} Set up digital output pin D{pin_num} ({pin_name})")
            
            self.arduino_ready.emit()
            if self.debug:
                print(f"{PREFIX} Connected successfully. Monitoring {self.n_inputs} analog inputs.")
            
            return True
            
        except (FileNotFoundError, AttributeError, Exception) as e:
            error_msg = f"Could not connect to Arduino on port {self.port}: {str(e)}"
            self.arduino_error.emit(error_msg)
            if self.debug:
                print(error_msg)
            return False

    def _create_callback(self, pin_number):
        """
        Create a callback function for a specific pin.
        
        Args:
            pin_number (int): The analog pin number (0-based).
            
        Returns:
            function: Callback function for the pin.
        """
        def callback(value):
            with self._lock:
                if value is not None:
                    self.previous_values[pin_number] = value
                    
                    # Check threshold crossing if threshold is set for this pin
                    if pin_number in self.thresholds:
                        threshold = self.thresholds[pin_number]
                        current_state = value >= threshold
                        previous_state = self.previous_states.get(pin_number, False)
                        
                        # Detect threshold crossing
                        if current_state != previous_state:
                            is_rising_edge = current_state  # True for rising edge, False for falling edge
                            self.threshold_crossed.emit(pin_number, value, is_rising_edge)
                            
                            if self.debug:
                                edge_type = "rising" if is_rising_edge else "falling"
                                print(f"{PREFIX} Pin A{pin_number}: {edge_type} edge detected (value: {value:.3f}, threshold: {threshold:.3f})")
                        
                        self.previous_states[pin_number] = current_state

                    # -- Debug level 2 --
                    if self.debug == 2 and pin_number == 0:  # Only print for pin 0 to avoid spam
                        print(f"{PREFIX} A{pin_number}: {value:.3f}")
        
        return callback

    def set_threshold(self, pin_number, threshold_value):
        """
        Set or update the threshold for a specific pin.
        
        Args:
            pin_number (int): The analog pin number (0-based).
            threshold_value (float): The threshold value (0.0 to 1.0).
        """
        with self._lock:
            self.thresholds[pin_number] = threshold_value
            # Initialize state if not already set
            if pin_number not in self.previous_states:
                current_value = self.previous_values.get(pin_number, 0.0)
                self.previous_states[pin_number] = current_value >= threshold_value
            
            if self.debug:
                print(f"{PREFIX} Set threshold for pin A{pin_number}: {threshold_value}")

    def remove_threshold(self, pin_number):
        """
        Remove the threshold for a specific pin.
        
        Args:
            pin_number (int): The analog pin number (0-based).
        """
        with self._lock:
            if pin_number in self.thresholds:
                del self.thresholds[pin_number]
            if pin_number in self.previous_states:
                del self.previous_states[pin_number]
            
            if self.debug:
                print(f"{PREFIX} Removed threshold for pin A{pin_number}")

    def get_current_values(self):
        """
        Get the current analog values for all pins.
        
        Returns:
            dict: Dictionary mapping pin numbers to current values.
        """
        with self._lock:
            return self.previous_values.copy()

    def set_digital_output(self, pin_name, state):
        """
        Set the state of a digital output pin.
        
        Args:
            pin_name (str): The name of the output pin as defined in config.OUTPUT_PINS.
                          Example: 'water1', 'water2'
            state (bool or int): The desired state. True/1 for HIGH, False/0 for LOW.
        
        Raises:
            ValueError: If pin_name is not found in configured output pins.
        """
        with self._lock:
            if pin_name not in self.digital_output_pins:
                raise ValueError(f"{PREFIX} Pin '{pin_name}' not found in configured output pins. "
                               f"Available pins: {list(self.digital_output_pins.keys())}")
            
            pin = self.digital_output_pins[pin_name]
            value = 1 if state else 0
            pin.write(value)
            
            if self.debug:
                state_str = "HIGH" if value else "LOW"
                pin_num = config.OUTPUT_PINS[pin_name]
                print(f"{PREFIX} Set digital output {pin_name} (D{pin_num}) to {state_str}")

    def run(self):
        """
        Main thread execution loop.
        
        With pyfirmata2's event-driven model, the board handles data reading
        automatically in the background. This thread just needs to stay alive
        to keep the connection active while callbacks process incoming data.
        """
        if not self.connect_arduino():
            return
        
        try:
            if self.debug:
                print(f"{PREFIX} Monitoring started.")
            
            # Keep the thread alive while the board's background thread handles I/O
            while self._run_flag:
                self.msleep(100)  # Sleep to reduce CPU usage

        except Exception as e:
            error_msg = f"Error in Arduino thread: {str(e)}"
            self.arduino_error.emit(error_msg)
            if self.debug:
                print(error_msg)
        finally:
            self.cleanup()

    def stop(self):
        """
        Stop the Arduino monitoring thread.
        """
        self._run_flag = False
        if self.debug:
            print(f"{PREFIX} Monitoring stop requested.")

    def cleanup(self):
        """
        Clean up Arduino connection and resources.
        """
        try:
            if self.board:
                self.board.exit()
                self.board = None
            if self.debug:
                print("Arduino connection closed.")
        except Exception as e:
            if self.debug:
                print(f"Error during Arduino cleanup: {e}")


class ArduinoInterface(QThread):
    """
    Interface between Arduino hardware and state machine.
    
    This class manages the connection between Arduino inputs/outputs and
    state machine events, providing:
    
    - Event mapping: translates Arduino threshold crossings to state machine events
    - Output control: translates state machine outputs to Arduino digital outputs
    - Named access: uses human-readable names instead of pin numbers
    - Configuration: uses config.py for pin mappings and thresholds
    
    The interface creates a consistent event structure:
    - Input events: '{input_name}in' (threshold crossed rising edge)
                   '{input_name}out' (threshold crossed falling edge)
    - Output mapping: direct correspondence to output list order
    
    The Arduino connection is initiated automatically in the constructor
    to minimize startup time. Connect to the arduino_ready signal to know
    when the connection is established.
    
    Usage:
        interface = ArduinoInterface(
            inputs=['port1', 'port2'],
            outputs=['water1', 'water2'],
            port='/dev/ttyACM0'
        )
        interface.arduino_ready.connect(on_ready_callback)
        interface.connect_state_machine(state_machine)
    """
    
    # Signals
    arduino_ready = pyqtSignal()
    arduino_error = pyqtSignal(str)
    
    def __init__(self,
                 inputs: List[str],
                 outputs: List[str],
                 port: Optional[str] = None,
                 thresholds: Optional[Dict[str, float]] = None,
                 sampling_interval: Optional[int] = None,
                 debug: bool = False,
                 parent: Optional[QThread] = None):
        """
        Initialize the Arduino interface.
        
        Args:
            inputs: List of input names (must exist in config.INPUT_PINS)
            outputs: List of output names (must exist in config.OUTPUT_PINS)
            port: Arduino serial port (None uses config.ARDUINO_PORT)
            thresholds: Dict mapping input names to threshold values (0.0-1.0)
                       If None, uses default threshold of 0.5 for all inputs
            sampling_interval: Arduino sampling interval in ms (None uses config)
            debug: Enable debug output
            parent: Parent QObject
        """
        super().__init__(parent)
        
        self.input_names = inputs.copy()
        self.output_names = outputs.copy()
        self.debug = debug
        
        # Validate that all inputs/outputs exist in config
        self._validate_pins()
        
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
        
        # Create pin-to-name mappings for quick lookup
        self.input_pin_to_name = {config.INPUT_PINS[name]: name 
                                   for name in self.input_names}
        self.output_name_to_pin = {name: config.OUTPUT_PINS[name] 
                                    for name in self.output_names}
        
        # Set up thresholds (convert from names to pin numbers)
        if thresholds is None:
            # Default threshold of 0.5 for all inputs
            pin_thresholds = {config.INPUT_PINS[name]: 0.5 
                             for name in self.input_names}
        else:
            pin_thresholds = {config.INPUT_PINS[name]: thresholds[name] 
                             for name in self.input_names if name in thresholds}
        
        # Create Arduino thread
        port = port or config.ARDUINO_PORT
        sampling_interval = sampling_interval or config.ARDUINO_SAMPLING_INTERVAL
        n_inputs = max(config.INPUT_PINS.values()) + 1 if config.INPUT_PINS else 0
        
        self.arduino_thread = ArduinoThread(
            port=port,
            n_inputs=n_inputs,
            thresholds=pin_thresholds,
            debug=debug
        )
        
        # State machine reference
        self.state_machine = None
        self.event_mapping: Dict[str, int] = {}
        
        # Connect Arduino signals
        self.arduino_thread.arduino_ready.connect(self._on_arduino_ready)
        self.arduino_thread.arduino_error.connect(self._on_arduino_error)
        self.arduino_thread.threshold_crossed.connect(self._on_threshold_crossed)
        
        # Start the Arduino thread immediately to connect as soon as possible
        self.arduino_thread.start()
        
    def _validate_pins(self):
        """Validate that all input/output names exist in config."""
        # Check inputs
        for input_name in self.input_names:
            if input_name not in config.INPUT_PINS:
                raise ValueError(
                    f"Input '{input_name}' not found in config.INPUT_PINS. "
                    f"Available: {list(config.INPUT_PINS.keys())}"
                )
        
        # Check outputs
        for output_name in self.output_names:
            if output_name not in config.OUTPUT_PINS:
                raise ValueError(
                    f"Output '{output_name}' not found in config.OUTPUT_PINS. "
                    f"Available: {list(config.OUTPUT_PINS.keys())}"
                )
    
    def get_events(self) -> Dict[str, int]:
        """
        Get the event mapping created by this interface.
        
        Returns:
            Dictionary mapping event names to sequential indices.
            Each input creates two events: '{input}in' and '{input}out'.
        """
        return self.events.copy()
    
    def get_outputs(self) -> Dict[str, int]:
        """
        Get the output mapping for this interface.
        
        Returns:
            Dictionary mapping output names to sequential indices.
        """
        return self.output_mapping.copy()
    
    def connect_state_machine(self, state_machine):
        """
        Connect the interface to a state machine.
        
        This establishes bidirectional communication:
        - Arduino threshold crossings trigger state machine events
        - State machine output changes trigger Arduino digital outputs
        
        Args:
            state_machine: StateMachine instance to connect to
        """
        self.state_machine = state_machine
        self.event_mapping = self.get_events()  # Assume direct mapping
        
        # Connect state machine output changes to Arduino outputs
        if hasattr(state_machine, 'outputChanged'):
            state_machine.outputChanged.connect(self._on_output_changed)
        
        if self.debug:
            print(f"{PREFIX} Interface connected to state machine")
            print(f"{PREFIX} Event mapping: {self.event_mapping}")
            print(f"{PREFIX} Output mapping: {self.output_mapping}")
    
    def disconnect_state_machine(self):
        """Disconnect from the current state machine."""
        if self.state_machine:
            if hasattr(self.state_machine, 'outputChanged'):
                self.state_machine.outputChanged.disconnect(self._on_output_changed)
        
        self.state_machine = None
        self.event_mapping.clear()
    
    # def start(self):
    #     """
    #     Start the Arduino interface.
        
    #     Note: The Arduino thread is automatically started in the constructor
    #     to connect as quickly as possible. This method is kept for backwards
    #     compatibility but does nothing if the thread is already running.
    #     """
    #     if not self.arduino_thread.isRunning():
    #         if self.debug:
    #             print("Starting Arduino interface...")
    #         self.arduino_thread.start()
    #     elif self.debug:
    #         print("Arduino interface already started")
    
    # def stop(self):
    #     """Stop the Arduino interface."""
    #     if self.debug:
    #         print("Stopping Arduino interface...")
    #     self.arduino_thread.stop()
    #     self.arduino_thread.wait()  # Wait for thread to finish
    
    def set_threshold(self, input_name: str, threshold: float):
        """
        Set threshold for an input.
        
        Args:
            input_name: Name of the input (must be in self.input_names)
            threshold: Threshold value (0.0 to 1.0)
        """
        if input_name not in self.input_names:
            raise ValueError(f"Input '{input_name}' not found. "
                           f"Available: {self.input_names}")
        
        pin_number = config.INPUT_PINS[input_name]
        self.arduino_thread.set_threshold(pin_number, threshold)
    
    def get_current_values(self) -> Dict[str, float]:
        """
        Get current analog values for all inputs.
        
        Returns:
            Dictionary mapping input names to current values (0.0 to 1.0)
        """
        pin_values = self.arduino_thread.get_current_values()
        return {name: pin_values.get(config.INPUT_PINS[name], 0.0) 
                for name in self.input_names}
    
    def force_output(self, output_name: str, state: bool):
        """
        Manually force an output state (for testing/manual control).
        
        Args:
            output_name: Name of the output (must be in self.output_names)
            state: Desired state (True=HIGH, False=LOW)
        """
        if output_name not in self.output_names:
            raise ValueError(f"Output '{output_name}' not found. "
                           f"Available: {self.output_names}")
        
        self.arduino_thread.set_digital_output(output_name, state)
    
    def _on_arduino_ready(self):
        """Handle Arduino connection ready."""
        if self.debug:
            print("Arduino connected and ready")
        self.arduino_ready.emit()
    
    def _on_arduino_error(self, error_msg: str):
        """Handle Arduino connection error."""
        if self.debug:
            print(f"Arduino error: {error_msg}")
        self.arduino_error.emit(error_msg)
    
    def _on_threshold_crossed(self, pin_number: int, value: float, is_rising_edge: bool):
        """
        Handle threshold crossing from Arduino.
        
        Translates Arduino pin events to state machine events.
        
        Args:
            pin_number: Arduino analog pin number
            value: Current analog value
            is_rising_edge: True for rising edge, False for falling edge
        """
        if not self.state_machine or not self.state_machine.is_running:
            return
        
        # Get input name from pin number
        if pin_number not in self.input_pin_to_name:
            if self.debug:
                print(f"Ignoring threshold crossing on unmonitored pin {pin_number}")
            return
        
        input_name = self.input_pin_to_name[pin_number]
        
        # Create event name based on edge direction
        # If using pull-up resistors, logic is inverted: high=out, low=in
        if config.ARDUINO_INPUTS_INVERTED:
            event_suffix = 'out' if is_rising_edge else 'in'
        else:
            event_suffix = 'in' if is_rising_edge else 'out'
        event_key = input_name + event_suffix
        
        # Send event to state machine
        if event_key in self.event_mapping:
            state_machine_event_index = self.event_mapping[event_key]
            try:
                self.state_machine.process_input(state_machine_event_index)
                if self.debug:
                    edge_str = "rising" if is_rising_edge else "falling"
                    print(f"{PREFIX} Event: {input_name} {edge_str} edge → "
                          f"SM event {event_key} (index {state_machine_event_index})")
            except Exception as e:
                if self.debug:
                    print(f"Error sending event {event_key} to state machine: {e}")
        else:
            if self.debug:
                print(f"Event {event_key} not mapped to state machine")
    
    def _on_output_changed(self, output_index: int, value: bool):
        """
        Handle state machine output change.
        
        Translates state machine output changes to Arduino digital outputs.
        
        Args:
            output_index: State machine output index
            value: Output value (True=HIGH, False=LOW)
        """
        # Find output name from mapping
        output_name = None
        for name, index in self.output_mapping.items():
            if index == output_index:
                output_name = name
                break
        
        if output_name:
            try:
                self.arduino_thread.set_digital_output(output_name, value)
                if self.debug:
                    state_str = "HIGH" if value else "LOW"
                    print(f"{PREFIX} SM output {output_index} ({output_name}) → Arduino {state_str}")
            except Exception as e:
                if self.debug:
                    print(f"Error setting Arduino output {output_name}: {e}")
        else:
            if self.debug:
                print(f"Output index {output_index} not mapped to Arduino output")
    
    def close(self):
        """Clean up resources and turn off all outputs."""
        if self.debug:
            print("Cleaning up Arduino interface...")
        
        # Turn off all outputs
        for output_name in self.output_names:
            try:
                self.arduino_thread.set_digital_output(output_name, False)
            except Exception as e:
                if self.debug:
                    print(f"Error turning off output {output_name}: {e}")
        
        # Stop the thread
        # self.stop()
        if self.debug:
            print("Stopping Arduino interface...")
        self.arduino_thread.stop()
        self.arduino_thread.wait()  # Wait for thread to finish


