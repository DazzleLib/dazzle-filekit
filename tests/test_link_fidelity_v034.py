"""Regression tests for link-node fidelity (v0.3.4).

Three defects surfaced while designing the linkmirror engine (mirroring all
NTFS links from a failing drive onto its replacement):

1. JUNCTION TIMESTAMPS: ``apply_file_metadata`` gated the reparse-aware
   timestamp path with ``Path.is_symlink()``, which is False for junctions
   (IO_REPARSE_TAG_MOUNT_POINT). Junctions fell through to plain
   ``os.utime``, which follows the reparse point and stamps the TARGET
   directory -- the exact bug class fixed for symlinks in 0.3.1.

2. BROKEN DIRECTORY SYMLINKS: ``create_symlink`` auto-derived
   ``target_is_directory`` from ``target.is_dir()``, which is always False
   for a nonexistent target -- so a broken DIRECTORY symlink was recreated
   as a FILE symlink. Additionally, relative targets were probed against the
   process CWD instead of the link's parent directory.

3. TARGET STRING FIDELITY: the target was laundered through ``Path()``
   before creation, which normalizes away segments like ``a\\.\\b`` and
   flips ``/`` to ``\\`` -- a mirror must store the source's raw target
   bytes. (Measured 2026-07-21, tests/one-offs/probe_symlink_target_fidelity.py:
   os.symlink/CreateSymbolicLinkW store RELATIVE targets verbatim and the
   kernel canonicalizes ABSOLUTE targets to \\\\?\\ form regardless of API --
   so passing the raw string through unchanged is both necessary and
   sufficient for readlink round-trip fidelity.)
"""

import os
import platform

import pytest

from dazzle_filekit import apply_file_metadata
from dazzle_filekit.links import create_junction
from dazzle_filekit.operations import create_symlink

IS_WINDOWS = platform.system() == "Windows"

EPOCH_2020 = 1577836800.0  # 2020-01-01

FILE_ATTRIBUTE_DIRECTORY = 0x10


def _symlinks_available(tmp_path):
    probe_t = tmp_path / "_probe_target.txt"
    probe_t.write_text("x", encoding="utf-8")
    probe_l = tmp_path / "_probe_link.txt"
    try:
        os.symlink(str(probe_t), str(probe_l))
    except (OSError, NotImplementedError):
        return False
    os.unlink(str(probe_l))
    return True


# ---------------------------------------------------------------------------
# 1. Junction timestamps target the junction, never the target directory
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not IS_WINDOWS, reason="junctions are Windows-only")
def test_apply_timestamps_to_junction_does_not_touch_target_dir(tmp_path):
    target_dir = tmp_path / "target_dir"
    target_dir.mkdir()
    (target_dir / "payload.txt").write_text("x", encoding="utf-8")
    junction = tmp_path / "junc"
    assert create_junction(str(target_dir), str(junction)) is True

    target_mtime_before = os.lstat(str(target_dir)).st_mtime

    ok = apply_file_metadata(
        str(junction),
        {"timestamps": {"created": EPOCH_2020, "modified": EPOCH_2020,
                        "accessed": EPOCH_2020}},
    )
    assert ok is True

    # The junction NODE received the timestamp...
    assert abs(os.lstat(str(junction)).st_mtime - EPOCH_2020) < 2
    # ...and the target directory was not touched.
    assert abs(os.lstat(str(target_dir)).st_mtime - target_mtime_before) < 2


# ---------------------------------------------------------------------------
# 2. Broken directory symlinks keep their directory kind
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not IS_WINDOWS, reason="symlink kind is a Windows concept")
def test_broken_directory_symlink_keeps_directory_kind(tmp_path):
    if not _symlinks_available(tmp_path):
        pytest.skip("symlink creation not permitted on this platform/account")
    link = tmp_path / "broken_dir_link"
    ok = create_symlink(
        r"no\such\directory", str(link), target_is_directory=True
    )
    assert ok is True
    attrs = os.lstat(str(link)).st_file_attributes
    assert attrs & FILE_ATTRIBUTE_DIRECTORY, (
        "broken directory symlink was created as a FILE symlink"
    )


@pytest.mark.skipif(not IS_WINDOWS, reason="symlink kind is a Windows concept")
def test_relative_target_kind_probed_against_link_parent(tmp_path):
    """Auto-detection must resolve relative targets against the LINK's parent,
    not the process CWD."""
    if not _symlinks_available(tmp_path):
        pytest.skip("symlink creation not permitted on this platform/account")
    # tmp_path/sub/real_dir exists; CWD has no 'real_dir'
    sub = tmp_path / "sub"
    (sub / "real_dir").mkdir(parents=True)
    link = sub / "dir_link"
    old_cwd = os.getcwd()
    os.chdir(str(tmp_path))  # ensure CWD != link parent
    try:
        ok = create_symlink("real_dir", str(link))  # no explicit kind
    finally:
        os.chdir(old_cwd)
    assert ok is True
    attrs = os.lstat(str(link)).st_file_attributes
    assert attrs & FILE_ATTRIBUTE_DIRECTORY, (
        "relative dir target probed against CWD instead of link parent"
    )


# ---------------------------------------------------------------------------
# 3. Raw target string is stored verbatim (readlink round-trip)
# ---------------------------------------------------------------------------

def test_relative_target_stored_verbatim(tmp_path):
    if not _symlinks_available(tmp_path):
        pytest.skip("symlink creation not permitted on this platform/account")
    link = tmp_path / "verbatim_link"
    raw = r"sub\.\odd_but_legal.txt" if IS_WINDOWS else "sub/./odd_but_legal.txt"
    assert create_symlink(raw, str(link), target_is_directory=False) is True
    assert os.readlink(str(link)) == raw, (
        "target string was normalized; a mirror must store source bytes"
    )


@pytest.mark.skipif(not IS_WINDOWS, reason="junctions are Windows-only")
def test_create_junction_raw_roundtrip_and_broken_target(tmp_path):
    """create_junction_raw must (a) round-trip readlink byte-identically with
    a New-Item-created junction's form, and (b) create junctions whose target
    does not exist -- which New-Item refuses."""
    from dazzle_filekit.links import create_junction_raw
    from dazzle_filekit.utils.validation import is_junction

    real_target = tmp_path / "real_dir"
    real_target.mkdir()

    # (a) existing target: readlink form matches what the OS renders
    junc = tmp_path / "junc_ok"
    assert create_junction_raw(str(real_target), str(junc)) is True
    assert is_junction(str(junc))
    assert os.readlink(str(junc)) == "\\\\?\\" + str(real_target)
    # readlink -> recreate -> readlink is stable (the mirror round-trip)
    junc2 = tmp_path / "junc_ok2"
    assert create_junction_raw(os.readlink(str(junc)), str(junc2)) is True
    assert os.readlink(str(junc2)) == os.readlink(str(junc))

    # (b) BROKEN target: creation succeeds, link classifies as junction,
    # target stays broken (not resolved, not "fixed")
    broken = tmp_path / "junc_broken"
    missing = str(tmp_path / "no_such_dir")
    assert create_junction_raw(missing, str(broken)) is True
    assert is_junction(str(broken))
    assert os.readlink(str(broken)) == "\\\\?\\" + missing
    assert not os.path.exists(os.readlink(str(broken)))


def test_broken_relative_target_stored_verbatim(tmp_path):
    """The founding case: test_broken_links\\src\\broken_link on D: stores a
    relative target whose file does not exist; the mirror must reproduce it
    unresolved and unrepaired."""
    if not _symlinks_available(tmp_path):
        pytest.skip("symlink creation not permitted on this platform/account")
    link = tmp_path / "broken_link"
    raw = (r"test_broken_links\src\nonexistent.txt" if IS_WINDOWS
           else "test_broken_links/src/nonexistent.txt")
    assert create_symlink(raw, str(link), target_is_directory=False) is True
    assert os.readlink(str(link)) == raw
    assert not os.path.exists(str(link))  # still broken, not "fixed"
