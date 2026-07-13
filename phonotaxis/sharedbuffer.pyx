import threading
import numpy as np
cimport numpy as cnp
from .resultbus import WorkerResult

cdef class SharedFrameBuffer:
    """
    SPSC ring buffer for numpy frames.
    
    Designed for Cython conversion: all attributes are typed,
    no Qt dependencies, uses threading.Event for signaling.
    """
    def __init__(self, int capacity, tuple frame_shape, object dtype=np.uint8):
        self._capacity = capacity
        # allocate buffer
        self._buffer = np.zeros((capacity, *frame_shape), dtype=dtype)
        self._timestamps = np.zeros(capacity, dtype=np.float64)
        
        self._write_idx = 0
        self._read_idx = 0
        self._items_available = 0
        
        self._lock = threading.Lock()
        self._event = threading.Event()
        
    def try_write(self, double timestamp, cnp.ndarray frame) -> bool:
        """Non-blocking write. Overwrites if full."""
        with self._lock:
            self._buffer[self._write_idx] = frame
            self._timestamps[self._write_idx] = timestamp
            
            self._write_idx = (self._write_idx + 1) % self._capacity
            
            if self._items_available < self._capacity:
                self._items_available += 1
            else:
                self._read_idx = (self._read_idx + 1) % self._capacity
                
            self._event.set()
        return True

    def try_read(self):
        """Non-blocking read. Returns None if buffer is empty."""
        with self._lock:
            if self._items_available == 0:
                return None
            
            frame = self._buffer[self._read_idx].copy()
            timestamp = self._timestamps[self._read_idx]
            
            self._read_idx = (self._read_idx + 1) % self._capacity
            self._items_available -= 1
            
            if self._items_available == 0:
                self._event.clear()
                
            return timestamp, frame

    def read_blocking(self, double timeout = 0.1):
        """Blocking read with timeout, uses threading.Event."""
        if self._event.wait(timeout):
            return self.try_read()
        return None

cdef class ResultBuffer:
    """
    Lock-protected buffer for a ProcessWorker to pass results back
    to the coordinator.  Stores ``WorkerResult`` objects.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._result = None
        
    def try_write_result(self, object result):
        """Write a ``WorkerResult`` into the buffer (overwrites previous)."""
        with self._lock:
            self._result = result
            
    def try_read_result(self):
        """Non-blocking read.  Returns ``None`` if buffer is empty."""
        with self._lock:
            res = self._result
            self._result = None
            return res
