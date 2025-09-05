"""
Interface for Arduino.

This module enables collecting analog signals from an Arduino Mega 2560
which has the standard firmata loaded into it and provides Qt signals
when analog inputs cross configurable thresholds.

It uses the pyfirmata2 package. Note that reading via polling is not supported by this library.
"""

import time
import threading
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from pyfirmata2 import Arduino
from phonotaxis import config


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
    analog_value_acquired = pyqtSignal(int, float)  # pin, value

    def __init__(self, port=None, n_inputs=None, thresholds=None, debug=False):
        """
        Args:
            port (str): Arduino serial port. If None, uses config.ARDUINO_PORT.
            n_inputs (int): Number of analog inputs to monitor. If None, uses config.ARDUINO_N_ANALOG_INPUTS.
            thresholds (dict): Dictionary mapping pin numbers to threshold values.
                             Example: {0: 0.5, 1: 0.3} sets thresholds for pins A0 and A1.
                             If None, no thresholds are set (only raw values are emitted).
            debug (bool): If True, prints debug information to console.
        """
        super().__init__()
        self.port = port or config.ARDUINO_PORT
        self.n_inputs = n_inputs or config.ARDUINO_N_ANALOG_INPUTS
        self.thresholds = thresholds or {}
        self.debug = debug
        self._run_flag = True
        self.board = None
        self.analog_pins = []
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
                print(f"Connecting to Arduino on port: {self.port}")
            
            self.board = Arduino(self.port)
            
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
                    print(f"Set up analog pin A{pin_num}")
            
            self.arduino_ready.emit()
            if self.debug:
                print(f"Arduino connected successfully. Monitoring {self.n_inputs} analog inputs.")
            
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
                    
                    # Emit the raw analog value
                    self.analog_value_acquired.emit(pin_number, value)
                    
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
                                print(f"Pin A{pin_number}: {edge_type} edge detected (value: {value:.3f}, threshold: {threshold:.3f})")
                        
                        self.previous_states[pin_number] = current_state
                    
                    if self.debug and pin_number == 0:  # Only print for pin 0 to avoid spam
                        print(f"A{pin_number}: {value:.3f}")
        
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
                print(f"Set threshold for pin A{pin_number}: {threshold_value}")

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
                print(f"Removed threshold for pin A{pin_number}")

    def get_current_values(self):
        """
        Get the current analog values for all pins.
        
        Returns:
            dict: Dictionary mapping pin numbers to current values.
        """
        with self._lock:
            return self.previous_values.copy()

    def run(self):
        """
        Main thread execution loop.
        """
        if not self.connect_arduino():
            return
        
        try:
            if self.debug:
                print("Arduino monitoring started. Press stop to terminate.")
            
            while self._run_flag:
                if self.board:
                    self.board.iterate()
                # Note: The actual update rate is set by board.samplingOn()
                #       See https://github.com/berndporr/pyFirmata2
                self.msleep(1)  # In ms

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
            print("Arduino monitoring stop requested.")

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


