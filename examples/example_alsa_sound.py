"""
Example of playing a sound via direct ALSA hardware access (Linux only).

Uses AlsaPlayer to bypass PulseAudio/PipeWire and write directly to the hw
device, enabling low-latency playback at high sampling rates (e.g. 384 kHz).

Requires pyalsaaudio: pip install pyalsaaudio
Device parameters are read from config.py (ALSA_DEVICE, ALSA_SAMPLERATE,
ALSA_PERIOD_SIZE).
"""

import time
from phonotaxis import soundmodule, config

DEVICE = config.ALSA_DEVICE
SAMPLERATE = config.ALSA_SAMPLERATE
PERIOD_SIZE = config.ALSA_PERIOD_SIZE

# Create sounds at the device's native sampling rate.
sound1 = soundmodule.Sound(duration=1.0, srate=SAMPLERATE)
sound1.add_tone(freq=1000, amp=0.3)
sound1.apply_rise_fall(riseTime=0.005, fallTime=0.005)

sound2 = soundmodule.Sound(duration=1.0, srate=SAMPLERATE)
sound2.add_noise(amp=0.2)
sound2.apply_rise_fall(riseTime=0.005, fallTime=0.005)

player = soundmodule.AlsaPlayer(
    device=DEVICE,
    samplerate=SAMPLERATE,
    period_size=PERIOD_SIZE,
)
player.set_sound(1, sound1)
player.set_sound(2, sound2)

print(f"Playing 1 kHz tone via {DEVICE} at {SAMPLERATE} Hz...")
player.play(1)
player.wait_until_done()

time.sleep(0.2)

print("Playing noise burst...")
player.play(2)
player.wait_until_done()

player.close()
print("Done.")
