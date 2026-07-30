"""Tests for :mod:`dazzle_filekit.longpath`.

The safety tests matter more than the arithmetic ones. A shim reaper deletes
junctions continuously, and a junction is indistinguishable from an ordinary
directory to every naive check -- so "does removal ever touch the target?" is
pinned here with a canary file rather than argued.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from dazzle_filekit import longpath as lp

WINDOWS = os.name == "nt"
win_only = pytest.mark.skipif(not WINDOWS, reason="junctions are Windows-only")


# --------------------------------------------------------------------------
# needs_shim -- the trigger
# --------------------------------------------------------------------------

@win_only
def test_short_path_needs_no_shim():
    assert lp.needs_shim(r"C:\short\file.pdf") is False


@win_only
def test_long_path_needs_shim():
    long_path = "C:\\" + "a" * 300 + "\\f.pdf"
    assert lp.needs_shim(long_path) is True


@win_only
def test_extended_prefix_is_left_alone():
    """A path that already opted out of MAX_PATH must not be rewritten."""
    p = "\\\\?\\C:\\" + "a" * 300 + "\\f.pdf"
    assert lp.needs_shim(p) is False


@win_only
def test_threshold_is_honoured():
    p = "C:\\" + "a" * 100 + "\\f.pdf"
    assert lp.needs_shim(p, threshold=50) is True
    assert lp.needs_shim(p, threshold=500) is False


def test_posix_never_needs_a_shim():
    """AC9: PATH_MAX is 4096/1024 off Windows -- this must be a pure no-op."""
    if WINDOWS:
        pytest.skip("POSIX behaviour")
    assert lp.needs_shim("/" + "a" * 5000) is False
    assert lp.resolve_shim_root("/tmp/x") is None
    plan = lp.plan_shim("/" + "a" * 5000 + "/f.pdf")
    assert plan.needed is False
    assert plan.resolved() == Path("/" + "a" * 5000 + "/f.pdf")


# --------------------------------------------------------------------------
# root resolution and budget -- AC12/AC13/AC14
# --------------------------------------------------------------------------

@win_only
def test_candidate_roots_are_shortest_first():
    roots = lp.candidate_roots(r"D:\some\file.pdf")
    lengths = [len(str(r)) for r in roots]
    assert lengths[0] <= lengths[-1]
    assert any(str(r).upper().startswith("D:") for r in roots)


@win_only
def test_candidate_roots_deduplicate():
    roots = [str(r).casefold() for r in lp.candidate_roots(r"C:\x\y.pdf")]
    assert len(roots) == len(set(roots))


def test_budget_shrinks_as_root_grows():
    """AC13: the budget is what makes a degraded root reportable."""
    short = lp.budget_for("C:\\.dzs")
    long_root = lp.budget_for("C:\\Users\\Administrator\\AppData\\Local\\dz\\longpath")
    assert short > long_root
    # the measured worst case in the motivating corpus was a 244-char filename
    assert short >= 244


def test_budget_matches_usable_path_arithmetic():
    root = "C:\\.dzs"
    assert lp.budget_for(root, id_len=4) == lp.USABLE_PATH - (len(root) + 1 + 4 + 1)


@win_only
def test_resolve_shim_root_without_probe_takes_first():
    got = lp.resolve_shim_root(r"D:\x\y.pdf", probe=False)
    assert got == lp.candidate_roots(r"D:\x\y.pdf")[0]


@win_only
def test_resolve_shim_root_falls_through_unwritable_candidates():
    """AC12: an unwritable tier must be skipped, not fatal."""
    bogus = Path("Q:\\definitely\\not\\writable\\.dzs")
    usable = Path(os.environ["TEMP"]) / ".dzs_test_root"
    got = lp.resolve_shim_root(candidates=[bogus, usable])
    assert got == usable
    if usable.is_dir():
        try:
            os.rmdir(usable)
        except OSError:
            pass


@win_only
def test_long_username_root_is_reported_as_degraded():
    """AC14: correctness must not depend on the developer's short username."""
    long_root = "C:\\Users\\SomeVeryLongAccountName\\.dzs"
    assert lp.budget_for(long_root) < 244    # would drop the worst real files


# --------------------------------------------------------------------------
# plan_shim -- the arithmetic
# --------------------------------------------------------------------------

@win_only
def test_plan_is_noop_for_short_path():
    """AC1: under threshold, nothing is planned and the original is returned."""
    plan = lp.plan_shim(r"C:\a\b.pdf")
    assert plan.needed is False
    assert plan.link is None
    assert plan.resolved() == Path(r"C:\a\b.pdf")


@win_only
def test_plan_brings_long_path_under_the_limit():
    """AC2: the whole point."""
    deep = Path("D:\\") / ("dir" + "x" * 60) / ("sub" + "y" * 60) / ("n" * 200 + ".pdf")
    plan = lp.plan_shim(deep, root="C:\\.dzs")
    assert plan.needed is True
    assert plan.usable, plan.reason
    assert len(str(plan.shimmed)) <= lp.USABLE_PATH


@win_only
def test_plan_prefers_the_shallowest_anchor_that_fits():
    """Shallowest maximises reuse: one shim serves the widest subtree."""
    deep = Path("D:\\") / "aa" / "bb" / "cc" / ("n" * 40 + ".pdf")
    plan = lp.plan_shim(deep, root="C:\\.dzs", threshold=10)
    assert plan.anchor == Path("D:\\")


@win_only
def test_plan_anchors_deeper_when_the_filename_is_huge():
    """A 240-char name leaves room only for its immediate parent."""
    deep = Path("D:\\") / "aa" / "bb" / "cc" / ("n" * 240 + ".pdf")
    plan = lp.plan_shim(deep, root="C:\\.dzs")
    assert plan.needed is True
    if plan.usable:
        assert plan.anchor == deep.parent


@win_only
def test_component_over_name_max_is_reported_not_faked():
    """No link can shorten a single component -- say so rather than pretend."""
    bad = Path("D:\\x") / ("z" * (lp.NAME_MAX + 10) + ".pdf")
    plan = lp.plan_shim(bad, root="C:\\.dzs")
    assert plan.needed is True
    assert plan.usable is False
    assert "NAME_MAX" in plan.reason


@win_only
def test_impossible_plan_still_returns_the_original():
    """AC6: never leave a caller worse off than if this module were absent."""
    bad = Path("D:\\x") / ("z" * (lp.NAME_MAX + 10) + ".pdf")
    plan = lp.plan_shim(bad, root="C:\\.dzs")
    assert plan.resolved() == bad


@win_only
def test_same_anchor_yields_a_stable_link():
    """Reuse depends on the id being a pure function of the anchor."""
    a = lp.plan_shim(Path("D:\\") / ("q" * 250) / "f.pdf", root="C:\\.dzs")
    b = lp.plan_shim(Path("D:\\") / ("q" * 250) / "g.pdf", root="C:\\.dzs")
    if a.usable and b.usable and a.anchor == b.anchor:
        assert a.link == b.link


@win_only
def test_anchor_id_is_case_insensitive():
    """Windows paths are case-insensitive; two spellings must share one shim."""
    lower = lp._anchor_id(Path("d:\\some\\dir"))
    upper = lp._anchor_id(Path("D:\\SOME\\DIR"))
    assert lower == upper


# --------------------------------------------------------------------------
# THE SAFETY TESTS -- AC3/AC4/AC5
# --------------------------------------------------------------------------

@win_only
def test_remove_shim_refuses_a_real_directory(tmp_path):
    """AC3: a real directory in the shim root must survive the reaper."""
    real = tmp_path / "not_a_junction"
    real.mkdir()
    (real / "canary.txt").write_text("must survive")

    assert lp.remove_shim(real) is False
    assert real.is_dir()
    assert (real / "canary.txt").read_text() == "must survive"


@win_only
def test_remove_shim_removes_link_but_never_the_target(tmp_path):
    """AC4: the load-bearing safety property, pinned with a canary."""
    target = tmp_path / "TARGET"
    target.mkdir()
    canary = target / "canary.txt"
    canary.write_text("must survive")

    link = tmp_path / "lnk"
    assert lp.create_shim(
        lp.ShimPlan(original=target / "x", needed=True, anchor=target, link=link)
    ) is True
    assert lp.remove_shim(link) is True

    assert not link.exists()
    assert target.is_dir()
    assert canary.read_text() == "must survive"


@win_only
def test_remove_shim_refuses_a_file(tmp_path):
    f = tmp_path / "plain.txt"
    f.write_text("x")
    assert lp.remove_shim(f) is False
    assert f.exists()


@win_only
def test_remove_shim_on_missing_path_is_false_not_an_error():
    assert lp.remove_shim(Path("C:\\nope\\nope\\nope_missing")) is False


@win_only
def test_reaper_skips_young_shims_and_spares_real_dirs(tmp_path):
    """AC3 + AC5 together, in the shape the reaper actually runs."""
    target = tmp_path / "T"
    target.mkdir()
    (target / "canary.txt").write_text("survive")

    link = tmp_path / "root" / "aaaa"
    link.parent.mkdir()
    real = link.parent / "real_dir"
    real.mkdir()
    (real / "keep.txt").write_text("keep")

    lp.create_shim(lp.ShimPlan(original=target / "x", needed=True,
                               anchor=target, link=link))

    # too young -> nothing reaped
    assert lp.reap_shims(link.parent, max_age_seconds=9999) == []
    assert link.exists()

    # old enough -> the junction goes, the real directory does not
    removed = lp.reap_shims(link.parent, max_age_seconds=0,
                            now=time.time() + 10_000)
    assert link in removed
    assert real.is_dir()
    assert (real / "keep.txt").read_text() == "keep"
    assert (target / "canary.txt").read_text() == "survive"


@win_only
def test_reaper_on_missing_root_is_empty_not_an_error():
    assert lp.reap_shims(Path("C:\\nope\\missing\\root")) == []


# --------------------------------------------------------------------------
# end-to-end
# --------------------------------------------------------------------------

@win_only
def test_shim_path_roundtrip_opens_a_long_file(tmp_path):
    """AC2 end to end: write via a long path, read back via the shim."""
    deep = tmp_path
    while len(str(deep)) < 150:
        deep = deep / "nested_directory_segment"
    deep.mkdir(parents=True, exist_ok=True)

    target = deep / ("L" * 120 + ".txt")
    if len(str(target)) <= lp.DEFAULT_THRESHOLD:
        pytest.skip("tmp_path too short to construct an over-threshold case")

    # write through the extended-length prefix, which Python honours
    with open("\\\\?\\" + str(target), "w") as fh:
        fh.write("payload")

    root = tmp_path / ".dzs"
    resolved = lp.shim_path(target, root=root)

    assert len(str(resolved)) <= lp.USABLE_PATH
    assert Path(resolved).read_text() == "payload"


@win_only
def test_shim_path_passes_short_paths_through_untouched(tmp_path):
    """AC1: byte-identical passthrough, and no shim root brought into being."""
    f = tmp_path / "small.txt"
    f.write_text("hi")
    root = tmp_path / ".dzs"
    assert lp.shim_path(f, root=root) == f
    assert not root.exists()
