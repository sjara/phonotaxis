cdef class WorkerResult:
    cdef public double timestamp
    cdef public dict data
    cdef public str worker_name

cdef class ResultBus:
    cdef public dict _subscribers
    cdef public object _lock
