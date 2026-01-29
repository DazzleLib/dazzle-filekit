"""
File operations for copying, moving and verifying files.

This module provides functions for file operations with attribute preservation
across different platforms, including timestamps, permissions, and other metadata.
"""

import os
import sys
import stat
import shutil
import errno
import logging
import datetime
import time
import platform
from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple, Any, Set, Callable

# Set up module-level logger
logger = logging.getLogger(__name__)


def copy_file(
    source: Union[str, Path], 
    destination: Union[str, Path],
    preserve_attrs: bool = True,
    overwrite: bool = False
) -> bool:
    """
    Copy a file with attribute preservation.

    Args:
        source: Source file path
        destination: Destination file path
        preserve_attrs: Whether to preserve file attributes
        overwrite: Whether to overwrite the destination if it exists

    Returns:
        True if successful, False otherwise
    """
    source_path = Path(source)
    dest_path = Path(destination)

    # Check if source exists
    if not source_path.exists():
        logger.error(f"Source file does not exist: {source_path}")
        return False

    # Check if source is a file
    if not source_path.is_file():
        logger.error(f"Source is not a file: {source_path}")
        return False

    # Check if destination exists
    if dest_path.exists() and not overwrite:
        logger.warning(f"Destination file already exists and overwrite is disabled: {dest_path}")
        return False

    try:
        # Create parent directories if needed
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Collect file metadata before copying if attribute preservation is enabled
        if preserve_attrs:
            metadata = collect_file_metadata(source_path)

        # Copy the file based on platform
        if platform.system() == 'Windows' and preserve_attrs:
            # On Windows, try using robocopy for better attribute preservation
            success = _copy_with_robocopy(source_path, dest_path)
            if not success:
                # Fall back to shutil.copy2
                shutil.copy2(source_path, dest_path)
        else:
            # Use shutil.copy2 which preserves metadata on Unix
            shutil.copy2(source_path, dest_path)

        # Apply metadata to destination if preservation is enabled
        if preserve_attrs:
            apply_file_metadata(dest_path, metadata)

        logger.debug(f"Copied {source_path} to {dest_path}")
        return True

    except Exception as e:
        logger.error(f"Error copying {source_path} to {dest_path}: {e}")
        return False


def move_file(
    source: Union[str, Path], 
    destination: Union[str, Path],
    preserve_attrs: bool = True,
    overwrite: bool = False
) -> bool:
    """
    Move a file with attribute preservation.

    Args:
        source: Source file path
        destination: Destination file path
        preserve_attrs: Whether to preserve file attributes
        overwrite: Whether to overwrite the destination if it exists

    Returns:
        True if successful, False otherwise
    """
    source_path = Path(source)
    dest_path = Path(destination)

    # Check if source exists
    if not source_path.exists():
        logger.error(f"Source file does not exist: {source_path}")
        return False

    # Check if source is a file
    if not source_path.is_file():
        logger.error(f"Source is not a file: {source_path}")
        return False

    # Check if destination exists
    if dest_path.exists() and not overwrite:
        logger.warning(f"Destination file already exists and overwrite is disabled: {dest_path}")
        return False

    try:
        # Create parent directories if needed
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Collect file metadata before moving if preservation is enabled
        if preserve_attrs:
            metadata = collect_file_metadata(source_path)

        # Try to move the file directly (which preserves attributes)
        try:
            # shutil.move has better attribute preservation than os.rename
            shutil.move(str(source_path), str(dest_path))
            success = True
        except OSError as e:
            # Cross-device moves require copy+delete
            if e.errno == errno.EXDEV:
                success = copy_file(source_path, dest_path, preserve_attrs, overwrite)
                if success:
                    os.unlink(source_path)
            else:
                raise

        # Apply metadata to destination if preservation is enabled
        # This is redundant for same-device moves but necessary for cross-device moves
        if preserve_attrs and success:
            apply_file_metadata(dest_path, metadata)

        logger.debug(f"Moved {source_path} to {dest_path}")
        return success

    except Exception as e:
        logger.error(f"Error moving {source_path} to {dest_path}: {e}")
        return False


def collect_file_metadata(path: Union[str, Path]) -> Dict[str, Any]:
    """
    Collect file metadata for preservation.

    Args:
        path: Path to the file

    Returns:
        Dictionary of file metadata
    """
    metadata = {}
    path_obj = Path(path)

    try:
        # Get basic file stats
        file_stat = path_obj.stat()

        # Store file mode (permissions)
        metadata['mode'] = file_stat.st_mode

        # Store timestamps
        metadata['timestamps'] = {
            'modified': file_stat.st_mtime,
            'accessed': file_stat.st_atime,
            # Note: st_ctime means different things on Unix vs Windows
            'created': file_stat.st_ctime
        }

        # Platform-specific metadata
        if platform.system() == 'Windows':
            metadata['windows'] = _collect_windows_metadata(path_obj)
        else:
            # Unix-specific metadata
            metadata['unix'] = {
                'uid': file_stat.st_uid,
                'gid': file_stat.st_gid
            }

        return metadata

    except Exception as e:
        logger.error(f"Error collecting metadata for {path}: {e}")
        return metadata


def apply_file_metadata(path: Union[str, Path], metadata: Dict[str, Any]) -> bool:
    """
    Apply metadata to a file.

    Args:
        path: Path to the file
        metadata: Metadata to apply

    Returns:
        True if successful, False otherwise
    """
    path_obj = Path(path)
    success = True

    try:
        # Apply mode (permissions)
        if 'mode' in metadata:
            try:
                os.chmod(path_obj, metadata['mode'])
            except Exception as e:
                logger.warning(f"Error applying permissions to {path}: {e}")
                success = False

        # Apply timestamps
        if 'timestamps' in metadata:
            timestamps = metadata['timestamps']
            try:
                os.utime(
                    path_obj,
                    (timestamps['accessed'], timestamps['modified'])
                )
            except Exception as e:
                logger.warning(f"Error applying timestamps to {path}: {e}")
                success = False

        # Apply platform-specific metadata
        if platform.system() == 'Windows' and 'windows' in metadata:
            success = success and _apply_windows_metadata(path_obj, metadata['windows'])
        elif platform.system() != 'Windows' and 'unix' in metadata:
            success = success and _apply_unix_metadata(path_obj, metadata['unix'])

        return success

    except Exception as e:
        logger.error(f"Error applying metadata to {path}: {e}")
        return False


def _copy_with_robocopy(source: Path, destination: Path) -> bool:
    """
    Copy a file using robocopy on Windows for better attribute preservation.

    Args:
        source: Source file path
        destination: Destination file path

    Returns:
        True if successful, False otherwise
    """
    if platform.system() != 'Windows':
        logger.warning("Robocopy is only available on Windows")
        return False

    try:
        # Get source directory and filename
        source_dir = source.parent
        filename = source.name

        # Get destination directory
        dest_dir = destination.parent

        # Run robocopy
        import subprocess
        cmd = [
            'robocopy',
            str(source_dir),  # Source directory
            str(dest_dir),    # Destination directory
            filename,         # File to copy
            '/COPY:DAT',      # Copy data, attributes, and timestamps
            '/R:3',           # 3 retries
            '/W:1'            # 1 second wait between retries
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        # Robocopy returns non-zero exit codes even for successful copies
        # Check if the file exists at the destination
        if destination.exists():
            return True
        else:
            logger.warning(f"Robocopy failed: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Error using robocopy: {e}")
        return False


def _collect_windows_metadata(path: Path) -> Dict[str, Any]:
    """
    Collect Windows-specific file metadata.

    Args:
        path: Path to the file

    Returns:
        Dictionary of Windows-specific metadata
    """
    windows_metadata = {}

    if platform.system() != 'Windows':
        return windows_metadata

    try:
        # Try to use pywin32 if available
        try:
            import win32api
            import win32con

            # Get file attributes
            attrs = win32api.GetFileAttributes(str(path))
            windows_metadata['attributes'] = attrs

        except ImportError:
            logger.debug("pywin32 not available, using limited Windows metadata collection")

            # Use attrib command as fallback
            try:
                import subprocess
                result = subprocess.run(['attrib', str(path)], capture_output=True, text=True)
                if result.returncode == 0:
                    attrs_line = result.stdout.strip()
                    windows_metadata['attrib_output'] = attrs_line
            except Exception as attrib_error:
                logger.debug(f"Error running attrib command: {attrib_error}")

        return windows_metadata

    except Exception as e:
        logger.error(f"Error collecting Windows metadata for {path}: {e}")
        return windows_metadata


def _apply_windows_metadata(path: Path, metadata: Dict[str, Any]) -> bool:
    """
    Apply Windows-specific metadata to a file.

    Args:
        path: Path to the file
        metadata: Windows-specific metadata to apply

    Returns:
        True if successful, False otherwise
    """
    if platform.system() != 'Windows':
        return False

    success = True

    try:
        # Try to use pywin32 if available
        try:
            import win32api

            # Apply file attributes
            if 'attributes' in metadata:
                win32api.SetFileAttributes(str(path), metadata['attributes'])

        except ImportError:
            logger.debug("pywin32 not available, using limited Windows metadata application")

            # Use attrib command as fallback
            if 'attrib_output' in metadata:
                import subprocess
                attrib_str = metadata['attrib_output']

                # Parse attrib output and apply
                if 'A' in attrib_str:
                    subprocess.run(['attrib', '+A', str(path)])
                if 'R' in attrib_str:
                    subprocess.run(['attrib', '+R', str(path)])
                if 'H' in attrib_str:
                    subprocess.run(['attrib', '+H', str(path)])
                if 'S' in attrib_str:
                    subprocess.run(['attrib', '+S', str(path)])

        return success

    except Exception as e:
        logger.error(f"Error applying Windows metadata to {path}: {e}")
        return False


def _apply_unix_metadata(path: Path, metadata: Dict[str, Any]) -> bool:
    """
    Apply Unix-specific metadata to a file.

    Args:
        path: Path to the file
        metadata: Unix-specific metadata to apply

    Returns:
        True if successful, False otherwise
    """
    if platform.system() == 'Windows':
        return False

    success = True

    try:
        # Apply owner and group
        if 'uid' in metadata and 'gid' in metadata:
            try:
                os.chown(path, metadata['uid'], metadata['gid'])
            except Exception as e:
                logger.warning(f"Error applying owner/group to {path}: {e}")
                success = False

        return success

    except Exception as e:
        logger.error(f"Error applying Unix metadata to {path}: {e}")
        return False


def copy_files_with_path(
    source_files: List[Union[str, Path]],
    source_base: Union[str, Path],
    dest_base: Union[str, Path],
    path_style: str = 'relative',
    include_base: bool = False,
    preserve_attrs: bool = True,
    overwrite: bool = False
) -> Dict[str, Tuple[bool, Path]]:
    """
    Copy multiple files preserving their path structure.

    Args:
        source_files: List of source file paths
        source_base: Base directory for source files
        dest_base: Destination base directory
        path_style: Path style ('relative', 'absolute', 'flat')
        include_base: Whether to include the base directory name
        preserve_attrs: Whether to preserve file attributes
        overwrite: Whether to overwrite existing files

    Returns:
        Dictionary mapping source paths to tuples of (success, destination_path)
    """
    from .paths import create_dest_path
    
    results = {}
    source_base_path = Path(source_base)
    dest_base_path = Path(dest_base)

    # Create destination directory if it doesn't exist
    dest_base_path.mkdir(parents=True, exist_ok=True)

    for source_file in source_files:
        source_path = Path(source_file)
        
        # Skip if source doesn't exist or isn't a file
        if not source_path.exists() or not source_path.is_file():
            logger.warning(f"Source file doesn't exist or isn't a file: {source_path}")
            results[str(source_path)] = (False, source_path)
            continue
            
        # Determine destination path
        try:
            dest_path = create_dest_path(
                source_path,
                source_base_path,
                dest_base_path,
                path_style,
                include_base
            )
            
            # Copy the file
            success = copy_file(source_path, dest_path, preserve_attrs, overwrite)
            
            # Record the result
            results[str(source_path)] = (success, dest_path)
            
        except Exception as e:
            logger.error(f"Error copying {source_path}: {e}")
            results[str(source_path)] = (False, source_path)
    
    return results


def move_files_with_path(
    source_files: List[Union[str, Path]],
    source_base: Union[str, Path],
    dest_base: Union[str, Path],
    path_style: str = 'relative',
    include_base: bool = False,
    preserve_attrs: bool = True,
    overwrite: bool = False
) -> Dict[str, Tuple[bool, Path]]:
    """
    Move multiple files preserving their path structure.

    Args:
        source_files: List of source file paths
        source_base: Base directory for source files
        dest_base: Destination base directory
        path_style: Path style ('relative', 'absolute', 'flat')
        include_base: Whether to include the base directory name
        preserve_attrs: Whether to preserve file attributes
        overwrite: Whether to overwrite existing files

    Returns:
        Dictionary mapping source paths to tuples of (success, destination_path)
    """
    from .paths import create_dest_path
    
    results = {}
    source_base_path = Path(source_base)
    dest_base_path = Path(dest_base)

    # Create destination directory if it doesn't exist
    dest_base_path.mkdir(parents=True, exist_ok=True)

    for source_file in source_files:
        source_path = Path(source_file)
        
        # Skip if source doesn't exist or isn't a file
        if not source_path.exists() or not source_path.is_file():
            logger.warning(f"Source file doesn't exist or isn't a file: {source_path}")
            results[str(source_path)] = (False, source_path)
            continue
            
        # Determine destination path
        try:
            dest_path = create_dest_path(
                source_path,
                source_base_path,
                dest_base_path,
                path_style,
                include_base
            )
            
            # Move the file
            success = move_file(source_path, dest_path, preserve_attrs, overwrite)
            
            # Record the result
            results[str(source_path)] = (success, dest_path)
            
        except Exception as e:
            logger.error(f"Error moving {source_path}: {e}")
            results[str(source_path)] = (False, source_path)
    
    return results


def create_directory_structure(
    dest_path: Union[str, Path], 
    directory_paths: List[Union[str, Path]]
) -> bool:
    """
    Create a directory structure at destination path.

    Args:
        dest_path: Base destination path
        directory_paths: List of directory paths to create

    Returns:
        True if successful, False otherwise
    """
    dest_base = Path(dest_path)
    success = True

    try:
        # Create base directory
        dest_base.mkdir(parents=True, exist_ok=True)

        # Create each directory
        for dir_path in directory_paths:
            full_path = dest_base / dir_path
            try:
                full_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"Error creating directory {full_path}: {e}")
                success = False

        return success

    except Exception as e:
        logger.error(f"Error creating directory structure at {dest_path}: {e}")
        return False


def remove_file(path: Union[str, Path], force: bool = False) -> bool:
    """
    Remove a file.

    Args:
        path: Path to the file
        force: Whether to force removal (ignore errors)

    Returns:
        True if successful, False otherwise
    """
    path_obj = Path(path)

    try:
        if not path_obj.exists():
            logger.warning(f"File doesn't exist: {path}")
            return True  # Already gone, consider it a success

        if not path_obj.is_file():
            logger.error(f"Path is not a file: {path}")
            return False

        # Remove the file
        path_obj.unlink()
        return True

    except Exception as e:
        if force:
            logger.warning(f"Error removing file {path}, but force=True: {e}")
            return True
        else:
            logger.error(f"Error removing file {path}: {e}")
            return False


def remove_directory(path: Union[str, Path], recursive: bool = False, force: bool = False) -> bool:
    """
    Remove a directory.

    Args:
        path: Path to the directory
        recursive: Whether to remove contents recursively
        force: Whether to force removal (ignore errors)

    Returns:
        True if successful, False otherwise
    """
    path_obj = Path(path)

    try:
        if not path_obj.exists():
            logger.warning(f"Directory doesn't exist: {path}")
            return True  # Already gone, consider it a success

        if not path_obj.is_dir():
            logger.error(f"Path is not a directory: {path}")
            return False

        # Remove the directory
        if recursive:
            shutil.rmtree(path_obj)
        else:
            path_obj.rmdir()  # Will fail if not empty
        return True

    except Exception as e:
        if force:
            logger.warning(f"Error removing directory {path}, but force=True: {e}")
            return True
        else:
            logger.error(f"Error removing directory {path}: {e}")
            return False


def create_symlink(
    target: Union[str, Path],
    link: Union[str, Path],
    force: bool = False,
    target_is_directory: Optional[bool] = None
) -> bool:
    """
    Create a symbolic link with cross-platform handling.

    On Unix systems, uses os.symlink directly.
    On Windows, attempts multiple methods:
    1. os.symlink (requires Developer Mode or admin on Windows 10+)
    2. dazzlelink library if available (handles elevation gracefully)
    3. mklink command as fallback

    Args:
        target: The target path the symlink will point to
        link: The path where the symlink will be created
        force: If True, remove existing file/symlink at link path first
        target_is_directory: Whether target is a directory (auto-detected if None)

    Returns:
        True if symlink was created successfully, False otherwise

    Example:
        >>> create_symlink('/path/to/file.txt', '/path/to/link.txt')
        True
        >>> create_symlink('C:\\data\\folder', 'C:\\links\\folder_link', target_is_directory=True)
        True
    """
    target_path = Path(target)
    link_path = Path(link)

    # Handle existing link
    if link_path.exists() or link_path.is_symlink():
        if not force:
            logger.warning(f"Link path already exists: {link_path}")
            return False
        try:
            if link_path.is_dir() and not link_path.is_symlink():
                shutil.rmtree(link_path)
            else:
                link_path.unlink()
            logger.debug(f"Removed existing path: {link_path}")
        except Exception as e:
            logger.error(f"Failed to remove existing path {link_path}: {e}")
            return False

    # Create parent directories if needed
    try:
        link_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create parent directories for {link_path}: {e}")
        return False

    # Auto-detect if target is a directory
    if target_is_directory is None:
        target_is_directory = target_path.is_dir()

    # Try to create symlink
    if platform.system() != 'Windows':
        # Unix: straightforward symlink
        try:
            os.symlink(target_path, link_path)
            logger.debug(f"Created symlink: {link_path} -> {target_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to create symlink on Unix: {e}")
            return False

    # Windows: try multiple methods
    return _create_windows_symlink(target_path, link_path, target_is_directory)


def _create_windows_symlink(target: Path, link: Path, is_directory: bool) -> bool:
    """
    Create a symbolic link on Windows using multiple fallback methods.

    Args:
        target: Target path
        link: Link path to create
        is_directory: Whether target is a directory

    Returns:
        True if successful, False otherwise
    """
    # Method 1: Try os.symlink (works with Developer Mode enabled)
    try:
        os.symlink(target, link, target_is_directory=is_directory)
        logger.debug(f"Created Windows symlink using os.symlink: {link} -> {target}")
        return True
    except OSError as e:
        # Error 1314 = "A required privilege is not held by the client"
        if getattr(e, 'winerror', 0) == 1314:
            logger.debug("os.symlink failed (Developer Mode not enabled), trying alternatives")
        else:
            logger.warning(f"os.symlink failed: {e}")

    # Method 2: Try dazzlelink if available
    try:
        from dazzlelink.operations import create_windows_symlink as dazzle_create_symlink
        result = dazzle_create_symlink(str(target), str(link), is_directory)
        if result:
            logger.debug(f"Created Windows symlink using dazzlelink: {link} -> {target}")
            return True
    except ImportError:
        logger.debug("dazzlelink not available, trying mklink fallback")
    except Exception as e:
        logger.warning(f"dazzlelink symlink creation failed: {e}")

    # Method 3: Try mklink command (may require elevation)
    try:
        import subprocess
        dir_flag = '/D ' if is_directory else ''
        cmd = f'mklink {dir_flag}"{link}" "{target}"'

        result = subprocess.run(
            ['cmd', '/c', cmd],
            text=True,
            capture_output=True,
            check=False
        )

        if result.returncode == 0:
            logger.debug(f"Created Windows symlink using mklink: {link} -> {target}")
            return True
        else:
            logger.warning(f"mklink failed: {result.stderr.strip()}")
    except Exception as e:
        logger.warning(f"mklink command failed: {e}")

    # All methods failed
    logger.error(
        f"Failed to create symlink on Windows. This typically requires either:\n"
        f"  1. Developer Mode enabled (Settings > Update & Security > For developers)\n"
        f"  2. Running as Administrator\n"
        f"  3. Install dazzlelink: pip install dazzlelink"
    )
    return False
