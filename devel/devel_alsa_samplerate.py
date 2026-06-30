"""
Diagnose ALSA sample rate negotiation for the D10s USB audio interface.

Run this on the machine with the D10s to check whether pyalsaaudio is
correctly setting the requested sample rate.
"""

import alsaaudio

DEVICE = 'hw:D10s,0'
REQUESTED_RATE = 384000

print(f"Opening device: {DEVICE}")
pcm = alsaaudio.PCM(alsaaudio.PCM_PLAYBACK, device=DEVICE)
pcm.setchannels(2)
actual_rate = pcm.setrate(REQUESTED_RATE)
pcm.setformat(alsaaudio.PCM_FORMAT_S32_LE)
pcm.setperiodsize(1024)

print(f"Requested rate : {REQUESTED_RATE} Hz")
print(f"setrate() returned: {actual_rate} Hz")
print()
print("PCM info:")
print(pcm.info())

pcm.close()
