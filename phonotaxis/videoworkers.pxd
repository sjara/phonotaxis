cimport numpy as cnp
from .sharedbuffer cimport SharedFrameBuffer, ResultBuffer
from .resultbus cimport WorkerResult, ResultBus

cdef class CaptureWorker:
    cdef public object cap
    cdef public list process_buffers
    cdef public SharedFrameBuffer record_buffer
    cdef public bint running
    cdef public bint recording

cdef class FileCaptureWorker:
    cdef public object cap
    cdef public list process_buffers
    cdef public SharedFrameBuffer record_buffer
    cdef public object fps_limit
    cdef public bint loop
    cdef public bint running
    cdef public bint recording
    cdef public bint paused
    cdef public double file_fps
    cdef public int frame_width
    cdef public int frame_height

cdef class ContourTracker:
    cdef public int threshold
    cdef public int minarea
    cdef public bint tracking
    cdef public bint mask_enabled
    cdef public list mask_coords
    cdef public str mode

cdef class ProcessWorker:
    cdef public object strategy
    cdef public ResultBuffer result_buffer
    cdef public str name
    cdef public SharedFrameBuffer raw_buffer
    cdef public bint running
    cdef public bint is_processing
    cdef public object _subscription_queue
    cdef public ResultBus _publish_bus
    cdef public object _on_start
    cdef public object _on_stop

cdef class RecordWorker:
    cdef public SharedFrameBuffer record_buffer
    cdef public bint running
    cdef public object _ffmpeg_process
    cdef public object _frame_size
