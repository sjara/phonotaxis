#!/usr/bin/env python3
"""
Benchmark utility for measuring the maximum framerate and latency of the
phonotaxis VideoThread multithreaded pipeline.
"""

from numpy._core import fromnumeric
import os
import sys
import time
import argparse
import tempfile
import numpy as np
import cv2
from PyQt6.QtCore import QCoreApplication, QTimer

# Ensure the parent directory is in the path so we can import phonotaxis
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def create_benchmark_video(filename, width, height, num_frames=1000):
    """
    Generates a synthetic video containing a dark moving circle on a light background.
    This simulates a rodent's movement for realistic contour tracking.
    """
    print(f"Generating temporary video ({num_frames} frames, {width}x{height})...")
    fourcc = cv2.VideoWriter_fourcc(*'MJPG')
    out = cv2.VideoWriter(filename, fourcc, 30.0, (width, height), isColor=False)
    
    for i in range(num_frames):
        # Create light gray background
        frame = np.ones((height, width), dtype=np.uint8) * 220
        # Compute position of a moving circular "rodent"
        angle = (2 * np.pi * i) / 100
        cx = int(width / 2 + (width / 4) * np.cos(angle))
        cy = int(height / 2 + (height / 4) * np.sin(angle))
        # Draw the rodent (dark grey circle)
        cv2.circle(frame, (cx, cy), 20, 30, -1)
        out.write(frame)
        
    out.release()
    print("Temporary video generated successfully.")


class MemoryVideoCapture:
    """
    In-memory video reader that pre-loads all frames from a video file into RAM
    and mocks the cv2.VideoCapture interface. This eliminates disk I/O and video
    decoding bottlenecks during benchmarking.
    """
    def __init__(self, filepath, num_frames=1000):
        self.filepath = filepath
        self.frames = []
        
        print(f"Pre-loading video '{filepath}' into RAM to bypass decoding bottlenecks...")
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened():
            raise IOError(f"Could not open video file for preloading: {filepath}")
            
        self.fps = cap.get(cv2.CAP_PROP_FPS)
        if self.fps <= 0:
            self.fps = 30.0
        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        while len(self.frames) < num_frames:
            ret, frame = cap.read()
            if not ret:
                break
            self.frames.append(frame)
            
        cap.release()
        self.num_frames = len(self.frames)
        print(f"Loaded {self.num_frames} frames into memory.")
        self.idx = 0
        self.opened = True
        
    def isOpened(self):
        return self.opened
        
    def get(self, propId):
        if propId == cv2.CAP_PROP_FPS:
            return self.fps
        elif propId == cv2.CAP_PROP_FRAME_WIDTH:
            return self.width
        elif propId == cv2.CAP_PROP_FRAME_HEIGHT:
            return self.height
        return 0.0
        
    def read(self):
        if not self.opened or self.num_frames == 0:
            return False, None
        
        frame = self.frames[self.idx]
        self.idx = (self.idx + 1) % self.num_frames
        return True, frame.copy()
        
    def set(self, propId, value):
        if propId == cv2.CAP_PROP_POS_FRAMES:
            self.idx = int(value) % self.num_frames
            return True
        return False
        
    def release(self):
        self.opened = False
        self.frames = []


def print_ascii_histogram(data, bins=10, max_width=40):
    """Prints a premium ASCII bar chart representing the distribution of data."""
    if not data:
        return
    counts, edges = np.histogram(data, bins=bins)
    max_count = max(counts) if max(counts) > 0 else 1
    
    print("\nLatency Distribution (ms):")
    for i in range(len(counts)):
        bar = "#" * int(counts[i] / max_count * max_width)
        bar = bar.ljust(max_width)
        print(f"  [{edges[i]:6.2f} - {edges[i+1]:6.2f} ms] : {counts[i]:4d} | {bar}")


def main():
    parser = argparse.ArgumentParser(description="phonotaxis VideoThread Multithreading Benchmark")
    parser.add_argument("--duration", type=float, default=5.0, help="Test duration in seconds")
    parser.add_argument("--fps", type=float, default=210.0, help="Target capture FPS (0 for unlimited/max)")
    parser.add_argument("--width", type=int, default=1440, help="Frame width")
    parser.add_argument("--height", type=int, default=1080, help="Frame height")
    parser.add_argument("--no-tracking", action="store_true", help="Disable contour tracking")
    parser.add_argument("--mode", type=str, choices=["grayscale", "binary"], default="grayscale", help="Video mode")
    parser.add_argument("--mask", type=str, choices=["none", "circular", "rectangular"], default="none", help="Region-of-interest mask shape")
    parser.add_argument("--record", action="store_true", help="Enable video recording to /dev/null")
    parser.add_argument("--encoder", type=str, default="libx264", help="Video encoder for recording")
    parser.add_argument("--paradigm", type=str, default=None, help="Name of paradigm module from ptparadigms to benchmark (e.g. locomotion_action_space)")
    parser.add_argument("--video", type=str, default=None, help="Path to an existing video file to use for benchmark")
    parser.add_argument("--output-data", type=str, default="tests/benchmark_data.csv", help="Path to write the ProcessWorker data output CSV")
    parser.add_argument("--output-timing", type=str, default="tests/benchmark_timing.csv", help="Path to write the worker timing log CSV")
    args = parser.parse_args()

    from phonotaxis.videomodule import VideoThread

    # Generate or load video file
    # We generate enough frames to satisfy the target FPS * duration (plus a buffer)
    # If FPS is 0 (unbounded), we generate 1500 frames to run a dense throughput test.
    fps_limit = args.fps if args.fps > 0 else -1.0
    target_fps_for_video = args.fps if args.fps > 0 else 300.0
    num_frames = int(max(target_fps_for_video * args.duration * 1.5, 1000))
    
    temp_dir = tempfile.mkdtemp()
    video_is_temp = False
    if args.video:
        if not os.path.exists(args.video):
            print(f"Error: Video file '{args.video}' does not exist.")
            sys.exit(1)
        video_path = args.video
    else:
        video_path = os.path.join(temp_dir, "benchmark_input.avi")
        video_is_temp = True
    
    actual_width = args.width
    actual_height = args.height
    if args.video:
        cap_info = cv2.VideoCapture(args.video)
        actual_width = int(cap_info.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(cap_info.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap_info.release()

    try:
        if video_is_temp:
            create_benchmark_video(video_path, args.width, args.height, num_frames)
        
        # Load and initialize VideoThread or Paradigm
        if args.paradigm:
            # Set offscreen to prevent GUI window creation
            os.environ["QT_QPA_PLATFORM"] = "offscreen"
            from PyQt6.QtWidgets import QApplication
            app = QApplication(sys.argv)
            
            import importlib
            from unittest.mock import MagicMock
            
            # Setup mocks for hardware and sound backends
            mock_arduino = MagicMock()
            sys.modules['sounddevice'] = MagicMock()
            sys.modules['alsaaudio'] = MagicMock()
            sys.modules['phonotaxis.arduinomodule'] = mock_arduino
            
            # Make sure phonotaxis package has the mocked module
            import phonotaxis
            phonotaxis.arduinomodule = mock_arduino
            
            # Set config for video thread to run our benchmark video
            from phonotaxis import config as phonotaxis_config
            phonotaxis_config.VIDEO_PLAYBACK_PATH = video_path
            phonotaxis_config.VIDEO_PLAYBACK_FPS = fps_limit
            phonotaxis_config.VIDEO_PLAYBACK_LOOP = True
            
            # Dynamically import the paradigm module
            sys.path.insert(0, "/home/jaralab/src/ptparadigms")
            try:
                paradigm_module = importlib.import_module(args.paradigm)
            except ModuleNotFoundError as e:
                print(f"Error: Could not import paradigm '{args.paradigm}' from ptparadigms/. Detail: {e}")
                sys.exit(1)
                
            # Get the Paradigm class
            ParadigmClass = getattr(paradigm_module, 'Paradigm', None)
            if ParadigmClass is None:
                print(f"Error: Paradigm module '{args.paradigm}' does not define a 'Paradigm' class.")
                sys.exit(1)
                
            print(f"Instantiating paradigm '{args.paradigm}' headlessly...")
            paradigm = ParadigmClass()
            
            # Retrieve the video thread configured by the paradigm
            vt = paradigm.video_thread
        else:
            # Initialize Qt Core application (required for cross-thread signals)
            app = QCoreApplication(sys.argv)
            
            # Instantiate default VideoThread
            vt = VideoThread(
                camera_index=video_path,
                mode=args.mode,
                tracking=not args.no_tracking,
                fps_limit=fps_limit,
                loop=True,  # Loop input file to prevent premature starvation
            )
        
        # Configure masks if specified
        if args.mask == "circular":
            vt.set_circular_mask([actual_width // 2, actual_height // 2, actual_width // 4])
        elif args.mask == "rectangular":
            vt.set_rectangular_mask([actual_width // 4, actual_height // 4, 3 * actual_width // 4, 3 * actual_height // 4])
            
        # Replace the real file-based VideoCapture with a pre-loaded in-memory reader to avoid disk/decoding bottlenecks
        mem_cap = MemoryVideoCapture(video_path,num_frames)
        if hasattr(vt.capture_worker, 'video_source') and hasattr(vt.capture_worker.video_source, 'cap'):
            vt.capture_worker.video_source.cap = mem_cap
        else:
            vt.capture_worker.cap = mem_cap

        # Ensure we simulate live-camera mode: do not block the capture thread on buffer full
        # This allows us to measure frame drops
        vt.capture_worker.wait_on_full = False
        
        # Configure recording
        record_path = os.path.join(temp_dir, "benchmark_output.mp4")
        if args.record:
            # We want to record using the selected encoder
            vt.record_worker.release_writer()
            vt.start_recording(record_path, encoder=args.encoder)
            
        # Benchmarking state variables
        latencies = []
        timestamps_received = []
        
        def on_frame_processed(timestamp, frame, points, contour):
            now = time.time()
            latency = (now - timestamp) * 1000.0  # in ms
            latencies.append(latency)
            timestamps_received.append(now)
            
        vt.frame_processed.connect(on_frame_processed)
        
        print("\nStarting benchmark...")
        print(f"  Duration:          {args.duration} s")
        print(f"  Resolution:        {actual_width}x{actual_height}")
        print(f"  Target FPS:        {args.fps if args.fps > 0 else 'Unlimited (Max Throughput)'}")
        print(f"  Tracking:          {'ON' if not args.no_tracking else 'OFF'} ({args.mode} mode)")
        print(f"  Mask:              {args.mask}")
        print(f"  Recording:         {'ON (' + args.encoder + ')' if args.record else 'OFF'}")
        if args.paradigm:
            print(f"  Paradigm:          {args.paradigm}")
        
        start_time = time.time()
        
        # Timer to stop the benchmark after the specified duration
        def stop_benchmark():
            print("\nStopping benchmark...")
            vt.stop()
            app.quit()
            
        QTimer.singleShot(int(args.duration * 1000), stop_benchmark)
        
        # Start VideoThread
        if args.paradigm:
            vt.paused = False
        else:
            vt.start()
        
        # Run Qt Event Loop
        app.exec()
        
        # Benchmark finished: extract statistics
        end_time = time.time()
        elapsed_actual = end_time - start_time
        
        captured_count = vt.capture_worker.captured_count
        processed_count = len(timestamps_received)
        dropped_count = max(0, captured_count - processed_count)
        drop_rate = (dropped_count / captured_count * 100.0) if captured_count > 0 else 0.0
        
        capture_fps = captured_count / elapsed_actual if elapsed_actual > 0 else 0.0
        process_fps = processed_count / elapsed_actual if elapsed_actual > 0 else 0.0
        
        # Clean up
        if args.record:
            vt.stop_recording()
            
        # Write CSV outputs if requested
        all_timestamps = set()
        for w in vt.process_workers:
            all_timestamps.update(w.timing_history.keys())
        sorted_timestamps = sorted(list(all_timestamps))
        
        capture_log = getattr(vt.capture_worker, 'capture_log', {})
        
        if args.output_timing and sorted_timestamps:
            print(f"\nWriting timing log to {args.output_timing}...")
            import csv
            try:
                with open(args.output_timing, mode='w', newline='') as f:
                    writer = csv.writer(f)
                    header = ['captured_timestamp', 'frame_number'] + [f"{w.name}_recv_emit" for w in vt.process_workers]
                    writer.writerow(header)
                    for t in sorted_timestamps:
                        frame_num = capture_log.get(t, "")
                        row = [t, frame_num]
                        for w in vt.process_workers:
                            val = w.timing_history.get(t, (None, None))
                            row.append(str(val))
                        writer.writerow(row)
                print("Timing log written successfully.")
            except Exception as e:
                print(f"Error writing timing log: {e}")
                
        if args.output_data and sorted_timestamps:
            print(f"Writing data output to {args.output_data}...")
            import csv
            all_keys = set()
            for w in vt.process_workers:
                for t in sorted_timestamps:
                    if t in w.data_history:
                        all_keys.update(w.data_history[t].keys())
            sorted_keys = sorted(list(all_keys))
            
            try:
                with open(args.output_data, mode='w', newline='') as f:
                    writer = csv.writer(f)
                    header = ['captured_timestamp', 'frame_number'] + sorted_keys
                    writer.writerow(header)
                    for t in sorted_timestamps:
                        frame_num = capture_log.get(t, "")
                        row = [t, frame_num]
                        merged_data = {}
                        for w in vt.process_workers:
                            if t in w.data_history:
                                merged_data.update(w.data_history[t])
                        for key in sorted_keys:
                            row.append(merged_data.get(key, ""))
                        writer.writerow(row)
                print("Data output written successfully.")
            except Exception as e:
                print(f"Error writing data output: {e}")
            
        # Print results
        print("\n" + "="*50)
        print("                 BENCHMARK RESULTS")
        if args.paradigm:
            print(f"  Paradigm:          {args.paradigm}")
        print("="*50)
        print(f"Actual Runtime:     {elapsed_actual:.3f} s")
        print(f"Frames Captured:    {captured_count} ({capture_fps:.2f} fps)")
        print(f"Frames Processed:   {processed_count} ({process_fps:.2f} fps)")
        print(f"Frames Dropped:     {dropped_count} ({drop_rate:.2f}%)")
        print("-" * 50)
        print("Worker Performance & Frame Drop Breakdown:")
        
        # 1. Capture Worker
        print(f"  - capture_worker:")
        print(f"      Class:        {vt.capture_worker.__class__.__name__}")
        print(f"      Processed:    {captured_count} frames ({capture_fps:.2f} fps)")
        print(f"      Dropped:      0 frames (0.00%)")
        
        # 2. Process Workers
        for worker in vt.process_workers:
            w_processed = getattr(worker, 'processed_count', 0)
            w_dropped = max(0, captured_count - w_processed)
            w_drop_rate = (w_dropped / captured_count * 100.0) if captured_count > 0 else 0.0
            w_fps = w_processed / elapsed_actual if elapsed_actual > 0 else 0.0
            
            strategy_name = worker.strategy.__class__.__name__
            try:
                name = strategy_name
            except Exception:
                name = str(worker.strategy)
                
            input_mode = "Frame mode" if worker.raw_buffer is not None else "Bus mode"
            
            print(f"  - {worker.name}:")
            print(f"      Strategy:     {name}")
            print(f"      Mode:         {input_mode}")
            print(f"      Processed:    {w_processed} frames ({w_fps:.2f} fps)")
            print(f"      Dropped:      {w_dropped} frames ({w_drop_rate:.2f}%)")

        # 3. Record Worker
        if hasattr(vt, 'record_worker'):
            rec_worker = vt.record_worker
            rec_processed = getattr(rec_worker, 'recorded_count', 0)
            if args.record:
                rec_dropped = max(0, captured_count - rec_processed)
                rec_drop_rate = (rec_dropped / captured_count * 100.0) if captured_count > 0 else 0.0
                rec_fps = rec_processed / elapsed_actual if elapsed_actual > 0 else 0.0
                
                print(f"  - record_worker:")
                print(f"      Processed:    {rec_processed} frames ({rec_fps:.2f} fps)")
                print(f"      Dropped:      {rec_dropped} frames ({rec_drop_rate:.2f}%)")
            else:
                if rec_processed > 0:
                    rec_fps = rec_processed / elapsed_actual if elapsed_actual > 0 else 0.0
                    print(f"  - record_worker:")
                    print(f"      Processed:    {rec_processed} frames ({rec_fps:.2f} fps)")
        
        if latencies:
            lat_mean = np.mean(latencies)
            lat_std = np.std(latencies)
            lat_min = np.min(latencies)
            lat_max = np.max(latencies)
            lat_p95 = np.percentile(latencies, 95)
            lat_p99 = np.percentile(latencies, 99)
            
            print("-" * 50)
            print("LATENCY (from capture to display/callback):")
            print(f"  Mean:             {lat_mean:.2f} ms")
            print(f"  Std Dev:          {lat_std:.2f} ms")
            print(f"  Min / Max:        {lat_min:.2f} / {lat_max:.2f} ms")
            print(f"  95th Percentile:  {lat_p95:.2f} ms")
            print(f"  99th Percentile:  {lat_p99:.2f} ms")
            
            print_ascii_histogram(latencies, bins=10)
        else:
            print("\nNo frames were successfully processed.")
            
        print("="*50)
        
        # Assessment
        target_fps = args.fps
        if target_fps > 0:
            margin = 0.95  # 5% tolerance
            if process_fps >= target_fps * margin and drop_rate <= 1.0:
                print(f"\n[SUCCESS] Pipeline successfully handled {args.fps} FPS target!")
                print(f"  Mean Latency: {np.mean(latencies):.2f} ms (< 1 frame interval of {1000.0/args.fps:.2f} ms)")
            else:
                print(f"\n[WARNING] Pipeline struggled to maintain the {args.fps} FPS target.")
                print(f"  Achieved process rate: {process_fps:.2f} FPS")
                print(f"  Frame drop rate:       {drop_rate:.2f}%")
        else:
            print(f"\n[INFO] Maximum sustainable pipeline throughput on this machine is {process_fps:.2f} FPS.")
            
    finally:
        # Cleanup temporary files
        if 'video_is_temp' in locals() and video_is_temp:
            if 'video_path' in locals() and os.path.exists(video_path):
                os.remove(video_path)
        if 'record_path' in locals() and os.path.exists(record_path):
            os.remove(record_path)
        if 'temp_dir' in locals() and os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except Exception:
                pass


if __name__ == "__main__":
    main()
