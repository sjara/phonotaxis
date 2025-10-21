"""
Test more than two sound channels.

You need to set which device to use in the config.py file.

USAGE:
python test_multichannel_sound.py
python test_multichannel_sound.py <channel_index>
"""

import sys
import sounddevice as sd
import numpy as np
from phonotaxis import config

# Get which channel to use as command line argument
if len(sys.argv) > 1:
    channel_index = int(sys.argv[1])
else:
    channel_index = None

DEVICE_INDEX = config.SOUND_DEVICE
N_CHANNELS = 6  # Number of channels to test

print(f"Default device: {sd.default.device}")
sd.default.device = DEVICE_INDEX
print(f"Device to use: {sd.default.device}")

# Generate a sine wave for each channel
duration = 1.0  # seconds
samplerate = 44100  # samples per second
frequency = 440  # Hz
amplitude = 0.5  # Amplitude of the sound wave

tvec = np.linspace(0, duration, int(samplerate * duration), endpoint=False)
sine_wave = amplitude * np.sin(2 * np.pi * frequency * tvec)

if channel_index is not None:
    multichan_output = np.zeros((len(sine_wave), N_CHANNELS),
                                dtype=np.float32)
    multichan_output[:, channel_index] = sine_wave
else:
    # Play a different sound on each speaker
    multichan_output = np.zeros((N_CHANNELS*len(sine_wave), N_CHANNELS),
                                dtype=np.float32)
    # Play the modulated sine wave on each channel sequentially
    for indc in range(N_CHANNELS):
        samples_range = slice(indc*len(sine_wave), (indc+1)*len(sine_wave))
        mod = (amplitude * np.sin(2 * np.pi * tvec * (indc + 1))) > 0
        multichan_output[samples_range, indc] = mod*sine_wave

# Play the multichannel sound
sd.play(multichan_output, samplerate=samplerate, device=DEVICE_INDEX)
sd.wait()  # Wait until sound has finished playing
