#!/usr/bin/env python3
"""
Test script for Arduino threshold detection with Qt signals and real-time plotting.

This script demonstrates how to use the ArduinoThread class to monitor
analog inputs and receive Qt signals when thresholds are crossed.
It also displays real-time plots of the analog signals with threshold lines.
"""

import sys
import collections
import numpy as np
import time
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout
from PyQt6.QtWidgets import QSlider, QWidget, QLabel, QPushButton
from PyQt6.QtCore import Qt, QTimer
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from phonotaxis.arduinomodule import ArduinoThread
from phonotaxis import gui
#from phonotaxis import config

DEFAULT_THRESHOLDS = {
    0: 0.5,  # Pin A0
    1: 0.5,  # Pin A1
    2: 0.5,  # Pin A2
    3: 0.5,  # Pin A3
    4: 0.5,  # Pin A4
    5: 0.5   # Pin A5
}

class ArduinoTestWindow(QMainWindow):
    """
    Simple test window for Arduino threshold detection with real-time plotting.
    """
    
    def __init__(self):
        super().__init__()
        #self.arduino_thread = None
        #self.arduino_thread = ArduinoThread(thresholds=self.thresholds, debug=False)
        self.setup_arduino()
        self.n_inputs = self.arduino_thread.n_inputs  # Number of analog inputs to monitor

        # Data storage for plotting
        self.max_data_points = 200  # Maximum number of points to keep in memory
        self.data_buffers = {}  # Will store deque objects for each pin
        self.time_buffers = {}  # Will store time deque objects for each pin
        self.start_time = None
        
        # Plot update timer
        self.plot_timer = QTimer()
        self.plot_timer.timeout.connect(self.update_plots)
        #self.plot_timer.setInterval(50)  # Update plots every 50ms (20 Hz)
        self.plot_timer.setInterval(10)

        self.init_ui()
        #self.setup_arduino()
        self.add_threshold_lines()
    
    def setup_arduino(self):
        """Set up the Arduino thread with threshold configuration."""
        # Configure thresholds for the first 3 pins
        self.thresholds = DEFAULT_THRESHOLDS
        self.arduino_thread = ArduinoThread(thresholds=self.thresholds, debug=False)

        self.arduino_thread.arduino_ready.connect(self.on_arduino_ready)
        self.arduino_thread.arduino_error.connect(self.on_arduino_error)
        self.arduino_thread.threshold_crossed.connect(self.on_threshold_crossed)
        
        self.arduino_thread.start()
        # Add threshold lines to plots
        #self.add_threshold_lines()
    
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("Arduino Threshold Test with Real-time Plotting")
        self.setGeometry(100, 100, 1200, 800)
        
        # Central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # Left panel for controls and status
        left_panel = QWidget()
        left_panel.setMinimumWidth(200)
        left_panel.setMaximumWidth(400)
        left_layout = QVBoxLayout(left_panel)
        main_layout.addWidget(left_panel)
        
        # Status label
        self.status_label = QLabel("Arduino Status: Connecting...")
        left_layout.addWidget(self.status_label)
        
        # Value displays for each pin
        self.value_labels = {}
        for ind in range(self.n_inputs):
            label = QLabel(f"A{ind}: ---")
            self.value_labels[ind] = label
            left_layout.addWidget(label)
        
        # Threshold event display
        self.threshold_label = QLabel("Event: None")
        left_layout.addWidget(self.threshold_label)
        
        # Control buttons
        self.start_button = QPushButton("Start Monitoring")
        self.start_button.clicked.connect(self.start_monitoring)
        left_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton("Stop Monitoring")
        self.stop_button.clicked.connect(self.stop_monitoring)
        self.stop_button.setEnabled(False)
        left_layout.addWidget(self.stop_button)
        
        # Clear plot button
        self.clear_button = QPushButton("Clear Plots")
        self.clear_button.clicked.connect(self.clear_plots)
        left_layout.addWidget(self.clear_button)
        
        # Vertical slider for threshold control (for pin 0)

        slider_container = QWidget()
        slider_layout = QVBoxLayout(slider_container)
        slider_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)


        self.threshold_slider_label = QLabel("<b>Threshold</b>")
        self.threshold_slider_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        slider_layout.addWidget(self.threshold_slider_label)

        # Value label under the slider label
        self.threshold_value_label = QLabel(f"{self.thresholds[0]:.3f}")
        self.threshold_value_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        slider_layout.addWidget(self.threshold_value_label)

        self.threshold_slider = QSlider(Qt.Orientation.Vertical, self)
        self.threshold_slider.setMinimum(0)
        self.threshold_slider.setMaximum(1000)
        self.threshold_slider.setValue(int(self.thresholds[0] * 1000))
        self.threshold_slider.setTickPosition(QSlider.TickPosition.TicksBothSides)
        self.threshold_slider.setTickInterval(100)
        self.threshold_slider.setSingleStep(1)
        #self.threshold_slider.setStyleSheet(gui.SLIDER_STYLESHEET)
        self.threshold_slider.valueChanged.connect(self.on_slider_threshold_changed)
        slider_layout.addWidget(self.threshold_slider, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Add vertical space above the slider
        slider_spacer = QWidget()
        slider_spacer.setFixedHeight(30)
        left_layout.addWidget(slider_spacer)

        left_layout.addWidget(slider_container)

        # Add stretch to push everything to the top
        left_layout.addStretch()

        # Right panel for plots
        self.setup_plots(main_layout)

    def on_slider_threshold_changed(self, value):
        """Update the threshold for all pins and the plot lines when the slider is moved."""
        new_threshold = value / 1000.0
        self.threshold_value_label.setText(f"{new_threshold:.3f}")
        for pin in self.thresholds:
            self.thresholds[pin] = new_threshold
            # Update ArduinoThread threshold if possible
            if hasattr(self.arduino_thread, 'set_threshold'):
                self.arduino_thread.set_threshold(pin, new_threshold)
            # Update threshold line on plot
            if pin in self.threshold_lines:
                self.threshold_lines[pin].set_ydata([new_threshold, new_threshold])
        self.canvas.draw()

    def setup_plots(self, main_layout):
        """Set up the matplotlib plotting area."""
        # Create matplotlib figure and canvas
        self.figure = Figure(figsize=(12, 8))
        self.canvas = FigureCanvas(self.figure)
        
        # Set the figure background to match the application background
        app_palette = self.palette()
        bg_color = app_palette.color(app_palette.ColorRole.Window)
        bg_color_hex = bg_color.name()  # Convert to hex string
        #self.figure.patch.set_facecolor(bg_color_hex)
        
        main_layout.addWidget(self.canvas)
        
        # Create subplots for each pin that has a threshold
        self.axes = {}
        self.lines = {}
        self.threshold_lines = {}
        
        # We'll create plots for pins with thresholds (initially 3 pins: 0, 1, 2)
        n_plots = self.n_inputs
        for i in range(n_plots):
            ax = self.figure.add_subplot(n_plots, 1, i + 1)
            self.axes[i] = ax
            
            # Set subplot background to match application background
            #ax.set_facecolor(bg_color_hex)
            
            # Initialize empty line for data
            line, = ax.plot([], [], 'b-', linewidth=1, label=f'A{i}')
            self.lines[i] = line
            
            # Set up axes
            ax.set_ylabel(f'A{i} Value')
            ax.set_ylim(-0.05, 1.05)
            ax.grid(True, alpha=0.3)
            #ax.legend(loc='upper right')
            
            # Initialize data buffer for this pin
            self.data_buffers[i] = collections.deque(maxlen=self.max_data_points)
            self.time_buffers[i] = collections.deque(maxlen=self.max_data_points)
        
        # Only show x-label on the bottom plot
        if n_plots > 0:
            self.axes[n_plots - 1].set_xlabel('Time (seconds)')
        
        self.figure.tight_layout()
        self.canvas.draw()
    
    def add_threshold_lines(self):
        """Add horizontal threshold lines to the plots."""
        for pin, threshold in self.thresholds.items():
            if pin in self.axes:
                ax = self.axes[pin]
                threshold_line = ax.axhline(y=threshold, color='darkred', linestyle='--', 
                                          linewidth=1, alpha=0.7, 
                                          label=f'Threshold ({threshold})')
                self.threshold_lines[pin] = threshold_line
                #ax.legend(loc='upper right')
        self.canvas.draw()
    
    def clear_plots(self):
        """Clear all plot data."""
        # Clear data buffers
        for pin in self.data_buffers:
            self.data_buffers[pin].clear()
            self.time_buffers[pin].clear()
        
        # Clear plot lines
        for pin, line in self.lines.items():
            line.set_data([], [])
        
        # Reset time reference
        self.start_time = None
        
        # Redraw plots
        self.canvas.draw()
    
    def update_plots(self):
        """Update the real-time plots."""
        # Poll current values from Arduino thread
        if self.arduino_thread:
            current_values = self.arduino_thread.get_current_values()
            
            # Update value labels and store data for plotting
            for pin_number, value in current_values.items():
                if pin_number in self.value_labels:
                    self.value_labels[pin_number].setText(f"A{pin_number}: {value:.3f}")
                
                # Store data for plotting (only for pins we're plotting)
                if pin_number in self.data_buffers:
                    current_time = time.time()
                    
                    # Set start time with first data point
                    if self.start_time is None:
                        self.start_time = current_time
                    
                    # Calculate relative time
                    relative_time = current_time - self.start_time
                    
                    # Add data to buffers for this specific pin
                    self.time_buffers[pin_number].append(relative_time)
                    self.data_buffers[pin_number].append(value)
        
        # Update each plot
        for pin, line in self.lines.items():
            if pin in self.data_buffers and self.data_buffers[pin] and pin in self.time_buffers:
                times = np.array(list(self.time_buffers[pin]))
                values = np.array(list(self.data_buffers[pin]))
                
                # Ensure times and values have the same length
                if len(times) == len(values) and len(times) > 0:
                    line.set_data(times, values)
                    
                    # Update x-axis limits to show the period covered by max_data_points
                    if len(times) > 1:
                        period_to_show = times[-1] - times[0]
                        current_time = times[-1]
                        self.axes[pin].set_xlim(max(0, current_time - period_to_show), current_time)

        # Redraw canvas
        self.canvas.draw()
    
    def start_monitoring(self):
        """Start Arduino monitoring and plotting."""
        if self.arduino_thread:
            #self.arduino_thread.start()
            self.plot_timer.start()
            self.start_time = None  # Will be set with first data point
            self.status_label.setText("Arduino Status: Monitoring...")
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
    
    def stop_monitoring(self):
        """Stop Arduino monitoring and plotting."""
        if self.arduino_thread and self.arduino_thread.isRunning():
            #self.arduino_thread.stop()
            #self.arduino_thread.wait()  # Wait for thread to finish
            self.plot_timer.stop()
            self.status_label.setText("Arduino Status: Stopped")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)

    def on_arduino_ready(self):
        """Handle Arduino ready signals."""
        self.status_label.setText('Arduino Status: <b>Ready</b>')
    
    def on_arduino_error(self, error_message):
        """Handle Arduino error signals."""
        self.status_label.setText(f"Arduino Error: {error_message}")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
    
    def on_threshold_crossed(self, pin_number, value, is_rising_edge):
        """Handle threshold crossing signals if plot timer is active"""
        if self.plot_timer.isActive():
            edge_type = "Rising" if is_rising_edge else "Falling"
            message = f"Pin A{pin_number}: {edge_type} edge (value: {value:.3f})"
            self.threshold_label.setText(f"Event: {message}")
            #print(f"THRESHOLD CROSSED: {message}")
    
    def closeEvent(self, event):
        """Handle window close event."""
        self.stop_monitoring()
        self.arduino_thread.stop()
        if self.plot_timer.isActive():
            self.plot_timer.stop()
        event.accept()


def main():
    """Main function to run the test application."""
    app = QApplication(sys.argv)
    
    # Create and show the test window
    window = ArduinoTestWindow()
    window.show()
    
    # Run the application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
