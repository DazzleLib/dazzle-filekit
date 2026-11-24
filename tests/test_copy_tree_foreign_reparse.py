"""copy_tree_preserving_links does not crash on a reparse point it cannot read (0.5.4).

``is_junction`` answers "junction" when it cannot read an entry's reparse tag
(a guess that keeps copytree from entering it). The entry is then recreated
with ``os.readlink``, which raises ValueError ("not a symbolic link") for a
reparse point that is not a symlink or junction: a WSL symlink, an app alias, a
cloud placeholder. Before 0.5.4 that ValueError escaped mid-copy, and junctions
later in the tree were never recreated. Now it is reported like any other
junction that could not be recreated, in the shutil.Error raised at the end.

Found 2026-11-23 by a read-only review across the DazzleLib stack, after the
same fault was fixed in dazzlecmd-lib. Nothing here needs a real WSL link:
is_junction and os.readlink are patched for the one entry under test.
"""
import os
import shutil

import pytest

import dazzle_filekit.utils.validation as validation
from dazzle_filekit.operations import copy_tree_preserving_links


def test_an_unreadable_reparse_point_is_reported_not_raised(tmp_path, monkeypatch):
    src = tmp_path / "src"
    (src / "odd").mkdir(parents=True)          # stands in for the foreign reparse point
    (src / "keep.txt").write_text("k")
    odd = os.path.normcase(str(src / "odd"))
    real_is_junction = validation.is_junction
    real_readlink = os.readlink

    monkeypatch.setattr(validation, "is_junction",
                        lambda p: os.path.normcase(str(p)) == odd or real_is_junction(p))

    def readlink(p, *a, **k):
        if os.path.normcase(str(p)) == odd:
            raise ValueError("not a symbolic link")
        return real_readlink(p, *a, **k)
    monkeypatch.setattr(os, "readlink", readlink)

    with pytest.raises(shutil.Error) as info:
        copy_tree_preserving_links(src, tmp_path / "dst")

    assert "odd" in str(info.value)
    assert (tmp_path / "dst" / "keep.txt").read_text() == "k"     # the rest was copied
    assert not (tmp_path / "dst" / "odd").exists()                  # never entered
