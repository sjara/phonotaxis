"""
Use a slider to set the threshold for binarizing video.
"""

import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout
from PyQt6.QtWidgets import QWidget, QMessageBox, QSlider
from PyQt6.QtGui import QImage, QPixmap, QIcon, QPainter
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer
from phonotaxis import videomodule
from phonotaxis import gui
from phonotaxis import config

CAMERA_INDEX = config.CAMERA_INDEX
SAVE_VIDEO_TO = None

class TestVideoThreshold(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video threshold test")
        self.setGeometry(800, 400, 800, 600)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.video_widget = gui.VideoWidget()
        #self.threshold_slider = gui.ThresholdSlider()
        self.threshold_slider = gui.SliderWidget(maxvalue=255, label="Threshold")
        self.minarea_slider = gui.SliderWidget(maxvalue=16000, label="Min area")

        self.layout.addWidget(self.video_widget)
        self.layout.addWidget(self.threshold_slider)
        self.layout.addWidget(self.minarea_slider)

        self.threshold_slider.value_changed.connect(self.update_threshold)
        self.minarea_slider.value_changed.connect(self.update_minarea)
        
        self.video_thread = videomodule.VideoThread(config.CAMERA_INDEX, mode='binary', tracking=True, debug=True)
        self.video_thread.frame_processed.connect(self.update_image)
        self.update_threshold(self.threshold_slider.value)
        self.update_minarea(self.minarea_slider.value)
        self.video_thread.start()
        
    def update_image(self, timestamp, frame, points):
        self.video_widget.display_frame(frame, points)
        
    def update_threshold(self, value):
        self.video_thread.set_threshold(value)

    def update_minarea(self, value):
        self.video_thread.set_minarea(value)
        
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TestVideoThreshold()
    window.show()
    sys.exit(app.exec())
