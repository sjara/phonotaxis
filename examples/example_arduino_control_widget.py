"""
Test the Arduino control widget.
"""

import sys
from PyQt6.QtWidgets import QApplication
from phonotaxis import widgets
from phonotaxis import arduinomodule

app = QApplication(sys.argv)

# Create Arduino thread (will attempt to connect on start)
arduino_thread = arduinomodule.ArduinoThread(debug=False)

# Create control widget
widget = widgets.ArduinoControlWidget()
widget.connect_arduino(arduino_thread)
widget.show()

# Start Arduino thread
arduino_thread.start()

# Run application
exit_code = app.exec()

# Clean up
arduino_thread.stop()
arduino_thread.wait()

sys.exit(exit_code)

