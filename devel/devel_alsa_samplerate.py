"""
Diagnose ALSA sample rate negotiation for the D10s USB audio interface.

Run this on the machine with the D10s to check whether pyalsaaudio is
correctly setting the requested sample rate.
"""

import alsaaudio

DEVICE = 'hw:D10s,0'
REQUESTED_RATE = 384000

print(f"Opening device: {DEVICE}")
pcm = alsaaudio.PCM(
    alsaaudio.PCM_PLAYBACK,
    device=DEVICE,
    channels=2,
    rate=REQUESTED_RATE,
    format=alsaaudio.PCM_FORMAT_S32_LE,
    periodsize=1024,
)

info = pcm.info()
actual_rate = info['rate']

print(f"Requested rate : {REQUESTED_RATE} Hz")
print(f"Actual rate    : {actual_rate} Hz")
if actual_rate != REQUESTED_RATE:
    print("WARNING: rates do not match — sound duration will be wrong.")
else:
    print("OK: rates match.")
print()
print("PCM info:")
print(info)

pcm.close()
