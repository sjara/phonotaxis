"""
Collect analog signal from an Arduino Mega 2560 which has the standard firmata
loaded into it.

You should set the `ARDUINO_PORT` variable in `config.py`.
"""

import time
from pyfirmata2 import Arduino
from phonotaxis import config


PORT = config.ARDUINO_PORT #Arduino.AUTODETECT

def on_analog_read(value):
    print(f"Analog value: {value} \t Press Ctrl+C to stop.")
    #time.sleep(0.1)  # Simulate some processing delay
    #pass

print(f'Connecting to Arduino on port: {PORT} ...')
board = Arduino(PORT)

#board.samplingOn(1) # See https://github.com/berndporr/pyFirmata2

analog_pin = board.get_pin('a:0:i')
analog_pin.enable_reporting()

analog_pin.register_callback(on_analog_read)

print("Collecting analog data. Press Ctrl+C to stop.")
try:
    while True:
        board.iterate()
        time.sleep(0.01)
except KeyboardInterrupt:
    print("Exiting...")
finally:
    board.exit()
