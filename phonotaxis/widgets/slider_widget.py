"""
Slider widget for phonotaxis applications.
"""

from PyQt6.QtWidgets import QWidget, QLabel, QHBoxLayout
from PyQt6.QtCore import pyqtSignal, Qt
from .basic import CustomSlider


# Stylesheet for slider appearance
SLIDER_STYLESHEET = """
    QSlider::handle:horizontal {
        background: #555;
    }
    QSlider::add-page:horizontal {
        background: #bbb;
    }
    QSlider::sub-page:horizontal {
        background: #888;
    }
"""


class SliderWidget(QWidget):
    """
    A widget that contains a slider for adjusting a video parameter.
    
    Emits a value_changed signal when the slider value changes.
    """
    value_changed = pyqtSignal(int)
    
    def __init__(self, parent=None, maxvalue=128, label="Value", value=None):
        """
        Initialize the slider widget.
        
        Args:
            parent: Parent widget (optional)
            maxvalue (int): Maximum slider value
            label (str): Label text to display
            value (int): Initial value (defaults to maxvalue // 2 if None)
        """
        super().__init__(parent)
        self.maxvalue = maxvalue
        self.value = value if value is not None else maxvalue // 2
        self.label = label
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)  # Remove margins for compact layout
        
        # Label to display the current slider value
        self.value_label = QLabel(f"{self.label}: {self.value}")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.value_label.setStyleSheet("font-size: 12px; padding: 4px;")
        self.value_label.setFixedWidth(100)  # Set a fixed width for consistent layout
        self.layout.addWidget(self.value_label)
        
        # Slider to adjust the value
        self.slider = CustomSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(self.maxvalue)
        self.slider.setValue(self.value)
        self.slider.setSingleStep(self.maxvalue//128)
        self.slider.setStyleSheet(SLIDER_STYLESHEET)
        self.slider.valueChanged.connect(self.update_value)
        self.layout.addWidget(self.slider)
        
    def update_value(self, value):
        """
        Updates the current value and the display label.
        This method is connected to the QSlider's valueChanged signal.
        
        Args:
            value (int): New slider value
        """
        self.value = value
        self.value_label.setText(f"{self.label}: {self.value}")
        self.value_changed.emit(self.value)
