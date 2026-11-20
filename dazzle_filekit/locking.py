"""An exclusive lock on one dedicated lock file, on every OS.

``exclusive_lock(path, timeout=5.0)`` holds an exclusive lock on ``path`` for
the length of a ``with`` block. ``path`` must be a **dedicated lock file** --
never the data file the lock protects: on Windows the lock is a mandatory
byte-range lock (byte 0 becomes unreadable through other handles), on POSIX an
advisory ``flock``. The file is created if missing and may stay empty.

Acquiring never blocks indefinitely: it retries a non-blocking attempt until
``timeout`` seconds have passed, then raises :class:`LockTimeoutError` naming
the file. (Windows' own blocking mode, ``LK_LOCK``, gives up after about ten
seconds with an error, so it is not used.) The lock is released when the block
ends, and by the operating system when the holder's process dies -- measured
on Windows: a holder killed with ``taskkill /f`` freed the lock for the next
process at its first attempt, under 0.09 s.

Added in 0.5.3 (first consumer: dz relaunch's store; csb's lock is the next
candidate).
"""

from __future__ import annotations

import contextlib
import os
import sys
import time
from typing import Iterator, Optional, Union

from dazzle_lib.exceptions import FileOperationError

__all__ = ["LockTimeoutError", "exclusive_lock", "try_lock", "unlock"]

_WINDOWS = sys.platform == "win32"


class LockTimeoutError(FileOperationError, TimeoutError):
    """The lock file stayed locked by another holder until the deadline."""


def _open_lock_file(path: str) -> int:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    return os.open(path, flags, 0o666)


def try_lock(fd: int) -> bool:
    """One non-blocking attempt on an open lock-file descriptor. True if taken."""
    if _WINDOWS:
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)  # msvcrt.locking locks from the current position
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    import fcntl
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (BlockingIOError, PermissionError):
        return False
    except OSError as e:
        import errno
        if e.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
            return False
        raise


def unlock(fd: int) -> None:
    """Release a lock taken by :func:`try_lock` (closing the descriptor also does)."""
    if _WINDOWS:
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        return
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_UN)


@contextlib.contextmanager
def exclusive_lock(path: Union[str, "os.PathLike[str]"], *, timeout: float = 5.0,
                   poll: float = 0.02,
                   clock=time.monotonic, sleep=time.sleep) -> Iterator[int]:
    """Hold an exclusive lock on the dedicated lock file ``path``.

    Yields the open descriptor (callers normally ignore it). Raises
    :class:`LockTimeoutError` if the lock is still held elsewhere after
    ``timeout`` seconds; ``timeout=0`` means a single attempt.
    """
    p = os.fspath(path)
    fd = _open_lock_file(p)
    try:
        deadline = clock() + max(0.0, timeout)
        while not try_lock(fd):
            if clock() >= deadline:
                raise LockTimeoutError(
                    f"lock file {p} is still held by another process after {timeout:g}s")
            sleep(poll)
        try:
            yield fd
        finally:
            unlock(fd)
    finally:
        os.close(fd)
