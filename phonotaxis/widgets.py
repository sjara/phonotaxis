"""
Useful widgets for phonotaxis applications
"""

# import cv2
# import numpy as np
import socket
import time
from typing import Dict, Optional
from PyQt6.QtWidgets import QLabel, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QSlider
from PyQt6.QtWidgets import QGroupBox, QGridLayout, QDoubleSpinBox, QCheckBox
from PyQt6.QtCore import pyqtSignal, Qt, QTimer, QPointF
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QFont, QPolygonF
from phonotaxis import gui


class SessionInfo(QWidget):
    """
    Widget for session information parameters.
    
    Contains standard session parameters: hostname, subject, trainer, maxSessionDuration, 
    and maxTrials. Provides a consistent interface for displaying and saving session info 
    across tasks.
    
    Usage:
        session_info = SessionInfo()
        layout.addWidget(session_info)
        
        # Later, save to HDF5 file
        session_info.append_to_file(h5file)
    """
    
    def __init__(self, parent=None):
        """
        Initialize SessionInfo widget with default parameters.
        
        Args:
            parent: Parent widget (optional)
        """
        super().__init__(parent)
        
        # Create parameter container
        self.params = gui.Container()
        
        # Define session parameters (without history)
        self.params['subject'] = gui.StringParam('Subject', value='', 
                                                 group='Session info')
        self.params['trainer'] = gui.StringParam('Trainer', value='', 
                                                 group='Session info')
        self.params['hostname'] = gui.StringParam('Hostname', value=socket.gethostname(), 
                                                  group='Session info', enabled=False)
        self.params['maxSessionDuration'] = gui.NumericParam('Max duration (s)', value=float('inf'), 
                                                          units='s', history=False,
                                                          group='Session info')
        self.params['maxTrials'] = gui.NumericParam('Max trials', value=float('inf'), 
                                                     units='trials', decimals=0, history=False,
                                                     group='Session info')
        
        # Create layout with the group
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.groupBox = self.params.layout_group('Session info')
        self._layout.addWidget(self.groupBox)
    
    def get_value(self, param_name):
        """
        Get the value of a specific parameter.
        
        Args:
            param_name: Name of the parameter ('hostname', 'subject', 'trainer', 
                       'maxSessionDuration', or 'maxTrials')
        
        Returns:
            The current value of the parameter
        """
        if param_name not in self.params:
            raise KeyError(f"Parameter '{param_name}' not found in SessionInfo")
        return self.params[param_name].get_value()
    
    def set_value(self, param_name, value):
        """
        Set the value of a specific parameter.
        
        Args:
            param_name: Name of the parameter
            value: New value for the parameter
        """
        if param_name not in self.params:
            raise KeyError(f"Parameter '{param_name}' not found in SessionInfo")
        self.params[param_name].set_value(value)
    
    def set_values(self, values_dict):
        """
        Set multiple parameter values at once.
        
        Args:
            values_dict: Dictionary with parameter names as keys and their values
        """
        self.params.set_values(values_dict)
    
    def append_to_file(self, h5file):
        """
        Append session info to an HDF5 file.
        
        Saves all session parameters to the 'sessionData' group in the HDF5 file.
        Unlike Container.append_to_file(), this method does not save history,
        as session parameters should remain constant throughout a session.
        
        Args:
            h5file: Open HDF5 file object (h5py.File)
        """
        sessionDataGroup = h5file.require_group('sessionData')
        
        # Append date/time
        dateAndTime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        dset = sessionDataGroup.create_dataset('date', data=dateAndTime)
        
        # Append all session parameters (including hostname)
        for key, item in self.params.items():
            if item.get_type() == 'string':
                dset = sessionDataGroup.create_dataset(key, data=item.get_value())
            else:
                dset = sessionDataGroup.create_dataset(key, data=item.get_value())
            dset.attrs['Description'] = item.get_label()
            if item.get_type() == 'numeric':
                dset.attrs['Units'] = item.get_units()
    

class StatusWidget(QLabel):
    def __init__(self):
        super().__init__("Monitoring video feed...")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reset()
    def reset(self, label="Monitoring video feed..."):
        self.setText(label)
        self.setStyleSheet("font-size: 20px; font-weight: bold;" +
                           "padding: 10px; border-radius: 6px;" +
                           "background-color: #333; color: #eee;")


class CustomSlider(QSlider):
    """Custom QSlider that ignores arrow key events."""
    def keyPressEvent(self, event):
        """Override to ignore arrow keys."""
        if event.key() in [Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down]:
            # Ignore arrow keys - let parent handle them
            event.ignore()
        else:
            # For other keys, use default slider behavior
            super().keyPressEvent(event)


SLIDER_STYLESHEET = """
    QSlider::handle:horizontal {
        background: #555;
    }
    QSlider::add-page:horizontal {
        background: #bbb;
    }
    QSlider::sub-page:horizontal {
        background: #888;
    }
"""

class SliderWidget(QWidget):
    """
    A widget that contains a slider for adjusting a video parameter.
    """
    value_changed = pyqtSignal(int)
    
    def __init__(self, parent=None, maxvalue=128, label="Value", value=None):
        super().__init__(parent)
        self.maxvalue = maxvalue
        self.value = value if value is not None else maxvalue // 2
        self.label = label
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)  # Remove margins for compact layout
        # Label to display the current slider value
        self.value_label = QLabel(f"{self.label}: {self.value}")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.value_label.setStyleSheet("font-size: 12px; padding: 4px;")
        self.value_label.setFixedWidth(100)  # Set a fixed width for consistent layout
        self.layout.addWidget(self.value_label)
        # Slider to adjust the value
        self.slider = CustomSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(self.maxvalue)
        self.slider.setValue(self.value)
        self.slider.setSingleStep(self.maxvalue//128)
        self.slider.setStyleSheet(SLIDER_STYLESHEET)
        self.slider.valueChanged.connect(self.update_value)
        self.layout.addWidget(self.slider)
        
    def update_value(self, value):
        """
        Updates the current value and the display label.
        This method is connected to the QSlider's valueChanged signal.
        """
        self.value = value
        self.value_label.setText(f"{self.label}: {self.value}")
        self.value_changed.emit(self.value)


IZ_COLOR = (52, 101, 164)  # RGB for Tango Sky Blue
CENTROID_COLOR = (239, 41, 41)  # RGB for Tango Scarlet Red
CONTOUR_COLOR = (138, 226, 52)  # RGB for Tango Chameleon green

class VideoWidget(QWidget):
    """
    Widget for displaying video feed with optional control sliders.
    
    Args:
        controls (bool): If True, display control sliders for threshold, min area, 
                        initzone radius, and mask radius. Default is False.
        threshold (int): Initial threshold value (0-255). Default is 50.
        minarea (int): Initial minimum area value. Default is 4000.
        initzone_radius (int): Initial initiation zone radius. Default is 80.
        mask_radius (int): Initial mask radius. Default is 240.
    """
    def __init__(self, controls=False, threshold=50, minarea=4000, 
                 initzone_radius=80, mask_radius=240):
        super().__init__()
        #self.setGeometry(100, 100, 800, 600)
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(2)  # Reduce spacing between widgets
        self.video_label = QLabel("Placeholder for video")  # ("Waiting for camera feed...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: #222; color: #fff;" +
                                       "border-radius: 6px;")
        # Set minimum size to match the expected video display size (640x480)
        self.video_label.setMinimumSize(640, 480)
        self.layout.addWidget(self.video_label)
        
        # Store first point trail (list of (x, y) tuples)
        self.first_point_trail = []
        self.max_trail_length = 20
        
        # Display settings
        self.show_contours = False  # Whether to display contours
        self.show_trail = False  # Whether to display point trail
        
        # Video thread reference (for controls)
        self.video_thread = None
        self.video_interface = None
        
        # Control widgets (optional)
        self.controls_visible = controls
        self.contour_checkbox = None
        self.mode_checkbox = None
        self.trail_checkbox = None
        self.threshold_slider = None
        self.minarea_slider = None
        self.initzone_radius_slider = None
        self.mask_radius_slider = None
        
        # Store initial values
        self._threshold = threshold
        self._minarea = minarea
        self._initzone_radius = initzone_radius
        self._mask_radius = mask_radius
        
        if controls:
            self._setup_controls()
    
    def _setup_controls(self):
        """Create and add control widgets to the widget."""
        # Checkboxes row
        checkbox_layout = QHBoxLayout()
        
        checkbox_layout.addStretch()
        self.contour_checkbox = QCheckBox("Show contour")
        self.contour_checkbox.setChecked(self.show_contours)
        self.contour_checkbox.setStyleSheet("font-size: 12px; padding: 4px;")
        self.contour_checkbox.stateChanged.connect(self._toggle_contour)
        checkbox_layout.addWidget(self.contour_checkbox)
        
        checkbox_layout.addSpacing(20)  # Add horizontal spacing
        
        self.trail_checkbox = QCheckBox("Show trail")
        self.trail_checkbox.setChecked(self.show_trail)
        self.trail_checkbox.setStyleSheet("font-size: 12px; padding: 4px;")
        self.trail_checkbox.stateChanged.connect(self._toggle_trail)
        checkbox_layout.addWidget(self.trail_checkbox)
        
        checkbox_layout.addSpacing(20)  # Add horizontal spacing
        
        self.mode_checkbox = QCheckBox("Binary/Masked mode")
        self.mode_checkbox.setChecked(True)  # Default to binary mode
        self.mode_checkbox.setStyleSheet("font-size: 12px; padding: 4px;")
        self.mode_checkbox.stateChanged.connect(self._toggle_mode)
        checkbox_layout.addWidget(self.mode_checkbox)
        
        #checkbox_layout.addStretch()
        self.layout.addLayout(checkbox_layout)
        
        # Sliders
        self.threshold_slider = SliderWidget(maxvalue=255, label="Threshold", 
                                            value=self._threshold)
        self.minarea_slider = SliderWidget(maxvalue=16000, label="Min area", 
                                          value=self._minarea)
        self.initzone_radius_slider = SliderWidget(maxvalue=300, label="IZ radius", 
                                                   value=self._initzone_radius)
        self.mask_radius_slider = SliderWidget(maxvalue=300, label="Mask radius", 
                                              value=self._mask_radius)
        
        self.layout.addWidget(self.threshold_slider)
        self.layout.addWidget(self.minarea_slider)
        self.layout.addWidget(self.initzone_radius_slider)
        self.layout.addWidget(self.mask_radius_slider)
    
    def connect_video_thread(self, video_thread):
        """
        Connect to a video thread for control.
        
        Args:
            video_thread: VideoThread instance to control
        """
        self.video_thread = video_thread
        
        # Extract mask from video thread if available
        if hasattr(video_thread, 'mask_coords') and video_thread.mask_coords is not None:
            self._mask = list(video_thread.mask_coords)
        
        # Update mode checkbox to reflect video thread's current mode
        if self.controls_visible and self.mode_checkbox is not None:
            if hasattr(video_thread, 'mode'):
                is_binary = (video_thread.mode == 'binary')
                self.mode_checkbox.setChecked(is_binary)
        
        # Connect slider signals if controls are visible
        if self.controls_visible and video_thread is not None:
            self.threshold_slider.value_changed.connect(self._update_threshold)
            self.minarea_slider.value_changed.connect(self._update_minarea)
            self.mask_radius_slider.value_changed.connect(self._update_mask_radius)
    
    def connect_video_interface(self, video_interface, zone_name='IZ'):
        """
        Connect to a video interface for zone updates.
        
        Args:
            video_interface: VideoInterface instance for zone updates
            zone_name: Name of the zone to control with the initzone radius slider (default: 'IZ')
        """
        self.video_interface = video_interface
        self._zone_name = zone_name
        
        # Extract initzone from video interface if the zone exists
        if hasattr(video_interface, 'zones') and zone_name in video_interface.zones:
            zone_info = video_interface.zones[zone_name]
            if zone_info['type'] == 'circular':
                self._initzone = list(zone_info['coords'])
        
        # Connect initzone slider signal if controls are visible
        if self.controls_visible and video_interface is not None:
            self.initzone_radius_slider.value_changed.connect(self._update_initzone_radius)
    
    def _update_threshold(self, value):
        """Update video thread threshold."""
        if self.video_thread:
            self.video_thread.set_threshold(value)
    
    def _update_minarea(self, value):
        """Update video thread minimum area."""
        if self.video_thread:
            self.video_thread.set_minarea(value)
    
    def _update_initzone_radius(self, radius):
        """Update initzone radius in video thread and interface."""
        if hasattr(self, '_initzone'):
            self._initzone[2] = radius
            if self.video_interface and hasattr(self, '_zone_name'):
                self.video_interface.add_zone(self._zone_name, 'circular', tuple(self._initzone))
    
    def _update_mask_radius(self, radius):
        """Update mask radius in video thread."""
        if hasattr(self, '_mask'):
            self._mask[2] = radius
            if self.video_thread:
                self.video_thread.set_circular_mask(self._mask)
    
    def _toggle_contour(self, state):
        """Toggle contour display on/off."""
        self.show_contours = (state == Qt.CheckState.Checked.value)
    
    def _toggle_trail(self, state):
        """Toggle trail display on/off."""
        self.show_trail = (state == Qt.CheckState.Checked.value)
    
    def _toggle_mode(self, state):
        """Toggle between binary and grayscale mode."""
        if self.video_thread:
            new_mode = 'binary' if state == Qt.CheckState.Checked.value else 'grayscale'
            self.video_thread.mode = new_mode

    def display_frame(self, frame, points=(), initzone=None, mask=None, contour=None):
        """
        Converts a grayscale frame to a QPixmap and displays it in the video label.
        Args:
            frame (np.ndarray): The grayscale frame to display.
            points (tuple): Tuple of tuples containing the centroid coordinates (x, y).
            initzone (tuple): Tuple containing (x, y, radius) of initiation zone. 
                            If None, uses internal _initzone if available.
            mask (tuple): Tuple containing (x, y, radius) of mask.
                         If None, uses internal _mask if available.
            contour (np.ndarray): OpenCV contour array to display (optional)
        """
        # Use internal values if parameters are None
        if initzone is None and hasattr(self, '_initzone'):
            initzone = self._initzone
        if mask is None and hasattr(self, '_mask'):
            mask = self._mask
        
        h, w = frame.shape  # Grayscale frames have only height and width
        bytes_per_line = w
        img_format = QImage.Format.Format_Grayscale8
        convert_to_qt_format = QImage(frame.data, w, h, bytes_per_line, img_format)
        p = convert_to_qt_format.scaled(640, 480, Qt.AspectRatioMode.KeepAspectRatio)
        pixmap = QPixmap.fromImage(p)
        #print(roi[2]); print('------------------------')
        #print(points); print('------------------------')
        if initzone is not None and len(initzone):
            self.add_circular_roi(pixmap, initzone[:2], initzone[2], color=IZ_COLOR) # SkyBlue
        if mask is not None and len(mask):
            self.add_circular_roi(pixmap, mask[:2], mask[2], color=(240,240,240))
            #self.add_rectangular_roi(pixmap, mask)
        
        # Draw contour if enabled and provided
        if self.show_contours and contour is not None:
            self.add_contour(pixmap, contour)
        
        # Update first point trail with new first point
        if points and points[0][0] > 0:
            self.update_first_point_trail(points[0])
        else:
            # Clear trail if no valid point is detected
            self.clear_first_point_trail()
        
        # Draw centroids based on internal show_trail setting
        if self.show_trail:
            # Draw the first point trail
            self.add_first_point_trail(pixmap)
        else:
            # Draw only the latest point(s)
            for point in points:
                if point[0] > 0:
                    self.add_point(pixmap, point)
        
        self.video_label.setPixmap(pixmap)

    def add_point(self, pixmap, point):
        """
        Displays the centroid as a red dot on the video label.
        Args:
            pixmap (QPixmap): The pixmap to draw on.
            point (tuple): The coordinates of the centroid (x, y).
        """
        painter = QPainter(pixmap)
        painter.setPen(Qt.PenStyle.NoPen)  # No border
        painter.setBrush(QColor(*CENTROID_COLOR))
        painter.drawEllipse(point[0] - 5, point[1] - 5, 10, 10)
        painter.end()

    def update_first_point_trail(self, point):
        """
        Updates the first point trail with a new point.
        Args:
            point (tuple): The coordinates of the first point (x, y).
        """
        self.first_point_trail.append(point)
        # Keep only the last max_trail_length points
        if len(self.first_point_trail) > self.max_trail_length:
            self.first_point_trail.pop(0)

    def add_first_point_trail(self, pixmap):
        """
        Draws the first point trail with decreasing transparency.
        Args:
            pixmap (QPixmap): The pixmap to draw on.
        """
        if not self.first_point_trail:
            return
            
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw trail points with decreasing alpha (oldest to newest)
        for ind, point in enumerate(self.first_point_trail):
            # Calculate alpha based on position in trail (0 = oldest, -1 = newest)
            alpha = int(255 * (ind + 1) / len(self.first_point_trail))
            
            # Create color with alpha
            color = QColor(*CENTROID_COLOR, alpha)  # Centroid color with varying alpha
            painter.setPen(Qt.PenStyle.NoPen)  # No border
            painter.setBrush(color)
            
            # Draw smaller circles for older points, larger for newer ones
            radius = 3 + (ind * 2) // len(self.first_point_trail)
            painter.drawEllipse(point[0] - radius, point[1] - radius, 
                              2 * radius, 2 * radius)
        
        painter.end()

    def clear_first_point_trail(self):
        """
        Clears the first point trail.
        """
        self.first_point_trail.clear()

    def set_trail_length(self, length):
        """
        Sets the maximum length of the first point trail.
        Args:
            length (int): Maximum number of points to keep in the trail.
        """
        self.max_trail_length = max(1, length)
        # Trim existing trail if necessary
        while len(self.first_point_trail) > self.max_trail_length:
            self.first_point_trail.pop(0)

    def set_contour_display(self, show: bool):
        """
        Enable or disable contour display.
        Args:
            show (bool): If True, contours will be displayed on the video.
        """
        self.show_contours = show

    def add_contour(self, pixmap: QPixmap, contour):
        """
        Draw a contour on the pixmap.
        Args:
            pixmap (QPixmap): The pixmap to draw on.
            contour (np.ndarray): OpenCV contour array (Nx1x2 shape).
        """
        if contour is None or len(contour) == 0:
            return
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Set pen for contour outline
        pen = QPen(QColor(*CONTOUR_COLOR), 2, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        
        # Draw the contour as a polygon
        # Contour shape is typically (N, 1, 2) - reshape to (N, 2)
        points = contour.reshape(-1, 2)
        
        # Convert to Qt points and draw
        qt_points = [QPointF(float(x), float(y)) for x, y in points]
        polygon = QPolygonF(qt_points)
        painter.drawPolygon(polygon)
        
        painter.end()

    def add_circular_roi(self, pixmap: QPixmap, center: tuple, radius: int,
                color: tuple = (32,74,135)) -> QPixmap:
        """
        Draw a circular region of interest on a QPixmap.
        """
        #new_pixmap = pixmap.copy()
        painter = QPainter(pixmap)
        pen = QPen(QColor(*color), 3, Qt.PenStyle.SolidLine)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(pen)
        #painter.setPen(Qt.GlobalColor.blue)

        rect_x = center[0] - radius
        rect_y = center[1] - radius
        diameter = 2 * radius

        painter.drawEllipse(rect_x, rect_y, diameter, diameter)
        painter.end()
        #return new_pixmap

    def add_rectangular_roi(self, pixmap: QPixmap, roi: tuple,
                           color: tuple = (255,0,0)) -> QPixmap:
        """
        Draw a rectangular region of interest on a QPixmap.
        
        Args:
            pixmap (QPixmap): The pixmap to draw on
            roi (tuple): (x1, y1, x2, y2) coordinates of the rectangle
            color (tuple): RGB color for the rectangle border (default: red)
        """
        x1, y1, x2, y2 = roi
        painter = QPainter(pixmap)
        pen = QPen(QColor(*color), 2, Qt.PenStyle.SolidLine)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(pen)

        # Draw rectangle from top-left to bottom-right
        width = x2 - x1
        height = y2 - y1
        painter.drawRect(x1, y1, width, height)
        painter.end()


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
        background-color: #C4A000;
        border: 1px solid #806000;
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

class ArduinoControlWidget(QWidget):
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
    
    def __init__(self, parent: Optional[QWidget] = None):
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
        
        # Timer for polling analog values
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self._poll_analog_values)
        self.poll_interval = 100  # Poll every 100ms (10 Hz)
        
        # GUI elements
        self.output_buttons: Dict[str, QPushButton] = {}
        self.input_indicators: Dict[int, QLabel] = {}
        self.input_value_labels: Dict[int, QLabel] = {}
        self.input_threshold_spinboxes: Dict[int, QDoubleSpinBox] = {}
        self.status_label: Optional[QLabel] = None
        self.monitoring_button: Optional[QPushButton] = None
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Set up the user interface."""
        self.setWindowTitle("Arduino Control Panel")
        self.setMinimumSize(480, 240)
        
        # Main layout
        main_layout = QVBoxLayout()
        
        # Status section (single line with monitoring toggle button)
        status_layout = QHBoxLayout()
        
        self.status_label = QLabel("Not connected to Arduino")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            QLabel {
                padding: 4px;
                font-size: 11px;
                color: #666666;
            }
        """)
        
        self.monitoring_button = QPushButton("Monitoring: ON")
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
        controls_group = QGroupBox("Arduino Controls")
        self.controls_layout = QGridLayout()
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
        if hasattr(arduino_thread, 'threshold_crossed'):
            arduino_thread.threshold_crossed.connect(self._on_threshold_crossed)
        
        # Start polling timer
        self.poll_timer.start(self.poll_interval)
        
        # Update status
        self.status_label.setText("Waiting for connection to Arduino...")
    
    def disconnect_arduino(self):
        """Disconnect from the current Arduino thread."""
        # Stop polling timer
        self.poll_timer.stop()
        
        if self.arduino_thread:
            # Disconnect signals
            try:
                if hasattr(self.arduino_thread, 'arduino_ready'):
                    self.arduino_thread.arduino_ready.disconnect(self._on_arduino_ready)
                if hasattr(self.arduino_thread, 'arduino_error'):
                    self.arduino_thread.arduino_error.disconnect(self._on_arduino_error)
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
        header_font = QFont()
        header_font.setBold(True)
        
        # Column headers
        input_header = QLabel("Input")
        input_header.setFont(header_font)
        self.controls_layout.addWidget(input_header, 0, 0)
        
        value_header = QLabel("Value")
        value_header.setFont(header_font)
        value_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.controls_layout.addWidget(value_header, 0, 1)
        
        threshold_header = QLabel("Threshold")
        threshold_header.setFont(header_font)
        threshold_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.controls_layout.addWidget(threshold_header, 0, 2)
        
        # Add spacing column
        self.controls_layout.setColumnMinimumWidth(3, 20)
        
        output_header = QLabel("Output")
        output_header.setFont(header_font)
        output_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
                indicator_label = QLabel(f"{pin_name} (A{pin_num})" if pin_name else f"A{pin_num}")
                indicator_label.setStyleSheet(INPUT_INDICATOR_STYLE_BELOW)
                indicator_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.controls_layout.addWidget(indicator_label, row, 0)
                self.input_indicators[pin_num] = indicator_label
                
                # Value display
                value_label = QLabel("0.000")
                value_label.setAlignment(Qt.AlignmentFlag.AlignRight | 
                                         Qt.AlignmentFlag.AlignVCenter)
                value_label.setStyleSheet("font-family: monospace; padding: 5px;")
                self.controls_layout.addWidget(value_label, row, 1)
                self.input_value_labels[pin_num] = value_label
                
                # Threshold spinbox
                threshold_spinbox = QDoubleSpinBox()
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
                    empty_label = QLabel("")
                    self.controls_layout.addWidget(empty_label, row, col)
            
            # --- OUTPUT COLUMN ---
            if ind < len(output_items):
                output_name, pin_num = output_items[ind]
                
                button = QPushButton(f"{output_name} (D{pin_num})")
                button.setStyleSheet(OUTPUT_BUTTON_STYLE_LOW)
                button.clicked.connect(lambda checked, name=output_name: self._toggle_output(name))
                self.controls_layout.addWidget(button, row, 4)
                
                self.output_buttons[output_name] = button
                self.output_states[output_name] = False
            else:
                # Empty cell if no more outputs
                empty_label = QLabel("")
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
    
    def set_poll_rate(self, rate_hz: float):
        """
        Set the rate at which analog values are polled from the Arduino.
        
        Args:
            rate_hz: Polling rate in Hz (updates per second). 
                    Default is 10 Hz. Recommended range: 1-100 Hz.
        """
        self.poll_interval = max(10, int(1000 / rate_hz))  # Minimum 10ms (100Hz)
        if self.poll_timer.isActive():
            self.poll_timer.setInterval(self.poll_interval)
    
    def _on_arduino_ready(self):
        """Handle Arduino ready signal."""
        self._setup_controls()
        self.status_label.setText("Arduino connected and ready")
    
    def _on_arduino_error(self, error_msg: str):
        """Handle Arduino error signal."""
        self.status_label.setText(f"Arduino error: {error_msg}")
    
    def _poll_analog_values(self):
        """Poll analog input values from Arduino thread."""
        # Only poll if monitoring is enabled and arduino is connected
        if not self.monitoring_enabled or not self.arduino_thread:
            return
        
        # Get current values from Arduino thread
        current_values = self.arduino_thread.get_current_values()
        
        # Update displays for each pin
        for pin_num, value in current_values.items():
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



