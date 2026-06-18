# API Reference

Full function reference for `dazzle_filekit`. For a quick-start walkthrough,
see the [README](../README.md). For the locked public API surface that
external tools depend on, see [api-stability.md](api-stability.md).

## Table of Contents

- [Cross-Platform Utilities](#cross-platform-utilities)
- [Path Functions](#path-functions)
- [File Operations](#file-operations)
- [Metadata Module](#metadata-module)
- [Platform-Specific (Windows)](#platform-specific-windows)
- [Disk Space Functions](#disk-space-functions)
- [Verification Functions](#verification-functions)
- [Utility Functions](#utility-functions)
- [Validation Functions](#validation-functions)
- [Logging Configuration](#logging-configuration)

---

## Cross-Platform Utilities

All three path normalizers live in `dazzle_filekit.paths` and are
re-exported at the top level. In v0.2.4 they all route through the
same canonical implementation.

- `normalize_cross_platform_path(path, *, resolve=False)` — **Canonical**
  path normalizer (v0.2.4). Handles Git Bash `/c/`, WSL `/mnt/c/`,
  Windows `C:\` / `C:/`, tilde (`~/`), env vars (`%USERPROFILE%` /
  `$HOME`), `\\?\` extended-length prefix, and platform-direction
  conversion. With `resolve=True`, follows symlinks via `Path.resolve()`.
  Bare drive letters (e.g. `/c`) map to the drive root (`C:\`) so the
  result is genuinely absolute.
- `resolve_cross_platform_path(path)` — Normalize and probe alternate
  platform formats when the result doesn't exist on disk (existence-
  aware). Used by filekit's own path-recovery workflows and by
  `dazzlecmd/projects/core/fixpath` for CLI-noise handling.
- `path_exists_cross_platform(path)` — Check path existence across
  cross-platform formats.
- `is_windows()` / `is_unix()` / `is_wsl()` — Platform detection.
  `is_wsl()` (v0.2.4) returns True when running inside WSL (checks
  `WSL_DISTRO_NAME` env var + `/proc/version` scan).

### Path Functions

The following path helpers live in `dazzle_filekit.paths`:

- `normalize_path(path)` / `normalize_path_no_resolve(path)` —
  Backwards-compatibility wrappers for
  `normalize_cross_platform_path(path, resolve=True)` and
  `resolve=False` respectively. Kept for API stability per
  [api-stability.md](api-stability.md); preferred entry point for
  new code is `normalize_cross_platform_path`.
- `is_same_file(path1, path2)` — Check if two paths refer to the same
  underlying file (via `os.path.samefile()` semantics).
- `split_drive_letter(path)` — Split drive letter from path (Windows).
- `is_unc_path(path)` — Check if path is UNC format.
- `get_relative_path(path, base)` — Get relative path from base.
- `find_files(directory, patterns, exclude)` — Find files matching
  glob patterns.
- `find_regex_files(directory, pattern)` — Find files matching a regex.
- `collect_files_from_include_file(include_file)` — Read a list of
  files from an include file (for batch operations).
- `create_parent_dirs(path)` — Create parent directories for a path.
- `ensure_unique_path(path)` — Generate a unique path by appending
  a counter if the original exists.
- `create_dest_path(src, src_base, dst_base, path_style, include_base)` —
  Build a destination path for batch file operations.
- `get_path_type(path)` — Detect path type (`unc`, `network`, `subst`,
  `local`).

---

## File Operations

Core operations live in `dazzle_filekit.operations` and are re-exported
at the top level.

### Basic copy, move, remove

- `copy_file(src, dst, preserve_attrs=True, overwrite=False)` — Copy
  a single file with optional attribute preservation. On Windows,
  uses robocopy as a fallback for rich attribute handling when
  pywin32 is available.
- `move_file(src, dst, preserve_attrs=True, overwrite=False)` — Move
  a single file with optional attribute preservation.
- `copy_files_with_path(source_files, source_base, dest_base, path_style='relative', include_base=False, preserve_attrs=True, overwrite=False)` —
  Batch copy with path style control (`relative`, `absolute`, `flat`).
- `move_files_with_path(source_files, source_base, dest_base, ...)` —
  Batch move counterpart.
- `create_directory_structure(dest_path, directory_paths)` — Create
  a directory tree from a list.
- `remove_file(path, force=False)` — Remove a file safely.
- `remove_directory(path, recursive=True, force=False)` — Remove a
  directory.
- `create_symlink(target, link, force=False, target_is_directory=None)` —
  Create a symbolic link. On Windows, uses `os.symlink` with fallbacks:
  `dazzlelink` library → `mklink` command.

### Metadata convenience wrappers

These delegate to the rich `dazzle_filekit.metadata` module as of v0.2.4:

- `collect_file_metadata(path)` — Collect rich file metadata. Returns
  a dict with SDDL ACLs on Windows, xattrs on Unix, NTFS ctime,
  attribute flags, owner/group, ISO timestamps, and size.
- `apply_file_metadata(path, metadata)` — Apply metadata to a file.
  Honors all rich fields (SDDL, ctime, xattrs) when present.

### Atomic write primitives (v0.2.4)

- `atomic_write_text(path, content, *, encoding='utf-8', newline=None)` —
  Tmp+rename atomic text write. Creates parent directories if needed.
  Atomic on POSIX and Windows (Python ≥ 3.3).
- `atomic_write_json(path, data, *, indent=2, sort_keys=False, default=str, trailing_newline=True)` —
  Atomic JSON write. `default=str` handles `Path`/`datetime`/other
  non-JSON-native types out of the box.
- `copy_tree_preserving_links(src, dst, *, dirs_exist_ok=False, ignore=None, ignore_dangling_symlinks=False)` —
  `shutil.copytree(symlinks=True)` wrapper with documented intent.
  Never traverses junctions on Windows.

---

## Metadata Module

Rich metadata capture and application. Import via
`from dazzle_filekit import metadata` or
`from dazzle_filekit.metadata import ...`.

### Main entry points

- `metadata.collect_file_metadata(path)` — Rich capture. On Windows
  returns a dict with SDDL security descriptor string, attribute
  flag booleans (`is_hidden`, `is_system`, `is_readonly`, `is_archive`),
  owner/group as `DOMAIN\Name` strings, creation time, ISO timestamp
  projections, and size. On Linux/macOS returns POSIX mode, owner/group
  (uid/gid), extended attributes (xattrs) as a base64-encoded dict,
  and ISO timestamps.
- `metadata.apply_file_metadata(path, md)` — Rich apply. Honors SDDL
  ACLs via `ConvertStringSecurityDescriptorToSecurityDescriptorW`,
  ctime via `SetFileTime`, and xattrs via `os.setxattr` (skipping
  `com.apple.quarantine` on restore).

### Windows-specific helpers

- `metadata.restore_windows_creation_time(path, created)` — NTFS ctime
  restoration via pywin32 `SetFileTime`. Handles directories via
  `FILE_FLAG_BACKUP_SEMANTICS` and readonly files via a
  clear-then-restore dance.
- `metadata.is_win32_available()` — Cached pywin32 availability probe.

### Diff / projection helpers

- `metadata.compare_metadata(md1, md2)` — Diff two metadata dicts.
  Returns only the differences. Allows a 2-second timestamp tolerance
  to account for filesystem precision.
- `metadata.metadata_to_json(md)` — JSON-safe projection of a metadata
  dict (recursively converts non-JSON types to strings or base64).
- `metadata.get_metadata_summary(md)` — Human-readable summary with
  formatted size, timestamps, permissions, and attribute list.

### Timestamp-only helpers

- `metadata.collect_timestamp_info(path)` — Timestamp-only capture
  (without the rest of the metadata).
- `metadata.apply_timestamp_strategy(path, strategy, link_timestamps=None, target_timestamps=None)` —
  Strategy-based timestamp apply for symlink restoration workflows.
  Strategies: `'current'`, `'symlink'`, `'target'`, `'preserve-all'`.

### Private helpers (not in `__all__`, but reachable)

- `metadata._collect_unix_xattrs(path)` — Linux/macOS xattrs via
  `os.listxattr` / `os.getxattr`, base64-encoded.
- `metadata._apply_unix_xattrs(path, xattrs)` — Apply xattrs, skipping
  `com.apple.quarantine`.

---

## Platform-Specific (Windows)

Import via `from dazzle_filekit.platform import windows`. All functions
return safe defaults (empty list / False) when pywin32 or ctypes aren't
available.

### Admin detection

- `windows.is_admin()` — Check if the current process has admin
  privileges via `win32security.IsUserAnAdmin`.

### NTFS Alternate Data Streams (v0.2.4)

- `windows.detect_alternate_streams(path)` — Enumerate NTFS ADS via
  ctypes `FindFirstStreamW` / `FindNextStreamW`. Filters out `::$DATA`
  (the main data stream) and `:Zone.Identifier:$DATA` (browser
  download marker).
- `windows.has_significant_ads(path)` — Returns True if any non-ignored
  stream exists. Useful as a warning check before cross-device copy
  (ADS are lost on non-NTFS destinations).

---

## Disk Space Functions

Disk space checking and size calculation. All functions are cross-
platform via `shutil.disk_usage`.

- `get_disk_usage(path)` — Get `DiskUsage` (named tuple with `total`,
  `used`, `free`, plus `used_percent` / `free_percent` properties).
- `check_disk_space(dest_path, required_bytes, safety_margin=0.1, raise_on_insufficient=False)` —
  Check if destination has sufficient space. Returns
  `(has_space, required_with_margin, available, message)`. Set
  `raise_on_insufficient=True` to raise `InsufficientSpaceError`
  instead of returning `False`.
- `calculate_total_size(paths, follow_symlinks=True)` — Calculate
  total size of files/directories (recursive for directories).
- `ensure_disk_space(dest_path, source_paths, safety_margin=0.1)` —
  Verify space for a copy operation: computes total size of sources,
  checks destination. Returns `(has_space, message)`.

### Classes and exceptions

- `DiskUsage` — Named tuple with `total`, `used`, `free`, `used_percent`,
  `free_percent`.
- `InsufficientSpaceError(Exception)` — Raised when destination lacks
  space (when `raise_on_insufficient=True`).

---

## Verification Functions

File content verification via hash algorithms. Supports MD5, SHA1,
SHA256, SHA512 and other `hashlib`-compatible algorithms.

- `calculate_file_hash(path, algorithm='sha256')` — Calculate file hash.
- `verify_file_hash(path, expected_hash, algorithm='sha256')` — Verify
  a file matches an expected hash.
- `verify_files_with_manifest(manifest_path)` — Verify files against
  a saved hash manifest.
- `calculate_directory_hashes(directory, algorithm='sha256')` — Hash
  all files in a directory tree.
- `save_hashes_to_file(hashes, output_file)` — Persist a hash dict to
  a file.
- `load_hashes_from_file(hash_file)` — Load a persisted hash dict.
- `compare_directories(dir1, dir2)` — Compare directory contents by
  file existence, size, and hash.
- `verify_copied_files(src_dir, dst_dir)` — Verify a copy operation
  produced matching files in the destination.

---

## Utility Functions

### Platform detection (`utils.compat`)

- `is_windows()` / `is_unix()` / `is_wsl()` — Platform detection.
- `is_admin()` / `is_root()` — Privilege detection.
- `fix_path_separators(path)` — Normalize path separators to OS native.
- `fix_path_case(path)` — Normalize case where the filesystem is
  case-insensitive.
- `get_system_encoding()` — Get the filesystem encoding.
- `get_system_temp_dir()` — Cross-platform temp directory.
- `get_home_dir()` — Current user's home directory.
- `get_app_data_dir(app_name)` — Application data directory
  (`%APPDATA%\<app>` on Windows, `~/.config/<app>` on Linux,
  `~/Library/Application Support/<app>` on macOS).
- `get_drive_mappings()` — **removed in 0.3.0** (DazzleLib stack V9). Drive↔UNC
  mapping is path-identity knowledge owned by L0; its `win32wnet` provider-chain
  scan was folded into `unctools` (≥0.2.2). Use `unctools.get_mappings()` /
  `unctools.get_reverse_mappings()`.

### Low-level disk helpers (`utils.disk`)

Same surface as the top-level disk functions above, plus internal
helpers that aren't typically used directly.

---

## Validation Functions

Path validation helpers in `dazzle_filekit.utils.validation`.

- `is_valid_path(path)` — Check if a path string is valid for the
  current platform.
- `is_safe_path(path, base_path)` — Check if a path is safely contained
  within a base path (prevents directory traversal).
- `validate_path_chars(path)` — Check for invalid characters.
- `is_absolute_path(path)` / `is_relative_path(path)` — Absolute/
  relative check.
- `is_unc_path(path)` — UNC path detection (also exported at top level).
- `is_hidden_path(path)` — Hidden file detection (platform-aware).
- `is_symlink(path)` — Symlink detection.
- `is_junction(path)` — Junction detection (Windows). **Fixed in
  v0.2.4** to use `DeviceIoControl(FSCTL_GET_REPARSE_POINT)` and
  correctly distinguish junctions (`IO_REPARSE_TAG_MOUNT_POINT`)
  from directory symlinks (`IO_REPARSE_TAG_SYMLINK`).

---

## Logging Configuration

- `configure_logging(level=logging.INFO, log_file=None)` — Configure
  package-level logging. Optionally log to a file.
- `enable_verbose_logging()` — Shortcut for `configure_logging(DEBUG)`.

---

## Version

- `__version__` — Package version string. Currently `'0.2.4'`.
