"""Junction-detection improvements contributed from dazzlesum.

Two changes, each pinned here:

  1. ``utils.validation.is_junction`` uses ``os.path.isjunction`` on
     Python 3.12+ (single lstat; same mount-point reparse-tag semantics)
     and only falls back to the ctypes ``DeviceIoControl`` probe on older
     interpreters. The two implementations must agree.
  2. ``links.detect_link_type`` gates existence on ``os.lstat`` (the link
     itself) instead of ``Path.exists()`` (which follows the link), so a
     junction whose target is missing is still reported as a junction and
     ``analyze_link`` can mark it broken. Previously broken junctions were
     silently reported as "not a link".

Junction fixtures are Windows-only (no elevation needed); symlink cases
skip gracefully where privileges are lacking.
"""

import os
import sys
from pathlib import Path

import pytest

from dazzle_filekit import analyze_link, create_junction, detect_link_type
from dazzle_filekit.utils.validation import is_junction

IS_WINDOWS = sys.platform == "win32"


def _try_symlink(target: Path, link: Path, target_is_directory: bool = False) -> bool:
    """Create a symlink, returning False (for skip) if privileges are lacking."""
    try:
        if os.name == "nt":
            os.symlink(str(target), str(link), target_is_directory=target_is_directory)
        else:
            os.symlink(str(target), str(link))
        return True
    except (OSError, NotImplementedError):
        return False


def _make_junction(tmp_path: Path):
    """Create target dir + junction to it; skip if junction creation fails."""
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "junction"
    if not create_junction(target, link):
        pytest.skip("junction creation unavailable")
    return target, link


# ---------------------------------------------------------------------------
# 1. is_junction fast path (Python 3.12+) vs ctypes fallback
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not IS_WINDOWS, reason="junctions are Windows-only")
def test_is_junction_classifies_junction_dir_and_file(tmp_path):
    target, link = _make_junction(tmp_path)
    plain_file = tmp_path / "plain.txt"
    plain_file.write_text("data")

    assert is_junction(link) is True
    assert is_junction(target) is False       # plain directory
    assert is_junction(plain_file) is False   # plain file
    assert is_junction(tmp_path / "missing") is False


@pytest.mark.skipif(not IS_WINDOWS, reason="junctions are Windows-only")
@pytest.mark.skipif(not hasattr(os.path, "isjunction"),
                    reason="fast path requires Python 3.12+")
def test_is_junction_fast_path_agrees_with_ctypes(tmp_path, monkeypatch):
    """The 3.12+ lstat fast path and the ctypes DeviceIoControl fallback
    must classify the same objects identically."""
    target, link = _make_junction(tmp_path)
    dir_symlink = tmp_path / "dir_symlink"
    have_symlink = _try_symlink(target, dir_symlink, target_is_directory=True)

    probes = [link, target, tmp_path / "missing"]
    if have_symlink:
        probes.append(dir_symlink)  # must NOT be classified as a junction

    fast = [is_junction(p) for p in probes]

    # Force the ctypes fallback by hiding os.path.isjunction.
    monkeypatch.delattr(os.path, "isjunction")
    slow = [is_junction(p) for p in probes]

    assert fast == slow
    assert fast[0] is True    # the junction
    assert fast[1] is False   # its plain target
    assert fast[2] is False   # nonexistent
    if have_symlink:
        assert fast[3] is False  # directory symlink is not a junction


@pytest.mark.skipif(not IS_WINDOWS, reason="junctions are Windows-only")
def test_is_junction_on_broken_junction(tmp_path):
    """A junction whose target was removed is still a junction (the check
    reads the link itself, not its target)."""
    target, link = _make_junction(tmp_path)
    target.rmdir()
    assert is_junction(link) is True


# ---------------------------------------------------------------------------
# 2. detect_link_type / analyze_link on broken links
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not IS_WINDOWS, reason="junctions are Windows-only")
def test_detect_link_type_broken_junction(tmp_path):
    """A broken junction is reported as a junction (previously None,
    because Path.exists() followed the link to its missing target)."""
    target, link = _make_junction(tmp_path)
    assert detect_link_type(link) == "junction"

    target.rmdir()
    assert detect_link_type(link) == "junction"

    info = analyze_link(link)
    assert info.kind == "junction"
    assert info.is_broken is True


def test_detect_link_type_broken_symlink(tmp_path):
    """Regression guard for the lstat gate: broken symlinks keep being
    reported as symlinks (the old exists()/is_symlink() gate covered them)."""
    link = tmp_path / "dangling"
    if not _try_symlink(tmp_path / "missing-target", link):
        pytest.skip("symlink creation unavailable")

    assert detect_link_type(link) == "symlink"
    info = analyze_link(link)
    assert info.kind == "symlink"
    assert info.is_broken is True


def test_detect_link_type_nonexistent_and_plain(tmp_path):
    """The lstat gate keeps the old answers for the ordinary cases."""
    assert detect_link_type(tmp_path / "missing") is None

    plain = tmp_path / "plain.txt"
    plain.write_text("data")
    assert detect_link_type(plain) is None
    assert detect_link_type(tmp_path) is None
