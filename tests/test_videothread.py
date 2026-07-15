import pytest
import numpy as np
import time
import queue
import cv2
import tempfile
import os
import threading
from phonotaxis.sharedbuffer import SharedFrameBuffer, ResultBuffer
from phonotaxis.videoworkers import ProcessWorker, ContourTracker, FileCaptureWorker, RecordWorker
from phonotaxis.videomodule import VideoThread
from phonotaxis.resultbus import WorkerResult, ResultBus

# ---------------------------------------------------------------------------
# SharedFrameBuffer tests
# ---------------------------------------------------------------------------

def test_shared_frame_buffer_write_read():
    buf = SharedFrameBuffer(3, (10, 10))
    frame1 = np.ones((10, 10), dtype=np.uint8)
    
    buf.try_write(1.0, frame1)
    
    res = buf.try_read()
    assert res is not None
    ts, f = res
    assert ts == 1.0
    assert np.array_equal(f, frame1)

def test_shared_frame_buffer_overflow():
    buf = SharedFrameBuffer(2, (10, 10))
    
    buf.try_write(1.0, np.ones((10, 10), dtype=np.uint8) * 1)
    buf.try_write(2.0, np.ones((10, 10), dtype=np.uint8) * 2)
    buf.try_write(3.0, np.ones((10, 10), dtype=np.uint8) * 3)
    
    # Oldest (1.0) should be overwritten, so we read 2.0 then 3.0
    res1 = buf.try_read()
    assert res1[0] == 2.0
    res2 = buf.try_read()
    assert res2[0] == 3.0
    assert buf.try_read() is None

# ---------------------------------------------------------------------------
# ContourTracker tests
# ---------------------------------------------------------------------------

def test_contour_tracker_process_frame():
    tracker = ContourTracker(threshold=128, minarea=10, tracking=True)
    
    # Create a frame with a black square in the middle
    frame = np.ones((100, 100), dtype=np.uint8) * 255
    frame[40:60, 40:60] = 0
    
    result = tracker(0.0, frame)
    
    assert isinstance(result, dict)
    assert result['points'] != ((-1,-1),)
    # the centroid should be near 50, 50
    assert abs(result['points'][0][0] - 50) < 5
    assert abs(result['points'][0][1] - 50) < 5
    assert result['contour'] is not None
    assert 'orientations' in result

def test_contour_tracker_no_tracking():
    tracker = ContourTracker(threshold=128, minarea=10, tracking=False)
    frame = np.ones((100, 100), dtype=np.uint8) * 255
    
    result = tracker(0.0, frame)
    
    assert result['points'] == ()
    assert result['contour'] is None

def test_contour_tracker_mask():
    tracker = ContourTracker(threshold=128, minarea=10, tracking=True)
    tracker.set_circular_mask([50, 50, 10])
    assert tracker.mask_enabled is True
    assert tracker.mask_coords == [50, 50, 10]
    
    tracker.disable_mask()
    assert tracker.mask_enabled is False
    assert tracker.mask_coords is None

# ---------------------------------------------------------------------------
# ResultBuffer tests (with WorkerResult)
# ---------------------------------------------------------------------------

def test_result_buffer_worker_result():
    buf = ResultBuffer()
    
    wr = WorkerResult(
        timestamp=1.0,
        data={'points': ((50, 50),), 'contour': None},
        worker_name='test_worker',
    )
    buf.try_write_result(wr)
    
    res = buf.try_read_result()
    assert res is not None
    assert isinstance(res, WorkerResult)
    assert res.timestamp == 1.0
    assert res.data['points'] == ((50, 50),)
    assert res.worker_name == 'test_worker'
    
    # Buffer should be empty now
    assert buf.try_read_result() is None

# ---------------------------------------------------------------------------
# ResultBus tests
# ---------------------------------------------------------------------------

def test_result_bus_pub_sub():
    bus = ResultBus()
    q = bus.subscribe('tracker')
    
    wr = WorkerResult(timestamp=1.0, data={'x': 10}, worker_name='tracker')
    bus.publish(wr)
    
    msg = q.get(timeout=1.0)
    assert msg.timestamp == 1.0
    assert msg.data['x'] == 10

def test_result_bus_multiple_subscribers():
    bus = ResultBus()
    q1 = bus.subscribe('tracker')
    q2 = bus.subscribe('tracker')
    
    wr = WorkerResult(timestamp=2.0, data={'y': 20}, worker_name='tracker')
    bus.publish(wr)
    
    msg1 = q1.get(timeout=1.0)
    msg2 = q2.get(timeout=1.0)
    assert msg1.timestamp == 2.0
    assert msg2.timestamp == 2.0

def test_result_bus_drop_oldest():
    bus = ResultBus()
    q = bus.subscribe('tracker', maxsize=2)
    
    # Fill the queue
    bus.publish(WorkerResult(timestamp=1.0, data={}, worker_name='tracker'))
    bus.publish(WorkerResult(timestamp=2.0, data={}, worker_name='tracker'))
    # This should drop timestamp=1.0
    bus.publish(WorkerResult(timestamp=3.0, data={}, worker_name='tracker'))
    
    msg1 = q.get(timeout=1.0)
    msg2 = q.get(timeout=1.0)
    assert msg1.timestamp == 2.0
    assert msg2.timestamp == 3.0
    assert q.empty()

def test_result_bus_no_subscribers():
    """Publishing with no subscribers should not raise."""
    bus = ResultBus()
    wr = WorkerResult(timestamp=1.0, data={}, worker_name='nobody')
    bus.publish(wr)  # Should be a no-op

# ---------------------------------------------------------------------------
# Generic ProcessWorker tests
# ---------------------------------------------------------------------------

def test_process_worker_frame_mode():
    """Verify generic worker reads from buffer, calls strategy, writes result."""
    buf = SharedFrameBuffer(4, (10, 10))
    res_buf = ResultBuffer()
    
    # Simple strategy that returns a dict
    def strategy(timestamp, frame):
        return {'mean': float(np.mean(frame))}
    
    worker = ProcessWorker(
        strategy=strategy,
        result_buffer=res_buf,
        name='test',
        raw_buffer=buf,
    )
    
    # Write a frame
    frame = np.ones((10, 10), dtype=np.uint8) * 42
    buf.try_write(1.0, frame)
    
    # Run worker in a thread, let it process one frame, then stop
    import threading
    t = threading.Thread(target=worker.run, daemon=True)
    t.start()
    
    # Give it time to process
    time.sleep(0.2)
    worker.stop()
    t.join(timeout=2.0)
    
    result = res_buf.try_read_result()
    assert result is not None
    assert result.timestamp == 1.0
    assert result.data['mean'] == 42.0
    assert result.worker_name == 'test'

def test_process_worker_bus_mode():
    """Verify generic worker subscribes to bus and processes messages."""
    bus = ResultBus()
    res_buf = ResultBuffer()
    
    # Strategy that doubles the 'value' field
    def strategy(msg):
        return {'doubled': msg.data['value'] * 2}
    
    worker = ProcessWorker(
        strategy=strategy,
        result_buffer=res_buf,
        name='doubler',
        bus=bus,
        subscribe_to='upstream',
    )
    
    import threading
    t = threading.Thread(target=worker.run, daemon=True)
    t.start()
    
    # Publish an upstream result
    bus.publish(WorkerResult(timestamp=5.0, data={'value': 7}, worker_name='upstream'))
    
    time.sleep(0.2)
    worker.stop()
    t.join(timeout=2.0)
    
    result = res_buf.try_read_result()
    assert result is not None
    assert result.data['doubled'] == 14
    assert result.worker_name == 'doubler'

def test_process_worker_publishes_to_bus():
    """Verify worker publishes its own results to a downstream bus."""
    in_buf = SharedFrameBuffer(4, (10, 10))
    res_buf = ResultBuffer()
    out_bus = ResultBus()
    
    # Subscribe before worker starts
    downstream_q = out_bus.subscribe('publisher')
    
    def strategy(timestamp, frame):
        return {'sum': int(np.sum(frame))}
    
    worker = ProcessWorker(
        strategy=strategy,
        result_buffer=res_buf,
        name='publisher',
        raw_buffer=in_buf,
        publish_to_bus=out_bus,
    )
    
    frame = np.ones((10, 10), dtype=np.uint8) * 3
    in_buf.try_write(2.0, frame)
    
    import threading
    t = threading.Thread(target=worker.run, daemon=True)
    t.start()
    
    time.sleep(0.2)
    worker.stop()
    t.join(timeout=2.0)
    
    # Check the bus received the result
    assert not downstream_q.empty()
    msg = downstream_q.get(timeout=1.0)
    assert msg.timestamp == 2.0
    assert msg.data['sum'] == 300  # 10*10*3

def test_worker_result_dataclass():
    """Verify WorkerResult fields."""
    wr = WorkerResult(timestamp=1.5, data={'a': 1}, worker_name='w')
    assert wr.timestamp == 1.5
    assert wr.data == {'a': 1}
    assert wr.worker_name == 'w'


# ---------------------------------------------------------------------------
# FileCaptureWorker and VideoThread playback tests
# ---------------------------------------------------------------------------

def create_dummy_video(filename, width=100, height=100, fps=30, num_frames=10):
    fourcc = cv2.VideoWriter_fourcc(*'MJPG')
    out = cv2.VideoWriter(filename, fourcc, fps, (width, height), isColor=False)
    for i in range(num_frames):
        frame = np.ones((height, width), dtype=np.uint8) * 255
        cx = int(width / 2 + i * 2)
        cy = int(height / 2)
        cv2.circle(frame, (cx, cy), 5, 0, -1)
        out.write(frame)
    out.release()


def test_file_capture_worker_basic():
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "test.avi")
        create_dummy_video(video_path, fps=30, num_frames=10)
        
        cap = cv2.VideoCapture(video_path)
        raw_buffer = SharedFrameBuffer(capacity=15, frame_shape=(100, 100))
        
        # Test paced mode
        worker = FileCaptureWorker(cap, process_buffers=[raw_buffer], fps_limit=30, loop=False)
        assert worker.file_fps == 30.0
        assert worker.frame_width == 100
        assert worker.frame_height == 100
        
        t = threading.Thread(target=worker.run, daemon=True)
        t.start()
        t.join(timeout=2.0)
        
        # We should have read exactly 10 frames
        count = 0
        while raw_buffer.try_read() is not None:
            count += 1
        assert count == 10


def test_file_capture_worker_benchmark():
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "test.avi")
        create_dummy_video(video_path, fps=30, num_frames=15)
        
        cap = cv2.VideoCapture(video_path)
        raw_buffer = SharedFrameBuffer(capacity=20, frame_shape=(100, 100))
        
        # Test benchmark mode (fps_limit=0 or negative)
        worker = FileCaptureWorker(cap, process_buffers=[raw_buffer], fps_limit=0, loop=False)
        
        t = threading.Thread(target=worker.run, daemon=True)
        t.start()
        t.join(timeout=1.0)
        
        count = 0
        while raw_buffer.try_read() is not None:
            count += 1
        assert count == 15


def test_file_capture_worker_loop():
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "test.avi")
        create_dummy_video(video_path, fps=1000, num_frames=5)
        
        cap = cv2.VideoCapture(video_path)
        raw_buffer = SharedFrameBuffer(capacity=20, frame_shape=(100, 100))
        
        # Test looping mode
        worker = FileCaptureWorker(cap, process_buffers=[raw_buffer], fps_limit=1000, loop=True)
        
        t = threading.Thread(target=worker.run, daemon=True)
        t.start()
        
        # Let it run for a short duration; it should read more than 5 frames due to looping
        time.sleep(0.1)
        worker.stop()
        t.join(timeout=1.0)
        
        count = 0
        while raw_buffer.try_read() is not None:
            count += 1
        assert count > 5


def test_video_thread_file_integration():
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "test.avi")
        create_dummy_video(video_path, fps=30, num_frames=10)
        
        # Initialize VideoThread with string path
        vt = VideoThread(camera_index=video_path, tracking=True, fps_limit=30, loop=False)
        assert isinstance(vt.capture_worker, FileCaptureWorker)
        vt.set_minarea(10)
        
        vt.start()
        # Wait for the thread to exit (which it should automatically do when the file ends)
        assert vt.wait(2000)  # Wait up to 2 seconds for clean auto-termination
        
        # Verify that tracking was successful and generated coordinates
        assert len(vt.timestamps) == 10
        assert len(vt.points) > 0
        # The moving spot was tracked, coordinates shouldn't be (-1, -1)
        assert vt.points[0][0] != (-1, -1)


def test_file_capture_worker_captured_count():
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "test.avi")
        create_dummy_video(video_path, fps=100, num_frames=10)
        
        cap = cv2.VideoCapture(video_path)
        raw_buffer = SharedFrameBuffer(capacity=20, frame_shape=(100, 100))
        
        worker = FileCaptureWorker(cap, process_buffers=[raw_buffer], fps_limit=100, loop=False)
        assert worker.captured_count == 0
        
        t = threading.Thread(target=worker.run, daemon=True)
        t.start()
        t.join(timeout=2.0)
        
        assert worker.captured_count == 10


def test_file_capture_worker_wait_on_full_disabled():
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "test.avi")
        create_dummy_video(video_path, fps=1000, num_frames=15)
        
        cap = cv2.VideoCapture(video_path)
        raw_buffer = SharedFrameBuffer(capacity=5, frame_shape=(100, 100))
        
        # Test with wait_on_full=False
        worker = FileCaptureWorker(cap, process_buffers=[raw_buffer], fps_limit=1000, loop=False, wait_on_full=False)
        assert worker.wait_on_full is False
        
        t = threading.Thread(target=worker.run, daemon=True)
        t.start()
        t.join(timeout=2.0)
        
        # It should read all 15 frames without waiting
        assert worker.captured_count == 15
        
        # Buffer only holds at most 5 items because it overwrites rather than waiting
        count = 0
        while raw_buffer.try_read() is not None:
            count += 1
        assert count == 5


def test_worker_performance_counters():
    """Verify that processed_count on ProcessWorker and recorded_count on RecordWorker increment correctly."""
    buf = SharedFrameBuffer(5, (10, 10))
    res_buf = ResultBuffer()
    
    worker = ProcessWorker(
        strategy=lambda ts, f: {'val': 1},
        result_buffer=res_buf,
        name='test_worker',
        raw_buffer=buf,
    )
    assert worker.processed_count == 0
    
    # Write frames and run worker
    buf.try_write(1.0, np.zeros((10, 10), dtype=np.uint8))
    buf.try_write(2.0, np.zeros((10, 10), dtype=np.uint8))
    
    t = threading.Thread(target=worker.run, daemon=True)
    t.start()
    time.sleep(0.1)
    worker.stop()
    t.join(timeout=2.0)
    
    assert worker.processed_count == 2
    
    # Test RecordWorker
    rec_worker = RecordWorker()
    assert rec_worker.recorded_count == 0
    
    # mock _ffmpeg_process
    class MockFFmpeg:
        def __init__(self):
            class MockStdin:
                def write(self, data):
                    pass
                def close(self):
                    pass
            self.stdin = MockStdin()
        def wait(self):
            pass
    rec_worker._ffmpeg_process = MockFFmpeg()
    
    rec_worker.write_frame(1.0, np.zeros((10, 10), dtype=np.uint8))
    
    assert rec_worker.recorded_count == 1

