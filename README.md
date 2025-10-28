# filetoolkit

[![PyPI version](https://badge.fury.io/py/filetoolkit.svg)](https://badge.fury.io/py/filetoolkit)
[![Python Versions](https://img.shields.io/pypi/pyversions/filetoolkit.svg)](https://pypi.org/project/filetoolkit/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Cross-platform file operations toolkit with path handling, verification, and metadata preservation**

## Features

- **Path Operations**: Cross-platform path handling, normalization, and manipulation
- **File Operations**: Copy, move, and manage files with metadata preservation
- **File Verification**: Calculate and verify file hashes (MD5, SHA1, SHA256, SHA512)
- **Platform Support**: Windows, Linux, and macOS with platform-specific optimizations
- **UNC Path Support**: Optional integration with `unctools` for Windows UNC path handling
- **Metadata Preservation**: Preserve timestamps, permissions, and file attributes

## Installation

```bash
pip install filetoolkit
```

### Optional Dependencies

For Windows UNC path support:
```bash
pip install filetoolkit[unctools]
```

For development:
```bash
pip install filetoolkit[dev]
```

## Quick Start

### Path Operations

```python
from filetoolkit import normalize_path, find_files, is_unc_path

# Normalize paths
path = normalize_path("/some/path/../file.txt")

# Find files with patterns
files = find_files("/directory", patterns=["*.py", "*.txt"])

# Check UNC paths
if is_unc_path(r"\\server\share"):
    print("This is a UNC path")
```

### File Operations

```python
from filetoolkit import copy_file, collect_file_metadata

# Copy file with metadata preservation
success = copy_file("source.txt", "dest.txt", preserve_metadata=True)

# Collect file metadata
metadata = collect_file_metadata("file.txt")
print(f"Size: {metadata['size']}, Modified: {metadata['mtime']}")
```

### File Verification

```python
from filetoolkit import calculate_file_hash, verify_file_hash

# Calculate hash
hash_value = calculate_file_hash("file.txt", algorithm="sha256")

# Verify hash
is_valid = verify_file_hash("file.txt", expected_hash, algorithm="sha256")
```

## API Reference

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

### Verification Functions

- `calculate_file_hash(path, algorithm)` - Calculate file hash
- `verify_file_hash(path, expected_hash, algorithm)` - Verify hash
- `calculate_directory_hashes(directory, algorithm)` - Hash all files in directory
- `save_hashes_to_file(hashes, output_file)` - Save hashes to file
- `load_hashes_from_file(hash_file)` - Load hashes from file
- `compare_directories(dir1, dir2)` - Compare directory contents
- `verify_copied_files(src_dir, dst_dir)` - Verify copy operation

## Platform Support

### Windows
- Full UNC path support (with `unctools`)
- Network drive detection
- NTFS metadata preservation
- Long path support (>260 characters)

### Linux/Unix
- POSIX permissions preservation
- Symlink handling
- Extended attributes

### macOS
- HFS+ and APFS support
- Extended attributes
- Resource forks (where applicable)

## Configuration

### Logging

```python
from filetoolkit import configure_logging, enable_verbose_logging
import logging

# Configure logging level
configure_logging(level=logging.DEBUG, log_file="filetoolkit.log")

# Or enable verbose logging
enable_verbose_logging()
```

## Development

### Setup Development Environment

```bash
git clone https://github.com/DazzleLib/filetoolkit.git
cd filetoolkit/local
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest tests/ -v --cov=filetoolkit
```

### Code Formatting

```bash
black filetoolkit tests
flake8 filetoolkit tests
```

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Like the project?

[!["Buy Me A Coffee"](https://camo.githubusercontent.com/0b448aabee402aaf7b3b256ae471e7dc66bcf174fad7d6bb52b27138b2364e47/68747470733a2f2f7777772e6275796d6561636f666665652e636f6d2f6173736574732f696d672f637573746f6d5f696d616765732f6f72616e67655f696d672e706e67)](https://www.buymeacoffee.com/djdarcy)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Part of DazzleLib

filetoolkit is part of the [DazzleLib](https://github.com/DazzleLib) ecosystem of Python file manipulation tools.

### Related Projects

- [unctools](https://github.com/DazzleLib/unctools) - Windows UNC path utilities
- [preservelib](https://github.com/DazzleLib/preservelib) - File preservation with manifest tracking
- [dazzletreelib](https://github.com/DazzleLib/dazzletreelib) - Tree structure utilities

## Acknowledgements

Dustin Darcy (6962246+djdarcy@users.noreply.github.com)
