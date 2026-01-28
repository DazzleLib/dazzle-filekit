"""
Disk space checking utilities.

This module provides utilities for checking disk space availability
before performing file operations.
"""

import os
import shutil
import logging
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple, Union

# Set up module-level logger
logger = logging.getLogger(__name__)


class DiskUsage(NamedTuple):
    """Disk usage statistics."""
    total: int  # Total space in bytes
    used: int   # Used space in bytes
    free: int   # Free space in bytes

    @property
    def used_percent(self) -> float:
        """Percentage of disk used."""
        return (self.used / self.total * 100) if self.total > 0 else 0.0

    @property
    def free_percent(self) -> float:
        """Percentage of disk free."""
        return (self.free / self.total * 100) if self.total > 0 else 0.0


class InsufficientSpaceError(Exception):
    """Raised when destination lacks sufficient space for an operation."""

    def __init__(
        self,
        message: str,
        required: int,
        available: int,
        path: Optional[Union[str, Path]] = None
    ):
        """
        Initialize InsufficientSpaceError.

        Args:
            message: Human-readable error message
            required: Required space in bytes
            available: Available space in bytes
            path: Path that was checked (optional)
        """
        super().__init__(message)
        self.required = required
        self.available = available
        self.path = path
        self.shortfall = required - available


def get_disk_usage(path: Union[str, Path]) -> DiskUsage:
    """
    Get disk usage statistics for the drive/mount containing path.

    If the path doesn't exist, walks up the directory tree to find
    the nearest existing parent and reports its disk usage.

    Args:
        path: Path to check (file or directory)

    Returns:
        DiskUsage named tuple with total, used, and free space in bytes

    Raises:
        OSError: If no valid path can be found in the directory tree
    """
    path = Path(path)

    # Walk up to find existing path
    check_path = path
    while not check_path.exists():
        parent = check_path.parent
        if parent == check_path:
            # Reached root without finding existing path
            raise OSError(f"Cannot determine disk usage - no valid path in tree: {path}")
        check_path = parent

    usage = shutil.disk_usage(str(check_path))
    return DiskUsage(total=usage.total, used=usage.used, free=usage.free)


def check_disk_space(
    dest_path: Union[str, Path],
    required_bytes: int,
    safety_margin: float = 0.1,
    raise_on_insufficient: bool = False
) -> Tuple[bool, int, int, str]:
    """
    Check if destination has sufficient space for an operation.

    Args:
        dest_path: Destination path to check
        required_bytes: Number of bytes required
        safety_margin: Additional margin as fraction (0.1 = 10% extra)
        raise_on_insufficient: If True, raises InsufficientSpaceError instead of returning False

    Returns:
        Tuple of:
            - has_space: Boolean indicating if space is sufficient
            - required_with_margin: Required bytes including safety margin
            - available: Available bytes
            - message: Human-readable status message

    Raises:
        InsufficientSpaceError: If raise_on_insufficient=True and space is insufficient
    """
    try:
        usage = get_disk_usage(dest_path)
        available = usage.free

        # Calculate required space with margin
        margin_bytes = int(required_bytes * safety_margin)
        required_with_margin = required_bytes + margin_bytes

        if available >= required_with_margin:
            message = (
                f"Sufficient space: {_format_bytes(available)} available, "
                f"{_format_bytes(required_with_margin)} required "
                f"({_format_bytes(required_bytes)} + {safety_margin*100:.0f}% margin)"
            )
            return True, required_with_margin, available, message
        else:
            shortfall = required_with_margin - available
            message = (
                f"Insufficient space: {_format_bytes(available)} available, "
                f"{_format_bytes(required_with_margin)} required. "
                f"Need {_format_bytes(shortfall)} more."
            )
            if raise_on_insufficient:
                raise InsufficientSpaceError(
                    message=message,
                    required=required_with_margin,
                    available=available,
                    path=dest_path
                )
            return False, required_with_margin, available, message

    except OSError as e:
        message = f"Cannot check disk space: {e}"
        logger.error(message)
        if raise_on_insufficient:
            raise
        return False, required_bytes, 0, message


def calculate_total_size(
    paths: List[Union[str, Path]],
    follow_symlinks: bool = True
) -> int:
    """
    Calculate total size of files in the list.

    For directories, calculates the total size of all files within.

    Args:
        paths: List of file or directory paths
        follow_symlinks: Whether to follow symbolic links

    Returns:
        Total size in bytes
    """
    total = 0

    for path in paths:
        path = Path(path)

        if not path.exists():
            logger.warning(f"Path does not exist, skipping: {path}")
            continue

        if path.is_file():
            try:
                if follow_symlinks or not path.is_symlink():
                    total += path.stat().st_size
            except OSError as e:
                logger.warning(f"Cannot get size of {path}: {e}")
        elif path.is_dir():
            # Recursively calculate directory size
            for root, dirs, files in os.walk(str(path), followlinks=follow_symlinks):
                for file in files:
                    file_path = Path(root) / file
                    try:
                        if follow_symlinks or not file_path.is_symlink():
                            total += file_path.stat().st_size
                    except OSError as e:
                        logger.warning(f"Cannot get size of {file_path}: {e}")

    return total


def ensure_disk_space(
    dest_path: Union[str, Path],
    source_paths: List[Union[str, Path]],
    safety_margin: float = 0.1
) -> Tuple[bool, str]:
    """
    Ensure destination has enough space for source files.

    Convenience function that combines calculate_total_size and check_disk_space.

    Args:
        dest_path: Destination path
        source_paths: List of source file/directory paths
        safety_margin: Additional margin as fraction (0.1 = 10% extra)

    Returns:
        Tuple of (has_space, message)
    """
    total_size = calculate_total_size(source_paths)
    has_space, _, _, message = check_disk_space(dest_path, total_size, safety_margin)
    return has_space, message


def _format_bytes(size: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if abs(size) < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} EB"
