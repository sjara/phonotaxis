import threading
import queue

cdef class WorkerResult:
    """
    Generic container for a worker's output.

    Attributes:
        timestamp: Frame timestamp from the source capture.
        data: Strategy-specific payload dict (e.g., processed_frame,
              points, contour, orientations for contour tracking).
        worker_name: Identifies the source worker for routing.
    """
    def __init__(self, double timestamp, dict data, str worker_name):
        self.timestamp = timestamp
        self.data = data
        self.worker_name = worker_name

cdef class ResultBus:
    """
    Thread-safe pub/sub channel for inter-worker result sharing.

    Publishers push WorkerResult objects; subscribers receive copies
    via bounded queues.  When a subscriber's queue is full the oldest
    item is silently dropped, matching the frame-drop policy used
    elsewhere in the pipeline.

    Multiple subscribers per publisher are supported (fan-out).
    """

    def __init__(self):
        self._subscribers = {}
        self._lock = threading.Lock()

    def subscribe(self, str worker_name, int maxsize = 4):
        """
        Subscribe to results published by *worker_name*.

        Args:
            worker_name: Name of the upstream worker to listen to.
            maxsize: Bounded queue depth.  When full, the oldest item
                     is dropped on the next publish (non-blocking).

        Returns:
            A ``queue.Queue`` that will receive ``WorkerResult`` objects.
        """
        q = queue.Queue(maxsize=maxsize)
        with self._lock:
            self._subscribers.setdefault(worker_name, []).append(q)
        return q

    def publish(self, WorkerResult result):
        """
        Push *result* to every subscriber of ``result.worker_name``.

        If a subscriber's queue is full the oldest entry is discarded
        before the new one is enqueued.
        """
        cdef list subs
        cdef str name = result.worker_name
        with self._lock:
            subs = self._subscribers.get(name, [])
        for q in subs:
            # Drop-oldest policy: discard head if full, then put.
            if q.full():
                try:
                    q.get_nowait()
                except queue.Empty:
                    pass
            try:
                q.put_nowait(result)
            except queue.Full:
                pass  # Shouldn't happen after the drain above.
