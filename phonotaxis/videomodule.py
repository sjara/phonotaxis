"""
Record video and trigger events from video.
"""

import sys
import os
import time
import cv2
import numpy as np
from typing import Dict, List, Optional, Tuple
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QObject
import threading
from .sharedbuffer import SharedFrameBuffer, ResultBuffer
from .videoworkers import CaptureWorker, ProcessWorker, RecordWorker, ContourTracker, FileCaptureWorker
from .resultbus import ResultBus, WorkerResult
from .videosource import VideoSource, CV2VideoSource

# --- Configuration ---
#FOURCC_CODEC = cv2.VideoWriter_fourcc(*'XVID')  # Codec for AVI files. 'MP4V' for .mp4
FOURCC_CODEC = cv2.VideoWriter_fourcc(*'MP4V')  # Codec for AVI files. 'MP4V' for .mp4
RECORDING_FPS = 60  # Desired FPS for the output video. Can be adjusted or derived from camera.
DEFAULT_BLACK_THRESHOLD = 128  # Trigger sound when average pixel intensity is less than this
DEFAULT_MINIMUM_AREA = 4000  # Minimum area of the largest contour to consider it significant

class VideoThread(QThread):
    """
    A QThread subclass for handling video capture and processing in a separate thread.
    This prevents the GUI from freezing during video operations.

    Signals:
        camera_error_signal (str): Emitted when there is an error with the camera.
        frame_processed (float, np.ndarray, tuple): Emits the timestamp, processed frame,
                                                    and (x,y) of points of interest.
    """
    camera_error_signal = pyqtSignal(str)
    frame_processed = pyqtSignal(float, np.ndarray, tuple, object) # Emits timestamp, frame, points, and contour

    def __init__(self, camera_index=0, mode='grayscale', tracking=False, debug=False, fps_limit=None, loop=False, start_paused=False):
        """
        Args:
            camera_index (int or str or VideoSource): Index of the camera, path to a video file, or a VideoSource.
            mode (str): Type of image emitted: ['grayscale', 'binary']
                        Note that this does not affect the saved video.
            tracking (bool): Whether to track the largest dark object in the video.
            debug (bool): If True, prints debug information to console.
            fps_limit (float, optional): Maximum frame rate for file playback.
            loop (bool): Whether to loop video file playback.
            start_paused (bool): Whether to start paused (for file playback).
        """
        super().__init__()
        self.camera_index = camera_index
        self.fps_limit = fps_limit
        self.loop = loop
        self._run_flag = True
        self.fps = None
        self._mode = mode
        self.tracking = tracking
        self.recording_status = False  # Whether video recording is active
        self.filepath = None  # Path to save the video output, if any
        self.threshold = DEFAULT_BLACK_THRESHOLD  # Default threshold for detecting dark objects
        self.minarea = DEFAULT_MINIMUM_AREA  # Default minimum area of object to track
        self._paused = start_paused  # Start paused state

        # Store tracking
        self.timestamps = []
        self.points = []  # List where each element is a list of (x,y) coordinates for one point across time

        self.debug = debug
        
        # Setup VideoSource
        if isinstance(self.camera_index, VideoSource):
            self.video_source = self.camera_index
        else:
            self.video_source = CV2VideoSource(self.camera_index)

        # Setup buffers and workers
        self._result_ready_event = threading.Event()
        self.result_buffer = ResultBuffer(event=self._result_ready_event)
        
        # Create inter-worker communication bus
        self.result_bus = ResultBus()
        
        self.process_workers = []
        
        # Setup contour-tracking strategy and primary worker
        self.contour_tracker = ContourTracker(
            self.threshold, self.minarea, tracking=self.tracking
        )
        self.contour_tracker.mode = self._mode
        
        primary_worker = ProcessWorker(
            strategy=self.contour_tracker,
            result_buffer=self.result_buffer,
            name='contour_tracker',
            bus=self.result_bus,
            subscribe_to='capture',
            publish_to_bus=self.result_bus,
        )
        self.process_workers.append(primary_worker)
        
        # Setup record worker
        self.record_worker = RecordWorker(bus=self.result_bus, subscribe_to='capture')
        
        # Setup capture worker
        if isinstance(self.camera_index, str):
            self.capture_worker = FileCaptureWorker(
                video_source=self.video_source,
                publish_to_bus=self.result_bus,
                fps_limit=self.fps_limit,
                loop=self.loop,
                paused=self._paused
            )
        else:
            self.capture_worker = CaptureWorker(
                video_source=self.video_source,
                publish_to_bus=self.result_bus
            )
        
        # We will keep track of threads here
        self._capture_thread = None
        self._process_threads = []
        self._record_thread = None


    @property
    def mask_coords(self):
        if hasattr(self, 'contour_tracker'):
            return self.contour_tracker.mask_coords
        return None

    @property
    def paused(self) -> bool:
        if hasattr(self, 'capture_worker'):
            return getattr(self.capture_worker, 'paused', False)
        return self._paused

    @paused.setter
    def paused(self, value: bool):
        self._paused = value
        if hasattr(self, 'capture_worker'):
            self.capture_worker.paused = value

    @property
    def mask_enabled(self):
        if hasattr(self, 'contour_tracker'):
            return self.contour_tracker.mask_enabled
        return False

    def set_threshold(self, threshold):
        self.threshold = threshold
        if hasattr(self, 'contour_tracker'):
            self.contour_tracker.threshold = threshold
        
    def set_minarea(self, minarea):
        self.minarea = minarea
        if hasattr(self, 'contour_tracker'):
            self.contour_tracker.minarea = minarea

    def set_circular_mask(self, coords):
        if len(coords) != 3:
            raise ValueError("Circular mask requires exactly 3 coordinates: [center_x, center_y, radius]")
        if hasattr(self, 'contour_tracker'):
            self.contour_tracker.set_circular_mask(coords)
        if self.debug:
            center_x, center_y, radius = coords
            print(f"Circular MASK set: center ({center_x}, {center_y}), radius {radius}")

    def set_rectangular_mask(self, coords):
        if len(coords) != 4:
            raise ValueError("Rectangular mask requires exactly 4 coordinates: [x1, y1, x2, y2]")
        if hasattr(self, 'contour_tracker'):
            self.contour_tracker.set_rectangular_mask(coords)
        if self.debug:
            x1, y1, x2, y2 = coords
            print(f"Rectangular MASK set: ({x1}, {y1}) to ({x2}, {y2})")

    def set_rectangular_mask_from_center(self, center_x, center_y, width, height):
        half_width = width // 2
        half_height = height // 2
        x1 = max(0, center_x - half_width)
        y1 = max(0, center_y - half_height)
        x2 = center_x + half_width
        y2 = center_y + half_height
        self.set_rectangular_mask([x1, y1, x2, y2])

    def disable_mask(self):
        if hasattr(self, 'contour_tracker'):
            self.contour_tracker.disable_mask()
        if self.debug:
            print("MASK masking disabled")

    def get_mask(self):
        if not hasattr(self, 'contour_tracker'):
            return None
        ct = self.contour_tracker
        if not ct.mask_enabled or ct.mask_coords is None:
            return None
        
        if len(ct.mask_coords) == 3:
            center_x, center_y, radius = ct.mask_coords
            return {
                'type': 'circular',
                'coords': ct.mask_coords,
                'center_x': center_x,
                'center_y': center_y,
                'radius': radius,
                'enabled': ct.mask_enabled
            }
        elif len(ct.mask_coords) == 4:
            x1, y1, x2, y2 = ct.mask_coords
            return {
                'type': 'rectangular',
                'coords': ct.mask_coords,
                'x1': x1,
                'y1': y1,
                'x2': x2,
                'y2': y2,
                'enabled': ct.mask_enabled
            }
        else:
            return None

    @property
    def cap(self):
        if hasattr(self, 'video_source') and isinstance(self.video_source, CV2VideoSource):
            self.video_source.open()
            return self.video_source.cap
        return None

    @property
    def mode(self):
        if hasattr(self, 'contour_tracker'):
            return self.contour_tracker.mode
        return self._mode
        
    @mode.setter
    def mode(self, mode_val):
        if mode_val not in ['grayscale', 'binary']:
            raise ValueError("Mode must be 'grayscale' or 'binary'.")
        self._mode = mode_val
        if hasattr(self, 'contour_tracker'):
            self.contour_tracker.mode = mode_val

    def set_mode(self, mode_val):
        self.mode = mode_val
            
    def add_process_worker(self, worker):
        """Register an additional ProcessWorker for parallel analysis."""
        if hasattr(self, '_result_ready_event') and worker.result_buffer is not None:
            worker.result_buffer.set_event(self._result_ready_event)
        self.process_workers.append(worker)
        if hasattr(self, 'capture_worker') and hasattr(self.capture_worker, 'process_buffers') and worker.raw_buffer is not None:
            self.capture_worker.process_buffers.append(worker.raw_buffer)
        
        # If the video thread is already running, spawn and start the thread for this worker immediately
        if self.isRunning() and self._run_flag:
            import threading
            t = threading.Thread(target=worker.run, daemon=True)
            self._process_threads.append(t)
            t.start()

    def store_tracking_data(self, timestamp, points):
        """
        Appends timestamp and points to the tracking lists whenever tracking is enabled.
        """
        if self.tracking:
            self.timestamps.append(timestamp)
            
            # Ensure we have enough point lists for all detected points
            while len(self.points) < len(points):
                self.points.append([])
            
            # Append coordinates to each point's list
            for i, point in enumerate(points):
                self.points[i].append(point)
                
    def initialize_camera(self):
        pass

    def start_recording(self, filepath=None, fps=None, encoder='h264_nvenc'):
        """Starts the video recording. This should be called after setting the output file."""
        if filepath is not None:
            self.filepath = filepath
            dir_path = os.path.dirname(self.filepath)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path)
            self.recording_status = True
            
            recording_fps = fps if fps is not None else getattr(self.capture_worker, 'fps', RECORDING_FPS)
            if recording_fps <= 0:
                recording_fps = RECORDING_FPS
                
            self.record_worker.start_recording(self.filepath, recording_fps, encoder)
            print(f"Video recording started: {self.filepath}")
        else:
            print("Video recording not started: No output file set.")
        
    def stop_recording(self):
        """Stops the video recording."""
        self.recording_status = False
        self.record_worker.stop_recording()
        print("Video recording stopped.")
            
    def initialize_video_writer(self, filepath):
        pass
        
    def run(self):
        """
        Main loop for the thread. Coordinates workers, drains result buffers,
        and emits signals for display.
        """
        if not hasattr(self, 'capture_worker'):
            return

        # Start capture worker thread
        self._capture_thread = threading.Thread(target=self.capture_worker.run, daemon=True)
        self._capture_thread.start()
        
        # Wait for capture worker to open the source and be ready
        if not self.capture_worker.ready_event.wait(timeout=5.0):
            self.camera_error_signal.emit("Timeout waiting for camera to initialize.")
            self._run_flag = False
            return
            
        if self.capture_worker.error_message:
            self.camera_error_signal.emit(self.capture_worker.error_message)
            self._run_flag = False
            return

        self.fps = self.capture_worker.fps

        # Start process and record worker threads
        self._process_threads = []
        for worker in self.process_workers:
            t = threading.Thread(target=worker.run, daemon=True)
            self._process_threads.append(t)
        self._record_thread = threading.Thread(target=self.record_worker.run, daemon=True)
        
        for t in self._process_threads:
            t.start()
        self._record_thread.start()
        
        # Drain results from ALL process workers and emit Qt signals
        while self._run_flag:
            got_result = False
            for worker in self.process_workers:
                result = worker.result_buffer.try_read_result()
                if result is not None:
                    data = result.data
                    processed_frame = data.get('frame')
                    points = data.get('points')
                    if processed_frame is not None and isinstance(points, (tuple, list)):
                        timestamp = result.timestamp
                        contour = data.get('contour')
                        self.store_tracking_data(timestamp, points)
                        self.frame_processed.emit(timestamp, processed_frame, points, contour)
                    got_result = True
            
            if got_result:
                continue
            
            # Check if file playback is finished and buffers are drained
            if isinstance(self.capture_worker, FileCaptureWorker) and not self._capture_thread.is_alive():
                queues_empty = all(w._subscription_queue is None or w._subscription_queue.empty() for w in self.process_workers)
                workers_idle = all(not w.is_processing for w in self.process_workers)
                results_empty = all(w.result_buffer._items_available == 0 for w in self.process_workers)
                if queues_empty and workers_idle and results_empty:
                    self._run_flag = False
                    break

            # Block reactively on the shared event rather than polling
            self._result_ready_event.wait(timeout=0.05)
            self._result_ready_event.clear()
        
        # Shutdown workers sequentially
        self.capture_worker.stop()
        if self._capture_thread.is_alive():
            self._capture_thread.join(timeout=2.0)
            
        for worker in self.process_workers:
            worker.stop()
        for t in self._process_threads:
            if t.is_alive():
                t.join(timeout=2.0)
                
        self.record_worker.stop()
        if self._record_thread.is_alive():
            self._record_thread.join(timeout=2.0)
        
        print("Video thread stopped and resources released.")
    
    def append_to_file(self, h5file):
        """
        Save tracking data (timestamps and centroid positions) to an HDF5 file.
        
        Creates a '/video_tracking' group in the HDF5 file and saves:
        - 'timestamps': array of frame timestamps (float)
        - 'centroid_x': array of x-coordinates of tracked centroids (int)
        - 'centroid_y': array of y-coordinates of tracked centroids (int)
        
        Tracking data is collected whenever tracking is enabled (tracking=True),
        independently of whether video recording is active. This allows you to
        save tracking data without necessarily saving the raw video file.
        
        Args:
            h5file: Open HDF5 file handle (from h5py)
            
        Returns:
            HDF5 group object containing the tracking datasets
            
        Raises:
            UserWarning: If no tracking data has been collected
            RuntimeError: If there's an error creating the HDF5 group or datasets
        """
        if len(self.timestamps) == 0:
            raise UserWarning('No tracking data found. Make sure tracking was enabled (tracking=True).')
        
        try:
            tracking_group = h5file.create_group('/videoTracking')
            
            # Save timestamps
            tracking_group.create_dataset('timestamps', data=np.array(self.timestamps))
            
            # Save centroid coordinates
            # self.points is a list of lists, where each element is a list of (x,y) tuples for one point
            # For the typical case of tracking one object, we have self.points[0] = [(x1,y1), (x2,y2), ...]
            if len(self.points) > 0 and len(self.points[0]) > 0:
                # Extract x and y coordinates from the first tracked point
                centroid_x = np.array([point[0] for point in self.points[0]])
                centroid_y = np.array([point[1] for point in self.points[0]])
                
                tracking_group.create_dataset('centroid_x', data=centroid_x)
                tracking_group.create_dataset('centroid_y', data=centroid_y)
            else:
                # No points tracked, create empty datasets
                tracking_group.create_dataset('centroid_x', data=np.array([]))
                tracking_group.create_dataset('centroid_y', data=np.array([]))
            
            return tracking_group
            
        except Exception as e:
            raise RuntimeError(f'Error saving video tracking data to file: {str(e)}')
        
    def stop(self):
        """Stops the video capture thread gracefully."""
        self._run_flag = False
        self.wait()


class VideoInterface(QObject):
    """
    Interface between video events and state machine.
    
    This class manages the connection between video-based events (e.g., ROI entry/exit,
    zone crossings) and state machine events, providing:
    
    - Event mapping: translates video detections to state machine events
    - Zone monitoring: tracks when tracked objects enter/exit defined zones
    - Named access: uses human-readable names for zones
    - Flexible configuration: supports multiple zones with different shapes
    
    The interface creates a consistent event structure:
    - Input events: '{zone_name}in' (object entered zone)
                   '{zone_name}out' (object exited zone)
    
    Zone types supported:
    - Circular zones: defined by (center_x, center_y, radius)
    - Rectangular zones: defined by (x1, y1, x2, y2) or center + dimensions
    
    Usage:
        interface = VideoInterface(
            video_thread=video_thread,
            zones={'init_zone': ('circular', (320, 240, 40))}
        )
        interface.connect_state_machine(state_machine)
        video_thread.frame_processed.connect(interface.on_frame_processed)
    
    The interface monitors the video thread's frame_processed signal and generates
    state machine events when tracked objects cross zone boundaries.
    """
    
    def __init__(self,
                 video_thread: VideoThread,
                 zones: Optional[Dict[str, Tuple[str, tuple]]] = None,
                 event_offset: int = 0,
                 debug: bool = False,
                 parent: Optional[QObject] = None):
        """
        Initialize the video interface.
        
        Args:
            video_thread: VideoThread instance to monitor for video events
            zones: Dictionary mapping zone names to zone specifications.
                  Each zone is specified as: (zone_type, coordinates)
                  - For circular zones: ('circular', (center_x, center_y, radius))
                  - For rectangular zones: ('rectangular', (x1, y1, x2, y2))
                  Example: {'init_zone': ('circular', (320, 240, 40)),
                           'left_port': ('rectangular', (100, 100, 200, 300))}
            event_offset: Starting index for event numbering (default 0).
                         Use this when combining with other input sources to avoid
                         event index collisions.
            debug: Enable debug output
            parent: Parent QObject
        """
        super().__init__(parent)
        
        self.video_thread = video_thread
        self.debug = debug
        
        # Initialize zones and tracking state
        self.zones = {}
        self.previous_zone_states = {}  # Initialize before adding zones
        
        # State machine reference
        self.state_machine = None
        self.event_mapping: Dict[str, int] = {}
        
        # Add zones if provided
        if zones is not None:
            for zone_name, (zone_type, coords) in zones.items():
                self.add_zone(zone_name, zone_type, coords)
        
        # Create event mapping: each zone gets 'in' and 'out' events
        self.events = {}
        event_index = event_offset  # Start from the provided offset
        for zone_name in self.zones.keys():
            self.events[f'{zone_name}in'] = event_index
            event_index += 1
            self.events[f'{zone_name}out'] = event_index
            event_index += 1
        
        # Connect to video thread's frame_processed signal
        if self.video_thread is not None:
            self.video_thread.frame_processed.connect(self.on_frame_processed)
            
        if self.debug:
            print(f"VideoInterface initialized with {len(self.zones)} zones")
            print(f"Events: {self.events}")
    
    def add_zone(self, zone_name: str, zone_type: str, coords: tuple):
        """
        Add a zone for monitoring.
        
        Args:
            zone_name: Name of the zone (e.g., 'init_zone', 'left_port')
            zone_type: Type of zone ('circular' or 'rectangular')
            coords: Coordinates defining the zone
                   - For circular: (center_x, center_y, radius)
                   - For rectangular: (x1, y1, x2, y2)
        
        Raises:
            ValueError: If zone_type is invalid or coordinates are malformed
        """
        if zone_type not in ['circular', 'rectangular']:
            raise ValueError(f"Invalid zone type '{zone_type}'. Must be 'circular' or 'rectangular'")
        
        if zone_type == 'circular':
            if len(coords) != 3:
                raise ValueError(f"Circular zone requires 3 coordinates (center_x, center_y, radius), got {len(coords)}")
        elif zone_type == 'rectangular':
            if len(coords) != 4:
                raise ValueError(f"Rectangular zone requires 4 coordinates (x1, y1, x2, y2), got {len(coords)}")
        
        self.zones[zone_name] = {
            'type': zone_type,
            'coords': coords
        }
        
        # Initialize previous state
        if zone_name not in self.previous_zone_states:
            self.previous_zone_states[zone_name] = False
        
        if self.debug:
            print(f"Added {zone_type} zone '{zone_name}' with coords {coords}")
    
    def remove_zone(self, zone_name: str):
        """
        Remove a zone from monitoring.
        
        Args:
            zone_name: Name of the zone to remove
        """
        if zone_name in self.zones:
            del self.zones[zone_name]
            del self.previous_zone_states[zone_name]
            if self.debug:
                print(f"Removed zone '{zone_name}'")
    
    def get_events(self) -> Dict[str, int]:
        """
        Get the event mapping created by this interface.
        
        Returns:
            Dictionary mapping event names to sequential indices.
            Each zone creates two events: '{zone}in' and '{zone}out'.
        """
        return self.events.copy()
    
    def connect_state_machine(self, state_machine):
        """
        Connect the interface to a state machine.
        
        This establishes bidirectional communication where video zone crossings
        trigger state machine events.
        
        Args:
            state_machine: StateMachine instance to connect to
        """
        self.state_machine = state_machine
        self.event_mapping = self.get_events()
        
        if self.debug:
            print(f"Connected to state machine with {len(self.event_mapping)} events")
    
    def disconnect_state_machine(self):
        """Disconnect from the current state machine."""
        self.state_machine = None
        self.event_mapping.clear()
        
        if self.debug:
            print("Disconnected from state machine")
    
    def point_in_zone(self, point: Tuple[int, int], zone_name: str) -> bool:
        """
        Check if a point is inside a zone.
        
        Args:
            point: (x, y) coordinates of the point
            zone_name: Name of the zone to check
        
        Returns:
            True if point is inside the zone, False otherwise
        """
        if zone_name not in self.zones:
            return False
        
        zone = self.zones[zone_name]
        x, y = point
        
        # Handle invalid points (from tracking failures)
        if x < 0 or y < 0:
            return False
        
        if zone['type'] == 'circular':
            center_x, center_y, radius = zone['coords']
            distance = np.sqrt((x - center_x)**2 + (y - center_y)**2)
            return distance <= radius
        
        elif zone['type'] == 'rectangular':
            x1, y1, x2, y2 = zone['coords']
            return x1 <= x <= x2 and y1 <= y <= y2
        
        return False
    
    def on_frame_processed(self, timestamp: float, frame: np.ndarray, points: Tuple):
        """
        Handle frame processed signal from video thread.
        
        This is the main callback that checks for zone crossings and generates
        state machine events. Called automatically when connected to video thread.
        
        Args:
            timestamp: Frame timestamp
            frame: Processed video frame (not used, but kept for signal compatibility)
            points: Tuple of tracked points, typically (centroid,)
        
        Note that the signal may have additional parameters not used here.
        """
        if not self.state_machine or not self.state_machine.is_active:
            return
        
        # Only process if we have valid tracking data
        if not points or len(points) == 0:
            return
        
        # Get the first tracked point (typically the centroid)
        tracked_point = points[0]
        
        # Check each zone for entry/exit
        for zone_name in self.zones.keys():
            is_in_zone = self.point_in_zone(tracked_point, zone_name)
            was_in_zone = self.previous_zone_states[zone_name]
            
            # Detect rising edge (entered zone)
            if is_in_zone and not was_in_zone:
                event_name = f'{zone_name}in'
                if event_name in self.event_mapping:
                    event_index = self.event_mapping[event_name]
                    if self.debug:
                        print(f"Zone entry detected: {zone_name} at {tracked_point}, triggering event {event_index}")
                    self.state_machine.process_input(event_index)
            
            # Detect falling edge (exited zone)
            elif not is_in_zone and was_in_zone:
                event_name = f'{zone_name}out'
                if event_name in self.event_mapping:
                    event_index = self.event_mapping[event_name]
                    if self.debug:
                        print(f"Zone exit detected: {zone_name} at {tracked_point}, triggering event {event_index}")
                    self.state_machine.process_input(event_index)
            
            # Update previous state
            self.previous_zone_states[zone_name] = is_in_zone
    
    def get_zone_info(self, zone_name: str) -> Optional[Dict]:
        """
        Get information about a specific zone.
        
        Args:
            zone_name: Name of the zone
        
        Returns:
            Dictionary with zone information or None if zone doesn't exist
        """
        return self.zones.get(zone_name)
    
    def get_all_zones(self) -> Dict[str, Dict]:
        """
        Get information about all zones.
        
        Returns:
            Dictionary mapping zone names to zone information
        """
        return self.zones.copy()
    
    def is_point_in_any_zone(self, point: Tuple[int, int]) -> List[str]:
        """
        Check which zones contain a given point.
        
        Args:
            point: (x, y) coordinates to check
        
        Returns:
            List of zone names that contain the point
        """
        zones_containing_point = []
        for zone_name in self.zones.keys():
            if self.point_in_zone(point, zone_name):
                zones_containing_point.append(zone_name)
        return zones_containing_point


# -- For testing purposes --
class VideoThreadBlackDetect(VideoThread):
    """
    A specialized video thread that detects black screens and triggers a signal.
    Inherits from VideoThread to reuse camera handling and video processing.
    """
    black_screen_detected_signal = pyqtSignal()
    
    def __init__(self, camera_index=0, save_to=None, threshold=DEFAULT_BLACK_THRESHOLD):
        super().__init__(camera_index, save_to)
        self.black_threshold = threshold

    def process_frame(self, frame):
        # Check if the screen is mostly black
        avg_intensity = np.mean(frame)
        if avg_intensity < self.black_threshold:
            self.black_screen_detected_signal.emit()
        return (frame, (), None)  # Return the frame, empty points tuple, and no contour


def count_video_frames(video_path):
    """
    Manually count frames by reading through the entire video.
    This is slower but works with any video format.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return 0
    
    frame_count = 0
    while True:
        ret, _ = cap.read()
        if not ret:
            break
        frame_count += 1
    
    cap.release()
    return frame_count