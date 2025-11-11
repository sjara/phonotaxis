"""
Basic utility widgets for phonotaxis applications.
"""

from PyQt6.QtWidgets import QLabel, QSlider
from PyQt6.QtCore import Qt


class StatusWidget(QLabel):
    """
    A simple status display widget.
    
    Displays status messages with predefined styling.
    """
    def __init__(self):
        super().__init__("Monitoring video feed...")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reset()
        
    def reset(self, label="Monitoring video feed..."):
        """
        Reset the status widget with a new label.
        
        Args:
            label (str): Text to display
        """
        self.setText(label)
        self.setStyleSheet("font-size: 20px; font-weight: bold;" +
                           "padding: 10px; border-radius: 6px;" +
                           "background-color: #333; color: #eee;")


class CustomSlider(QSlider):
    """
    Custom QSlider that ignores arrow key events.
    
    This prevents the slider from capturing arrow key events,
    allowing parent widgets to handle them instead.
    """
    def keyPressEvent(self, event):
        """Override to ignore arrow keys."""
        if event.key() in [Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down]:
            # Ignore arrow keys - let parent handle them
            event.ignore()
        else:
            # For other keys, use default slider behavior
            super().keyPressEvent(event)
