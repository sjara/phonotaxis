"""
Track object on video and use a slider to set the threshold for binarizing video.
"""

from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout
from phonotaxis import videomodule
from phonotaxis import gui
from phonotaxis import widgets
from phonotaxis import config

CAMERA_INDEX = config.CAMERA_INDEX
# SAVE_VIDEO_TO = None

class TestVideoThreshold(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video threshold test")
        self.setGeometry(800, 400, 800, 600)
        self.setWindowIcon(gui.create_icon())

        # -- Define main GUI layout --
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.video_widget = widgets.VideoWidget()
        self.threshold_slider = widgets.SliderWidget(maxvalue=255, label="Threshold")
        self.minarea_slider = widgets.SliderWidget(maxvalue=16000, label="Min area")

        self.layout.addWidget(self.video_widget)
        self.layout.addWidget(self.threshold_slider)
        self.layout.addWidget(self.minarea_slider)

        self.threshold_slider.value_changed.connect(self.update_threshold)
        self.minarea_slider.value_changed.connect(self.update_minarea)
        
        self.video_thread = videomodule.VideoThread(config.CAMERA_INDEX, mode='binary',
                                                    tracking=True, debug=True)
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

    def closeEvent(self, event):
        """Ensures the video thread is stopped when the main window closes."""
        self.video_thread.stop()
        event.accept()
        
if __name__ == "__main__":
    (app, paradigm) = gui.create_app(TestVideoThreshold)
