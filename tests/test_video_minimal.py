"""
Test video capture from the video module.
"""

import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QMessageBox
from PyQt6.QtGui import QImage, QPixmap, QIcon, QPainter
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer
from phonotaxis import videomodule
from phonotaxis import config

CAMERA_INDEX = config.CAMERA_INDEX
SAVE_VIDEO_TO = None

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setGeometry(100, 100, 800, 600)
        self.setWindowTitle("Video Module Test")
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.video_label = QLabel("Waiting for camera feed...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: #222; color: #fff;")
        self.layout.addWidget(self.video_label)

        # Start the video capture thread and connects its signals
        self.thread = videomodule.VideoThread(CAMERA_INDEX, SAVE_VIDEO_TO)
        #self.thread.new_frame_signal.connect(self.update_image)
        self.thread.frame_processed.connect(self.update_image)
        self.thread.camera_error_signal.connect(self.show_camera_error)
        self.thread.start()

    def update_image(self, timestamp, frame):
        """Slot to update the video display label with new frames."""

        # If it's a 3-channel image, convert it to grayscale
        if len(frame.shape) == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = frame.shape  # Grayscale frames have only height and width
        bytes_per_line = w
        img_format = QImage.Format.Format_Grayscale8
        convert_to_qt_format = QImage(frame.data, w, h, bytes_per_line, img_format)
        p = convert_to_qt_format.scaled(640, 480, Qt.AspectRatioMode.KeepAspectRatio)
        self.video_label.setPixmap(QPixmap.fromImage(p))

    def show_camera_error(self, message):
        """Displays an error message if the camera cannot be opened or fails."""
        QMessageBox.critical(self, "Camera Error", message)
        self.status_label.setText("Camera Error: " + message)
        self.video_label.setText("Camera feed unavailable.")
        self.thread.stop() # Stop the thread if there's a critical error

    def closeEvent(self, event):
        """Ensures the video thread is stopped when the main window closes."""
        print("Closing application. Stopping video thread...")
        self.thread.stop()
        event.accept()
        
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Create and show the main window
    window = MainWindow()
    window.show()

    # Start the application event loop
    sys.exit(app.exec())
