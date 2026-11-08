"""Windows-only containment and conservative process identity (stdlib)."""
import os
import socket
import subprocess
import tempfile
import time

if os.name == 'nt':
    import ctypes as c
    from ctypes import wintypes as w
    import _winapi

    k = c.WinDLL('kernel32', use_last_error=True)
    # Explicit handle signatures are essential on 64-bit Windows.
    for name, args, result in [
        ('CreateJobObjectW', [c.c_void_p, w.LPCWSTR], w.HANDLE),
        ('SetInformationJobObject', [w.HANDLE, c.c_int, c.c_void_p, w.DWORD], w.BOOL),
        ('AssignProcessToJobObject', [w.HANDLE, w.HANDLE], w.BOOL),
        ('CloseHandle', [w.HANDLE], w.BOOL),
        ('ResumeThread', [w.HANDLE], w.DWORD),
        ('OpenProcess', [w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
        ('GetProcessTimes', [w.HANDLE, c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p], w.BOOL),
        ('WaitForSingleObject', [w.HANDLE, w.DWORD], w.DWORD),
    ]:
        fn = getattr(k, name)
        fn.argtypes, fn.restype = args, result

    class BASIC(c.Structure):
        _fields_ = [('process_time', c.c_int64), ('job_time', c.c_int64),
                    ('flags', w.DWORD), ('min_ws', c.c_size_t), ('max_ws', c.c_size_t),
                    ('active', w.DWORD), ('affinity', c.c_size_t),
                    ('priority', w.DWORD), ('scheduling', w.DWORD)]

    class EXTENDED(c.Structure):
        _fields_ = [('basic', BASIC), ('io', c.c_uint64 * 6),
                    ('process_mem', c.c_size_t), ('job_mem', c.c_size_t),
                    ('peak_process', c.c_size_t), ('peak_job', c.c_size_t)]


def _birth(handle):
    values = [c.c_uint64() for _ in range(4)]
    if not k.GetProcessTimes(handle, *(c.byref(v) for v in values)):
        raise OSError(c.get_last_error(), 'GetProcessTimes')
    return str(values[0].value)


def identity():
    if os.name != 'nt':
        return (socket.gethostname(), os.getpid(), None)
    handle = k.OpenProcess(0x1000, False, os.getpid())
    if not handle:
        return (socket.gethostname(), os.getpid(), None)
    try:
        return (socket.gethostname(), os.getpid(), _birth(handle))
    finally:
        k.CloseHandle(handle)


def owner_state(host, pid, birth):
    """Only 'dead' is recovery authority; access errors are unknown."""
    if os.name != 'nt' or host != socket.gethostname() or not pid or not birth:
        return 'unknown'
    handle = k.OpenProcess(0x1000 | 0x100000, False, pid)
    if not handle:
        return 'dead' if c.get_last_error() == 87 else 'unknown'
    try:
        if _birth(handle) != birth:
            return 'dead'  # PID reuse, original process is gone
        result = k.WaitForSingleObject(handle, 0)
        return {0: 'dead', 258: 'alive'}.get(result, 'unknown')
    except OSError:
        return 'unknown'
    finally:
        k.CloseHandle(handle)


def run(argv, *, cwd, timeout, cancel_event=None, **ignored):
    """Create suspended, assign kill-on-close job, then resume. No fallback.

    Job handle is non-inheritable: controller death closes the last handle.
    Descendants cannot break away. Output uses files so pipes cannot hang cleanup.
    """
    if os.name != 'nt':
        raise OSError('OS process containment unavailable; launch refused')
    if cancel_event is not None and cancel_event.is_set():
        raise InterruptedError('controller interrupted')
    job = k.CreateJobObjectW(None, None)
    if not job:
        raise c.WinError(c.get_last_error())
    process = thread = None
    assigned = False
    try:
        limits = EXTENDED()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k.SetInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits)):
            raise c.WinError(c.get_last_error())
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr, open(os.devnull, 'rb') as stdin:
            import msvcrt
            handles = [msvcrt.get_osfhandle(f.fileno()) for f in (stdin, stdout, stderr)]
            # Duplicate inheritable handles; never change shared parent handles.
            duplicates = []
            try:
                for h in handles:
                    duplicates.append(_winapi.DuplicateHandle(
                        _winapi.GetCurrentProcess(), h,
                        _winapi.GetCurrentProcess(), 0, True, 2))
                si = subprocess.STARTUPINFO()
                si.dwFlags = subprocess.STARTF_USESTDHANDLES
                si.hStdInput, si.hStdOutput, si.hStdError = duplicates
                si.lpAttributeList = {'handle_list': duplicates}
                process, thread, _, _ = _winapi.CreateProcess(
                    None, subprocess.list2cmdline(argv), None, None, True,
                    0x4 | 0x08000000, None, cwd, si)  # suspended, no window
            finally:
                for h in duplicates:
                    _winapi.CloseHandle(h)
            if not k.AssignProcessToJobObject(job, process):
                raise c.WinError(c.get_last_error())
            assigned = True
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError('controller interrupted')
            if k.ResumeThread(thread) == 0xFFFFFFFF:
                raise c.WinError(c.get_last_error())
            deadline = time.monotonic() + timeout
            while True:
                waited = k.WaitForSingleObject(process, 20)
                if waited == 0:
                    break
                if waited != 258:
                    raise c.WinError(c.get_last_error())
                if cancel_event is not None and cancel_event.is_set():
                    raise InterruptedError('controller interrupted')
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(argv, timeout)
            code = _winapi.GetExitCodeProcess(process)
            # Also clean descendants after a successful direct-child exit.
            k.CloseHandle(job)
            job = None
            stdout.seek(0, 2)
            size = stdout.tell()
            stdout.seek(max(0, size - 16000))
            out = stdout.read().decode(errors='replace')
            stderr.seek(0, 2)
            size = stderr.tell()
            stderr.seek(max(0, size - 8000))
            err = stderr.read().decode(errors='replace')
            return subprocess.CompletedProcess(argv, code, out, err)
    finally:
        if job:
            k.CloseHandle(job)
        if process:
            if not assigned:  # suspended and never executed; exact owned handle
                _winapi.TerminateProcess(process, 1)
            _winapi.WaitForSingleObject(process, 5000)
            _winapi.CloseHandle(process)
        if thread:
            _winapi.CloseHandle(thread)
