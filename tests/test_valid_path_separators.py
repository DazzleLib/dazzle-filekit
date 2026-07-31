"""`is_valid_path` must accept forward-slash paths on Windows.

Windows accepts `/` as a path separator everywhere it accepts `\\` -- the
Win32 API normalizes it, and every Python stdlib path call honors it. But
`_is_valid_windows_path` split on backslash ONLY, so a path like
`C:/code/project` collapsed into a single "component" containing `/` and
`:` -- both members of WINDOWS_INVALID_CHARS -- and was reported invalid.

These tests do not assert that Windows accepts forward slashes; they
DEMONSTRATE it against the real filesystem first, then require
`is_valid_path` to agree with the operating system.
"""

import os
import sys

import pytest

from dazzle_filekit.utils.validation import is_valid_path

WINDOWS_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="Windows separator semantics")


# ── First: prove the premise against the real filesystem ──────────────

@WINDOWS_ONLY
def test_windows_really_does_accept_forward_slashes(tmp_path):
    """Ground truth: the OS resolves a forward-slash path to the same
    directory as its backslash spelling. If this ever fails, the tests
    below are testing the wrong thing."""
    target = tmp_path / "code" / "project"
    target.mkdir(parents=True)

    forward = str(target).replace("\\", "/")
    assert "/" in forward
    assert os.path.isdir(forward), "Windows should resolve forward-slash paths"
    assert os.path.samefile(forward, str(target))

    # Writing through the forward-slash spelling works too.
    with open(forward + "/probe.txt", "w", encoding="utf-8") as fh:
        fh.write("ok")
    assert (target / "probe.txt").read_text(encoding="utf-8") == "ok"


# ── Then: require is_valid_path to agree with the OS ──────────────────

@WINDOWS_ONLY
def test_forward_slash_path_is_valid(tmp_path):
    """The regression: a real, resolvable directory must not be called
    invalid merely because it is spelled with forward slashes."""
    target = tmp_path / "code" / "project"
    target.mkdir(parents=True)
    forward = str(target).replace("\\", "/")

    assert os.path.isdir(forward)          # the OS says it exists
    assert is_valid_path(forward) is True  # ...so validation must not disagree


@WINDOWS_ONLY
@pytest.mark.parametrize("path", [
    "C:/code/project",
    "C:/code/project/sub/dir",
    "D:/",
    "C:/Users/name/AppData/Local",
])
def test_common_forward_slash_shapes_are_valid(path):
    assert is_valid_path(path) is True


@WINDOWS_ONLY
@pytest.mark.parametrize("path", [
    r"C:\code\project",
    r"C:\code\project\sub\dir",
    r"\\server\share\folder",
])
def test_backslash_paths_remain_valid(path):
    """The fix must not regress the spelling that already worked."""
    assert is_valid_path(path) is True


@WINDOWS_ONLY
def test_mixed_separators_are_valid():
    """Windows tolerates mixed separators; validation should too."""
    assert is_valid_path(r"C:\code/project\sub") is True


# ── Genuinely invalid paths must STILL be rejected ────────────────────

@WINDOWS_ONLY
@pytest.mark.parametrize("path", [
    'C:/code/bad"name',      # quote
    "C:/code/bad<name",      # angle bracket
    "C:/code/bad|name",      # pipe
    "C:/code/bad?name",      # question mark
    "C:/code/bad*name",      # wildcard
    "C:/code/extra:colon",   # colon outside the drive spec
])
def test_invalid_characters_still_rejected(path):
    """Splitting on both separators must not weaken the character check --
    these were rejected before the fix and must stay rejected."""
    assert is_valid_path(path) is False


@WINDOWS_ONLY
@pytest.mark.parametrize("path", ["C:/code/nul", "C:/code/con.txt", "C:/tmp/com1"])
def test_reserved_names_still_rejected_with_forward_slashes(path):
    """Reserved-name detection must work on forward-slash paths too --
    before the fix these were rejected for the WRONG reason (the '/'
    character), which meant the reserved-name check never actually ran."""
    assert is_valid_path(path) is False
