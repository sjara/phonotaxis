cimport numpy as cnp

cdef class SharedFrameBuffer:
    cdef public int _capacity
    cdef public cnp.ndarray _buffer
    cdef public cnp.ndarray _timestamps
    cdef public int _write_idx
    cdef public int _read_idx
    cdef public int _items_available
    cdef public object _lock
    cdef public object _event

cdef class ResultBuffer:
    cdef public object _lock
    cdef public object _result
