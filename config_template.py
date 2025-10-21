"""
Configuration file for phonotaxis application in a specific rig.
"""

CAMERA_INDEX = 0

ARDUINO_PORT = '/dev/ttyACM0' # COM4

# Input pins need to be defined in order from 0 to N-1
INPUT_PINS = {
    'port1': 0,  # Analog pin A0
    'port2': 1,  # Analog pin A1
}

# Output pins can be defined in any order
OUTPUT_PINS = {
    'water1': 13,  # Digital pin for water delivery 1
    'water2': 12,  # Digital pin for water delivery 2
}

# You can list available sound devices in Python with:
# python -c "import sounddevice as sd; print(sd.query_devices())"
SOUND_DEVICE = 15  # 32: Xonar 5.1 surround sound card

VIDEO_PATH = '/var/tmp/videophonotaxis/'
DATA_PATH = '/var/tmp/dataphonotaxis/'
