"""
Minimal test of the GUI.
"""

from phonotaxis import gui

class Task(gui.MainWindow):
    def __init__(self):
        super().__init__()

if __name__ == "__main__":
    (app,paradigm) = gui.create_app(Task)
