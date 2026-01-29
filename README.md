# dazzle-filekit

[![PyPI version](https://img.shields.io/pypi/v/dazzle-filekit.svg)](https://pypi.org/project/dazzle-filekit/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS%20%7C%20BSD-lightgrey.svg)](docs/platform-support.md)
[![GitHub Discussions](https://img.shields.io/github/discussions/DazzleLib/dazzle-filekit)](https://github.com/DazzleLib/dazzle-filekit/discussions)

> **Cross-platform file operations with path handling, verification, and metadata preservation.**

A Python toolkit for reliable file operations across Windows, Linux, and macOS. Handles path normalization between Git Bash, WSL, and native formats, file verification with multiple hash algorithms, and metadata-preserving copy/move operations.

## Features

- **Cross-Platform Paths** - Normalize between Git Bash (`/c/...`), WSL (`/mnt/c/...`), and native Windows/Unix paths
- **File Operations** - Copy, move, and manage files with metadata preservation
- **File Verification** - Calculate and verify file hashes (MD5, SHA1, SHA256, SHA512)
- **Disk Space Checking** - Pre-flight space verification before operations
- **Platform Support** - Windows, Linux, macOS, and BSD with platform-specific optimizations
- **UNC Path Support** - Optional integration with `unctools` for Windows UNC path handling

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
# Windows UNC path support
pip install dazzle-filekit[unctools]

# Development tools
pip install dazzle-filekit[dev]
```

## Quick Start

### Cross-Platform Path Handling

```python
from dazzle_filekit import normalize_cross_platform_path, path_exists_cross_platform

# Convert Git Bash style paths to native format
# On Windows: /c/Users/foo -> C:\Users\foo
# On Unix: C:\Users\foo -> /c/Users/foo
path = normalize_cross_platform_path("/c/Users/foo/file.txt")

# Also handles WSL paths: /mnt/c/Users/...
path = normalize_cross_platform_path("/mnt/c/Users/foo/file.txt")

# Check if a cross-platform path exists
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

# Copy file with metadata preservation
success = copy_file("source.txt", "dest.txt", preserve_metadata=True)

# Collect file metadata
metadata = collect_file_metadata("file.txt")
print(f"Size: {metadata['size']}, Modified: {metadata['mtime']}")

# Create symbolic link (cross-platform)
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

## API Reference

### Cross-Platform Utilities

- `normalize_cross_platform_path(path)` - Normalize Git Bash/WSL/Windows paths to native format
- `path_exists_cross_platform(path)` - Check path existence across formats
- `is_windows()` / `is_unix()` - Platform detection

### Path Functions

- `normalize_path(path)` - Normalize path to canonical form
- `is_same_file(path1, path2)` - Check if paths refer to same file
- `split_drive_letter(path)` - Split drive letter from path (Windows)
- `is_unc_path(path)` - Check if path is UNC format
- `get_relative_path(path, base)` - Get relative path from base
- `find_files(directory, patterns, exclude)` - Find files matching patterns
- `get_path_type(path)` - Detect path type (unc, network, subst, local)

### File Operations

- `copy_file(src, dst, preserve_metadata)` - Copy file with options
- `move_file(src, dst, preserve_metadata)` - Move file with options
- `collect_file_metadata(path)` - Collect file metadata
- `apply_file_metadata(path, metadata)` - Apply metadata to file
- `create_directory_structure(path)` - Create directory tree
- `remove_file(path)` - Remove file safely
- `remove_directory(path, recursive)` - Remove directory
- `create_symlink(target, link, force)` - Create symbolic link with cross-platform support

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
