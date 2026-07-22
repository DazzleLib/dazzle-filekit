"""
Rich file metadata capture and application.

This module provides functionality for collecting, storing, and applying
file metadata across platforms, with first-class support for:

  - Windows SDDL ACL round-trip (JSON-serializable)
  - Windows creation time restoration via pywin32 SetFileTime
  - Linux/macOS extended attributes (xattrs) capture and apply
  - File mode, timestamps (with ISO projections), and owner/group

Ported into filekit in v0.2.4 from the preservelib module bundled with
``dazzlecmd/projects/core/safedel``. The port is byte-identical to the
source; any future enhancements should land here first and flow out to
downstream preservelib copies.

Two top-level entry points are re-exported from ``dazzle_filekit``:

    from dazzle_filekit import collect_file_metadata, apply_file_metadata

Or use the module directly:

    from dazzle_filekit import metadata
    md = metadata.collect_file_metadata(path)
    metadata.apply_file_metadata(target, md)

See ``is_win32_available()`` to check whether the richer Windows code
path is available (requires pywin32; shipped as a dependency in v0.2.4).
"""

import os
import sys
import stat
import shutil
import logging
import datetime
import time
import platform
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Set, Tuple

# Cross-layer payload schemas owned by the stack bedrock (STACK-MAP D10).
# filekit produces these shapes; consuming the TypedDicts as our signatures
# makes the contract explicit and machine-checkable (#15 Phase D).
from dazzle_lib import FileMetadataDict, TimestampsDict

# Set up module-level logger
logger = logging.getLogger(__name__)

def collect_file_metadata(path: Union[str, Path]) -> FileMetadataDict:
    """
    Collect file metadata for preservation.

    Args:
        path: The file path to collect metadata from

    Returns:
        A dictionary of file metadata
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
            'created': file_stat.st_ctime,
            'modified_iso': datetime.datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
            'accessed_iso': datetime.datetime.fromtimestamp(file_stat.st_atime).isoformat(),
            'created_iso': datetime.datetime.fromtimestamp(file_stat.st_ctime).isoformat()
        }

        # Store size
        metadata['size'] = file_stat.st_size

        # Platform-specific metadata
        if platform.system() == 'Windows':
            metadata['windows'] = _collect_windows_metadata(path_obj)
        else:
            # Unix-specific metadata
            metadata['unix'] = {
                'uid': file_stat.st_uid,
                'gid': file_stat.st_gid
            }
            # Extended attributes (xattrs) on Linux/macOS
            xattrs = _collect_unix_xattrs(path_obj)
            if xattrs:
                metadata['xattrs'] = xattrs

        return metadata
    except Exception as e:
        logger.error(f"Error collecting metadata for {path}: {e}")
        return metadata

def _collect_windows_metadata(path: Path) -> Dict[str, Any]:
    """
    Collect Windows-specific file metadata.

    Args:
        path: The file path to collect metadata from

    Returns:
        A dictionary of Windows-specific metadata
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
            windows_metadata['is_hidden'] = bool(attrs & win32con.FILE_ATTRIBUTE_HIDDEN)
            windows_metadata['is_system'] = bool(attrs & win32con.FILE_ATTRIBUTE_SYSTEM)
            windows_metadata['is_readonly'] = bool(attrs & win32con.FILE_ATTRIBUTE_READONLY)
            windows_metadata['is_archive'] = bool(attrs & win32con.FILE_ATTRIBUTE_ARCHIVE)

            # Get security information
            try:
                import win32security
                security_info = win32security.GetFileSecurity(
                    str(path),
                    win32security.OWNER_SECURITY_INFORMATION |
                    win32security.GROUP_SECURITY_INFORMATION |
                    win32security.DACL_SECURITY_INFORMATION
                )

                # Get owner and group
                owner_sid = security_info.GetSecurityDescriptorOwner()
                group_sid = security_info.GetSecurityDescriptorGroup()

                try:
                    # Convert SIDs to names
                    owner_name, owner_domain, owner_type = win32security.LookupAccountSid(None, owner_sid)
                    group_name, group_domain, group_type = win32security.LookupAccountSid(None, group_sid)

                    windows_metadata['owner'] = f"{owner_domain}\\{owner_name}"
                    windows_metadata['group'] = f"{group_domain}\\{group_name}"
                except:
                    # If lookup fails, just use the SID
                    windows_metadata['owner_sid'] = str(owner_sid)
                    windows_metadata['group_sid'] = str(group_sid)

                # Store security descriptor as SDDL string (JSON-serializable)
                try:
                    sddl = win32security.ConvertSecurityDescriptorToStringSecurityDescriptor(
                        security_info,
                        win32security.SDDL_REVISION_1,
                        win32security.OWNER_SECURITY_INFORMATION |
                        win32security.GROUP_SECURITY_INFORMATION |
                        win32security.DACL_SECURITY_INFORMATION
                    )
                    windows_metadata['security_descriptor_sddl'] = sddl
                except Exception:
                    windows_metadata['security_descriptor_sddl'] = None
            except Exception as e:
                logger.debug(f"Error getting security info: {e}")

        except ImportError:
            logger.debug("pywin32 not available, using limited Windows metadata collection")

            # Use attrib command as fallback
            try:
                import subprocess
                result = subprocess.run(['attrib', str(path)], capture_output=True, text=True)
                if result.returncode == 0:
                    attrs_line = result.stdout.strip()
                    windows_metadata['attrib_output'] = attrs_line

                    # Parse attrib output
                    windows_metadata['is_readonly'] = 'R' in attrs_line
                    windows_metadata['is_hidden'] = 'H' in attrs_line
                    windows_metadata['is_system'] = 'S' in attrs_line
                    windows_metadata['is_archive'] = 'A' in attrs_line
            except Exception as attrib_error:
                logger.debug(f"Error running attrib command: {attrib_error}")

        return windows_metadata
    except Exception as e:
        logger.error(f"Error collecting Windows metadata for {path}: {e}")
        return windows_metadata

_FILE_ATTRIBUTE_REPARSE_POINT = 0x400

# Nanoseconds between 1601-01-01 (FILETIME epoch) and 1970-01-01 (Unix epoch)
_FILETIME_EPOCH_OFFSET_NS = 11644473600 * 10**9


def _set_link_times_exact_windows(
    path_str: str,
    created_ns: Optional[int],
    accessed_ns: Optional[int],
    modified_ns: Optional[int],
) -> bool:
    """Set timestamps on a link node with exact 100ns precision.

    Opens the node with ``FILE_FLAG_OPEN_REPARSE_POINT`` (never follows to
    the target) and calls ``SetFileTime`` with FILETIMEs computed directly
    from integer nanoseconds -- the float/datetime/pywintypes chain rounds
    to microseconds or worse, which a mirror's verify pass would flag.
    Pure ctypes; works without pywin32. Returns True on success.
    """
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32

        FILE_WRITE_ATTRIBUTES = 0x100
        OPEN_EXISTING = 3
        FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
        FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
        FILE_SHARE_ALL = 0x01 | 0x02 | 0x04

        def _ft(ns: Optional[int]):
            if ns is None:
                return None
            ticks = (ns + _FILETIME_EPOCH_OFFSET_NS) // 100
            return wintypes.FILETIME(
                ticks & 0xFFFFFFFF, (ticks >> 32) & 0xFFFFFFFF
            )

        handle = kernel32.CreateFileW(
            path_str, FILE_WRITE_ATTRIBUTES, FILE_SHARE_ALL, None,
            OPEN_EXISTING,
            FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
        if handle == wintypes.HANDLE(-1).value:
            return False
        try:
            ft_c = _ft(created_ns)
            ft_a = _ft(accessed_ns)
            ft_m = _ft(modified_ns)
            ok = kernel32.SetFileTime(
                handle,
                ctypes.byref(ft_c) if ft_c else None,
                ctypes.byref(ft_a) if ft_a else None,
                ctypes.byref(ft_m) if ft_m else None,
            )
            return bool(ok)
        finally:
            kernel32.CloseHandle(handle)
    except Exception as e:  # noqa: BLE001 - caller falls back to pywin32
        logger.debug(f"_set_link_times_exact_windows({path_str}) failed: {e}")
        return False


def _is_link_node(path_obj: Path) -> bool:
    """True for any link NODE whose own metadata must be set without
    following to the target: symlinks everywhere, plus junctions (and any
    other reparse point) on Windows. ``Path.is_symlink()`` alone is False for
    junctions (IO_REPARSE_TAG_MOUNT_POINT vs IO_REPARSE_TAG_SYMLINK), which
    routed junctions to the target-following ``os.utime`` path before v0.3.4.
    """
    if path_obj.is_symlink():
        return True
    if platform.system() != 'Windows':
        return False
    try:
        attrs = os.lstat(str(path_obj)).st_file_attributes
    except OSError:
        return False
    return bool(attrs & _FILE_ATTRIBUTE_REPARSE_POINT)


def _set_symlink_timestamps(path_obj: Path, timestamps: Dict[str, Any]) -> bool:
    """Apply timestamps to a link node ITSELF (symlink or junction), never
    the target it points to.

    ``os.utime()`` and a default Win32 ``CreateFile`` both follow the reparse
    point to the target -- so applying timestamps to a link the naive way
    silently corrupts the *target's* timestamps. On Windows we open the link
    with ``FILE_FLAG_OPEN_REPARSE_POINT`` and use ``SetFileTime``; on POSIX we
    use ``os.utime(follow_symlinks=False)``. Best-effort: returns False (with a
    warning) when the platform/runtime can't set link timestamps -- it never
    falls back to touching the target.
    """
    accessed = timestamps.get('accessed')
    modified = timestamps.get('modified')
    created = timestamps.get('created')
    # Optional exact-precision variants: integer nanoseconds. The float-
    # seconds path bottoms out in datetime/pywintypes at microsecond (or
    # worse) resolution; mirroring wants the NTFS 100ns tick preserved, so
    # *_ns keys, when present, take precedence and travel through an exact
    # integer FILETIME conversion.
    accessed_ns = timestamps.get('accessed_ns')
    modified_ns = timestamps.get('modified_ns')
    created_ns = timestamps.get('created_ns')

    if platform.system() != 'Windows':
        if os.utime not in os.supports_follow_symlinks:
            logger.warning(
                f"Cannot set link timestamps for {path_obj} on this platform "
                f"without following to the target; skipped."
            )
            return False
        try:
            if accessed_ns is not None and modified_ns is not None:
                os.utime(path_obj, ns=(accessed_ns, modified_ns),
                         follow_symlinks=False)
                return True
            if accessed is not None and modified is not None:
                os.utime(path_obj, (accessed, modified), follow_symlinks=False)
                return True
        except Exception as e:
            logger.warning(f"Error applying symlink timestamps to {path_obj}: {e}")
            return False
        logger.warning(
            f"Cannot set link timestamps for {path_obj}: no usable "
            f"accessed/modified values; skipped."
        )
        return False

    # Windows exact path: integer ns -> FILETIME (100ns ticks since 1601)
    # via ctypes SetFileTime. No float/datetime rounding, no pywin32 needed.
    if any(v is not None for v in (created_ns, accessed_ns, modified_ns)):
        if _set_link_times_exact_windows(
            str(path_obj), created_ns, accessed_ns, modified_ns
        ):
            return True
        logger.debug(
            f"Exact ns SetFileTime failed for {path_obj}; falling back to "
            f"pywin32 float path"
        )
        # Fall through to the float path with whatever float values exist.
        if accessed is None and accessed_ns is not None:
            accessed = accessed_ns / 1e9
        if modified is None and modified_ns is not None:
            modified = modified_ns / 1e9
        if created is None and created_ns is not None:
            created = created_ns / 1e9

    # Windows: open the link itself (FILE_FLAG_OPEN_REPARSE_POINT) + SetFileTime.
    if not is_win32_available():
        logger.warning(
            f"pywin32 unavailable; cannot set link timestamps for {path_obj} "
            f"without following to the target; skipped."
        )
        return False
    try:
        import win32file
        import win32con
        import pywintypes

        FILE_WRITE_ATTRIBUTES = 0x100
        FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000

        def _wt(value):
            if value is None:
                return None
            dt = (datetime.datetime.fromtimestamp(value)
                  if isinstance(value, (int, float)) else value)
            return pywintypes.Time(dt)

        handle = win32file.CreateFile(
            str(path_obj),
            FILE_WRITE_ATTRIBUTES,
            win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE,
            None,
            win32con.OPEN_EXISTING,
            FILE_FLAG_OPEN_REPARSE_POINT | win32con.FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
        try:
            # SetFileTime(handle, creation, access, write) -- None leaves unchanged.
            win32file.SetFileTime(handle, _wt(created), _wt(accessed), _wt(modified))
        finally:
            handle.close()
        return True
    except Exception as e:
        logger.warning(f"Error applying symlink timestamps to {path_obj}: {e}")
        return False


def apply_file_metadata(path: Union[str, Path], metadata: FileMetadataDict) -> bool:
    """
    Apply metadata to a file.

    Args:
        path: The file path to apply metadata to
        metadata: The metadata to apply

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

        # Apply timestamps. Link nodes (symlinks AND junctions) need special
        # handling: os.utime() and the default Win32 handle follow the reparse
        # point and would write to the TARGET, so route them through a
        # link-targeting helper that sets all three times on the node itself.
        if 'timestamps' in metadata:
            timestamps = metadata['timestamps']
            if _is_link_node(path_obj):
                if not _set_symlink_timestamps(path_obj, timestamps):
                    success = False
            else:
                try:
                    os.utime(
                        path_obj,
                        (timestamps['accessed'], timestamps['modified'])
                    )
                except Exception as e:
                    logger.warning(f"Error applying timestamps to {path}: {e}")
                    success = False

                # On Windows, also restore creation time via pywin32
                if platform.system() == 'Windows' and 'created' in timestamps:
                    if not restore_windows_creation_time(path_obj, timestamps['created']):
                        # Non-fatal -- ctime restoration is best-effort
                        pass

        # Apply platform-specific metadata
        if platform.system() == 'Windows' and 'windows' in metadata:
            success = success and _apply_windows_metadata(path_obj, metadata['windows'])
        elif platform.system() != 'Windows' and 'unix' in metadata:
            success = success and _apply_unix_metadata(path_obj, metadata['unix'])

        # Apply extended attributes (Linux/macOS)
        if platform.system() != 'Windows' and 'xattrs' in metadata:
            success = success and _apply_unix_xattrs(path_obj, metadata['xattrs'])

        return success
    except Exception as e:
        logger.error(f"Error applying metadata to {path}: {e}")
        return False

def _apply_windows_metadata(path: Path, metadata: Dict[str, Any]) -> bool:
    """
    Apply Windows-specific metadata to a file.

    Args:
        path: The file path to apply metadata to
        metadata: The Windows-specific metadata to apply

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
            import win32con
            import win32security

            # Apply file attributes
            if 'attributes' in metadata:
                win32api.SetFileAttributes(str(path), metadata['attributes'])
            else:
                # Apply individual attributes
                current_attrs = win32api.GetFileAttributes(str(path))

                if 'is_readonly' in metadata:
                    if metadata['is_readonly']:
                        current_attrs |= win32con.FILE_ATTRIBUTE_READONLY
                    else:
                        current_attrs &= ~win32con.FILE_ATTRIBUTE_READONLY

                if 'is_hidden' in metadata:
                    if metadata['is_hidden']:
                        current_attrs |= win32con.FILE_ATTRIBUTE_HIDDEN
                    else:
                        current_attrs &= ~win32con.FILE_ATTRIBUTE_HIDDEN

                if 'is_system' in metadata:
                    if metadata['is_system']:
                        current_attrs |= win32con.FILE_ATTRIBUTE_SYSTEM
                    else:
                        current_attrs &= ~win32con.FILE_ATTRIBUTE_SYSTEM

                if 'is_archive' in metadata:
                    if metadata['is_archive']:
                        current_attrs |= win32con.FILE_ATTRIBUTE_ARCHIVE
                    else:
                        current_attrs &= ~win32con.FILE_ATTRIBUTE_ARCHIVE

                win32api.SetFileAttributes(str(path), current_attrs)

            # Apply security information from SDDL string if available
            sddl = metadata.get('security_descriptor_sddl')
            if sddl:
                try:
                    sd = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
                        sddl, win32security.SDDL_REVISION_1
                    )
                    win32security.SetFileSecurity(
                        str(path),
                        win32security.OWNER_SECURITY_INFORMATION |
                        win32security.GROUP_SECURITY_INFORMATION |
                        win32security.DACL_SECURITY_INFORMATION,
                        sd
                    )
                except Exception as e:
                    logger.warning(f"Error applying security information to {path}: {e}")
                    success = False
            # Legacy: handle raw security_descriptor objects (pre-SDDL manifests)
            elif 'security_descriptor' in metadata:
                try:
                    win32security.SetFileSecurity(
                        str(path),
                        win32security.OWNER_SECURITY_INFORMATION |
                        win32security.GROUP_SECURITY_INFORMATION |
                        win32security.DACL_SECURITY_INFORMATION,
                        metadata['security_descriptor']
                    )
                except Exception as e:
                    logger.debug(f"Legacy security descriptor not applicable: {e}")

        except ImportError:
            logger.debug("pywin32 not available, using limited Windows metadata application")

            # Use attrib command as fallback
            if 'attrib_output' in metadata:
                import subprocess

                # Reset attributes first
                subprocess.run(['attrib', '-R', '-H', '-S', '-A', str(path)])

                # Apply stored attributes
                attrs = ""
                if metadata.get('is_readonly', False):
                    attrs += "+R "
                if metadata.get('is_hidden', False):
                    attrs += "+H "
                if metadata.get('is_system', False):
                    attrs += "+S "
                if metadata.get('is_archive', False):
                    attrs += "+A "

                if attrs:
                    subprocess.run(['attrib', *attrs.strip().split(), str(path)])

        return success

    except Exception as e:
        logger.error(f"Error applying Windows metadata to {path}: {e}")
        return False

def _collect_unix_xattrs(path: Path) -> Dict[str, str]:
    """Capture extended attributes on Linux/macOS as a dict of name -> base64.

    Uses os.listxattr / os.getxattr (stdlib, Python 3.3+). Handles macOS
    resource forks (which appear as com.apple.* xattrs on APFS/HFS+),
    Linux user.* xattrs, and security.* xattrs.

    Values are base64-encoded since they can contain arbitrary binary data
    and the manifest is JSON.
    """
    if platform.system() == 'Windows':
        return {}

    import base64
    result = {}

    try:
        names = os.listxattr(path, follow_symlinks=False)
    except (OSError, AttributeError):
        return {}

    for name in names:
        try:
            value = os.getxattr(path, name, follow_symlinks=False)
            result[name] = base64.b64encode(value).decode('ascii')
        except (OSError, AttributeError):
            continue

    return result


def _apply_unix_xattrs(path: Path, xattrs: Dict[str, str]) -> bool:
    """Apply extended attributes from a dict of name -> base64.

    Best effort -- failures are logged but don't block recovery.
    Skips com.apple.quarantine to avoid security surprises on restore.
    """
    if platform.system() == 'Windows' or not xattrs:
        return True

    import base64
    success = True

    for name, b64_value in xattrs.items():
        # Skip com.apple.quarantine -- it's sticky and re-evaluated by
        # Gatekeeper, restoring it could change security posture unexpectedly
        if name == 'com.apple.quarantine':
            continue
        try:
            value = base64.b64decode(b64_value)
            os.setxattr(path, name, value, follow_symlinks=False)
        except (OSError, AttributeError) as e:
            logger.debug(f"Could not restore xattr {name} on {path}: {e}")
            success = False

    return success


def _apply_unix_metadata(path: Path, metadata: Dict[str, Any]) -> bool:
    """
    Apply Unix-specific metadata to a file.

    Args:
        path: The file path to apply metadata to
        metadata: The Unix-specific metadata to apply

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

def compare_metadata(metadata1: Dict[str, Any], metadata2: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare two metadata dictionaries and return differences.

    Args:
        metadata1: First metadata dictionary
        metadata2: Second metadata dictionary

    Returns:
        Dictionary of differences
    """
    differences = {}

    # Compare sizes
    if metadata1.get('size') != metadata2.get('size'):
        differences['size'] = {
            'old': metadata1.get('size'),
            'new': metadata2.get('size')
        }

    # Compare timestamps
    if 'timestamps' in metadata1 and 'timestamps' in metadata2:
        timestamps1 = metadata1['timestamps']
        timestamps2 = metadata2['timestamps']

        timestamp_diffs = {}

        for key in ('modified', 'accessed', 'created'):
            if abs((timestamps1.get(key, 0) or 0) - (timestamps2.get(key, 0) or 0)) > 2:
                # Allow 2-second difference to account for filesystem precision
                timestamp_diffs[key] = {
                    'old': timestamps1.get(key),
                    'old_iso': timestamps1.get(f"{key}_iso"),
                    'new': timestamps2.get(key),
                    'new_iso': timestamps2.get(f"{key}_iso")
                }

        if timestamp_diffs:
            differences['timestamps'] = timestamp_diffs

    # Compare modes (permissions)
    if metadata1.get('mode') != metadata2.get('mode'):
        differences['mode'] = {
            'old': metadata1.get('mode'),
            'new': metadata2.get('mode'),
            'old_octal': oct(metadata1.get('mode', 0)) if metadata1.get('mode') is not None else None,
            'new_octal': oct(metadata2.get('mode', 0)) if metadata2.get('mode') is not None else None
        }

    # Compare platform-specific metadata
    if platform.system() == 'Windows':
        # Compare Windows metadata
        if 'windows' in metadata1 and 'windows' in metadata2:
            windows1 = metadata1['windows']
            windows2 = metadata2['windows']

            windows_diffs = {}

            # Compare attributes
            for attr in ('is_readonly', 'is_hidden', 'is_system', 'is_archive'):
                if windows1.get(attr) != windows2.get(attr):
                    windows_diffs[attr] = {
                        'old': windows1.get(attr),
                        'new': windows2.get(attr)
                    }

            if windows_diffs:
                differences['windows'] = windows_diffs
    else:
        # Compare Unix metadata
        if 'unix' in metadata1 and 'unix' in metadata2:
            unix1 = metadata1['unix']
            unix2 = metadata2['unix']

            unix_diffs = {}

            if unix1.get('uid') != unix2.get('uid'):
                unix_diffs['uid'] = {
                    'old': unix1.get('uid'),
                    'new': unix2.get('uid')
                }

            if unix1.get('gid') != unix2.get('gid'):
                unix_diffs['gid'] = {
                    'old': unix1.get('gid'),
                    'new': unix2.get('gid')
                }

            if unix_diffs:
                differences['unix'] = unix_diffs

    return differences

def get_metadata_summary(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a human-readable summary of file metadata.

    Args:
        metadata: The metadata to summarize

    Returns:
        Dictionary with summarized metadata
    """
    summary = {}

    # Size
    if 'size' in metadata:
        size = metadata['size']
        if size < 1024:
            summary['size'] = f"{size} bytes"
        elif size < 1024 * 1024:
            summary['size'] = f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            summary['size'] = f"{size / (1024 * 1024):.1f} MB"
        else:
            summary['size'] = f"{size / (1024 * 1024 * 1024):.1f} GB"

    # Timestamps
    if 'timestamps' in metadata:
        timestamps = metadata['timestamps']
        summary['timestamps'] = {
            'modified': timestamps.get('modified_iso', 'Unknown'),
            'accessed': timestamps.get('accessed_iso', 'Unknown'),
            'created': timestamps.get('created_iso', 'Unknown')
        }

    # Mode (permissions)
    if 'mode' in metadata:
        mode = metadata['mode']
        summary['permissions'] = oct(mode)[2:] if mode is not None else 'Unknown'

    # Platform-specific
    if platform.system() == 'Windows' and 'windows' in metadata:
        windows = metadata['windows']
        summary['attributes'] = []

        if windows.get('is_readonly', False):
            summary['attributes'].append('Read-only')
        if windows.get('is_hidden', False):
            summary['attributes'].append('Hidden')
        if windows.get('is_system', False):
            summary['attributes'].append('System')
        if windows.get('is_archive', False):
            summary['attributes'].append('Archive')

        if 'owner' in windows:
            summary['owner'] = windows['owner']

    elif platform.system() != 'Windows' and 'unix' in metadata:
        unix = metadata['unix']
        summary['owner'] = f"UID: {unix.get('uid', 'Unknown')}, GID: {unix.get('gid', 'Unknown')}"

    return summary

def metadata_to_json(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert metadata to a JSON-serializable format.

    Args:
        metadata: The metadata to convert

    Returns:
        JSON-serializable dictionary
    """
    # Create a copy to avoid modifying the original
    result = {}

    for key, value in metadata.items():
        if isinstance(value, dict):
            # Recursively convert nested dictionaries
            result[key] = metadata_to_json(value)
        elif isinstance(value, (int, float, str, bool, type(None))):
            # These types are already JSON-serializable
            result[key] = value
        elif isinstance(value, (bytes, bytearray)):
            # Convert bytes to base64
            import base64
            result[key] = base64.b64encode(value).decode('ascii')
        elif hasattr(value, '__dict__'):
            # For custom objects
            try:
                result[key] = str(value)
            except:
                result[key] = f"<non-serializable: {type(value).__name__}>"
        else:
            # For other types, convert to string
            try:
                result[key] = str(value)
            except:
                result[key] = f"<non-serializable: {type(value).__name__}>"

    return result

def collect_timestamp_info(path: Union[str, Path]) -> TimestampsDict:
    """
    Collect timestamp information from a file.

    Args:
        path: Path to the file

    Returns:
        Dictionary with timestamp information
    """
    result = {}
    path_obj = Path(path)

    try:
        if path_obj.exists():
            stat_result = path_obj.stat()

            result = {
                'created': stat_result.st_ctime,
                'modified': stat_result.st_mtime,
                'accessed': stat_result.st_atime,
                'created_iso': datetime.datetime.fromtimestamp(stat_result.st_ctime).isoformat(),
                'modified_iso': datetime.datetime.fromtimestamp(stat_result.st_mtime).isoformat(),
                'accessed_iso': datetime.datetime.fromtimestamp(stat_result.st_atime).isoformat()
            }
    except Exception as e:
        logger.warning(f"Error collecting timestamp info for {path}: {e}")

    return result

def apply_timestamp_strategy(path: Union[str, Path], strategy: str, link_timestamps: Optional[Dict[str, Any]] = None,
                          target_timestamps: Optional[Dict[str, Any]] = None) -> bool:
    """
    Apply timestamps to a file based on a strategy.

    Args:
        path: Path to the file
        strategy: Strategy to use ('current', 'symlink', 'target', 'preserve-all')
        link_timestamps: Timestamps from the original symlink (optional)
        target_timestamps: Timestamps from the target file (optional)

    Returns:
        True if successful, False otherwise
    """
    path_obj = Path(path)

    try:
        if strategy == 'current':
            # Use current time (do nothing)
            return True

        elif strategy == 'symlink' and link_timestamps:
            # Use symlink timestamps
            modified = link_timestamps.get('modified')
            accessed = link_timestamps.get('accessed')

            if modified and accessed:
                os.utime(path_obj, (accessed, modified))
                return True
            else:
                logger.warning(f"Missing timestamp information for {path}")
                return False

        elif strategy == 'target' and target_timestamps:
            # Use target timestamps
            modified = target_timestamps.get('modified')
            accessed = target_timestamps.get('accessed')

            if modified and accessed:
                os.utime(path_obj, (accessed, modified))
                return True
            else:
                logger.warning(f"Missing timestamp information for {path}")
                return False

        elif strategy == 'preserve-all':
            # Try to preserve all timestamps
            # For Windows, we need extra work for creation time

            if platform.system() == 'Windows':
                try:
                    import win32file
                    import win32con
                    import pywintypes

                    # Apply creation time if available
                    created = None
                    if link_timestamps and 'created' in link_timestamps:
                        created = link_timestamps['created']
                    elif target_timestamps and 'created' in target_timestamps:
                        created = target_timestamps['created']

                    if created:
                        # Convert to Windows filetime
                        wintime = pywintypes.Time(created)

                        # Open file and set creation time
                        handle = win32file.CreateFile(
                            str(path_obj),
                            win32con.FILE_WRITE_ATTRIBUTES,
                            win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE,
                            None,
                            win32con.OPEN_EXISTING,
                            win32con.FILE_ATTRIBUTE_NORMAL,
                            None
                        )

                        win32file.SetFileTime(handle, wintime)
                        handle.close()
                except ImportError:
                    logger.debug("pywin32 not available, skipping creation time preservation")
                except Exception as e:
                    logger.warning(f"Error setting creation time for {path}: {e}")

            # Apply modified and accessed times
            # Try symlink timestamps first, then target timestamps
            modified = None
            accessed = None

            if link_timestamps:
                modified = link_timestamps.get('modified')
                accessed = link_timestamps.get('accessed')

            if (not modified or not accessed) and target_timestamps:
                modified = modified or target_timestamps.get('modified')
                accessed = accessed or target_timestamps.get('accessed')

            if modified and accessed:
                os.utime(path_obj, (accessed, modified))
                return True
            else:
                logger.warning(f"Missing timestamp information for {path}")
                return False

        else:
            logger.warning(f"Unknown timestamp strategy: {strategy}")
            return False

    except Exception as e:
        logger.error(f"Error applying timestamps to {path}: {e}")
        return False


# -- Windows Creation Time Restoration --
#
# Pattern learned from claude-sesslog-datefix session:
# - Use pywin32, not raw ctypes (ctypes approach silently failed)
# - FILE_WRITE_ATTRIBUTES = 0x100 is not always in win32con, use raw value
# - Directories need FILE_FLAG_BACKUP_SEMANTICS, not FILE_ATTRIBUTE_NORMAL
# - pywintypes.Time(dt) accepts a datetime or epoch float directly

_WIN32_AVAILABLE = None  # Lazy check


def is_win32_available() -> bool:
    """Check if pywin32 is available for ctime restoration."""
    global _WIN32_AVAILABLE
    if _WIN32_AVAILABLE is not None:
        return _WIN32_AVAILABLE
    try:
        import win32file  # noqa: F401
        import win32con  # noqa: F401
        import pywintypes  # noqa: F401
        _WIN32_AVAILABLE = True
    except ImportError:
        _WIN32_AVAILABLE = False
    return _WIN32_AVAILABLE


def restore_windows_creation_time(
    path: Union[str, Path],
    created: Union[float, datetime.datetime],
) -> bool:
    """Restore the Windows creation time (ctime) of a file or directory.

    Windows NTFS stores three timestamps: creation, last-modified, last-accessed.
    Python's os.utime() can set modified and accessed but NOT creation time.
    This function uses pywin32 SetFileTime() to restore the creation time
    captured in the manifest.

    Args:
        path: File or directory path
        created: Creation time as epoch float or datetime object

    Returns:
        True on success, False on any failure (pywin32 missing, permission
        denied, etc.). This is best-effort -- failure should not block recovery.
    """
    if platform.system() != 'Windows':
        return False

    if not is_win32_available():
        return False

    try:
        import win32file
        import win32con
        import pywintypes

        path_obj = Path(path)
        path_str = str(path_obj)

        # Raw value for FILE_WRITE_ATTRIBUTES (0x100) -- not always in win32con
        FILE_WRITE_ATTRIBUTES = 0x100

        # Directories require FILE_FLAG_BACKUP_SEMANTICS to open. For link
        # nodes (symlink/junction) decide dir-ness from lstat attributes --
        # is_dir() follows the reparse point and reports False for a BROKEN
        # directory link, whose handle still needs BACKUP_SEMANTICS.
        if _is_link_node(path_obj):
            try:
                node_attrs = os.lstat(path_str).st_file_attributes
            except OSError:
                node_attrs = 0
            if node_attrs & stat.FILE_ATTRIBUTE_DIRECTORY:
                flags = win32con.FILE_FLAG_BACKUP_SEMANTICS
            else:
                flags = win32con.FILE_ATTRIBUTE_NORMAL
            # Open the link itself, not the target it points to, so the
            # creation time lands on the link (otherwise CreateFile follows it).
            flags |= 0x00200000  # FILE_FLAG_OPEN_REPARSE_POINT
        elif path_obj.is_dir():
            flags = win32con.FILE_FLAG_BACKUP_SEMANTICS
        else:
            flags = win32con.FILE_ATTRIBUTE_NORMAL

        # Handle readonly files: clear attribute, set time, restore attribute
        readonly_cleared = False
        try:
            attrs = win32file.GetFileAttributes(path_str)
            if attrs & win32con.FILE_ATTRIBUTE_READONLY:
                win32file.SetFileAttributes(
                    path_str, attrs & ~win32con.FILE_ATTRIBUTE_READONLY
                )
                readonly_cleared = True
        except Exception:
            pass  # Best-effort

        try:
            handle = win32file.CreateFile(
                path_str,
                FILE_WRITE_ATTRIBUTES,
                win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE,
                None,
                win32con.OPEN_EXISTING,
                flags,
                None,
            )
            try:
                # Convert epoch float to datetime if needed
                if isinstance(created, (int, float)):
                    dt = datetime.datetime.fromtimestamp(created)
                else:
                    dt = created
                wintime = pywintypes.Time(dt)
                # SetFileTime(handle, creation, access, write) -- None leaves unchanged
                win32file.SetFileTime(handle, wintime, None, None)
            finally:
                handle.close()

            return True

        finally:
            # Restore readonly attribute if we cleared it
            if readonly_cleared:
                try:
                    attrs = win32file.GetFileAttributes(path_str)
                    win32file.SetFileAttributes(
                        path_str, attrs | win32con.FILE_ATTRIBUTE_READONLY
                    )
                except Exception:
                    pass

    except Exception as e:
        logger.debug(f"Failed to restore creation time for {path}: {e}")
        return False


__all__ = [
    # Main entry points
    'collect_file_metadata',
    'apply_file_metadata',
    # Windows-specific capabilities
    'is_win32_available',
    'restore_windows_creation_time',
    # Comparison & formatting helpers
    'compare_metadata',
    'get_metadata_summary',
    'metadata_to_json',
    # Timestamp utilities
    'collect_timestamp_info',
    'apply_timestamp_strategy',
]
