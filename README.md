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
- **UNC Path Detection** - Native `is_unc_path` / `classify_fs_object` helpers; built on [UNCtools](https://github.com/DazzleLib/UNCtools) (a hard dependency as of 0.3.0) for UNC ↔ drive-letter translation and the optional path-variant resolver edge (see [docs/unctools-integration.md](docs/unctools-integration.md))
- **Link Primitives** - `analyze_link` / `create_junction` / `create_hardlink` / `read_link_target` (intrinsic link analysis; junctions via PowerShell, no `cmd`)
- **Long-Path Shims** - `shim_path` makes a file over Windows' 260-character `MAX_PATH` openable by *any* application, by siting a junction at a short root and handing back a shorter name for the same bytes. `\\?\` only lifts the limit at the API layer; it does not help an app that copies the path into a fixed 260-byte buffer (observed in two PDF readers), and nothing outside such an app can fix its buffer. A no-op on Linux/macOS, where `PATH_MAX` is 4096/1024

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

This pulls in the stack bedrock and path-identity layer automatically:
`dazzle-lib` (shared Protocols/types) and `unctools` (UNC ↔ drive-letter
identity). As of 0.3.0 both are **required** -- `unctools` backs the
fallback-aware file operations (`copy_file(..., try_path_variants=True)`,
`open_file`, etc.) via the `PathVariantResolver` seam.

### Optional Dependencies

```bash
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
from dazzle_filekit import normalize_cross_platform_path, find_files, is_unc_path

# Normalize paths (returns Path object). resolve=True follows symlinks;
# the default resolve=False is link-safe.
path = normalize_cross_platform_path("/some/path/../file.txt")
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

## API at a glance

The Quick Start above covers the common 90% of what most users need.
For the full function-by-function reference, see
**[docs/api-reference.md](docs/api-reference.md)**.

| Area | Key entry points |
|------|------------------|
| **Paths** | `normalize_cross_platform_path(path, *, resolve=False)` (canonical), `resolve_cross_platform_path`, `path_exists_cross_platform`, `is_wsl()` |
| **File ops** | `copy_file`, `move_file`, `create_symlink`, `copy_tree_preserving_links`, `atomic_write_text`, `atomic_write_json` |
| **Metadata** | `dazzle_filekit.metadata` -- `collect_file_metadata`, `apply_file_metadata`, `restore_windows_creation_time`, `compare_metadata`, `is_win32_available` |
| **Platform (Windows)** | `dazzle_filekit.platform.windows` -- `detect_alternate_streams`, `has_significant_ads`, `is_admin` |
| **Disk space** | `get_disk_usage`, `check_disk_space`, `calculate_total_size`, `ensure_disk_space` |
| **Verification** | `calculate_file_hash`, `verify_file_hash`, `verify_files_with_manifest`, `compare_directories` |
| **UNC detection** | `is_unc_path`, `classify_fs_object` (UNCtools is the hard-dep L0 layer for translation + the resolver edge -- see [docs/unctools-integration.md](docs/unctools-integration.md)) |
| **Link primitives** | `analyze_link`, `detect_link_type`, `read_link_target`, `create_junction`, `create_hardlink` |
| **Long paths** | `dazzle_filekit.longpath` -- `shim_path` (one-call), `needs_shim`, `plan_shim`, `resolve_shim_root`, `budget_for`, `create_shim`, `remove_shim`, `reap_shims` |

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
# Standard run
pytest tests/ -v --cov=dazzle_filekit

# Cross-platform cross-check (Windows + WSL Ubuntu from one command)
./scripts/run-cross-platform-tests.sh
```

### Code Formatting

```bash
black dazzle_filekit tests
flake8 dazzle_filekit tests
```

## Documentation

- **[docs/api-reference.md](docs/api-reference.md)** -- full function-by-function reference
- **[docs/api-stability.md](docs/api-stability.md)** -- locked public API surface and known external callers. Changes to symbols listed here require a migration plan.
- **[docs/platform-support.md](docs/platform-support.md)** -- platform matrix, test counts, and platform-specific feature breakdown
- **[docs/preservelib-integration.md](docs/preservelib-integration.md)** -- how preservelib composes with filekit and the layering contract
- **[docs/unctools-integration.md](docs/unctools-integration.md)** -- UNCtools composition patterns (filekit does UNC detection; unctools does UNC translation; user code composes them)
- **[BREAKING_CHANGES.md](BREAKING_CHANGES.md)** -- forward-looking log of version-specific breaks and the Phase 4+ migration procedure
- **[CHANGELOG.md](CHANGELOG.md)** -- version history

`tests/test_import_stability.py` is the automated canary that enforces `docs/api-stability.md`. If you rename or remove a locked symbol, that test will fail.

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
