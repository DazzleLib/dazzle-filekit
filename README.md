# dazzle-filekit

[![Release Date](https://img.shields.io/github/release-date/DazzleLib/dazzle-filekit?color=green)](https://github.com/DazzleLib/dazzle-filekit/releases)
[![PyPI](https://img.shields.io/pypi/v/dazzle-filekit?color=green)](https://pypi.org/project/dazzle-filekit/)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/dazzle-filekit?period=total&units=international_system&left_color=black&right_color=green&left_text=downloads)](https://pepy.tech/projects/dazzle-filekit)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![GitHub Discussions](https://img.shields.io/github/discussions/DazzleLib/dazzle-filekit)](https://github.com/DazzleLib/dazzle-filekit/discussions)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](docs/platform-support.md)

> **Cross-platform file operations with path handling, verification, and metadata preservation.**

A Python toolkit for reliable file operations across Windows, Linux, and macOS. Handles path normalization between Git Bash, WSL, and native formats, file verification with multiple hash algorithms, and metadata-preserving copy/move operations.

## Features

- **Cross-Platform Paths** - Normalize between Git Bash (`/c/...`), WSL (`/mnt/c/...`), and native Windows/Unix paths via a single canonical `normalize_cross_platform_path(path, *, resolve=False)` entry point
- **Rich Metadata Preservation** - `dazzle_filekit.metadata` module captures Windows SDDL ACLs (JSON-serializable), NTFS creation time, Unix extended attributes, and attribute flag booleans; restore-on-recovery preserves everything via `pywin32.SetFileTime` for ctime
- **File Operations** - Copy, move, and manage files with metadata preservation
- **Atomic Write Primitives** - `atomic_write_text` / `atomic_write_json` use tmp+rename for crash-safe config and manifest writes
- **Link-Safe Tree Copy** - `copy_tree_preserving_links` wraps `shutil.copytree(symlinks=True)` with documented intent (never traverses junctions on Windows)
- **NTFS ADS Detection** - `platform.windows.detect_alternate_streams` enumerates alternate data streams via `FindFirstStreamW`; `has_significant_ads` filters out browser Zone.Identifier noise
- **Correct Junction Detection** - `is_junction` uses `DeviceIoControl(FSCTL_GET_REPARSE_POINT)` to distinguish real junctions (`IO_REPARSE_TAG_MOUNT_POINT`) from directory symlinks
- **File Verification** - Calculate and verify file hashes (MD5, SHA1, SHA256, SHA512)
- **Disk Space Checking** - Pre-flight space verification before operations
- **Platform Support** - Windows, Linux, and macOS with platform-specific optimizations
- **UNC Path Detection** - Native `is_unc_path` / `get_path_type` helpers; optional [UNCtools](https://github.com/DazzleLib/UNCtools) peer for UNC ↔ drive-letter translation (see [docs/unctools-integration.md](docs/unctools-integration.md))

## Why dazzle-filekit?

While Python's standard library (`shutil`, `pathlib`, `os`) provides basic file operations, dazzle-filekit offers:

- **Metadata Preservation**: Automatic preservation of timestamps, permissions, and extended attributes across platforms
- **Hash Verification**: Built-in file verification with multiple hash algorithms (MD5, SHA1, SHA256, SHA512)
- **Cross-Platform Path Handling**: Unified API for handling Windows UNC paths, network drives, and Unix paths
- **Batch Operations**: Process entire directory trees with pattern matching and filtering
- **Safe Operations**: Built-in conflict resolution, unique path generation, and error handling
- **Directory Comparison**: Compare directory contents and verify file integrity across locations

dazzle-filekit was designed for applications requiring reliable file operations with verification, such as backup tools, file synchronization, and data preservation systems (like the [preserve](https://github.com/DazzleTools/preserve) project).

## Installation

```bash
pip install dazzle-filekit
```

### Optional Dependencies

```bash
# UNCtools peer install (enables UNC ↔ drive-letter translation
# via user-side composition; filekit does not import unctools directly).
# See docs/unctools-integration.md for composition patterns.
pip install 'dazzle-filekit[unctools]'

# Development tools
pip install 'dazzle-filekit[dev]'
```

## Quick Start

### Cross-Platform Path Handling

```python
from dazzle_filekit import (
    normalize_cross_platform_path,
    resolve_cross_platform_path,
    path_exists_cross_platform,
)

# Convert Git Bash style paths to native format
# On Windows: /c/Users/foo -> C:\Users\foo
# On Unix: C:\Users\foo -> /c/Users/foo
path = normalize_cross_platform_path("/c/Users/foo/file.txt")

# Also handles WSL paths: /mnt/c/Users/...
path = normalize_cross_platform_path("/mnt/c/Users/foo/file.txt")

# Resolve with probing: if the normalized path doesn't exist,
# tries alternate platform formats (WSL, MSYS, Windows)
path = resolve_cross_platform_path("/mnt/c/Users/foo/file.txt")

# Check if a cross-platform path exists (uses resolve internally)
if path_exists_cross_platform("/c/Users/foo/file.txt"):
    print("File exists!")
```

### Path Operations

```python
from dazzle_filekit import normalize_path, find_files, is_unc_path

# Normalize paths (returns Path object)
path = normalize_path("/some/path/../file.txt")
print(path)  # PosixPath('/some/file.txt') or WindowsPath('C:/some/file.txt')

# Find files with patterns (returns list of path strings)
files = find_files("/directory", patterns=["*.py", "*.txt"])

# Check UNC paths
if is_unc_path(r"\\server\share"):
    print("This is a UNC path")
```

### File Operations

```python
from dazzle_filekit import copy_file, collect_file_metadata, create_symlink

# Copy file with attribute preservation (timestamps, permissions, etc.)
success = copy_file("source.txt", "dest.txt", preserve_attrs=True)

# Collect file metadata (v0.2.4: returns SDDL ACLs on Windows,
# xattrs on Linux/macOS, ctime, and ISO timestamps alongside the raw floats)
metadata = collect_file_metadata("file.txt")
print(f"Size: {metadata['size']}, Modified: {metadata['timestamps']['modified_iso']}")

# Create symbolic link (cross-platform, with Windows fallbacks)
success = create_symlink("/path/to/target", "/path/to/link")

# Force replace existing link
success = create_symlink("/new/target", "/path/to/link", force=True)
```

### Disk Space Checking

```python
from dazzle_filekit import get_disk_usage, check_disk_space, ensure_disk_space

# Get disk usage statistics
usage = get_disk_usage("/path/to/check")
print(f"Total: {usage.total}, Free: {usage.free}, Used: {usage.used_percent:.1f}%")

# Check if space is available for an operation
has_space, required, available, message = check_disk_space(
    "/destination",
    required_bytes=1_000_000_000,  # 1GB
    safety_margin=0.1  # 10% extra margin
)

# Check space for a list of source files
has_space, message = ensure_disk_space(
    dest_path="/destination",
    source_paths=["/path/to/file1.zip", "/path/to/dir/"]
)
```

### File Verification

```python
from dazzle_filekit import calculate_file_hash, verify_file_hash

# Calculate hash
hash_value = calculate_file_hash("file.txt", algorithm="sha256")

# Verify hash
is_valid = verify_file_hash("file.txt", expected_hash, algorithm="sha256")
```

### Atomic Writes (v0.2.4)

```python
from dazzle_filekit import atomic_write_text, atomic_write_json

# Atomic text write (tmp + os.replace). Crash mid-write leaves the
# original file intact; readers see either the old or the new contents.
atomic_write_text("config.ini", "[section]\nkey=value\n")

# Atomic JSON write with sensible defaults. default=str handles
# datetime, Path, and other non-JSON-native types out of the box.
atomic_write_json("manifest.json", {
    "version": "1.0",
    "created_at": datetime.datetime.now(),
    "root": Path("/data"),
})
```

### Rich Metadata (v0.2.4)

```python
from dazzle_filekit import metadata

# Collect rich metadata. On Windows this captures SDDL ACL strings
# (JSON-serializable), creation time, file attribute flags, and owner.
# On Linux/macOS it captures extended attributes (xattrs) as base64.
md = metadata.collect_file_metadata("important.txt")

# Save it as JSON alongside the file
import json
with open("important.txt.meta.json", "w") as f:
    json.dump(metadata.metadata_to_json(md), f, indent=2)

# Later, restore metadata to a copy (including Windows ctime)
metadata.apply_file_metadata("restored.txt", md)

# Check if the richer Windows code path is available
if metadata.is_win32_available():
    print("pywin32 present -- full SDDL/ctime/ADS support")
```

### Link-Safe Tree Copy (v0.2.4)

```python
from dazzle_filekit import copy_tree_preserving_links

# Copies the tree, preserving symlinks and junctions as links (never
# traversing them). Safe for copying source trees that may contain
# self-referential junctions on Windows.
copy_tree_preserving_links("src_tree", "dst_tree", dirs_exist_ok=True)
```

## API Reference

### Cross-Platform Utilities

- `normalize_cross_platform_path(path, *, resolve=False)` - **Canonical** path normalizer (v0.2.4). Handles Git Bash `/c/`, WSL `/mnt/c/`, Windows `C:\` / `C:/`, tilde, env vars, `\\?\` prefix, and platform-direction conversion. With `resolve=True`, follows symlinks via `Path.resolve()`.
- `resolve_cross_platform_path(path)` - Normalize and probe alternate platform formats if path not found (existence-aware)
- `path_exists_cross_platform(path)` - Check path existence across formats
- `is_windows()` / `is_unix()` / `is_wsl()` - Platform detection. `is_wsl()` returns True when running inside WSL (checks `WSL_DISTRO_NAME` env var + `/proc/version`).

### Path Functions

- `normalize_path(path)` / `normalize_path_no_resolve(path)` - Backwards-compat wrappers for `normalize_cross_platform_path(path, resolve=True)` and `resolve=False` respectively.
- `is_same_file(path1, path2)` - Check if paths refer to same file
- `split_drive_letter(path)` - Split drive letter from path (Windows)
- `is_unc_path(path)` - Check if path is UNC format
- `get_relative_path(path, base)` - Get relative path from base
- `find_files(directory, patterns, exclude)` - Find files matching patterns
- `get_path_type(path)` - Detect path type (unc, network, subst, local)

### File Operations

- `copy_file(src, dst, preserve_attrs=True, overwrite=False)` - Copy file with options
- `move_file(src, dst, preserve_attrs=True, overwrite=False)` - Move file with options
- `collect_file_metadata(path)` - Collect file metadata (rich: SDDL ACLs, xattrs, ctime as of v0.2.4)
- `apply_file_metadata(path, metadata)` - Apply metadata to file (honors all rich fields when present)
- `create_directory_structure(path, directory_paths)` - Create directory tree
- `remove_file(path, force=False)` - Remove file safely
- `remove_directory(path, recursive=True, force=False)` - Remove directory
- `create_symlink(target, link, force=False)` - Create symbolic link with cross-platform support
- `atomic_write_text(path, content, *, encoding='utf-8')` *(v0.2.4)* - Atomic tmp+rename text write
- `atomic_write_json(path, data, *, indent=2, default=str)` *(v0.2.4)* - Atomic JSON write
- `copy_tree_preserving_links(src, dst, *, dirs_exist_ok=False)` *(v0.2.4)* - `shutil.copytree(symlinks=True)` wrapper

### Metadata Module (v0.2.4)

Import via `from dazzle_filekit import metadata` or `from dazzle_filekit.metadata import ...`.

- `metadata.collect_file_metadata(path)` - Rich capture (SDDL + ctime + xattrs + attr flags)
- `metadata.apply_file_metadata(path, md)` - Rich apply
- `metadata.restore_windows_creation_time(path, created)` - NTFS ctime restore via `SetFileTime`
- `metadata.is_win32_available()` - Cached pywin32 probe
- `metadata.compare_metadata(md1, md2)` - Diff two dicts with 2s timestamp tolerance
- `metadata.metadata_to_json(md)` - JSON-safe projection
- `metadata.get_metadata_summary(md)` - Human-readable summary
- `metadata.collect_timestamp_info(path)` / `apply_timestamp_strategy(path, strategy, ...)` - Timestamp-only helpers

### Platform-Specific (Windows, v0.2.4)

- `platform.windows.detect_alternate_streams(path)` - Enumerate NTFS ADS via `FindFirstStreamW`
- `platform.windows.has_significant_ads(path)` - True if any non-ignored stream exists

### Disk Space Functions

- `get_disk_usage(path)` - Get disk usage statistics (total, used, free)
- `check_disk_space(dest, required, margin)` - Check if space is sufficient
- `calculate_total_size(paths)` - Calculate total size of files/directories
- `ensure_disk_space(dest, sources, margin)` - Verify space for copy operation

### Verification Functions

- `calculate_file_hash(path, algorithm)` - Calculate file hash
- `verify_file_hash(path, expected_hash, algorithm)` - Verify hash
- `calculate_directory_hashes(directory, algorithm)` - Hash all files in directory
- `save_hashes_to_file(hashes, output_file)` / `load_hashes_from_file(hash_file)` - Hash persistence
- `compare_directories(dir1, dir2)` - Compare directory contents
- `verify_copied_files(src_dir, dst_dir)` - Verify copy operation

## Platform Support

See [docs/platform-support.md](docs/platform-support.md) for the full platform support matrix and platform-specific features.

| Platform | Status |
|----------|--------|
| Windows 10/11 | Tested |
| Linux | Tested |
| WSL / WSL2 | Tested |
| macOS | Expected to work |
| BSD | Expected to work |

## Configuration

### Logging

```python
from dazzle_filekit import configure_logging, enable_verbose_logging
import logging

# Configure logging level
configure_logging(level=logging.DEBUG, log_file="dazzle-filekit.log")

# Or enable verbose logging
enable_verbose_logging()
```

## Development

### Setup Development Environment

```bash
git clone https://github.com/DazzleLib/dazzle-filekit.git
cd dazzle-filekit
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest tests/ -v --cov=dazzle_filekit
```

### Code Formatting

```bash
black dazzle_filekit tests
flake8 dazzle_filekit tests
```

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Like the project?

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/djdarcy)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Part of DazzleLib

dazzle-filekit is part of the [DazzleLib](https://github.com/DazzleLib) ecosystem of Python file manipulation tools.

### Related Projects

- [UNCtools](https://github.com/DazzleLib/UNCtools) - Windows UNC path utilities
- [preserve](https://github.com/DazzleTools/preserve) - File preservation with manifest tracking and restoration
- [dazzle-tree-lib](https://github.com/DazzleLib/dazzle-tree-lib) - Tree structure utilities
