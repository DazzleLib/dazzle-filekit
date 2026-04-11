"""
Path handling and normalization utilities.

This module provides functions for path manipulation, normalization, and transformation
across different platforms, focusing on preserving path information when copying files.
"""

import os
import sys
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple, Any

# Set up module-level logger
logger = logging.getLogger(__name__)


# MSYS-style path pattern: /c/..., /c/, /c, or /d/... etc.
# Trailing slash and subpath are optional; bare /c matches.
_MSYS_DRIVE_RE = re.compile(r"^/([a-zA-Z])(/.*)?$")
# WSL mount pattern: /mnt/c/..., /mnt/c/, /mnt/c, etc.
_WSL_MNT_RE = re.compile(r"^/mnt/([a-zA-Z])(/.*)?$")
# Windows drive-letter pattern: C:\..., C:/..., c:..., etc.
_WIN_DRIVE_RE = re.compile(r"^([a-zA-Z]):[\\/](.*)$")


def _prepare_path_format(path_str: str) -> str:
    r"""Shared format-layer conversions for all path normalizers.

    Handles "portable path format" concerns that are the same regardless
    of whether the caller wants link-following or link-safe behavior:

      - whitespace trimming
      - tilde expansion (``~/foo``, ``~user/foo``)
      - env var expansion (``%USERPROFILE%``, ``$HOME``, ``${HOME}``)
      - Platform-direction drive conversion (bidirectional):
          * On Windows: ``/mnt/c/...`` or ``/c/...`` -> ``C:\...``
          * On Unix:    ``C:\...`` or ``C:/...`` -> ``/c/...``
      - forward slash -> OS-native separator
      - ``\\?\`` extended-length prefix strip (Windows only)

    Deliberately does NOT:

      - collapse . or .. segments (caller's choice -- lexical vs POSIX)
      - absolutize a relative path
      - follow symlinks
      - do filesystem I/O

    The drive-conversion direction is **platform-aware**: the function
    converts towards the current OS's native format. On Linux, a path
    like ``/c/Users/foo`` is a plain absolute Linux path and is LEFT
    ALONE (it is not interpreted as MSYS drive ``C:``). On Windows, the
    same input is converted to ``C:\Users\foo``.

    This is the single source of truth for "what counts as a portable
    path format" in filekit. Both ``normalize_path`` (link-following)
    and ``normalize_path_no_resolve`` (link-safe) layer on top of it.
    """
    path_str = path_str.strip()

    # Expand ~ first (handled by os.path.expanduser which is platform-aware)
    path_str = os.path.expanduser(path_str)

    # Expand env vars: %VAR% and $VAR / ${VAR}. On Windows, expandvars
    # understands both styles; on Unix, only $VAR / ${VAR}. Unknown vars
    # are left as literals, which is the same behavior fixpath relies on.
    path_str = os.path.expandvars(path_str)

    if sys.platform == "win32":
        # On Windows, normalize toward the native C:\ form.

        # WSL /mnt/c/... -> C:/... (must check BEFORE MSYS since
        # /mnt/c also partially matches single-letter patterns).
        #
        # A bare /mnt/c (no subpath) maps to drive root "C:/", not
        # "C:". Bare "C:" is NOT absolute on Windows (os.path.isabs
        # returns False) because it means "drive-relative", so we
        # produce "C:/" to get the drive root.
        m = _WSL_MNT_RE.match(path_str)
        if m:
            drive = m.group(1).upper()
            rest = m.group(2) or "/"
            path_str = drive + ":" + rest

        # MSYS /c/... -> C:/...
        m = _MSYS_DRIVE_RE.match(path_str)
        if m:
            drive = m.group(1).upper()
            rest = m.group(2) or "/"
            path_str = drive + ":" + rest

        # Normalize slashes to OS native
        path_str = path_str.replace("/", os.sep)

        # Strip extended-length prefix \\?\
        if path_str.startswith("\\\\?\\"):
            path_str = path_str[4:]
    else:
        # On Unix (Linux/macOS), normalize toward /c/ style.
        #
        # A Windows-style path like C:\Users\foo or C:/Users/foo gets
        # rewritten to /c/Users/foo so downstream code on Unix can
        # handle it. This is the counterpart to the MSYS conversion
        # above -- it only runs on Unix so that a legitimate Linux
        # path like /c/Users/foo stays untouched.
        m = _WIN_DRIVE_RE.match(path_str)
        if m:
            drive = m.group(1).lower()
            rest = m.group(2).replace("\\", "/")
            path_str = f"/{drive}/{rest}"
        else:
            # No drive letter -- just convert backslashes to forward slashes
            # in case a caller passed a mixed-separator path.
            path_str = path_str.replace("\\", "/")

    return path_str


def normalize_cross_platform_path(
    path: Union[str, Path],
    *,
    resolve: bool = False,
) -> Path:
    r"""Canonical path normalizer. Handles portable path formats across platforms.

    **This is the preferred path-normalization entry point in filekit.**
    ``normalize_path()`` and ``normalize_path_no_resolve()`` are thin
    backwards-compatibility wrappers around this function.

    Applies all portable-format conversions via ``_prepare_path_format``:

        /c/Users/foo         ->  C:\Users\foo       (MSYS/Git Bash style)
        /mnt/c/Users/foo     ->  C:\Users\foo       (WSL style)
        c:/Users/foo         ->  C:\Users\foo       (forward-slash Windows)
        ~/foo                ->  C:\Users\Me\foo    (tilde expansion)
        %USERPROFILE%/foo    ->  C:\Users\Me\foo    (env var, Windows)
        $HOME/foo            ->  /home/me/foo       (env var, Unix)
        ./relative           ->  <cwd>/relative     (relative to cwd)
        \\?\C:\...           ->  C:\...             (extended-length prefix)

    Then, based on ``resolve``:

      - ``resolve=False`` (default): collapses ``.`` and ``..`` LEXICALLY
        via ``os.path.normpath`` (does not follow symlinks), and
        absolutizes via cwd join. Preserves the literal link path.

      - ``resolve=True``: calls ``Path.resolve()`` which follows symlinks
        and junctions to their target (POSIX ``realpath`` semantics).
        Falls back to ``.absolute()`` for paths that don't exist.

    Args:
        path: The path to normalize.
        resolve: If True, follow symlinks. If False (default), preserve
            the literal link path and use lexical ``..`` collapsing.
            This is a keyword-only argument.

    Returns:
        The normalized path as a Path object.

    Examples:
        # Link-safe (default) -- preserves a symlink's literal path
        normalize_cross_platform_path("/mnt/c/code/my-link")
        # -> Path("C:/code/my-link")

        # Link-following -- follows a symlink to its target
        normalize_cross_platform_path("/mnt/c/code/my-link", resolve=True)
        # -> Path("C:/code/actual-target")
    """
    path_str = _prepare_path_format(str(path))

    if resolve:
        path_obj = Path(path_str)
        # Absolutize before resolve() to work around a Python 3.9 quirk on
        # Windows where ``Path('./a/b').resolve()`` returns a relative path
        # for nonexistent inputs instead of prepending cwd. On Python 3.10+
        # this is a no-op (resolve() handles the absolutization itself).
        if not path_obj.is_absolute():
            path_obj = path_obj.absolute()
        try:
            # Use Path.resolve() to follow symlinks/junctions (POSIX realpath).
            return path_obj.resolve()
        except (OSError, RuntimeError):
            # Fall back to the absolute (pre-resolve) form if resolve() fails.
            return path_obj

    # Link-safe: lexical normpath + cwd-based absolutize.
    # We use os.path.normpath rather than os.path.abspath here because on
    # Windows, abspath calls GetFullPathName which can resolve links, which
    # would destroy the link/target distinction.
    path_str = os.path.normpath(path_str)
    if not os.path.isabs(path_str):
        path_str = os.path.normpath(os.path.join(os.getcwd(), path_str))

    return Path(path_str)


def normalize_path(path: Union[str, Path]) -> Path:
    """Normalize a path, FOLLOWING symlinks.

    Thin wrapper for ``normalize_cross_platform_path(path, resolve=True)``.
    Kept for API stability -- referenced by README examples and used by
    ``dazzlecmd/projects/core/links/links.py``. The preferred entry point
    for new code is ``normalize_cross_platform_path(path, resolve=True)``.

    Args:
        path: The path to normalize

    Returns:
        The normalized, symlink-followed path as a Path object.
    """
    return normalize_cross_platform_path(path, resolve=True)


def normalize_path_no_resolve(path: Union[str, Path]) -> Path:
    """Normalize a path WITHOUT resolving symlinks or junctions.

    Thin wrapper for ``normalize_cross_platform_path(path, resolve=False)``.
    Kept for API stability -- used by
    ``dazzlecmd/projects/core/safedel/_classifier.py``. The preferred
    entry point for new code is ``normalize_cross_platform_path(path)``
    (the default ``resolve=False`` already does link-safe normalization).

    Args:
        path: The path to normalize

    Returns:
        The normalized path as a Path object, with the literal link
        path preserved (not its target).
    """
    return normalize_cross_platform_path(path, resolve=False)


def is_same_file(path1: Union[str, Path], path2: Union[str, Path]) -> bool:
    """
    Check if two paths refer to the same file or directory.
    
    This is more reliable than simple string comparison as it handles
    different path representations that point to the same file.
    
    Args:
        path1: First path
        path2: Second path
        
    Returns:
        True if paths refer to the same file, False otherwise
    """
    try:
        # Normalize paths
        norm_path1 = normalize_path(path1)
        norm_path2 = normalize_path(path2)
        
        # Check if normalized paths are the same
        if norm_path1 == norm_path2:
            return True
        
        # Check if both paths exist
        if norm_path1.exists() and norm_path2.exists():
            try:
                # Use samefile() on POSIX systems
                return os.path.samefile(norm_path1, norm_path2)
            except (OSError, AttributeError):
                # Fall back to string comparison on systems without samefile
                return str(norm_path1) == str(norm_path2)
    except Exception as e:
        logger.debug(f"Error comparing paths {path1} and {path2}: {e}")
        
    # Default to False if comparison fails
    return False


def split_drive_letter(path: Union[str, Path]) -> Tuple[str, str]:
    """
    Split a path into drive letter and path components.
    
    This is primarily useful on Windows where paths have drive letters.
    
    Args:
        path: The path to split
        
    Returns:
        Tuple of (drive_letter, path_without_drive)
    """
    path_str = str(path)
    
    # Use os.path.splitdrive for platform-specific behavior
    drive, rest = os.path.splitdrive(path_str)
    
    return drive, rest


def is_unc_path(path: Union[str, Path]) -> bool:
    """
    Check if a path is a UNC (Universal Naming Convention) path.
    
    UNC paths start with \\\\ on Windows, representing network resources.
    
    Args:
        path: The path to check
        
    Returns:
        True if the path is a UNC path, False otherwise
    """
    path_str = str(path)
    
    # UNC paths start with \\ on Windows
    if sys.platform == 'win32':
        return path_str.startswith('\\\\')
    
    # UNC paths don't exist on non-Windows systems
    return False


def get_relative_path(
    path: Union[str, Path], 
    base_path: Union[str, Path], 
    allow_cross_drive: bool = True
) -> Optional[Path]:
    """
    Get the relative path from base_path to path.
    
    Args:
        path: Target path
        base_path: Base reference path
        allow_cross_drive: Whether to allow paths on different drives
            
    Returns:
        Relative path, or None if cross-drive and not allowed
    """
    path_obj = Path(path)
    base_path_obj = Path(base_path)
    
    # Normalize paths
    path_norm = normalize_path(path_obj)
    base_norm = normalize_path(base_path_obj)
    
    # Check for cross-drive paths on Windows
    if sys.platform == 'win32':
        path_drive = split_drive_letter(path_norm)[0]
        base_drive = split_drive_letter(base_norm)[0]
        
        if path_drive.lower() != base_drive.lower() and not allow_cross_drive:
            logger.warning(f"Cross-drive path not allowed: {path_norm} relative to {base_norm}")
            return None
    
    # Calculate relative path
    try:
        relative = path_norm.relative_to(base_norm)
        return relative
    except ValueError:
        # Path is not relative to base_path
        logger.debug(f"Path {path_norm} is not relative to {base_norm}")
        return None


def create_dest_path(
    source_path: Union[str, Path],
    source_base: Union[str, Path],
    dest_base: Union[str, Path],
    path_style: str = 'relative',
    include_base: bool = False
) -> Path:
    """
    Create a destination path based on the source path and selected style.
    
    Args:
        source_path: Source file path
        source_base: Base directory for source files
        dest_base: Destination base directory
        path_style: Path style ('relative', 'absolute', 'flat')
        include_base: Whether to include the source_base name in the path
            
    Returns:
        Destination path as a Path object
    """
    source_path = normalize_path(source_path)
    source_base = normalize_path(source_base)
    dest_base = normalize_path(dest_base)
    
    # Style-specific path construction
    if path_style == 'flat':
        # Just use the filename in the destination directory
        return dest_base / source_path.name
    
    elif path_style == 'absolute':
        # Preserve the absolute path structure
        if sys.platform == 'win32':
            # On Windows, replace drive letter with a directory
            drive, rest = split_drive_letter(source_path)
            drive = drive.rstrip(':')  # Remove colon from drive letter
            
            # Use the drive letter as a directory name
            return dest_base / drive / rest.lstrip('/\\')
        else:
            # On Unix-like systems, remove leading slash
            path_str = str(source_path)
            return dest_base / path_str.lstrip('/')
    
    elif path_style == 'relative':
        # Get relative path from source_base to source_path
        rel_path = get_relative_path(source_path, source_base)
        
        if rel_path is None:
            # Fall back to absolute if not relative
            logger.warning(f"Path {source_path} is not relative to {source_base}, using absolute style")
            return create_dest_path(source_path, source_base, dest_base, 'absolute', include_base)
        
        if include_base:
            # Include base directory name
            base_name = source_base.name
            return dest_base / base_name / rel_path
        else:
            # Just use the relative path
            return dest_base / rel_path
    
    else:
        # Unknown style, fall back to relative
        logger.warning(f"Unknown path style: {path_style}, falling back to relative")
        return create_dest_path(source_path, source_base, dest_base, 'relative', include_base)


def find_files(
    search_paths: List[Union[str, Path]],
    patterns: Optional[List[str]] = None,
    recursive: bool = True,
    exclude_patterns: Optional[List[str]] = None
) -> List[Path]:
    """
    Find files in search paths matching the given patterns.
    
    Args:
        search_paths: List of directories to search
        patterns: List of glob patterns to match (e.g., ["*.txt", "*.csv"])
        recursive: Whether to search recursively
        exclude_patterns: List of glob patterns to exclude
            
    Returns:
        List of matching file paths
    """
    patterns = patterns or ['*']  # Default to all files
    exclude_patterns = exclude_patterns or []
    
    found_files = []
    
    for search_path in search_paths:
        path_obj = Path(search_path)
        
        if not path_obj.exists():
            logger.warning(f"Search path does not exist: {search_path}")
            continue
        
        if path_obj.is_file():
            # If the search path is a file, check if it matches any pattern
            if _matches_any_pattern(path_obj, patterns) and not _matches_any_pattern(path_obj, exclude_patterns):
                found_files.append(path_obj)
            continue
        
        # Walk directory
        for pattern in patterns:
            if recursive:
                # Use rglob for recursive glob
                matches = path_obj.rglob(pattern)
            else:
                # Use glob for non-recursive
                matches = path_obj.glob(pattern)
                
            # Filter files and apply exclusions
            for match in matches:
                if match.is_file() and not _matches_any_pattern(match, exclude_patterns):
                    found_files.append(match)
    
    return found_files


def _matches_any_pattern(path: Path, patterns: List[str]) -> bool:
    """
    Check if a path matches any of the given glob patterns.
    
    Args:
        path: Path to check
        patterns: List of glob patterns
            
    Returns:
        True if path matches any pattern, False otherwise
    """
    from fnmatch import fnmatch
    
    for pattern in patterns:
        if fnmatch(path.name, pattern):
            return True
    
    return False


def collect_files_from_include_file(include_file: Union[str, Path]) -> List[Path]:
    """
    Collect a list of files from an include file.
    
    The include file should contain one file path per line.
    Blank lines and lines starting with # are ignored.
    
    Args:
        include_file: Path to the include file
            
    Returns:
        List of file paths
    """
    include_path = Path(include_file)
    
    if not include_path.exists():
        logger.error(f"Include file does not exist: {include_file}")
        return []
    
    collected_files = []
    
    try:
        with open(include_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Expand user home directory (e.g., ~/)
                expanded_path = os.path.expanduser(line)
                
                # Convert to Path object
                path_obj = Path(expanded_path)
                
                if path_obj.exists():
                    collected_files.append(path_obj)
                else:
                    logger.warning(f"File from include list does not exist: {line}")
    
    except Exception as e:
        logger.error(f"Error reading include file {include_file}: {e}")
    
    return collected_files


def find_regex_files(
    search_paths: List[Union[str, Path]],
    regex_patterns: List[str],
    recursive: bool = True,
    exclude_patterns: Optional[List[str]] = None
) -> List[Path]:
    """
    Find files in search paths matching the given regex patterns.
    
    Args:
        search_paths: List of directories to search
        regex_patterns: List of regex patterns to match
        recursive: Whether to search recursively
        exclude_patterns: List of glob patterns to exclude
            
    Returns:
        List of matching file paths
    """
    exclude_patterns = exclude_patterns or []
    compiled_patterns = [re.compile(pattern) for pattern in regex_patterns]
    
    found_files = []
    
    for search_path in search_paths:
        path_obj = Path(search_path)
        
        if not path_obj.exists():
            logger.warning(f"Search path does not exist: {search_path}")
            continue
        
        if path_obj.is_file():
            # If the search path is a file, check if it matches any pattern
            if _matches_any_regex(path_obj, compiled_patterns) and not _matches_any_pattern(path_obj, exclude_patterns):
                found_files.append(path_obj)
            continue
        
        # Walk directory
        if recursive:
            for root, dirs, files in os.walk(path_obj):
                for file in files:
                    file_path = Path(root) / file
                    if _matches_any_regex(file_path, compiled_patterns) and not _matches_any_pattern(file_path, exclude_patterns):
                        found_files.append(file_path)
        else:
            # Non-recursive, only check immediate files
            for file in path_obj.glob('*'):
                if file.is_file() and _matches_any_regex(file, compiled_patterns) and not _matches_any_pattern(file, exclude_patterns):
                    found_files.append(file)
    
    return found_files


def _matches_any_regex(path: Path, patterns: List[re.Pattern]) -> bool:
    """
    Check if a path matches any of the given regex patterns.
    
    Args:
        path: Path to check
        patterns: List of compiled regex patterns
            
    Returns:
        True if path matches any pattern, False otherwise
    """
    path_str = str(path)
    
    for pattern in patterns:
        if pattern.search(path_str):
            return True
    
    return False


def create_parent_dirs(path: Union[str, Path]) -> bool:
    """
    Create parent directories for a path if they don't exist.
    
    Args:
        path: The path whose parents should be created
            
    Returns:
        True if successful or directories already exist, False on error
    """
    parent = Path(path).parent
    
    try:
        parent.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Error creating parent directories for {path}: {e}")
        return False


def ensure_unique_path(path: Union[str, Path]) -> Path:
    """
    Ensure a path is unique by appending a number if necessary.
    
    Args:
        path: Original path
            
    Returns:
        Unique path that doesn't exist yet
    """
    original_path = Path(path)
    
    if not original_path.exists():
        return original_path
    
    counter = 1
    stem = original_path.stem
    suffix = original_path.suffix
    parent = original_path.parent
    
    while True:
        new_path = parent / f"{stem}_{counter}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1


def get_path_type(path: Union[str, Path]) -> str:
    """
    Get the type of a path.
    
    Args:
        path: Path to check
            
    Returns:
        Path type: 'file', 'directory', 'symlink', 'socket', 'pipe', 'block_device', 
        'char_device', or 'unknown'
    """
    path_obj = Path(path)
    
    if not path_obj.exists():
        return 'nonexistent'
    
    if path_obj.is_symlink():
        return 'symlink'
    
    if path_obj.is_file():
        return 'file'
    
    if path_obj.is_dir():
        return 'directory'
    
    if path_obj.is_socket():
        return 'socket'
    
    if path_obj.is_fifo():
        return 'pipe'
    
    if path_obj.is_block_device():
        return 'block_device'
    
    if path_obj.is_char_device():
        return 'char_device'
    
    return 'unknown'
