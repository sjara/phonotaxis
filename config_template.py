"""
Configuration file for phonotaxis application in a specific rig.
"""

CAMERA_INDEX = 0

HARDWARE_INTERFACE = 'arduino'  # Options: 'arduino', 'emulator'
#HARDWARE_INTERFACE = 'emulator'  # Options: 'arduino', 'emulator'

ARDUINO_PORT = '/dev/ttyACM0' # COM4
ARDUINO_SAMPLING_INTERVAL = 10  # in milliseconds
ARDUINO_INPUTS_INVERTED = True  # Set to True if using pull-up resistors

# Input pins need to be defined in order from 0 to N-1
INPUT_PINS = {
    'L': 0,  # Analog pin A0
    'R': 1,  # Analog pin A1
}

# Output pins can be defined in any order
OUTPUT_PINS = {
    'ValveL': 13,  # Digital pin for water delivery 1
    'ValveR': 12,  # Digital pin for water delivery 2
}

# You can list available sound devices in Python with:
# python -c "import sounddevice as sd; print(sd.query_devices())"
SOUND_DEVICE = 15  # 32: Xonar 5.1 surround sound card

VIDEO_PATH = '/var/tmp/videophonotaxis/'
DATA_PATH = '/var/tmp/dataphonotaxis/'
