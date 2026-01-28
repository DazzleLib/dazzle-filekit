# Changelog

All notable changes to dazzle-filekit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-01-24

### Added
- `normalize_cross_platform_path()` - Normalize paths from Git Bash style (`/c/...`), WSL style (`/mnt/c/...`), and Windows style (`C:\...`) to native platform format
- `path_exists_cross_platform()` - Check if a path exists, handling cross-platform path formats
- Export `is_windows()` and `is_unix()` from main package for convenience
- Disk space utilities: `get_disk_usage()`, `check_disk_space()`, `calculate_total_size()`, `ensure_disk_space()`
- `DiskUsage` named tuple with `used_percent` and `free_percent` properties
- `InsufficientSpaceError` exception for disk space validation
- 53 unit tests for compat and disk modules
- Platform support documentation (`docs/platform-support.md`)
- CHANGELOG.md

### Fixed
- Added missing `Dict` import to `utils/compat.py` for proper type annotations

## [0.1.1] - 2026-01-15

### Changed
- Version bump for initial PyPI release preparation

## [0.1.0] - 2026-01-10

### Added
- Initial release
- Path operations: `normalize_path`, `is_same_file`, `split_drive_letter`, `is_unc_path`, `get_relative_path`, `create_dest_path`, `find_files`, `find_regex_files`, `collect_files_from_include_file`, `create_parent_dirs`, `ensure_unique_path`, `get_path_type`
- File operations: `copy_file`, `move_file`, `collect_file_metadata`, `apply_file_metadata`, `copy_files_with_path`, `move_files_with_path`, `create_directory_structure`, `remove_file`, `remove_directory`
- Verification functions: `calculate_file_hash`, `verify_file_hash`, `verify_files_with_manifest`, `calculate_directory_hashes`, `save_hashes_to_file`, `load_hashes_from_file`, `compare_directories`, `verify_copied_files`
- Utility functions: `is_windows`, `is_unix`, `is_admin`, `is_root`, `fix_path_separators`, `fix_path_case`, `get_system_encoding`, `get_system_temp_dir`, `get_home_dir`, `get_app_data_dir`
- Validation functions: `is_valid_path`, `is_safe_path`, `validate_path_chars`, `is_absolute_path`, `is_relative_path`, `is_hidden_path`, `is_symlink`, `is_junction`
- Cross-platform support for Windows, Linux, and macOS
- Optional UNC path support via unctools integration
