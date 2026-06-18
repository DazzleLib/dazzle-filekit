"""
Path validation utilities for dazzle_filekit.

This module provides functions for validating path strings and objects,
ensuring they meet the requirements for various file operations.
"""

import os
import sys
import re
import logging
from pathlib import Path
from typing import Union, List, Set, Optional

# Set up module-level logger
logger = logging.getLogger(__name__)

# Platform detection
IS_WINDOWS = sys.platform == 'win32'

# Invalid characters for various platforms
WINDOWS_INVALID_CHARS = set('<>:"/\\|?*')
UNIX_INVALID_CHARS = set('')  # Unix allows almost any character

# Invalid names on Windows (case-insensitive)
WINDOWS_INVALID_NAMES = {
    'con', 'prn', 'aux', 'nul',
    'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
    'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9'
}

def is_valid_path(path: Union[str, Path]) -> bool:
    """
    Check if a path is valid on the current platform.
    
    Args:
        path: Path to validate
        
    Returns:
        True if path is valid, False otherwise
    """
    path_str = str(path)
    
    # Check for empty path
    if not path_str:
        return False
    
    # Platform-specific checks
    if IS_WINDOWS:
        return _is_valid_windows_path(path_str)
    else:
        return _is_valid_unix_path(path_str)

def _is_valid_windows_path(path: str) -> bool:
    """
    Check if a path is valid on Windows.
    
    Args:
        path: Path string to validate
        
    Returns:
        True if path is valid, False otherwise
    """
    # Check for total path length limit (260 characters)
    if len(path) > 260:
        # Check if path is in long path format (\\?\)
        if not path.startswith('\\\\?\\'):
            logger.debug(f"Path exceeds Windows 260 character limit: {path}")
            return False
    
    # Check for invalid characters in path
    for part in path.split('\\'):
        # Skip drive letter (e.g., "C:")
        if len(part) == 2 and part[1] == ':':
            continue
            
        # Check for invalid characters
        if any(c in WINDOWS_INVALID_CHARS for c in part):
            logger.debug(f"Path contains invalid characters: {path}")
            return False
        
        # Check for reserved names
        name = part.split('.')[0].lower()
        if name in WINDOWS_INVALID_NAMES:
            logger.debug(f"Path contains reserved name: {path}")
            return False
        
        # Check for leading/trailing spaces or periods
        if part.strip() != part or part.rstrip('.') != part:
            logger.debug(f"Path contains invalid leading/trailing spaces or periods: {path}")
            return False
    
    return True

def _is_valid_unix_path(path: str) -> bool:
    """
    Check if a path is valid on Unix-like systems.
    
    Args:
        path: Path string to validate
        
    Returns:
        True if path is valid, False otherwise
    """
    # Unix allows almost any character in paths
    # Just ensure it's not empty and doesn't have NULL characters
    return bool(path) and '\0' not in path

def is_safe_path(path: Union[str, Path], base_dir: Union[str, Path]) -> bool:
    """
    Check if a path is safe (doesn't escape outside its base directory).
    
    Args:
        path: Path to validate
        base_dir: Base directory that the path should be under
        
    Returns:
        True if path is safe, False otherwise
    """
    # Resolve both paths
    try:
        path_obj = Path(path).resolve()
        base_dir_obj = Path(base_dir).resolve()
        
        # Check if the path is a descendant of the base directory
        return str(path_obj).startswith(str(base_dir_obj))
    except Exception as e:
        logger.debug(f"Error checking safe path: {e}")
        return False

def validate_path_chars(path: Union[str, Path]) -> List[str]:
    """
    Validate characters in a path and return any errors.
    
    Args:
        path: Path to validate
        
    Returns:
        List of error messages (empty if path is valid)
    """
    path_str = str(path)
    errors = []
    
    # Check for empty path
    if not path_str:
        errors.append("Path is empty")
        return errors
    
    # Platform-specific checks
    if IS_WINDOWS:
        # Check for invalid characters
        for char in WINDOWS_INVALID_CHARS:
            if char in path_str:
                errors.append(f"Invalid character '{char}' in path")
        
        # Check path length
        if len(path_str) > 260 and not path_str.startswith('\\\\?\\'):
            errors.append("Path exceeds 260 character limit")
        
        # Check for reserved names
        for part in path_str.split('\\'):
            # Skip drive letter (e.g., "C:")
            if len(part) == 2 and part[1] == ':':
                continue
                
            # Check for reserved names
            name = part.split('.')[0].lower()
            if name in WINDOWS_INVALID_NAMES:
                errors.append(f"Reserved name '{part}' in path")
            
            # Check for trailing spaces or periods
            if part.strip() != part:
                errors.append(f"Path component '{part}' has leading or trailing spaces")
            
            if part.rstrip('.') != part:
                errors.append(f"Path component '{part}' has trailing periods")
    else:
        # Unix-like systems
        if '\0' in path_str:
            errors.append("Path contains NULL character")
    
    return errors

def is_absolute_path(path: Union[str, Path]) -> bool:
    """
    Check if a path is absolute.
    
    Args:
        path: Path to check
        
    Returns:
        True if the path is absolute, False otherwise
    """
    return Path(path).is_absolute()

def is_relative_path(path: Union[str, Path]) -> bool:
    """
    Check if a path is relative.
    
    Args:
        path: Path to check
        
    Returns:
        True if the path is relative, False otherwise
    """
    return not Path(path).is_absolute()

def is_unc_path(path: Union[str, Path]) -> bool:
    """
    Check if a path is a UNC (Universal Naming Convention) path.
    
    Args:
        path: Path to check
        
    Returns:
        True if the path is a UNC path, False otherwise
    """
    path_str = str(path)
    
    # UNC paths start with \\ on Windows or // on other platforms
    if IS_WINDOWS:
        return path_str.startswith('\\\\')
    else:
        return path_str.startswith('//')

def is_hidden_path(path: Union[str, Path]) -> bool:
    """
    Check if a path is hidden.
    
    Args:
        path: Path to check
        
    Returns:
        True if the path is hidden, False otherwise
    """
    path_obj = Path(path)
    
    # Check if the path exists
    if not path_obj.exists():
        return False
    
    if IS_WINDOWS:
        try:
            import win32api
            import win32con
            attributes = win32api.GetFileAttributes(str(path_obj))
            return (attributes & win32con.FILE_ATTRIBUTE_HIDDEN) != 0
        except:
            # Fall back to checking filename
            name = path_obj.name
            return name.startswith('.') or name.endswith('.')
    else:
        # On Unix, files starting with a period are hidden
        return path_obj.name.startswith('.')

def is_symlink(path: Union[str, Path]) -> bool:
    """
    Check if a path is a symbolic link.
    
    Args:
        path: Path to check
        
    Returns:
        True if the path is a symbolic link, False otherwise
    """
    return Path(path).is_symlink()

def is_junction(path: Union[str, Path]) -> bool:
    """Check if a path is a Windows junction point (NOT a symlink).

    This is the distinction that matters for safe deletion and tree
    traversal: junctions and symlinks both have the reparse-point
    attribute set, but they have different reparse tags
    (``IO_REPARSE_TAG_MOUNT_POINT`` vs ``IO_REPARSE_TAG_SYMLINK``) and
    different cross-platform semantics.

    Implementation uses ``DeviceIoControl(FSCTL_GET_REPARSE_POINT)`` to
    read the reparse tag and check it's specifically
    ``IO_REPARSE_TAG_MOUNT_POINT``. This is the only reliable method.

    History: in filekit <= v0.2.3, this function referenced
    ``win32file.FILE_ATTRIBUTE_REPARSE_POINT`` (which doesn't exist --
    the constant lives in ``win32con``), and the bare ``except:`` clause
    silently returned False for everything, including real junctions.
    Additionally, even if the attribute check had worked, it would have
    misclassified directory symlinks as junctions since they share the
    same ``FILE_ATTRIBUTE_REPARSE_POINT`` flag. Fixed in v0.2.4 by
    porting the correct implementation from
    ``dazzlecmd/projects/core/links/links.py:_is_junction_win``.

    Args:
        path: Path to check

    Returns:
        True if the path is specifically a junction (mount-point reparse
        point), False otherwise. Returns False for symlinks, plain
        directories, files, and nonexistent paths.
    """
    if not IS_WINDOWS:
        return False

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32

        # Check reparse-point attribute first -- skip the expensive
        # DeviceIoControl call for non-reparse-point paths.
        FILE_ATTRIBUTE_REPARSE_POINT = 0x400
        attrs = kernel32.GetFileAttributesW(str(path))
        if attrs == -1 or not (attrs & FILE_ATTRIBUTE_REPARSE_POINT):
            return False

        # Open with FILE_FLAG_OPEN_REPARSE_POINT so we get the link itself,
        # not its target. FILE_FLAG_BACKUP_SEMANTICS is required for dirs.
        OPEN_EXISTING = 3
        FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
        FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
        FILE_SHARE_READ_WRITE_DELETE = 0x01 | 0x02 | 0x04

        handle = kernel32.CreateFileW(
            str(path), 0,
            FILE_SHARE_READ_WRITE_DELETE,
            None, OPEN_EXISTING,
            FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
        if handle == wintypes.HANDLE(-1).value:
            # Fallback: if the path is a reparse point but os.path.islink
            # returns False, it's probably a junction (not a symlink).
            return not os.path.islink(str(path))

        try:
            IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
            FSCTL_GET_REPARSE_POINT = 0x000900A8
            buf = ctypes.create_string_buffer(16384)
            bytes_returned = wintypes.DWORD(0)

            ok = kernel32.DeviceIoControl(
                handle, FSCTL_GET_REPARSE_POINT,
                None, 0, buf, 16384,
                ctypes.byref(bytes_returned), None,
            )
            if ok:
                # Reparse tag is the first 4 bytes of the REPARSE_DATA_BUFFER
                tag = int.from_bytes(buf[:4], byteorder="little")
                return tag == IO_REPARSE_TAG_MOUNT_POINT
            else:
                return not os.path.islink(str(path))
        finally:
            kernel32.CloseHandle(handle)
    except (OSError, AttributeError, ImportError) as e:
        logger.debug(f"is_junction({path}) failed: {e}")
        return False


def read_junction_target(path: Union[str, Path]) -> Optional[str]:
    """Return the target of a Windows junction, or None.

    Reads the junction's reparse point with
    ``DeviceIoControl(FSCTL_GET_REPARSE_POINT)`` and decodes the
    ``MountPointReparseBuffer`` PrintName (falling back to SubstituteName
    with its ``\\??\\`` prefix stripped). This is the clean, no-subprocess
    replacement for parsing ``cmd /c dir /al`` output.

    Returns None on non-Windows, for non-junctions, or on any error.
    """
    if not IS_WINDOWS:
        return None

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32

        OPEN_EXISTING = 3
        FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
        FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
        FILE_SHARE_READ_WRITE_DELETE = 0x01 | 0x02 | 0x04

        handle = kernel32.CreateFileW(
            str(path), 0,
            FILE_SHARE_READ_WRITE_DELETE,
            None, OPEN_EXISTING,
            FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
        if handle == wintypes.HANDLE(-1).value:
            return None

        try:
            IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
            FSCTL_GET_REPARSE_POINT = 0x000900A8
            buf = ctypes.create_string_buffer(16384)
            bytes_returned = wintypes.DWORD(0)

            ok = kernel32.DeviceIoControl(
                handle, FSCTL_GET_REPARSE_POINT,
                None, 0, buf, 16384,
                ctypes.byref(bytes_returned), None,
            )
            if not ok:
                return None

            raw = buf.raw
            tag = int.from_bytes(raw[:4], byteorder="little")
            if tag != IO_REPARSE_TAG_MOUNT_POINT:
                return None

            # MountPointReparseBuffer (after the 8-byte REPARSE_DATA_BUFFER
            # header): SubstituteNameOffset/Length, PrintNameOffset/Length
            # (each a little-endian WORD), then PathBuffer at offset 16.
            subst_off = int.from_bytes(raw[8:10], byteorder="little")
            subst_len = int.from_bytes(raw[10:12], byteorder="little")
            print_off = int.from_bytes(raw[12:14], byteorder="little")
            print_len = int.from_bytes(raw[14:16], byteorder="little")
            path_buffer = raw[16:]

            if print_len:
                target = path_buffer[print_off:print_off + print_len].decode("utf-16-le")
            else:
                target = path_buffer[subst_off:subst_off + subst_len].decode("utf-16-le")
                if target.startswith("\\??\\"):
                    target = target[4:]
            return target or None
        finally:
            kernel32.CloseHandle(handle)
    except (OSError, AttributeError, ImportError) as e:
        logger.debug(f"read_junction_target({path}) failed: {e}")
        return None
