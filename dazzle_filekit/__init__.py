"""
dazzle_filekit - A general-purpose file manipulation library.

This package provides utilities for file operations, path handling, and verification
across different platforms, with a focus on preserving file metadata.
"""

import os
import sys
import logging
from pathlib import Path

# Setup package-level logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create console handler if not already present
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    )
    logger.addHandler(console_handler)

# Import core functionality
from .paths import (
    is_same_file,
    split_drive_letter,
    is_unc_path,
    get_relative_path,
    compute_relative_path,
    create_dest_path,
    find_files,
    find_regex_files,
    collect_files_from_include_file,
    create_parent_dirs,
    ensure_unique_path,
    classify_fs_object
)

from .utils.compat import (
    normalize_cross_platform_path,
    resolve_cross_platform_path,
    path_exists_cross_platform,
    fix_path_case,
    path_exists_case_sensitive,
    get_case_sensitive_path,
    is_windows,
    is_unix,
    is_wsl,
)

from .utils.disk import (
    DiskUsage,
    InsufficientSpaceError,
    get_disk_usage,
    check_disk_space,
    calculate_total_size,
    ensure_disk_space
)

from .operations import (
    copy_file,
    move_file,
    open_file,
    collect_file_metadata,
    apply_file_metadata,
    copy_files_with_path,
    move_files_with_path,
    process_files,
    create_directory_structure,
    remove_file,
    remove_directory,
    create_symlink,
    # v0.2.4 primitives
    atomic_write_text,
    atomic_write_json,
    copy_tree_preserving_links,
)

from .verification import (
    calculate_file_hash,
    verify_file_hash,
    verify_files_with_manifest,
    calculate_directory_hashes,
    save_hashes_to_file,
    load_hashes_from_file,
    compare_directories,
    verify_copied_files
)

# Expose dazzle_filekit.metadata as a public submodule so callers can do:
#     from dazzle_filekit import metadata
#     md = metadata.collect_file_metadata(path)
# alongside the top-level convenience imports from .operations above.
from . import metadata  # noqa: F401
from .metadata import (
    is_win32_available,
    restore_windows_creation_time,
    compare_metadata,
    metadata_to_json,
)

# v0.3.0 content operations -- the L1 home of unctools' removed
# replace_in_file / batch_replace_in_files (STACK-MAP D7).
from . import content  # noqa: F401
from .content import replace_in_file, batch_replace_in_files

# v0.3.0 intrinsic link primitives (#15 Phase A) -- the L1 home of
# preservelib's intrinsic link analysis + junction/hardlink creation.
from . import links  # noqa: F401
from .links import (
    LinkInfo,
    analyze_link,
    detect_link_type,
    read_link_target,
    create_junction,
    create_hardlink,
)

__version__ = '0.3.1'

def configure_logging(level=logging.INFO, log_file=None):
    """
    Configure logging for dazzle_filekit.
    
    Args:
        level: Logging level
        log_file: Optional path to log file
    """
    logger.setLevel(level)
    
    # Clear existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Add console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    )
    logger.addHandler(console_handler)
    
    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
        logger.addHandler(file_handler)
        
    logger.debug(f"Logging configured with level {level}")

def enable_verbose_logging():
    """Enable verbose (debug) logging."""
    configure_logging(logging.DEBUG)

# Platform-specific functions can be imported conditionally
if sys.platform == 'win32':
    pass
    # Windows-specific functions
    # try:
        # from .platform.windows import (
        #     Import Windows-specific functions when implemented
        # )
    # except ImportError:
    #     logger.debug("Windows-specific functions not available")
else:
    pass
    # Unix-specific functions
    # try:
        # from .platform.unix import (
        #     Import Unix-specific functions when implemented
        # )
    # except ImportError:
    #     logger.debug("Unix-specific functions not available")

# __all__ defines the public API
__all__ = [
    # Version
    '__version__',
    
    # Logging functions
    'configure_logging',
    'enable_verbose_logging',
    
    # Path functions
    'is_same_file',
    'split_drive_letter',
    'is_unc_path',
    'get_relative_path',
    'compute_relative_path',
    'create_dest_path',
    'find_files',
    'find_regex_files',
    'collect_files_from_include_file',
    'create_parent_dirs',
    'ensure_unique_path',
    'classify_fs_object',

    # Cross-platform path utilities
    'normalize_cross_platform_path',
    'resolve_cross_platform_path',
    'path_exists_cross_platform',
    'fix_path_case',
    'path_exists_case_sensitive',
    'get_case_sensitive_path',
    'is_windows',
    'is_unix',
    'is_wsl',

    # Disk space utilities
    'DiskUsage',
    'InsufficientSpaceError',
    'get_disk_usage',
    'check_disk_space',
    'calculate_total_size',
    'ensure_disk_space',
    
    # Operation functions
    'copy_file',
    'move_file',
    'open_file',
    'collect_file_metadata',
    'apply_file_metadata',
    'copy_files_with_path',
    'move_files_with_path',
    'process_files',
    'create_directory_structure',
    'remove_file',
    'remove_directory',
    'create_symlink',

    # v0.2.4 primitives
    'atomic_write_text',
    'atomic_write_json',
    'copy_tree_preserving_links',

    # Rich metadata module (v0.2.4)
    'metadata',
    'is_win32_available',
    'restore_windows_creation_time',
    'compare_metadata',
    'metadata_to_json',

    # Content operations (v0.3.0)
    'content',
    'replace_in_file',
    'batch_replace_in_files',

    # Intrinsic link primitives (v0.3.0, #15 Phase A)
    'links',
    'LinkInfo',
    'analyze_link',
    'detect_link_type',
    'read_link_target',
    'create_junction',
    'create_hardlink',

    # Verification functions
    'calculate_file_hash',
    'verify_file_hash',
    'verify_files_with_manifest',
    'calculate_directory_hashes',
    'save_hashes_to_file',
    'load_hashes_from_file',
    'compare_directories',
    'verify_copied_files'
]