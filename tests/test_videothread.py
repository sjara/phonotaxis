import pytest
import numpy as np
import time
from phonotaxis.sharedbuffer import SharedFrameBuffer, ResultBuffer
from phonotaxis.videoworkers import ProcessWorker

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

def test_process_worker_process_frame():
    buf = SharedFrameBuffer(1, (100, 100))
    res_buf = ResultBuffer()
    worker = ProcessWorker(buf, res_buf, threshold=128, minarea=10, tracking=True)
    
    # Create a frame with a black square in the middle
    frame = np.ones((100, 100), dtype=np.uint8) * 255
    frame[40:60, 40:60] = 0
    
    processed, points, contour = worker.process_frame(frame)
    
    assert points != ((-1,-1),)
    # the centroid should be near 50, 50
    assert abs(points[0][0] - 50) < 5
    assert abs(points[0][1] - 50) < 5
    assert contour is not None
