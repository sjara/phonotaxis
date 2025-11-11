"""
Useful widgets for phonotaxis applications.

This package provides reusable UI components for building phonotaxis experiments,
including video display, session management, Arduino control, and parameter adjustment.
"""

# Import all widgets to maintain backward compatibility
# Users can still do: from phonotaxis import widgets; widgets.VideoWidget()
from .basic import StatusWidget, CustomSlider
from .session_info import SessionInfo
from .slider_widget import SliderWidget
from .video_widget import VideoWidget
from .arduino_control_widget import ArduinoControlWidget

# Export all public classes
__all__ = [
    'StatusWidget',
    'CustomSlider',
    'SessionInfo',
    'SliderWidget',
    'VideoWidget',
    'ArduinoControlWidget',
]
