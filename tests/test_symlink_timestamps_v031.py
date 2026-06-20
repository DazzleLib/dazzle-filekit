"""Regression tests for symlink-targeted timestamp application (v0.3.1).

Before 0.3.1, ``apply_file_metadata`` applied timestamps via ``os.utime(path)``,
which follows a symlink to its target -- so applying a record's timestamps to a
link silently corrupted the TARGET file's timestamps and left the link unchanged.
0.3.1 routes symlinks through a link-targeting path (Windows:
``FILE_FLAG_OPEN_REPARSE_POINT`` + ``SetFileTime``; POSIX:
``os.utime(follow_symlinks=False)``).
"""

import os

import pytest

from dazzle_filekit import apply_file_metadata


def _try_symlink(target, link):
    """Create a symlink, returning False (to skip) if privileges are lacking."""
    try:
        os.symlink(str(target), str(link))
    except (OSError, NotImplementedError):
        return False
    return os.path.islink(str(link))


def _link_timestamps_settable():
    """POSIX needs lutimes (os.utime follow_symlinks); Windows uses Win32."""
    if os.name == "nt":
        return True
    return os.utime in os.supports_follow_symlinks


def test_apply_timestamps_to_symlink_does_not_touch_target(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("payload", encoding="utf-8")
    link = tmp_path / "link.txt"
    if not _try_symlink(target, link):
        pytest.skip("symlink creation not permitted on this platform/account")
    if not _link_timestamps_settable():
        pytest.skip("platform cannot set link timestamps without following")

    target_before = os.lstat(str(target)).st_mtime
    epoch_2020 = 1577836800.0  # 2020-01-01, clearly distinct from "now"

    ok = apply_file_metadata(
        str(link),
        {"timestamps": {"created": epoch_2020, "modified": epoch_2020, "accessed": epoch_2020}},
    )
    assert ok is True

    # The target must be untouched...
    assert abs(os.lstat(str(target)).st_mtime - target_before) < 2
    # ...and the LINK itself must have received the timestamp.
    assert abs(os.lstat(str(link)).st_mtime - epoch_2020) < 2


def test_apply_timestamps_to_regular_file_still_works(tmp_path):
    # Non-symlink path must be unchanged by the 0.3.1 fix.
    f = tmp_path / "plain.txt"
    f.write_text("x", encoding="utf-8")
    epoch_2020 = 1577836800.0
    ok = apply_file_metadata(
        str(f),
        {"timestamps": {"created": epoch_2020, "modified": epoch_2020, "accessed": epoch_2020}},
    )
    assert ok is True
    assert abs(os.stat(str(f)).st_mtime - epoch_2020) < 2
