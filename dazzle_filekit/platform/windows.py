"""
Platform-specific implementations for Windows.

This module provides Windows-specific implementations for file operations
and metadata handling, including:

  - ``is_admin()``: current-process admin check
  - ``detect_alternate_streams(path)``: NTFS Alternate Data Stream enumeration
  - ``has_significant_ads(path)``: boolean "are there meaningful ADS"

Ported from ``safedel/_platform.py`` in v0.2.4.
"""

import os
import sys
import logging
from pathlib import Path
from typing import List, Union

# Platform check
if sys.platform != 'win32':
    raise ImportError("This module is only available on Windows")

# Set up module-level logger
logger = logging.getLogger(__name__)

# Import Windows-specific libraries when available
try:
    import win32api
    import win32con
    import win32file
    import win32security
    HAVE_WIN32API = True
except ImportError:
    logger.debug("win32api module not available, some functionality will be limited")
    HAVE_WIN32API = False


def is_admin():
    """
    Check if the current process has administrator privileges.

    Returns:
        bool: True if the process has admin privileges, False otherwise
    """
    if not HAVE_WIN32API:
        return False

    try:
        return win32security.IsUserAnAdmin()
    except Exception as e:
        logger.debug(f"Error checking admin status: {e}")
        return False


# ---------------------------------------------------------------------------
# NTFS Alternate Data Streams (v0.2.4)
# ---------------------------------------------------------------------------

# Streams to ignore when warning about ADS (pre-filter to reduce alert fatigue)
_ADS_IGNORE_STREAMS = {
    "::$DATA",                 # Default data stream (not really ADS)
    ":Zone.Identifier:$DATA",  # Browser download marker (nearly universal)
}


def detect_alternate_streams(path: Union[str, Path]) -> List[str]:
    """Enumerate NTFS alternate data streams on a file.

    Returns a list of non-default stream names found on the file.
    Filters out ``::$DATA`` (the main data stream) and
    ``:Zone.Identifier`` (the browser download marker, which is nearly
    universal and would cause alert fatigue).

    Returns an empty list on non-Windows platforms, on errors, or when
    only the default stream exists.

    Uses ctypes to call ``FindFirstStreamW`` / ``FindNextStreamW`` since
    pywin32 doesn't expose these functions.

    Args:
        path: File path to inspect.

    Returns:
        List of significant (non-ignored) stream names. Empty if none.
    """
    if sys.platform != "win32":
        return []

    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return []

    kernel32 = ctypes.windll.kernel32

    class WIN32_FIND_STREAM_DATA(ctypes.Structure):
        _fields_ = [
            ("StreamSize", ctypes.c_longlong),
            ("cStreamName", ctypes.c_wchar * 296),
        ]

    try:
        kernel32.FindFirstStreamW.argtypes = [
            wintypes.LPCWSTR, ctypes.c_int,
            ctypes.POINTER(WIN32_FIND_STREAM_DATA), wintypes.DWORD,
        ]
        kernel32.FindFirstStreamW.restype = wintypes.HANDLE
        kernel32.FindNextStreamW.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(WIN32_FIND_STREAM_DATA),
        ]
        kernel32.FindNextStreamW.restype = wintypes.BOOL
        kernel32.FindClose.argtypes = [wintypes.HANDLE]
    except (AttributeError, OSError):
        return []

    INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

    streams: List[str] = []
    data = WIN32_FIND_STREAM_DATA()

    try:
        handle = kernel32.FindFirstStreamW(str(path), 0, ctypes.byref(data), 0)
        if handle == INVALID_HANDLE_VALUE:
            return []

        try:
            while True:
                name = data.cStreamName
                if name and name not in _ADS_IGNORE_STREAMS:
                    streams.append(name)
                if not kernel32.FindNextStreamW(handle, ctypes.byref(data)):
                    break
        finally:
            kernel32.FindClose(handle)
    except Exception:
        return []

    return streams


def has_significant_ads(path: Union[str, Path]) -> bool:
    """Return True if a file has non-default, non-Zone.Identifier streams.

    Useful for staging warnings: if the file has significant ADS and
    we're about to do a cross-device copy, the ADS will be lost.
    """
    return len(detect_alternate_streams(path)) > 0
