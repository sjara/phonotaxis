"""
Read video tracking data from HDF5 file and plot the centroid.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl
import matplotlib.colors as mplcolors
from phonotaxis import utils
from phonotaxis import config
import os

RESOLUTION = (640, 480)  # Assuming a resolution of 640x480 for the video

subject = 'test000'
paradigm = 'initzone_and_ports'
session = '20251111a'

data_filepath = os.path.join(config.DATA_PATH, subject, f"{subject}_{paradigm}_{session}.h5")
sdata = utils.SessionData(data_filepath)

centroid_x = sdata.video_tracking['centroid_x']
centroid_y = sdata.video_tracking['centroid_y']
timestamps = sdata.video_tracking['timestamps']

fig = plt.gcf()
plt.clf()
(ax1, ax2) = fig.subplots(2, 1, height_ratios=(3, 1))
# Create a colormap that goes from light to dark
num_points = len(timestamps)
colors = mpl.cm.Blues(mplcolors.Normalize()(range(num_points)))

# Plot line segments with color gradient
plt.sca(ax1)
if 1:
    for indp in range(num_points - 1):
        plt.plot(centroid_x[indp:indp+2], centroid_y[indp:indp+2],
            color=colors[indp],linewidth=1, zorder=0)
else:
    plt.plot(centroid_x, centroid_y, color='0.9', lw=1, zorder=0)
# Plot points with color gradient
plt.scatter(centroid_x, centroid_y, c=colors, s=8, marker='o', ec='none')
plt.xlim(0, RESOLUTION[0])
plt.ylim(0, RESOLUTION[1])
plt.title(f"Centroid Trajectory for {subject}")
plt.xlabel('Centroid X Position')
plt.ylabel('Centroid Y Position')
# Make color of grid lines lighter
plt.grid(which='both', color='0.9', ls='-', lw=0.5)
plt.xticks(range(0, RESOLUTION[0]+1, 80))
plt.yticks(range(0, RESOLUTION[1]+1, 80))
# Fix aspect ratio to be equal
plt.gca().set_aspect('equal', adjustable='box')

plt.sca(ax2)
plt.plot(np.diff(timestamps), '.')
plt.xlabel('Frame Index')
plt.ylabel('Time between frames (s)')
plt.grid(axis='y', color='0.9', ls='-', lw=0.5)
plt.show()
