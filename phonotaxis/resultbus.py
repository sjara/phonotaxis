"""
Inter-worker result pub/sub channel.

Provides a lightweight, thread-safe mechanism for ProcessWorkers to
share results with downstream workers without direct coupling.
No Qt dependencies — suitable for Cython compilation.
"""

import threading
import queue
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class WorkerResult:
    """
    Generic container for a worker's output.

    Attributes:
        timestamp: Frame timestamp from the source capture.
        data: Strategy-specific payload dict (e.g., processed_frame,
              points, contour, orientations for contour tracking).
        worker_name: Identifies the source worker for routing.
    """
    timestamp: float
    data: Dict[str, Any]
    worker_name: str


class ResultRingBuffer:
    """
    Lock-protected circular ring buffer for WorkerResult objects.
    Adopts the same circular buffer logic as SharedFrameBuffer.
    """
    def __init__(self, capacity: int):
        self._capacity = capacity
        self._buffer = [None] * capacity
        self._write_idx = 0
        self._read_idx = 0
        self._items_available = 0
        self._lock = threading.Lock()
        self._event = threading.Event()

    def put_nowait(self, item: WorkerResult) -> bool:
        """Write an item to the buffer. If full, overwrite the oldest item."""
        with self._lock:
            self._buffer[self._write_idx] = item
            self._write_idx = (self._write_idx + 1) % self._capacity
            
            if self._items_available < self._capacity:
                self._items_available += 1
            else:
                self._read_idx = (self._read_idx + 1) % self._capacity
                
            self._event.set()
        return True

    def get(self, timeout: Optional[float] = None) -> WorkerResult:
        """Blocking read with optional timeout. Raises queue.Empty on timeout."""
        if timeout is not None:
            if self._event.wait(timeout):
                res = self.get_nowait()
                if res is not None:
                    return res
            raise queue.Empty()
        else:
            # Infinite wait
            while True:
                with self._lock:
                    if self._items_available > 0:
                        break
                self._event.wait(0.01)
            res = self.get_nowait()
            if res is not None:
                return res
            raise queue.Empty()

    def get_nowait(self) -> WorkerResult:
        """Non-blocking read. Raises queue.Empty if empty."""
        with self._lock:
            if self._items_available == 0:
                raise queue.Empty()
            
            item = self._buffer[self._read_idx]
            self._buffer[self._read_idx] = None  # Allow GC
            
            self._read_idx = (self._read_idx + 1) % self._capacity
            self._items_available -= 1
            
            if self._items_available == 0:
                self._event.clear()
                
            return item

    def empty(self) -> bool:
        with self._lock:
            return self._items_available == 0

    def full(self) -> bool:
        with self._lock:
            return self._items_available == self._capacity


class ResultBus:
    """
    Thread-safe pub/sub channel for inter-worker result sharing.

    Publishers push WorkerResult objects; subscribers receive copies
    via bounded ResultRingBuffers. When a subscriber's buffer is full
    the oldest item is silently overwritten (drop-oldest policy).
    """

    def __init__(self):
        self._subscribers: Dict[str, List[ResultRingBuffer]] = {}
        self._lock = threading.Lock()

    def subscribe(self, worker_name: str, maxsize: int = 4) -> ResultRingBuffer:
        """
        Subscribe to results published by *worker_name*.

        Args:
            worker_name: Name of the upstream worker to listen to.
            maxsize: Bounded buffer capacity.

        Returns:
            A ``ResultRingBuffer`` that will receive ``WorkerResult`` objects.
        """
        q = ResultRingBuffer(capacity=maxsize)
        with self._lock:
            self._subscribers.setdefault(worker_name, []).append(q)
        return q

    def publish(self, result: WorkerResult):
        """
        Push *result* to every subscriber of ``result.worker_name``.
        """
        with self._lock:
            subs = self._subscribers.get(result.worker_name, [])
        for q in subs:
            q.put_nowait(result)

