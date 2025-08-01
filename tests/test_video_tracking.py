"""
Test video tracking within the GUI.
"""

from phonotaxis import gui
from phonotaxis import videomodule
from phonotaxis import config

# --- Configuration ---
SAVE_VIDEO_TO = None #'/tmp/output.avi' #None
DISPLAY_MODE = 'binary'  # It can be 'grayscale' or 'binary'

# -- Settings for object tracking --
BLACK_THRESHOLD = 40  # Theshold for binarizing the video frame
MIN_AREA = 4000  # Minimum area of the object to be considered valid for tracking

class Task(gui.MainWindow):
    def __init__(self):
        super().__init__()
        self.video_thread = videomodule.VideoThread(config.CAMERA_INDEX, SAVE_VIDEO_TO,
                                                    mode=DISPLAY_MODE, tracking=True)
        self.video_thread.set_tracking_params(threshold=BLACK_THRESHOLD,
                                              min_area=MIN_AREA)
        self.video_thread.frame_processed.connect(self.update_image)
        self.video_thread.start()

    def update_image(self, timestamp, frame, points):
        self.display_frame(frame, points)
        
    def closeEvent(self, event):
        """Handles the close event to stop the video thread."""
        self.video_thread.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    (app,paradigm) = gui.create_app(Task)
