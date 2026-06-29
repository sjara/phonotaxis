"""
Example of playing a sound with selectable backend (ALSA or PortAudio).

ALSA (default) writes directly to the hw device for low-latency playback at
high sampling rates (e.g. 384 kHz). PortAudio is cross-platform and uses the
system's default audio stack.

Usage:
    python example_alsa_sound.py          # uses ALSA (default)
    python example_alsa_sound.py portaudio  # uses PortAudio

Device parameters are read from config.py.
"""

import sys
import time
from phonotaxis import soundmodule, config

backend = sys.argv[1] if len(sys.argv) > 1 else 'alsa'

if backend == 'alsa':
    DEVICE = config.ALSA_DEVICE
    SAMPLERATE = config.ALSA_SAMPLERATE
    PERIOD_SIZE = config.ALSA_PERIOD_SIZE
else:
    DEVICE = config.SOUND_DEVICE
    SAMPLERATE = 44100
    PERIOD_SIZE = None

# Create sounds at the device's native sampling rate.
sound1 = soundmodule.Sound(duration=1.0, srate=SAMPLERATE)
sound1.add_tone(freq=1000, amp=0.3)
sound1.apply_rise_fall(riseTime=0.005, fallTime=0.005)

sound2 = soundmodule.Sound(duration=1.0, srate=SAMPLERATE)
sound2.add_noise(amp=0.2)
sound2.apply_rise_fall(riseTime=0.005, fallTime=0.005)

if backend == 'alsa':
    player = soundmodule.AlsaPlayer(
        device=DEVICE,
        samplerate=SAMPLERATE,
        period_size=PERIOD_SIZE,
    )
else:
    player = soundmodule.SoundPlayer()
    player.device = DEVICE

player.set_sound(1, sound1)
player.set_sound(2, sound2)

print(f"Backend: {backend}  |  Device: {DEVICE}  |  Sample rate: {SAMPLERATE} Hz")
print("Playing 1 kHz tone...")
player.play(1)
player.wait_until_done()

time.sleep(0.2)

print("Playing noise burst...")
player.play(2)
player.wait_until_done()

player.close()
print("Done.")
