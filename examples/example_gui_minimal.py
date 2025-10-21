"""
Minimal test of the GUI.
"""

from PyQt6.QtWidgets import QMainWindow
from phonotaxis import gui
from phonotaxis import widgets

class Task(QMainWindow):
    def __init__(self):
        super().__init__()
        self.video_widget = widgets.VideoWidget()
        self.setCentralWidget(self.video_widget)

if __name__ == "__main__":
    (app,paradigm) = gui.create_app(Task)
