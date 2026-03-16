"""
Example script to load and display data from a phonotaxis experiment.
"""

from phonotaxis import utils
from phonotaxis import config
import os

subject = 'test000'
paradigm = 'initzone_and_ports'
session = '20251102a'

data_filepath = os.path.join(config.DATA_PATH, subject, f"{subject}_{paradigm}_{session}.h5")
sdata = utils.SessionData(data_filepath)

# Display basic info about the session
print(sdata)
print("")

print("Trial data keys:")
print(sdata.trialdata.keys())
print("")

print("Example trial data:")
print(f'choice = {sdata["choice"]}')
print("")

print("Example trial data labels:")
print(sdata.labels['choice'])
print("")

print("Events data keys:")
print(sdata.events.keys())
print("")

print("State matrix keys:")
print(sdata.state_matrix.keys())
print("")

print("Video tracking data keys:")
print(sdata.video_tracking.keys())
print("")
