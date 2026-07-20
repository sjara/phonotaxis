"""
Video display widget for phonotaxis applications.
"""

import cv2
import math
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QPolygonF
from .slider_widget import SliderWidget


# Color constants for video display
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
        
        # Add Play/Pause button
        self.play_pause_button = QPushButton("Play")
        self.play_pause_button.setStyleSheet("font-weight: bold; min-width: 80px; font-size: 12px; padding: 4px;")
        self.play_pause_button.clicked.connect(self._toggle_play_pause)
        self.play_pause_button.setVisible(False)  # Hidden by default, shown only in playback mode
        checkbox_layout.addWidget(self.play_pause_button)
        
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
        
        # Set initial visibility and button text based on thread's paused state
        is_playback = isinstance(video_thread.camera_index, str)
        if hasattr(self, 'play_pause_button'):
            self.play_pause_button.setVisible(is_playback)
            if is_playback:
                if self.video_thread.paused:
                    self.play_pause_button.setText("Play")
                else:
                    self.play_pause_button.setText("Pause")
        
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

    def _toggle_play_pause(self):
        """Toggle play/pause state of the video thread."""
        if self.video_thread is not None:
            new_paused = not self.video_thread.paused
            self.video_thread.paused = new_paused
            if new_paused:
                self.play_pause_button.setText("Play")
            else:
                self.play_pause_button.setText("Pause")

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
        
        # Calculate scale factor between original frame and the scaled QPixmap
        scale_x = p.width() / float(w) if w > 0 else 1.0
        scale_y = p.height() / float(h) if h > 0 else 1.0
        
        if initzone is not None and len(initzone):
            self.add_circular_roi(pixmap, initzone[:2], initzone[2], color=IZ_COLOR, scale_x=scale_x, scale_y=scale_y) # SkyBlue
        if mask is not None and len(mask):
            self.add_circular_roi(pixmap, mask[:2], mask[2], color=(240,240,240), scale_x=scale_x, scale_y=scale_y)
        
        # Draw contour if enabled and provided
        if self.show_contours and contour is not None:
            self.add_contour(pixmap, contour, scale_x=scale_x, scale_y=scale_y)
            self.add_contour_axes(pixmap, contour, scale_x=scale_x, scale_y=scale_y)
        
        # Update first point trail with new first point
        if points and points[0][0] > 0:
            self.update_first_point_trail(points[0])
        else:
            # Clear trail if no valid point is detected
            self.clear_first_point_trail()
        
        # Draw centroids based on internal show_trail setting
        if self.show_trail:
            # Draw the first point trail
            self.add_first_point_trail(pixmap, scale_x=scale_x, scale_y=scale_y)
        else:
            # Draw only the latest point(s)
            for point in points:
                if point[0] > 0:
                    self.add_point(pixmap, point, scale_x=scale_x, scale_y=scale_y)
        
        self.video_label.setPixmap(pixmap)
 
    def add_point(self, pixmap, point, scale_x=1.0, scale_y=1.0):
        """
        Displays the centroid as a red dot on the video label.
        
        Args:
            pixmap (QPixmap): The pixmap to draw on.
            point (tuple): The coordinates of the centroid (x, y).
        """
        painter = QPainter(pixmap)
        painter.setPen(Qt.PenStyle.NoPen)  # No border
        painter.setBrush(QColor(*CENTROID_COLOR))
        px = int(point[0] * scale_x)
        py = int(point[1] * scale_y)
        painter.drawEllipse(px - 5, py - 5, 10, 10)
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

    def add_first_point_trail(self, pixmap, scale_x=1.0, scale_y=1.0):
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
            px = int(point[0] * scale_x)
            py = int(point[1] * scale_y)
            painter.drawEllipse(px - radius, py - radius, 
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

    def add_contour(self, pixmap: QPixmap, contour, scale_x=1.0, scale_y=1.0):
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
        qt_points = [QPointF(float(x * scale_x), float(y * scale_y)) for x, y in points]
        polygon = QPolygonF(qt_points)
        painter.drawPolygon(polygon)
        
        painter.end()

    def add_contour_axes(self, pixmap: QPixmap, contour, scale_x=1.0, scale_y=1.0):
        """
        Draws the major and minor axes of the contour as lines.
        """
        if contour is None or len(contour) < 5:
            return
            
        try:
            (cx, cy), (d1, d2), angle = cv2.fitEllipse(contour)
            
            # Determine major and minor lengths and orientation angle
            if d1 >= d2:
                major_len = d1
                minor_len = d2
                major_angle = angle + 90
            else:
                major_len = d2
                minor_len = d1
                major_angle = angle
            
            theta_major = math.radians(major_angle)
            # Direction vector for major axis (clockwise from 12 o'clock)
            dx_major = math.sin(theta_major)
            dy_major = -math.cos(theta_major)
            
            # Direction vector for minor axis (perpendicular to major axis)
            theta_minor = math.radians(major_angle + 90)
            dx_minor = math.sin(theta_minor)
            dy_minor = -math.cos(theta_minor)
            
            # Major axis endpoints
            x1 = cx - (major_len / 2.0) * dx_major
            y1 = cy - (major_len / 2.0) * dy_major
            x2 = cx + (major_len / 2.0) * dx_major
            y2 = cy + (major_len / 2.0) * dy_major
            
            # Minor axis endpoints
            x3 = cx - (minor_len / 2.0) * dx_minor
            y3 = cy - (minor_len / 2.0) * dy_minor
            x4 = cx + (minor_len / 2.0) * dx_minor
            y4 = cy + (minor_len / 2.0) * dy_minor
            
            # Draw lines on pixmap
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # Draw major axis (Green / Tango Chameleon Green)
            painter.setPen(QPen(QColor(138, 226, 52), 2, Qt.PenStyle.SolidLine))
            painter.drawLine(
                QPointF(x1 * scale_x, y1 * scale_y),
                QPointF(x2 * scale_x, y2 * scale_y)
            )
            
            # Draw minor axis (Red / Tango Scarlet Red)
            painter.setPen(QPen(QColor(239, 41, 41), 2, Qt.PenStyle.SolidLine))
            painter.drawLine(
                QPointF(x3 * scale_x, y3 * scale_y),
                QPointF(x4 * scale_x, y4 * scale_y)
            )
            
            painter.end()
        except Exception as e:
            print(f"Error drawing contour axes: {e}")

    def add_circular_roi(self, pixmap: QPixmap, center: tuple, radius: int,
                color: tuple = (32,74,135), scale_x=1.0, scale_y=1.0) -> QPixmap:
        """
        Draw a circular region of interest on a QPixmap.
        
        Args:
            pixmap (QPixmap): The pixmap to draw on
            center (tuple): (x, y) coordinates of the circle center
            radius (int): Radius of the circle
            color (tuple): RGB color for the circle border
        """
        #new_pixmap = pixmap.copy()
        painter = QPainter(pixmap)
        pen = QPen(QColor(*color), 3, Qt.PenStyle.SolidLine)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(pen)
        #painter.setPen(Qt.GlobalColor.blue)

        scaled_cx = center[0] * scale_x
        scaled_cy = center[1] * scale_y
        scaled_radius = radius * scale_x

        rect_x = scaled_cx - scaled_radius
        rect_y = scaled_cy - scaled_radius
        diameter = 2 * scaled_radius

        painter.drawEllipse(int(rect_x), int(rect_y), int(diameter), int(diameter))
        painter.end()
        #return new_pixmap

    def add_rectangular_roi(self, pixmap: QPixmap, roi: tuple,
                           color: tuple = (255,0,0), scale_x=1.0, scale_y=1.0) -> QPixmap:
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
        scaled_x1 = x1 * scale_x
        scaled_y1 = y1 * scale_y
        scaled_x2 = x2 * scale_x
        scaled_y2 = y2 * scale_y

        width = scaled_x2 - scaled_x1
        height = scaled_y2 - scaled_y1
        painter.drawRect(int(scaled_x1), int(scaled_y1), int(width), int(height))
        painter.end()
