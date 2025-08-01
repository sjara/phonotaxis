"""
Create and present sounds.
"""

import sys
import sounddevice as sd
import random
import numpy as np

SOUND_DURATION = 0.5  # seconds
SOUND_FREQUENCY = 440  # Hz (A4 note)
SOUND_AMPLITUDE = 0.5 # Global amplitude for the sound wave
SAMPLERATE = 44100  # samples per second

def list_devices():
    return sd.query_devices()

def find_5_1_device():
    pass

class SoundPlayer(object):
    def __init__(self):
        self.device = sd.default.device[1]  # Use default device

    def play_noise(self, max_channels=2):
        tvec = np.linspace(0, SOUND_DURATION, int(SAMPLERATE * SOUND_DURATION), False)
        noise_wave = SOUND_AMPLITUDE * np.random.rand(len(tvec))
        multichan_output = np.tile(noise_wave[:,np.newaxis], (1, max_channels)).astype(np.float32)
        try:
            sd.play(multichan_output, SAMPLERATE, device=self.device)
        except Exception as e:
            print(f"Sound playback error: {e}")
        
        
    def play_tone(self, channel=0, max_channels=2):
        """
        Channels:
          0: left
          1: right
        """
        # Generate a sine wave
        tvec = np.linspace(0, SOUND_DURATION, int(SAMPLERATE * SOUND_DURATION), False)
        sine_wave = SOUND_AMPLITUDE * np.sin(2 * np.pi * SOUND_FREQUENCY * tvec)

        # Create multichan output
        multichan_output = np.zeros((len(sine_wave), max_channels), dtype=np.float32)
        multichan_output[:, channel] = sine_wave

        try:
            sd.play(multichan_output, SAMPLERATE, device=self.device)
            #sd.wait()  # Commented out as per user request to avoid slowing down video
        except Exception as e:
            #QMessageBox.warning(self, "Sound Error", f"Could not play sound: {e}\n"
            #                    "Please ensure your audio output device is correctly configured.")
            print(f"Sound playback error: {e}")
            ##self.reset_to_monitoring() # Reset state if sound fails

    
