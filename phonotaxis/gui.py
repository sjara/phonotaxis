"""
Graphical interface utilities. 
"""

import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QMessageBox
from PyQt6.QtGui import QImage, QPixmap, QIcon, QPainter
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Phonotaxis task")
        self.setGeometry(100, 100, 800, 600)
        self.setWindowIcon(self.create_icon())
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

        self.status_label = QLabel("Monitoring video feed...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 20px; font-weight: bold;" +
                                        "padding: 10px; border-radius: 8px;" +
                                        "background-color: #333; color: #eee;")
        self.layout.addWidget(self.status_label)

        #self.feedback_timer = QTimer(self)
        #self.feedback_timer.setSingleShot(True)
        #self.feedback_timer.timeout.connect(self.reset_to_monitoring)

    def display_frame(self, frame, points=()):
        """
        Converts a grayscale frame to a QPixmap and displays it in the video label.
        Args:
            frame (np.ndarray): The grayscale frame to display.
            points (tuple): Tuple of tuples containing the centroid coordinates (x, y).
        """
        h, w = frame.shape  # Grayscale frames have only height and width
        bytes_per_line = w
        img_format = QImage.Format.Format_Grayscale8
        convert_to_qt_format = QImage(frame.data, w, h, bytes_per_line, img_format)
        p = convert_to_qt_format.scaled(640, 480, Qt.AspectRatioMode.KeepAspectRatio)
        pixmap = QPixmap.fromImage(p)
        #print(points); print('------------------------')
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
    
