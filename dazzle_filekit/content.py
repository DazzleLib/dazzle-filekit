"""Text-content file operations.

The L1 home of unctools' removed ``replace_in_file`` / ``batch_replace_in_files``
(STACK-MAP D7: editing a file's *content* is a file operation, so it belongs in
dazzle-filekit, not the path-identity layer). Built on the fallback-aware
``open_file`` (read), ``atomic_write_text`` (crash-safe write -- a strict upgrade
over the original's plain write), and ``process_files`` (batch).
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Union

from dazzle_lib import PathVariantResolver

from .operations import atomic_write_text, open_file, process_files

logger = logging.getLogger(__name__)


def replace_in_file(
    file_path: Union[str, Path],
    old_text: str,
    new_text: str,
    *,
    encoding: str = "utf-8",
    try_path_variants: bool = False,
    resolver: Optional[PathVariantResolver] = None,
) -> bool:
    """Replace ``old_text`` with ``new_text`` in ``file_path``.

    Reads via the fallback-aware :func:`open_file` and writes via
    :func:`atomic_write_text` (so a crash mid-write cannot truncate the file).
    Returns True if the file was modified, False if ``old_text`` was not present
    (logged as a warning) or on error.
    """
    try:
        with open_file(file_path, "r", encoding=encoding,
                       try_path_variants=try_path_variants, resolver=resolver) as f:
            content = f.read()

        if old_text not in content:
            logger.warning(f"Text not found in file {file_path}")
            return False

        atomic_write_text(file_path, content.replace(old_text, new_text), encoding=encoding)
        return True
    except Exception as e:
        logger.error(f"Error replacing text in file {file_path}: {e}")
        return False


def batch_replace_in_files(
    directory: Union[str, Path],
    old_text: str,
    new_text: str,
    pattern: str = "*.txt",
    recursive: bool = True,
    *,
    encoding: str = "utf-8",
    try_path_variants: bool = False,
    resolver: Optional[PathVariantResolver] = None,
) -> Dict[str, bool]:
    """Run :func:`replace_in_file` over every file matching ``pattern`` under
    ``directory`` (via :func:`process_files`).

    Returns ``{str(path): modified?}`` (False for unmatched / errored files).
    """
    def _cb(path: Path) -> bool:
        return replace_in_file(path, old_text, new_text, encoding=encoding,
                               try_path_variants=try_path_variants, resolver=resolver)

    return process_files(directory, _cb, pattern, recursive,
                         try_path_variants=try_path_variants, resolver=resolver)
