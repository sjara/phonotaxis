"""
Test loading the video file.
"""

from phonotaxis import config
import cv2
import os

#RESOLUTION = (640, 480)  # Assuming a resolution of 640x480 for the video

subject = 'test000'
video_filepath = os.path.join(config.VIDEO_PATH, subject, f"{subject}_output.mp4")

cap = cv2.VideoCapture(video_filepath)
if not cap.isOpened():
    print("Error: Could not open video file.")
else:
    print("Video file opened successfully.")
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print(f"Frame count: {frame_count}")
    print(f"FPS: {fps}")
    print(f"Resolution: {width}x{height}")

    # Read and display the first frame
    ret, frame = cap.read()
    if ret:
        cv2.imshow('First Frame', frame)
        cv2.waitKey(0)
    else:
        print("Error: Could not read the first frame.")

    cap.release()
    cv2.destroyAllWindows()
