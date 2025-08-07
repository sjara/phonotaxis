"""
Read CSV file with tracked object and plot the centroid.
"""


import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl
import matplotlib.colors as mplcolors
from phonotaxis import config
import os

RESOLUTION = (640, 480)  # Assuming a resolution of 640x480 for the video

subject = 'test000'
#video_filepath = os.path.join(config.VIDEO_PATH, subject, f"{subject}_output.avi")
data_filepath = os.path.join(config.DATA_PATH, subject, f"{subject}_data.csv")

dframe = pd.read_csv(data_filepath)

fig = plt.gcf()
plt.clf()
(ax1, ax2) = fig.subplots(2, 1, height_ratios=(3, 1))
# Create a colormap that goes from light to dark
num_points = len(dframe)
colors = mpl.cm.Blues(mplcolors.Normalize()(range(num_points)))

# Plot line segments with color gradient
plt.sca(ax1)
if 0:
    for i in range(num_points - 1):
        plt.plot(dframe['centroid_x'].iloc[i:i+2],dframe['centroid_y'].iloc[i:i+2],
            color=colors[i],linewidth=1, zorder=0)
else:
    plt.plot(dframe['centroid_x'], dframe['centroid_y'], color='0.9', lw=1, zorder=0)
# Plot points with color gradient
plt.scatter(dframe['centroid_x'], dframe['centroid_y'], c=colors, s=8, marker='o', ec='none')
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
plt.plot(np.diff(dframe['timestamp']), '.')
plt.xlabel('Frame Index')
plt.ylabel('Time between frames (s)')
plt.grid(axis='y', color='0.9', ls='-', lw=0.5)
plt.show()
