"""
File operations for copying, moving and verifying files.

This module provides functions for file operations with attribute preservation
across different platforms, including timestamps, permissions, and other metadata.
"""

import json
import os
import sys
import stat
import shutil
import errno
import logging
import datetime
import time
import platform
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple, Any, Set, Callable

from dazzle_lib import PathVariantResolver

# Set up module-level logger
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Atomic write primitives (v0.2.4)
# ---------------------------------------------------------------------------


def atomic_write_text(
    path: Union[str, Path],
    content: str,
    *,
    encoding: str = "utf-8",
    newline: Optional[str] = None,
) -> None:
    """Atomically write text content to ``path``.

    Writes ``content`` to a sibling ``.tmp`` file and then renames it to
    ``path`` via ``os.replace`` (atomic on POSIX and Windows since Python 3.3).
    Readers observing the file see either the old contents or the new
    contents -- never a partial write.

    Creates parent directories if they don't exist.

    Args:
        path: Destination file path.
        content: Text content to write.
        encoding: Text encoding (keyword-only, default ``utf-8``).
        newline: Newline translation, passed to ``open()`` (keyword-only,
            default None = universal).

    Raises:
        OSError: If the write or rename fails. The ``.tmp`` file is left
            in place for inspection.

    Pattern source: ``safedel/_store.py:_save_manifest`` and
    ``safedel/_volumes.py:save_registry`` both used this idiom; this
    function centralizes it.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding=encoding, newline=newline) as f:
        f.write(content)
    # Windows: antivirus/indexers briefly lock freshly-written files, so a
    # first os.replace can fail with PermissionError [WinError 5] even
    # though nothing of ours holds the file (observed in the wild: one
    # random victim test per dazzlecmd full-suite run). A short bounded
    # retry absorbs the transient; a REAL permission problem still
    # surfaces after ~0.3s total.
    for attempt in range(6):
        try:
            os.replace(str(tmp_path), str(path))
            break
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.01 * (2 ** attempt))  # 10..160ms backoff


def atomic_write_json(
    path: Union[str, Path],
    data: Any,
    *,
    indent: int = 2,
    sort_keys: bool = False,
    default: Optional[Callable[[Any], Any]] = str,
    trailing_newline: bool = True,
) -> None:
    """Atomically write ``data`` as JSON to ``path``.

    Thin wrapper around ``atomic_write_text(path, json.dumps(...))``.
    The default ``default=str`` handles common non-JSON-native types
    (``datetime``, ``Path``, ``pathlib.PurePath``, etc.) by stringifying
    them -- matches safedel's ``_save_manifest`` behavior.

    Args:
        path: Destination JSON file path.
        data: The object to serialize. Must be JSON-compatible or have
            a string representation if non-native types are present.
        indent: ``json.dumps`` indent (keyword-only, default 2).
        sort_keys: ``json.dumps`` sort_keys (keyword-only, default False).
        default: Fallback serializer for non-JSON types (keyword-only,
            default ``str``). Set to ``None`` to get ``TypeError`` on
            unknown types instead.
        trailing_newline: Append a trailing newline (keyword-only,
            default True, matching POSIX text file convention).

    Raises:
        TypeError: If ``data`` contains non-JSON types and ``default`` is None.
        OSError: If the underlying write fails.
    """
    text = json.dumps(data, indent=indent, sort_keys=sort_keys, default=default)
    if trailing_newline:
        text += "\n"
    atomic_write_text(path, text, encoding="utf-8")


class AtomicStreamWriter:
    """Streaming counterpart of :func:`atomic_write_text`.

    For content too large -- or too incremental -- to build in memory:
    writes go to a sibling ``.tmp`` file, and on successful close the tmp
    is renamed over ``path`` via ``os.replace``. Readers observing ``path``
    see either the old contents or the complete new contents, never a
    partial write. On failure (an exception inside the ``with`` block, or
    an explicit ``close(success=False)``) the destination is untouched and
    the tmp is removed.

    Options (all keyword-only):

    * ``resume_from_existing``: seed the tmp with the current contents of
      ``path`` (``shutil.copy2``) and open it in append mode -- for
      resuming an interrupted long-running write. When ``path`` does not
      exist this degrades to a normal fresh write.
    * ``fsync_on_flush``: make each :meth:`flush` also ``os.fsync``,
      bounding data loss to the last flush for observers tailing the tmp
      during very long runs (fsync failures are swallowed -- not every
      platform/filesystem supports it).
    * ``encoding`` / ``newline`` / ``buffering``: passed to ``open()``,
      with the same defaults as :func:`atomic_write_text`.

    Usage::

        with AtomicStreamWriter(dest, fsync_on_flush=True) as w:
            for chunk in produce():
                w.write(chunk)
                w.flush()

    Provenance: generalized from dazzlesum's ``MonolithicWriter`` (its
    streaming checksum-manifest writer), minus the domain concerns
    (headers, footers, overwrite prompts). The one-shot sibling of this
    class is :func:`atomic_write_text`.
    """

    def __init__(
        self,
        path: Union[str, Path],
        *,
        encoding: str = "utf-8",
        newline: Optional[str] = None,
        resume_from_existing: bool = False,
        fsync_on_flush: bool = False,
        buffering: int = -1,
    ) -> None:
        self.path = Path(path)
        self.tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        self.encoding = encoding
        self.newline = newline
        self.resume_from_existing = resume_from_existing
        self.fsync_on_flush = fsync_on_flush
        self.buffering = buffering
        self._file = None
        self._closed = False

    def __enter__(self) -> "AtomicStreamWriter":
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close(success=exc_type is None)

    def open(self) -> "AtomicStreamWriter":
        """Open the tmp file for writing (called automatically by ``with``)."""
        if self._file is not None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.resume_from_existing and self.path.exists():
            shutil.copy2(str(self.path), str(self.tmp_path))
            mode = "a"
        else:
            mode = "w"
        self._file = open(
            self.tmp_path, mode,
            encoding=self.encoding, newline=self.newline,
            buffering=self.buffering,
        )
        self._closed = False
        return self

    def write(self, text: str) -> None:
        """Write ``text`` to the tmp file."""
        if self._file is None:
            raise ValueError("AtomicStreamWriter is not open")
        self._file.write(text)

    def flush(self) -> None:
        """Flush buffered writes to the tmp file (and fsync when enabled)."""
        if self._file is None:
            raise ValueError("AtomicStreamWriter is not open")
        self._file.flush()
        if self.fsync_on_flush:
            try:
                os.fsync(self._file.fileno())
            except (OSError, AttributeError):
                # fsync is not available on every platform/filesystem
                pass

    def close(self, success: bool = True) -> None:
        """Finalize: rename tmp over ``path`` on success, discard it otherwise.

        Idempotent; safe to call after the ``with`` block has already
        closed the writer.
        """
        if self._closed:
            return
        self._closed = True
        try:
            if self._file is not None:
                self._file.close()
                self._file = None
            if success:
                os.replace(str(self.tmp_path), str(self.path))
            else:
                self._discard_tmp()
        except Exception:
            self._discard_tmp()
            raise

    def _discard_tmp(self) -> None:
        try:
            if self.tmp_path.exists():
                os.remove(str(self.tmp_path))
        except OSError as e:
            logger.warning(f"Could not remove temp file {self.tmp_path}: {e}")


# ---------------------------------------------------------------------------
# Link-safe tree copy (v0.2.4)
# ---------------------------------------------------------------------------


def copy_tree_preserving_links(
    src: Union[str, Path],
    dst: Union[str, Path],
    *,
    dirs_exist_ok: bool = False,
    ignore: Optional[Callable[..., Any]] = None,
    ignore_dangling_symlinks: bool = False,
) -> Path:
    """Copy a directory tree, preserving symlinks and junctions literally.

    This is a wrapper around ``shutil.copytree`` with ``symlinks=True``
    hard-wired. The ``symlinks=True`` behavior is the whole point: when
    ``copytree`` encounters a symlink or junction, it copies the LINK
    (recording the target path) rather than recursing into the target.

    Why this matters: on Windows, the default ``symlinks=False`` will
    traverse a junction and copy everything under it, which can loop
    forever on self-referential junctions or pull in unexpectedly large
    trees. This wrapper makes the safe behavior the default and the
    name documents the intent.

    Args:
        src: Source directory path.
        dst: Destination directory path.
        dirs_exist_ok: If True, allow ``dst`` to exist (keyword-only,
            default False -- matches shutil.copytree's default).
        ignore: Callable ``(dir, contents) -> names_to_skip`` passed to
            ``shutil.copytree`` (keyword-only).
        ignore_dangling_symlinks: If True, skip symlinks whose target is
            missing (keyword-only, default False -- by default
            ``copytree`` raises on dangling links).

    Returns:
        The destination Path.

    Pattern source: ``safedel/_recover.py:338`` and other safedel call
    sites all used ``shutil.copytree(..., symlinks=True)``. Centralized
    here so the safety property has a name.
    """
    result = shutil.copytree(
        str(src),
        str(dst),
        symlinks=True,
        ignore=ignore,
        ignore_dangling_symlinks=ignore_dangling_symlinks,
        dirs_exist_ok=dirs_exist_ok,
    )
    return Path(result)


def copy_file(
    source: Union[str, Path], 
    destination: Union[str, Path],
    preserve_attrs: bool = True,
    overwrite: bool = False,
    *,
    try_path_variants: bool = False,
    resolver: Optional[PathVariantResolver] = None,
) -> bool:
    """
    Copy a file with attribute preservation.

    Args:
        source: Source file path
        destination: Destination file path
        preserve_attrs: Whether to preserve file attributes
        overwrite: Whether to overwrite the destination if it exists
        try_path_variants: If True, retry under alternative names for source/
            destination (e.g. a UNC path and its mapped-drive equivalent) when
            the first attempt fails (STACK-MAP D7 fallback). Off by default;
            default behavior is unchanged.
        resolver: A dazzle_lib.PathVariantResolver supplying name variants;
            only consulted when try_path_variants=True (default: unctools).

    Returns:
        True if successful, False otherwise
    """
    if try_path_variants:
        from . import _fallback
        return _fallback.retry_pair_bool(
            lambda s, d: copy_file(s, d, preserve_attrs, overwrite),
            str(source), str(destination),
            feature="copy_file(try_path_variants=True)", resolver=resolver,
        )
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
    overwrite: bool = False,
    *,
    try_path_variants: bool = False,
    resolver: Optional[PathVariantResolver] = None,
) -> bool:
    """
    Move a file with attribute preservation.

    Args:
        source: Source file path
        destination: Destination file path
        preserve_attrs: Whether to preserve file attributes
        overwrite: Whether to overwrite the destination if it exists
        try_path_variants: If True, retry under alternative names for source/
            destination when the first attempt fails (STACK-MAP D7 fallback).
            Off by default; default behavior is unchanged.
        resolver: A dazzle_lib.PathVariantResolver supplying name variants;
            only consulted when try_path_variants=True (default: unctools).

    Returns:
        True if successful, False otherwise
    """
    if try_path_variants:
        from . import _fallback
        return _fallback.retry_pair_bool(
            lambda s, d: move_file(s, d, preserve_attrs, overwrite),
            str(source), str(destination),
            feature="move_file(try_path_variants=True)", resolver=resolver,
        )
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


def open_file(
    path: Union[str, Path],
    mode: str = "r",
    encoding: Optional[str] = None,
    *,
    try_path_variants: bool = False,
    resolver: Optional[PathVariantResolver] = None,
    **kwargs,
):
    """Open a file, optionally retrying under alternative path names.

    A fallback-aware ``open()``: with ``try_path_variants=True``, a failed open
    (e.g. a UNC name blocked by a Windows security zone, even though the file
    exists) is retried under the path's other names from ``resolver`` (default:
    the unctools-backed resolver), re-raising the original error if every
    variant fails. This is the file-handle counterpart of
    ``copy_file(try_path_variants=True)`` and reproduces the old
    ``unctools.safe_open`` capability (STACK-MAP D7).

    ``mode``, ``encoding`` and any extra ``**kwargs`` are forwarded to the
    built-in ``open``; the return value is the file object. Off by default, so
    ``open_file(path)`` behaves exactly like ``open(path)``.
    """
    if try_path_variants:
        from . import _fallback
        return _fallback.retry_single(
            lambda p: open(p, mode=mode, encoding=encoding, **kwargs),
            str(path), feature="open_file(try_path_variants=True)", resolver=resolver,
        )
    return open(path, mode=mode, encoding=encoding, **kwargs)


def collect_file_metadata(path: Union[str, Path]) -> Dict[str, Any]:
    """
    Collect file metadata for preservation.

    As of v0.2.4, this is a thin wrapper around
    ``dazzle_filekit.metadata.collect_file_metadata`` which captures a
    strict superset of v0.2.3's output:

      - File mode, size, owner/group, timestamps (with ISO projections)
      - **Windows**: attribute flag booleans (is_hidden/is_system/...),
        SDDL ACL string (JSON-safe), owner/group as DOMAIN\\Name
      - **Linux/macOS**: extended attributes (xattrs) as base64

    Callers that only read the v0.2.3 fields are unaffected; the new keys
    are additive. Use ``dazzle_filekit.metadata`` directly for access to
    ``compare_metadata``, ``metadata_to_json``, etc.

    Args:
        path: Path to the file

    Returns:
        Dictionary of file metadata
    """
    from .metadata import collect_file_metadata as _collect
    return _collect(path)


def apply_file_metadata(path: Union[str, Path], metadata: Dict[str, Any]) -> bool:
    """
    Apply metadata to a file.

    As of v0.2.4, this is a thin wrapper around
    ``dazzle_filekit.metadata.apply_file_metadata`` which honors all the
    richer fields when present:

      - **Windows**: SDDL ACL restoration via
        ``ConvertStringSecurityDescriptorToSecurityDescriptorW``; creation
        time restoration via ``SetFileTime`` + ``FILE_WRITE_ATTRIBUTES``
      - **Linux/macOS**: extended attributes via ``os.setxattr``, with
        ``com.apple.quarantine`` skipped on restore

    Old (v0.2.3) manifests without the new fields restore correctly --
    each advanced field is optional.

    Args:
        path: Path to the file
        metadata: Metadata to apply

    Returns:
        True if successful, False otherwise
    """
    from .metadata import apply_file_metadata as _apply
    return _apply(path, metadata)


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


# v0.2.4: the old _collect_windows_metadata, _apply_windows_metadata, and
# _apply_unix_metadata helpers were removed. The richer equivalents live in
# dazzle_filekit.metadata (which collect_file_metadata / apply_file_metadata
# delegate to above). See BREAKING_CHANGES.md for the migration notes.


def copy_files_with_path(
    source_files: List[Union[str, Path]],
    source_base: Union[str, Path],
    dest_base: Union[str, Path],
    path_style: str = 'relative',
    include_base: bool = False,
    preserve_attrs: bool = True,
    overwrite: bool = False,
    *,
    try_path_variants: bool = False,
    resolver: Optional[PathVariantResolver] = None,
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
            
            # Copy the file (per-file variant fallback when requested)
            success = copy_file(source_path, dest_path, preserve_attrs, overwrite,
                                try_path_variants=try_path_variants, resolver=resolver)
            
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
    overwrite: bool = False,
    *,
    try_path_variants: bool = False,
    resolver: Optional[PathVariantResolver] = None,
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
            
            # Move the file (per-file variant fallback when requested)
            success = move_file(source_path, dest_path, preserve_attrs, overwrite,
                                try_path_variants=try_path_variants, resolver=resolver)
            
            # Record the result
            results[str(source_path)] = (success, dest_path)
            
        except Exception as e:
            logger.error(f"Error moving {source_path}: {e}")
            results[str(source_path)] = (False, source_path)

    return results


def process_files(
    directory: Union[str, Path],
    callback: Callable[[Path], Any],
    pattern: str = "*",
    recursive: bool = True,
    *,
    try_path_variants: bool = False,
    resolver: Optional[PathVariantResolver] = None,
) -> Dict[str, Any]:
    """Apply ``callback`` to every file under ``directory`` matching ``pattern``.

    The flat batch-apply primitive -- the L1 home of the old
    ``unctools.process_files``: globs ``directory`` for ``pattern`` (recursive
    by default), calls ``callback(Path)`` on each file, and returns
    ``{str(path): result}``. Per-file exceptions are swallowed (logged, result
    recorded as ``None``) so one bad file does not abort the batch.

    This is NOT a tree traversal (no depth/filter model -- that is
    dazzletreelib's domain); it is the generic sibling of
    ``copy_files_with_path``.

    Args:
        directory: Directory to scan.
        callback: Called with each matching file's ``Path``; its return value
            is stored in the result map.
        pattern: Glob pattern (default ``*``).
        recursive: Recurse into subdirectories (default True).
        try_path_variants: If True and ``directory`` does not exist under the
            given name, retry under the variant names from ``resolver`` (the
            directory-name fallback the original did).
        resolver: A dazzle_lib.PathVariantResolver; only consulted when
            ``try_path_variants=True`` (default: unctools).

    Returns:
        ``{str(file_path): callback_result_or_None}``.
    """
    dir_path = Path(directory)
    results: Dict[str, Any] = {}

    if try_path_variants and not dir_path.exists():
        from . import _fallback
        for cand in _fallback.variants_of(str(dir_path), resolver):
            if Path(cand).exists():
                dir_path = Path(cand)
                break

    if not dir_path.exists():
        logger.error(f"Directory not found: {dir_path}")
        return results

    glob_pattern = f"**/{pattern}" if recursive else pattern
    for file_path in dir_path.glob(glob_pattern):
        if file_path.is_file():
            try:
                results[str(file_path)] = callback(file_path)
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")
                results[str(file_path)] = None

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
    On Windows, attempts an escalating chain (see ``_create_windows_symlink``):
    1. os.symlink (requires Developer Mode or admin on Windows 10+)
    2. win32file.CreateSymbolicLink with the unprivileged-create flag
    3. mklink via a non-elevated cmd subprocess
    4. PowerShell elevation (Start-Process -Verb RunAs)

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
    # Keep the caller's raw target string for creation: Path() round-trips
    # normalize segments (``a\.\b`` -> ``a\b``, ``/`` -> ``\\``), but a link's
    # stored target must be able to reproduce the caller's bytes exactly
    # (mirroring reads it back via os.readlink and expects equality).
    raw_target = os.fspath(target)
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

    # Auto-detect if target is a directory. Relative targets resolve against
    # the LINK's parent directory (link semantics), not the process CWD. A
    # broken target probes False -- callers recreating an existing link (e.g.
    # mirroring) must pass target_is_directory explicitly from the source
    # link's own kind, since a broken DIRECTORY symlink cannot be inferred.
    if target_is_directory is None:
        probe = (target_path if target_path.is_absolute()
                 else link_path.parent / raw_target)
        target_is_directory = probe.is_dir()

    # Try to create symlink
    if platform.system() != 'Windows':
        # Unix: straightforward symlink
        try:
            os.symlink(raw_target, str(link_path))
            logger.debug(f"Created symlink: {link_path} -> {raw_target}")
            return True
        except Exception as e:
            logger.error(f"Failed to create symlink on Unix: {e}")
            return False

    # Windows: try multiple methods
    return _create_windows_symlink(raw_target, link_path, target_is_directory)


def _create_windows_symlink(
    target: Union[str, Path], link: Path, is_directory: bool
) -> bool:
    """
    Create a symbolic link on Windows using an escalating chain of methods.

    Each method is tried until one succeeds:
      1. ``os.symlink`` -- works with Developer Mode enabled, no elevation.
      2. ``win32file.CreateSymbolicLink`` with
         ``SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE`` (0x2) -- a clean Win32
         API path with no subprocess (Windows 10 v1703+).
      3. ``mklink`` via a non-elevated ``cmd`` subprocess.
      4. PowerShell ``Start-Process -Verb RunAs`` (elevated ``mklink``), then a
         brief poll because the elevated process runs asynchronously.

    Methods 2 and 4 were absorbed from ``dazzlelink.operations.create_windows_symlink``
    so filekit no longer imports dazzlelink for symlink creation (the L1->L2
    upward edge is cut). filekit's bool contract is preserved: total failure
    returns False (dazzlelink raised).

    Args:
        target: Target path. Passed through VERBATIM (no Path normalization)
            so the stored reparse target reproduces the caller's bytes.
        link: Link path to create
        is_directory: Whether target is a directory

    Returns:
        True if successful, False otherwise
    """
    target_str = os.fspath(target)
    link_str = str(link)

    # Method 1: os.symlink (Developer Mode enabled)
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

    # Method 2: win32file.CreateSymbolicLink with the unprivileged-create flag
    # (absorbed from dazzlelink). Clean API, no subprocess; Windows 10 v1703+.
    try:
        import win32file
        flags = win32file.SYMBOLIC_LINK_FLAG_DIRECTORY if is_directory else 0
        flags |= 0x2  # SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE
        if win32file.CreateSymbolicLink(link_str, target_str, flags):
            logger.debug(f"Created Windows symlink using win32file API: {link} -> {target}")
            return True
        logger.debug("win32file.CreateSymbolicLink returned falsy, trying mklink fallback")
    except ImportError:
        logger.debug("win32file not available, trying mklink fallback")
    except Exception as e:
        logger.warning(f"win32file symlink creation failed: {e}")

    # Method 3: mklink via a non-elevated cmd subprocess.
    dir_flag = '/D ' if is_directory else ''
    mklink_cmd = f'mklink {dir_flag}"{link_str}" "{target_str}"'
    try:
        result = subprocess.run(
            ['cmd', '/c', mklink_cmd],
            text=True, capture_output=True, check=False,
        )
        if result.returncode == 0:
            logger.debug(f"Created Windows symlink using mklink: {link} -> {target}")
            return True
        logger.warning(f"mklink failed: {result.stderr.strip()}")
    except Exception as e:
        logger.warning(f"mklink command failed: {e}")

    # Method 4: PowerShell elevation (absorbed from dazzlelink). Prompts UAC and
    # runs asynchronously, so poll briefly for the link to appear. (The inner
    # mklink is single-quoted as the PowerShell ArgumentList, fixing the nested
    # double-quote bug in the original dazzlelink implementation.)
    try:
        ps_cmd = f"Start-Process cmd.exe -Verb RunAs -ArgumentList '/c {mklink_cmd}'"
        subprocess.run(['powershell', '-NoProfile', '-Command', ps_cmd], check=True)
        for _ in range(5):
            if os.path.exists(link_str):
                logger.debug(f"Created Windows symlink using elevated mklink: {link} -> {target}")
                return True
            time.sleep(1)
        logger.warning("Elevated mklink requested but the link could not be verified")
    except Exception as e:
        logger.warning(f"Elevated symlink creation failed: {e}")

    # All methods failed
    logger.error(
        f"Failed to create symlink on Windows. This typically requires either:\n"
        f"  1. Developer Mode enabled (Settings > Update & Security > For developers)\n"
        f"  2. Running as Administrator\n"
        f"  3. pywin32 installed (for the unprivileged-create API)"
    )
    return False
