"""
Configuration file for phonotaxis application in a specific rig.
"""

CAMERA_INDEX = 0

ARDUINO_PORT = '/dev/ttyACM0' # COM4

# You can list available sound devices in Python with:
# python -c "import sounddevice as sd; print(sd.query_devices())"
SOUND_DEVICE = 15  # 32: Xonar 5.1 surround sound cardx
