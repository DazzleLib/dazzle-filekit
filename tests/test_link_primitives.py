"""v0.3.0 (#15 Phase A): intrinsic link primitives.

Covers the acceptance checks from the #15 completion design:

  - AC-1: analyze_link reports kind / is_broken / is_circular intrinsically,
          with no destination parameter; chain cycles are NOT flagged circular.
  - AC-2: compute_relative_path traverses siblings (``..``) where
          get_relative_path (subpath-only) returns None.
  - AC-3: create_junction / create_hardlink / read_link_target round-trip,
          with no ``cmd /c`` shell-outs in their bodies.

Link-creation tests skip gracefully where the platform/privileges don't allow
it (symlinks need admin/Developer Mode on Windows; hardlinks need same-volume
support; junctions are Windows-only but do NOT need elevation).
"""

import inspect
import os
import sys
from pathlib import Path

import pytest

from dazzle_filekit import (
    LinkInfo,
    analyze_link,
    compute_relative_path,
    create_hardlink,
    create_junction,
    detect_link_type,
    get_relative_path,
    read_link_target,
)
from dazzle_filekit import links as links_mod


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


# ---------------------------------------------------------------------------
# AC-2: compute_relative_path vs get_relative_path
# ---------------------------------------------------------------------------


def test_compute_relative_path_traverses_siblings(tmp_path):
    """compute_relative_path returns a ``..``-traversing path between siblings;
    get_relative_path (subpath containment) returns None for the same pair."""
    start = tmp_path / "a" / "x"
    target = tmp_path / "a" / "b" / "c"
    start.mkdir(parents=True)
    target.mkdir(parents=True)

    rel = compute_relative_path(target, start)
    assert rel == os.path.join("..", "b", "c")

    # The whole point: these are NOT the same operation.
    assert get_relative_path(target, start) is None


def test_compute_relative_path_subpath(tmp_path):
    start = tmp_path / "root"
    target = tmp_path / "root" / "sub" / "f"
    target.mkdir(parents=True)
    assert compute_relative_path(target, start) == os.path.join("sub", "f")


def test_compute_relative_path_cross_drive_fallback():
    """On a cross-drive ValueError (Windows), fall back to the absolute target."""
    if sys.platform != "win32":
        pytest.skip("cross-drive ValueError is Windows-only")
    # Z: is unlikely to be the cwd drive; relpath across drives raises ValueError.
    result = compute_relative_path(r"Z:\some\target", r"C:\start")
    assert result == os.path.abspath(r"Z:\some\target")
    assert compute_relative_path(r"Z:\some\target", r"C:\start", fallback_to_absolute=False) is None


# ---------------------------------------------------------------------------
# AC-1: analyze_link intrinsic contract
# ---------------------------------------------------------------------------


def test_analyze_link_has_no_dest_parameter():
    """The intrinsic analyze_link must NOT take a destination path (that is L3)."""
    params = list(inspect.signature(analyze_link).parameters)
    assert params == ["link_path"], f"analyze_link should take only link_path, got {params}"


def test_analyze_regular_file_is_not_a_link(tmp_path):
    f = tmp_path / "plain.txt"
    f.write_text("x")
    info = analyze_link(f)
    assert isinstance(info, LinkInfo)
    assert info.kind is None
    assert info.is_broken is False


def test_analyze_nonexistent_is_not_a_link(tmp_path):
    info = analyze_link(tmp_path / "nope")
    assert info.kind is None


def test_analyze_symlink(tmp_path):
    target = tmp_path / "t.txt"
    target.write_text("data")
    link = tmp_path / "s.txt"
    if not _try_symlink(target, link):
        pytest.skip("symlink creation requires admin/Developer Mode")

    info = analyze_link(link)
    assert info.kind == "symlink"
    assert info.is_broken is False
    assert info.is_circular is False
    assert info.resolved_target == target.resolve()


def test_analyze_broken_symlink(tmp_path):
    missing = tmp_path / "missing.txt"  # never created
    link = tmp_path / "s.txt"
    if not _try_symlink(missing, link):
        pytest.skip("symlink creation requires admin/Developer Mode")

    info = analyze_link(link)
    assert info.kind == "symlink"
    assert info.is_broken is True


def test_analyze_self_referential_symlink_is_circular(tmp_path):
    """A link pointing at its own path is intrinsically circular (AC-1)."""
    link = tmp_path / "selflink"
    if not _try_symlink(link, link):
        pytest.skip("symlink creation requires admin/Developer Mode")

    info = analyze_link(link)
    assert info.kind == "symlink"
    assert info.is_circular is True


def test_chain_cycle_is_not_flagged_circular(tmp_path):
    """A -> B -> A is a CHAIN cycle; the intrinsic check must NOT flag it
    (chain detection is a traversal/L3 concern, out of scope by design)."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    if not _try_symlink(b, a):  # a -> b
        pytest.skip("symlink creation requires admin/Developer Mode")
    if not _try_symlink(a, b):  # b -> a
        pytest.skip("symlink creation requires admin/Developer Mode")

    info = analyze_link(a)
    assert info.kind == "symlink"
    assert info.is_circular is False  # direct self-ref only


# ---------------------------------------------------------------------------
# AC-3: create_hardlink (no admin needed on same volume)
# ---------------------------------------------------------------------------


def test_create_hardlink_and_analyze(tmp_path):
    src = tmp_path / "file.txt"
    src.write_text("hard data")
    link = tmp_path / "hard.txt"
    if not create_hardlink(src, link):
        pytest.skip("hard links not supported on this filesystem")

    assert link.read_text() == "hard data"
    info = analyze_link(link)
    assert info.kind == "hardlink"
    # A hardlink is a valid second name -- NOT broken, no single target.
    assert info.is_broken is False
    assert info.raw_target is None


def test_create_hardlink_rejects_directory(tmp_path):
    d = tmp_path / "dir"
    d.mkdir()
    assert create_hardlink(d, tmp_path / "x") is False


def test_detect_link_type_plain_file(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    assert detect_link_type(f) is None


# ---------------------------------------------------------------------------
# AC-3: create_junction (Windows-only, no elevation needed)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are Windows-only")
def test_create_junction_analyze_and_read_target(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "jct"
    if not create_junction(target, link):
        pytest.skip("could not create junction in this environment")

    info = analyze_link(link)
    assert info.kind == "junction"
    assert info.is_broken is False

    rt = read_link_target(link)
    assert rt is not None
    assert Path(rt).name == "target"


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are Windows-only")
def test_create_junction_force_replaces(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "jct"
    if not create_junction(target, link):
        pytest.skip("could not create junction in this environment")
    # Without force, a second create must fail.
    assert create_junction(target, link, force=False) is False
    # With force, it succeeds.
    assert create_junction(target, link, force=True) is True


def test_create_junction_off_windows_returns_false(tmp_path):
    if sys.platform == "win32":
        pytest.skip("this asserts the non-Windows guard")
    assert create_junction(tmp_path / "t", tmp_path / "l") is False


# ---------------------------------------------------------------------------
# AC-3 (house rule): no banned cmd shell-outs in the link primitives
# ---------------------------------------------------------------------------


def test_no_cmd_shellouts_in_link_module():
    """create_junction/read_link_target must not invoke cmd.exe.

    The module docstring *mentions* the banned ``cmd /c mklink`` / ``dir /al``
    it replaces, so we check for the actual invocation form -- ``cmd`` as a
    quoted subprocess argv element -- not the prose, and positively confirm
    PowerShell is the mechanism instead.
    """
    source = inspect.getsource(links_mod)
    assert "'cmd'" not in source and '"cmd"' not in source, (
        "link primitives must not shell out to cmd.exe (use PowerShell / DeviceIoControl)"
    )
    assert "powershell" in source.lower()
