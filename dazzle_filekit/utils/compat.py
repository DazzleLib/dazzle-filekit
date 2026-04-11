"""
Compatibility utilities for cross-platform operations.

This module provides utilities for handling platform-specific differences
and ensuring consistent behavior across different operating systems.
"""

import os
import sys
import platform
import logging
from pathlib import Path
from typing import Dict, Optional, Union

# Set up module-level logger
logger = logging.getLogger(__name__)

# Detect platform
PLATFORM = platform.system().lower()

def is_windows() -> bool:
    """
    Check if the current platform is Windows.
    
    Returns:
        bool: True if Windows, False otherwise
    """
    return PLATFORM == 'windows'

def is_unix() -> bool:
    """
    Check if the current platform is Unix-like (Linux, macOS, etc.).

    Returns:
        bool: True if Unix-like, False otherwise
    """
    return PLATFORM in ('linux', 'darwin', 'freebsd', 'openbsd', 'netbsd')


def is_wsl() -> bool:
    """Check if the current Python process is running inside WSL.

    Detection strategy:
      1. Check for ``WSL_DISTRO_NAME`` environment variable (set by WSL 2+)
      2. Fall back to scanning ``/proc/version`` for ``microsoft`` or ``wsl``
      3. Return False on non-Linux platforms

    Returns:
        True if running inside WSL, False otherwise.

    Examples:
        >>> if is_wsl():
        ...     print("Running in WSL -- /mnt/c/ is DrvFs")
    """
    if PLATFORM != "linux":
        return False

    # WSL 2+ sets this env var
    if os.environ.get("WSL_DISTRO_NAME"):
        return True

    # Fallback: scan /proc/version
    try:
        with open("/proc/version", "r") as f:
            version_str = f.read().lower()
        return "microsoft" in version_str or "wsl" in version_str
    except OSError:
        return False

def is_admin() -> bool:
    """
    Check if the current process has administrative privileges on Windows.
    
    Returns:
        bool: True if admin, False otherwise
    """
    if not is_windows():
        return False
        
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        try:
            import win32security
            return win32security.IsUserAnAdmin()
        except:
            logger.debug("Cannot check admin status on Windows - missing required libraries")
            return False

def is_root() -> bool:
    """
    Check if the current process has root privileges on Unix-like systems.
    
    Returns:
        bool: True if root, False otherwise
    """
    if not is_unix():
        return False
        
    try:
        return os.geteuid() == 0
    except AttributeError:
        logger.debug("Cannot check root status - os.geteuid() not available")
        return False

def fix_path_separators(path: str) -> str:
    """
    Fix path separators to match the current platform.
    
    Args:
        path: Path string to fix
        
    Returns:
        Path string with corrected separators
    """
    if is_windows():
        # Convert forward slashes to backslashes on Windows
        return path.replace('/', '\\')
    else:
        # Convert backslashes to forward slashes on Unix
        return path.replace('\\', '/')

def fix_path_case(path: Union[str, Path]) -> str:
    """
    Fix path case for case-sensitive file systems.
    
    This is mostly a no-op except on Windows where it can resolve
    the actual case of files.
    
    Args:
        path: Path to fix
        
    Returns:
        Path with correct case
    """
    path_obj = Path(path)
    
    if not path_obj.exists():
        # Can't fix case for non-existent paths
        return str(path)
    
    if is_windows():
        try:
            # On Windows, try to get the actual case from the file system
            # This is a no-op on case-sensitive file systems
            import win32file
            win_path = str(path_obj.resolve())
            short_path = win32file.GetShortPathName(win_path)
            return win32file.GetLongPathName(short_path)
        except:
            # Fall back to resolving the path
            return str(path_obj.resolve())
    else:
        # On Unix, just resolve the path
        return str(path_obj.resolve())

def get_system_encoding() -> str:
    """
    Get the default encoding for the current system.
    
    Returns:
        String representing the system encoding
    """
    # Default system encoding
    encoding = sys.getfilesystemencoding()
    
    # Fall back to utf-8 if no encoding is detected
    if not encoding:
        if is_windows():
            encoding = 'cp1252'  # Windows default
        else:
            encoding = 'utf-8'   # Unix default
    
    return encoding

def get_system_temp_dir() -> Path:
    """
    Get the system temporary directory in a cross-platform way.
    
    Returns:
        Path to the system temporary directory
    """
    import tempfile
    return Path(tempfile.gettempdir())

def get_home_dir() -> Path:
    """
    Get the user's home directory in a cross-platform way.
    
    Returns:
        Path to the user's home directory
    """
    return Path.home()

def get_app_data_dir(app_name: str) -> Path:
    """
    Get the application data directory in a cross-platform way.
    
    Args:
        app_name: Name of the application
        
    Returns:
        Path to the application data directory
    """
    if is_windows():
        # Windows: %APPDATA%\app_name
        base_dir = os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))
        return Path(base_dir) / app_name
    elif platform.system() == 'Darwin':
        # macOS: ~/Library/Application Support/app_name
        return Path.home() / 'Library' / 'Application Support' / app_name
    else:
        # Linux/Unix: ~/.config/app_name
        xdg_config_home = os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))
        return Path(xdg_config_home) / app_name

# v0.2.4: normalize_cross_platform_path moved to dazzle_filekit.paths as the
# canonical path normalizer (now with an optional ``resolve=`` kwarg). The
# re-export below keeps existing imports working:
#
#     from dazzle_filekit.utils.compat import normalize_cross_platform_path
#
# Prefer the direct import from dazzle_filekit for new code:
#
#     from dazzle_filekit import normalize_cross_platform_path
from ..paths import normalize_cross_platform_path  # noqa: F401


def resolve_cross_platform_path(path: Union[str, Path]) -> Path:
    """
    Resolve a path by normalizing it and probing alternate platform formats.

    First normalizes using normalize_cross_platform_path(). If the result
    doesn't exist, tries alternate platform representations:

    On Windows:
      /mnt/c/Users/...           -> C:\\Users\\...         (WSL mount)
      /c/Users/...               -> C:\\Users\\...         (MSYS/Git Bash)
      .../mnt/c/Users/...        -> C:\\Users\\...         (MSYS-mangled WSL)

    On Linux/macOS:
      C:\\Users\\...             -> /mnt/c/Users/...       (WSL)
      C:\\Users\\...             -> /c/Users/...           (MSYS)

    Returns the first existing candidate, or the normalized form if none exist.

    Args:
        path: Path string in any supported format

    Returns:
        Path object for the best match found

    Examples:
        # On Windows, if C:\\Users\\foo\\file.txt exists:
        resolve_cross_platform_path("/mnt/c/Users/foo/file.txt")
        # -> Path("C:/Users/foo/file.txt")
    """
    import re

    normalized = normalize_cross_platform_path(path)

    if normalized.exists():
        return normalized

    path_str = str(normalized)

    if is_windows():
        # Try WSL /mnt/c/ -> C:\ (in case normalization didn't catch it)
        wsl_match = re.match(r'^/mnt/([a-zA-Z])(/.*)?$', str(path))
        if wsl_match:
            drive = wsl_match.group(1).upper()
            rest = (wsl_match.group(2) or '').replace('/', '\\')
            candidate = Path(f"{drive}:{rest}")
            if candidate.exists():
                return candidate

        # Check for MSYS-mangled WSL paths
        # Git Bash converts /mnt/c/... to C:\Program Files\Git\mnt\c\...
        mangled = re.search(r'[/\\]mnt[/\\]([a-zA-Z])[/\\](.*)', path_str)
        if mangled:
            drive = mangled.group(1).upper()
            rest = mangled.group(2).replace('/', '\\')
            candidate = Path(f"{drive}:\\{rest}")
            if candidate.exists():
                return candidate

    else:
        # On Linux/macOS: try Windows path -> WSL or MSYS format
        win_match = re.match(r'^([a-zA-Z]):[/\\](.*)', path_str)
        if win_match:
            drive = win_match.group(1).lower()
            rest = win_match.group(2).replace('\\', '/')

            # Try WSL mount
            candidate = Path(f"/mnt/{drive}/{rest}")
            if candidate.exists():
                return candidate

            # Try MSYS/Git Bash style
            candidate = Path(f"/{drive}/{rest}")
            if candidate.exists():
                return candidate

    return normalized


def path_exists_cross_platform(path: Union[str, Path]) -> bool:
    """
    Check if a path exists, handling cross-platform path formats.

    This is useful when receiving paths from external sources (like Claude Code)
    that may be in a different format than the current platform expects.

    Uses resolve_cross_platform_path() to try alternate platform formats
    if the normalized path doesn't exist.

    Args:
        path: Path string in any supported format

    Returns:
        True if the path exists, False otherwise
    """
    try:
        resolved = resolve_cross_platform_path(path)
        return resolved.exists()
    except Exception:
        return False


def get_drive_mappings() -> Dict[str, str]:
    """
    Get mappings of network drives on Windows.
    
    Returns:
        Dictionary mapping drive letters to UNC paths
    """
    if not is_windows():
        return {}
    
    mappings = {}
    
    try:
        import win32wnet
        for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            try:
                drive = f"{letter}:"
                unc = win32wnet.WNetGetUniversalName(drive, 1)
                mappings[drive] = unc
            except:
                # Not a mapped drive
                pass
    except ImportError:
        logger.debug("Cannot get drive mappings - win32wnet module not available")
    
    return mappings
