"""
Video display widget for phonotaxis applications.
"""

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QCheckBox
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
