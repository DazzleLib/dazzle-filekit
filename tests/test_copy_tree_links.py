"""copy_tree_preserving_links(links=...): the caller chooses what happens to links.

Through 0.4.3 the function kept symlinks but entered junctions and copied
what they pointed at, despite its name. From 0.5.0 ``links="keep"`` (the
default) recreates a junction as a junction, ``"follow"`` copies the contents,
and ``"skip"`` leaves links out.

Everything lives under ``tmp_path``: the junction's target is a scratch folder
beside the tree, and nothing is deleted.
"""
import os
import shutil
import sys

import pytest

from dazzle_filekit.links import create_junction_raw
from dazzle_filekit.operations import copy_tree_preserving_links
from dazzle_filekit.utils.validation import is_junction

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="junctions are Windows-only")


@pytest.fixture
def tree(tmp_path):
    """src/ with a file, a folder, and (on Windows) a junction to outside/."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("behind the link")
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "a.txt").write_text("alpha")
    (src / "sub" / "b.txt").write_text("beta")
    if sys.platform == "win32":
        assert create_junction_raw(str(outside), str(src / "sub" / "jn"))
    return src, outside, tmp_path / "dst"


def test_an_unknown_choice_is_refused_before_anything_is_copied(tree):
    src, _outside, dst = tree
    with pytest.raises(ValueError):
        copy_tree_preserving_links(src, dst, links="resolve")
    assert not dst.exists()


@windows_only
def test_keep_is_the_default_and_recreates_the_junction(tree):
    src, outside, dst = tree

    copy_tree_preserving_links(src, dst)

    copied = dst / "sub" / "jn"
    assert is_junction(copied)                               # a link, not a folder of copies
    assert os.path.samefile(os.readlink(copied), outside)    # same target
    assert (dst / "a.txt").read_text() == "alpha"
    assert (dst / "sub" / "b.txt").read_text() == "beta"
    assert is_junction(src / "sub" / "jn")                   # the source is untouched
    assert sorted(os.listdir(outside)) == ["secret.txt"]


@windows_only
def test_follow_copies_what_the_junction_points_at(tree):
    src, _outside, dst = tree

    copy_tree_preserving_links(src, dst, links="follow")

    copied = dst / "sub" / "jn"
    assert copied.is_dir() and not is_junction(copied)
    assert (copied / "secret.txt").read_text() == "behind the link"


@windows_only
def test_skip_leaves_the_junction_out(tree):
    src, _outside, dst = tree

    copy_tree_preserving_links(src, dst, links="skip")

    assert not os.path.lexists(dst / "sub" / "jn")
    assert (dst / "sub" / "b.txt").read_text() == "beta"


@windows_only
def test_a_junction_with_a_missing_target_is_still_kept(tree):
    src, _outside, dst = tree
    assert create_junction_raw(str(src.parent / "gone"), str(src / "dangling"))

    copy_tree_preserving_links(src, dst)

    assert is_junction(dst / "dangling")


@windows_only
def test_a_junction_that_cannot_be_recreated_is_an_error(tree, monkeypatch):
    src, _outside, dst = tree
    monkeypatch.setattr("dazzle_filekit.links.create_junction_raw", lambda target, link: False)

    with pytest.raises(shutil.Error):
        copy_tree_preserving_links(src, dst)


@windows_only
def test_the_callers_own_ignore_still_applies(tree):
    src, _outside, dst = tree

    copy_tree_preserving_links(src, dst, ignore=shutil.ignore_patterns("jn", "a.txt"))

    assert not os.path.lexists(dst / "sub" / "jn")           # ignored, so not recreated
    assert not (dst / "a.txt").exists()


def _symlink_or_skip(target, link):
    try:
        os.symlink(str(target), str(link))
    except (OSError, NotImplementedError):
        pytest.skip("creating a symlink needs a privilege this account lacks")


def test_symlinks_follow_the_same_three_choices(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    src = tmp_path / "src"
    src.mkdir()
    _symlink_or_skip(outside, src / "ln.txt")

    copy_tree_preserving_links(src, tmp_path / "keep")
    copy_tree_preserving_links(src, tmp_path / "follow", links="follow")
    copy_tree_preserving_links(src, tmp_path / "skip", links="skip")

    assert os.path.islink(tmp_path / "keep" / "ln.txt")
    followed = tmp_path / "follow" / "ln.txt"
    assert not os.path.islink(followed) and followed.read_text() == "outside"
    assert not os.path.lexists(tmp_path / "skip" / "ln.txt")
