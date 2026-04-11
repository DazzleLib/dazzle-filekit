"""Characterization tests for junction detection.

Documents the CURRENT (pre-v0.3.3) behavior of:
  - dazzle_filekit.utils.validation.is_junction (uses FILE_ATTRIBUTE_REPARSE_POINT
    which is set for BOTH junctions AND symlinks -- this is a known bug)
  - dazzlecmd's links.py:_is_junction_win (uses DeviceIoControl +
    FSCTL_GET_REPARSE_POINT to read the reparse tag -- correct)

POST-v0.3.3: filekit's is_junction will use the DeviceIoControl approach.
These tests will then assert filekit matches links.py behavior.
"""

import os
import subprocess
import sys
import tempfile

import pytest

from dazzle_filekit.utils.validation import is_junction as filekit_is_junction

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Junction tests are Windows-only"
)


def _create_junction(link_path: str, target_path: str) -> bool:
    """Create a junction via PowerShell. Returns True if successful."""
    result = subprocess.run(
        [
            "powershell", "-Command",
            f"New-Item -ItemType Junction -Path '{link_path}' -Target '{target_path}'"
        ],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def _can_create_symlink(tmp_path) -> bool:
    """Probe whether symlink creation is available (requires admin on Windows)."""
    target = tmp_path / "probe_target"
    target.mkdir()
    link = tmp_path / "probe_link"
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
        return True
    except OSError:
        return False


# v0.2.4: ``_import_links_is_junction`` removed.
# The back-to-back cross-check against dazzlecmd's links.py was useful
# during Phase 2 to prove "theirs is correct, ours is broken". Now that
# the fix has landed in ``dazzle_filekit.utils.validation.is_junction``,
# the equivalent assertions live in ``TestFilekitIsJunctionV024`` above
# and test filekit directly (no cross-repo hardcoded paths).


# ---------------------------------------------------------------------------
# Baseline: filekit.validation.is_junction on various inputs
# ---------------------------------------------------------------------------


class TestFilekitIsJunctionV024:
    """v0.2.4: filekit.validation.is_junction is FIXED.

    History: v0.2.3 referenced ``win32file.FILE_ATTRIBUTE_REPARSE_POINT``
    (nonexistent -- the constant is in ``win32con``), and the bare
    ``except:`` silently returned False for everything. Additionally,
    even a working attribute check would have misclassified directory
    symlinks as junctions since they share the same reparse-point
    attribute.

    v0.2.4 uses ``DeviceIoControl(FSCTL_GET_REPARSE_POINT)`` to read the
    reparse tag and checks specifically for ``IO_REPARSE_TAG_MOUNT_POINT``.
    These tests lock in the correct behavior.
    """

    def test_plain_directory_is_not_junction(self, tmp_path):
        d = tmp_path / "plain_dir"
        d.mkdir()
        assert filekit_is_junction(str(d)) is False

    def test_plain_file_is_not_junction(self, tmp_path):
        f = tmp_path / "plain.txt"
        f.write_text("x")
        assert filekit_is_junction(str(f)) is False

    def test_real_junction_correctly_detected(self, tmp_path):
        """v0.2.4: real junctions return True."""
        target = tmp_path / "target_dir"
        target.mkdir()
        link = tmp_path / "junction_link"

        if not _create_junction(str(link), str(target)):
            pytest.skip("Cannot create junction in test environment")

        assert filekit_is_junction(str(link)) is True, (
            "v0.2.4 is_junction must correctly detect real junctions"
        )

    def test_directory_symlink_correctly_NOT_junction(self, tmp_path):
        """v0.2.4: directory symlinks return False for the RIGHT reason.

        v0.2.3 returned False because the function was broken; v0.2.4
        returns False because symlinks have ``IO_REPARSE_TAG_SYMLINK``,
        not ``IO_REPARSE_TAG_MOUNT_POINT``.
        """
        if not _can_create_symlink(tmp_path):
            pytest.skip("Symlink creation requires admin on Windows")

        target = tmp_path / "sym_target_dir"
        target.mkdir()
        link = tmp_path / "sym_link_to_dir"
        os.symlink(str(target), str(link), target_is_directory=True)

        assert filekit_is_junction(str(link)) is False


