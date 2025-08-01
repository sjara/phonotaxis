"""
Graphical interface utilities. 
"""

import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout
from PyQt6.QtWidgets import QWidget, QMessageBox, QSlider
from PyQt6.QtGui import QImage, QPixmap, QIcon, QPainter, QPen, QColor
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Phonotaxis task")
        self.setGeometry(100, 100, 800, 600)
        self.setWindowIcon(self.create_icon())
        self.current_threshold = 10
        self.init_ui()
        
    def create_icon(self):
        """Creates a simple icon using a Font Awesome-like character."""
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = painter.font()
        font.setPointSize(40)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "🔊")
        painter.end()
        return QIcon(pixmap)

    def init_ui(self):
        """Initializes the user interface elements."""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.video_label = QLabel("Waiting for camera feed...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: #222; color: #fff;" +
                                       "border-radius: 10px;")
        self.layout.addWidget(self.video_label)

        #self.add_threshold_slider()
        
        self.status_label = QLabel("Monitoring video feed...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 20px; font-weight: bold;" +
                                        "padding: 10px; border-radius: 8px;" +
                                        "background-color: #333; color: #eee;")
        self.layout.addWidget(self.status_label)

    def add_threshold_slider(self):
        # Threshold label to display the current slider value
        self.threshold_value_label = QLabel(f"Binarization Threshold: {self.current_threshold}")
        self.threshold_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.threshold_value_label.setStyleSheet("font-size: 16px; padding: 5px;")
        self.layout.addWidget(self.threshold_value_label)

        # Threshold slider
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setMinimum(0)
        self.threshold_slider.setMaximum(255)  # Typical range for 8-bit grayscale
        self.threshold_slider.setValue(self.current_threshold)
        self.threshold_slider.setSingleStep(1)
        self.threshold_slider.setStyleSheet("QSlider::groove:horizontal { border: 1px solid #999; height: 8px; background: #ddd; margin: 2px 0; border-radius: 4px; }" +
                                            "QSlider::handle:horizontal { background: #555; border: 1px solid #555; width: 18px; margin: -2px 0; border-radius: 9px; }" +
                                            "QSlider::add-page:horizontal { background: #bbb; }" +
                                            "QSlider::sub-page:horizontal { background: #888; }")
        
        # Connect the slider's valueChanged signal to the update_threshold method
        self.threshold_slider.valueChanged.connect(self.update_threshold)
        
        self.layout.addWidget(self.threshold_slider)
        
    def update_threshold(self, value):
        """
        Updates the current threshold value and the display label.
        This method is connected to the QSlider's valueChanged signal.
        """
        self.current_threshold = value
        self.threshold_value_label.setText(f"Binarization Threshold: {self.current_threshold}")
        
        
    def display_frame(self, frame, points=(), roi=()):
        """
        Converts a grayscale frame to a QPixmap and displays it in the video label.
        Args:
            frame (np.ndarray): The grayscale frame to display.
            points (tuple): Tuple of tuples containing the centroid coordinates (x, y).
            roi (tuple): Tuple containing (x, y, radius) of ROI
        """
        h, w = frame.shape  # Grayscale frames have only height and width
        bytes_per_line = w
        img_format = QImage.Format.Format_Grayscale8
        convert_to_qt_format = QImage(frame.data, w, h, bytes_per_line, img_format)
        p = convert_to_qt_format.scaled(640, 480, Qt.AspectRatioMode.KeepAspectRatio)
        pixmap = QPixmap.fromImage(p)
        #print(roi[2]); print('------------------------')
        #print(points); print('------------------------')
        if len(roi):
            self.add_roi(pixmap, roi[:2], roi[2])
        for point in points:
            # Check that the point has valid coordinates
            if point[0]>0:
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
        painter.setPen(Qt.GlobalColor.red)
        painter.setBrush(Qt.GlobalColor.red)
        painter.drawEllipse(point[0] - 5, point[1] - 5, 10, 10)
        painter.end()

    def add_roi(self, pixmap: QPixmap, center: tuple, radius: int,
                color: tuple = (0,0,255)) -> QPixmap:
        """
        Draw a circular region of interest on a QPixmap.
        """
        #new_pixmap = pixmap.copy()
        painter = QPainter(pixmap)
        pen = QPen(QColor(*color), 3, Qt.PenStyle.SolidLine)
        #painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(pen)
        #painter.setPen(Qt.GlobalColor.blue)

        rect_x = center[0] - radius
        rect_y = center[1] - radius
        diameter = 2 * radius

        painter.drawEllipse(rect_x, rect_y, diameter, diameter)
        painter.end()
        #return new_pixmap
        
    def closeEvent(self, event):
        event.accept()


def create_app(task_class):

    app = QApplication(sys.argv)

    # Create a dummy QPainter for icon creation if not running in a full GUI environment
    # This is a workaround for the QPainter issue if run in a headless environment or certain IDEs
    try:
        from PyQt6.QtGui import QPainter
    except ImportError:
        print("QPainter not available. Icon might not render correctly.")
        # Define a dummy QPainter if not available (e.g., in some test environments)
        class QPainter:
            def __init__(self, *args): pass
            def setRenderHint(self, *args): pass
            def setFont(self, *args): pass
            def drawText(self, *args): pass
            def end(self): pass

    # Create and show the main window
    window = task_class()
    window.show()

    # Start the application event loop
    sys.exit(app.exec())
    
