"""v0.3.0 (#15 Phase C): D4 clean renames (no shims).

  - AC-7: classify_fs_object (renamed from get_path_type) returns the same
          values get_path_type did -- a junction still classifies as 'directory'
          (link-kind classification is analyze_link's job, not this function's).
  - AC-8: is_unc_path is one canonical, platform-independent definition
          (delegates to unctools): '//server/share' is True -- a strict superset
          of the old win32-only ('\\\\'-prefix) check that returned False for
          forward-slash UNC. Both export sites (paths + utils.validation) agree.
  - Clean break: the old names (normalize_path, normalize_path_no_resolve,
          get_path_type) are GONE -- no shims.
"""

import os
import sys

import pytest

import dazzle_filekit as fk
from dazzle_filekit.paths import classify_fs_object, is_unc_path as paths_is_unc
from dazzle_filekit.utils.validation import is_unc_path as validation_is_unc


# ---------------------------------------------------------------------------
# AC-7: classify_fs_object (was get_path_type)
# ---------------------------------------------------------------------------


def test_classify_regular_file(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    assert classify_fs_object(f) == "file"


def test_classify_directory(tmp_path):
    assert classify_fs_object(tmp_path) == "directory"


def test_classify_nonexistent(tmp_path):
    assert classify_fs_object(tmp_path / "nope") == "nonexistent"


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are Windows-only")
def test_classify_junction_is_directory(tmp_path):
    """A junction still classifies as 'directory' (unchanged from get_path_type).

    classify_fs_object answers WHAT kind of object; link-kind classification is
    analyze_link's job. This pins the pure-rename contract (no junction value).
    """
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "jct"
    if not fk.create_junction(target, link):
        pytest.skip("could not create junction")
    assert classify_fs_object(link) == "directory"
    # ...while analyze_link DOES distinguish it.
    assert fk.analyze_link(link).kind == "junction"


def test_classify_symlink(tmp_path):
    target = tmp_path / "t.txt"
    target.write_text("x")
    link = tmp_path / "s.txt"
    try:
        os.symlink(str(target), str(link))
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation requires privilege")
    assert classify_fs_object(link) == "symlink"


# ---------------------------------------------------------------------------
# AC-8: is_unc_path -- one canonical, platform-independent definition
# ---------------------------------------------------------------------------


def test_is_unc_path_forward_slash_is_true():
    """'//server/share' is True on every platform (was False under the old
    win32-only '\\\\'-prefix check). The divergence-correction, pinned."""
    assert fk.is_unc_path("//server/share") is True
    assert paths_is_unc("//server/share") is True
    assert validation_is_unc("//server/share") is True


def test_is_unc_path_backslash_is_true():
    assert fk.is_unc_path(r"\\server\share") is True


def test_is_unc_path_local_is_false():
    assert fk.is_unc_path(r"C:\Users\foo") is False
    assert fk.is_unc_path("/home/user") is False


def test_both_export_sites_agree_with_unctools():
    """paths.is_unc_path and utils.validation.is_unc_path are the same canonical
    behavior as unctools (single source of truth, no divergence)."""
    from unctools import is_unc_path as unc_is_unc
    for p in ("//server/share", r"\\srv\sh", r"C:\x", "/home/x", "relative/path"):
        expected = unc_is_unc(p)
        assert paths_is_unc(p) == expected
        assert validation_is_unc(p) == expected


# ---------------------------------------------------------------------------
# Clean break: old names are gone (no shims)
# ---------------------------------------------------------------------------


def test_old_names_removed():
    assert not hasattr(fk, "normalize_path")
    assert not hasattr(fk, "normalize_path_no_resolve")
    assert not hasattr(fk, "get_path_type")
    import dazzle_filekit.paths as paths
    assert not hasattr(paths, "normalize_path")
    assert not hasattr(paths, "normalize_path_no_resolve")
    assert not hasattr(paths, "get_path_type")


def test_canonical_normalizer_covers_both_old_behaviors(tmp_path):
    """normalize_cross_platform_path(resolve=True/False) reproduces the removed
    wrappers' link-following vs link-safe behavior."""
    from dazzle_filekit.paths import normalize_cross_platform_path as ncpp
    # link-safe (was normalize_path_no_resolve): preserves the literal path
    p = ncpp("/c/Users/foo/test.txt")  # resolve=False default
    assert "foo" in str(p)
    # link-following (was normalize_path): resolves to absolute
    p2 = ncpp(tmp_path / "real.txt", resolve=True)
    assert p2.is_absolute()
