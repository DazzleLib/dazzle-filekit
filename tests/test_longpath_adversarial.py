"""Adversarial tests for :mod:`dazzle_filekit.longpath`.

Companion to ``test_longpath.py`` (the author's own arithmetic + safety
suite). This file attacks properties the author did not think to assert:
hash-id collisions, TOCTOU windows, exotic junction states no PowerShell
call would ever produce, concurrency, and inputs chosen to make
:func:`shim_path` raise despite its "never raises" contract.

SAFETY COMMITMENT
------------------
``candidate_roots()`` / ``resolve_shim_root(probe=True)`` / ``create_shim`` /
``reap_shims`` must NEVER run against unmodified real-drive candidates
(``C:\\.dzs``, ``%USERPROFILE%\\.dzs``, etc). Every filesystem-touching call
in this file either passes an explicit ``tmp_path``-scoped ``root=`` /
``candidates=``, or monkeypatches ``SystemDrive``/``USERPROFILE``/``HOME``/
``TEMP``/``TMP`` to point under ``tmp_path`` first. Calls to ``plan_shim``
with a bare string like ``root="C:\\.dzs"`` are safe regardless -- per its
own docstring, ``plan_shim`` never touches the filesystem, it only computes
a plan.

Not everything here is a "this must fail" assertion. Some tests pin down
CURRENT behaviour (including a couple of narrow, low-impact gaps) so the
written report can describe them precisely instead of arguing from theory.
Those are called out in their docstrings.
"""
from __future__ import annotations

import concurrent.futures
import os
import shutil
import threading
import time
from pathlib import Path

import pytest

from dazzle_filekit import longpath as lp
from dazzle_filekit.links import create_junction, create_junction_raw
from dazzle_filekit.utils.validation import is_junction

WINDOWS = os.name == "nt"
win_only = pytest.mark.skipif(not WINDOWS, reason="junctions are Windows-only")


# ==========================================================================
# 1. HASH-ID COLLISION -- top priority. Two different anchors colliding on
#    the same short id means create_shim's `is_junction(link) -> return True`
#    fast path silently serves the WRONG directory's content. No crash.
# ==========================================================================

@win_only
def test_anchor_id_collision_create_shim_serves_wrong_directory(tmp_path, monkeypatch):
    """create_shim trusts that an existing junction at `link` was minted for
    the anchor being requested now ("id is a hash of it" -- see the comment
    in longpath.py). That assumption fails on any collision: is_junction
    (link) is still True, so create_shim reports success for the SECOND
    anchor without ever pointing the junction at it.
    """
    anchor_a = tmp_path / "AAA"
    anchor_a.mkdir()
    (anchor_a / "shared.txt").write_text("FROM_A")

    anchor_b = tmp_path / "BBB"
    anchor_b.mkdir()
    (anchor_b / "shared.txt").write_text("FROM_B")

    root = tmp_path / ".dzs"
    root.mkdir()
    link = root / "cafe"  # forced collision -- both anchors hash to this id

    monkeypatch.setattr(lp, "_anchor_id", lambda anchor, length=lp._ID_LEN: "cafe")

    plan_a = lp.ShimPlan(original=anchor_a / "shared.txt", needed=True,
                         anchor=anchor_a, link=link, shimmed=link / "shared.txt")
    plan_b = lp.ShimPlan(original=anchor_b / "shared.txt", needed=True,
                         anchor=anchor_b, link=link, shimmed=link / "shared.txt")

    assert lp.create_shim(plan_a) is True
    assert (link / "shared.txt").read_text() == "FROM_A"

    result_b = lp.create_shim(plan_b)
    served = plan_b.shimmed.read_text()

    # EXPECTED (safe) behaviour: create_shim must not claim success while
    # still serving anchor_a's tree for a request against anchor_b.
    assert result_b is False or served == "FROM_B", (
        "create_shim() returned %r and the shim now serves %r for a "
        "request against anchor_b -- id collision silently served the "
        "wrong directory's content with no error" % (result_b, served)
    )


@win_only
def test_anchor_id_collision_probability_at_default_id_len():
    """Not an assertion about the module -- a sanity check on the severity
    claim in the report. _ID_LEN=4 hex chars = 65536 slots; the birthday
    bound says ~300 distinct long-path anchors already cross 50% collision
    probability. That number should hold up on inspection.
    """
    import math
    n = 16 ** lp._ID_LEN
    k = 300
    p_collision = 1 - math.exp(-(k * k) / (2 * n))
    assert p_collision > 0.45


# ==========================================================================
# 2. EXOTIC JUNCTION STATES -- create_junction_raw builds states PowerShell's
#    New-Item refuses to build (missing target, relative target). These are
#    the shapes a reaper meets after a drive letter changes.
# ==========================================================================

@win_only
def test_remove_shim_handles_junction_with_relative_stored_target(tmp_path):
    link = tmp_path / "rel_link"
    assert create_junction_raw("some\\relative\\garbage", link) is True
    assert is_junction(link) is True
    assert lp.remove_shim(link) is True
    assert not os.path.lexists(str(link))


@win_only
def test_remove_shim_handles_junction_with_nonexistent_target(tmp_path):
    link = tmp_path / "dangling_link"
    assert create_junction_raw(r"Q:\this\drive\letter\does\not\exist", link) is True
    assert is_junction(link) is True
    assert link.exists() is False  # Path.exists() FOLLOWS -- broken target reads as "gone"
    assert lp.remove_shim(link) is True
    assert not os.path.lexists(str(link))


@win_only
def test_reap_shims_reaps_a_broken_junction_after_drive_letter_change_proxy(tmp_path):
    """A junction whose target drive no longer exists (the aftermath of a
    real drive-letter reassignment) must still be reaped."""
    root = tmp_path / "root"
    root.mkdir()
    link = root / "dead"
    assert create_junction_raw(r"Z:\gone\gone\gone", link) is True

    removed = lp.reap_shims(root, max_age_seconds=0, now=time.time() + 100_000)
    assert link in removed
    assert not os.path.lexists(str(link))


@win_only
def test_junction_target_deleted_after_creation_is_still_removable(tmp_path):
    """Ordinary 'broken junction' case: target existed at creation time,
    then got deleted (its own tmp_path scratch data -- not a manual delete
    of anything outside this test)."""
    target = tmp_path / "will_vanish"
    target.mkdir()
    (target / "canary.txt").write_text("should never be reachable through the dead link")
    link = tmp_path / "ghost_link"
    assert lp.create_shim(
        lp.ShimPlan(original=target / "x", needed=True, anchor=target, link=link)
    ) is True

    shutil.rmtree(target)

    assert is_junction(link) is True  # still a junction -- target's absence doesn't change that
    assert lp.remove_shim(link) is True
    assert not os.path.lexists(str(link))


# ==========================================================================
# 3. CORE SAFETY LAYER -- states the baseline suite doesn't cover.
# ==========================================================================

@win_only
def test_remove_shim_refuses_a_directory_symlink(tmp_path):
    """A directory SYMLINK is not a junction -- is_junction() must say False
    for it (shared reparse-point attribute, different tag), so remove_shim
    must refuse it exactly like it refuses a plain directory."""
    target = tmp_path / "sym_target"
    target.mkdir()
    (target / "canary.txt").write_text("must survive")
    link = tmp_path / "sym_link"
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
    except OSError as e:
        pytest.skip("no symlink privilege on this host: %s" % e)

    assert is_junction(link) is False
    assert lp.remove_shim(link) is False
    assert link.exists()
    assert (target / "canary.txt").read_text() == "must survive"


@win_only
def test_remove_shim_on_a_junction_that_targets_another_junction(tmp_path):
    real = tmp_path / "REAL"
    real.mkdir()
    (real / "canary.txt").write_text("innermost")

    link_a = tmp_path / "A"
    assert create_junction(real, link_a) is True

    link_b = tmp_path / "B"
    assert create_junction(link_a, link_b) is True
    assert is_junction(link_b) is True

    assert lp.remove_shim(link_b) is True
    assert not os.path.lexists(str(link_b))
    assert is_junction(link_a) is True
    assert (real / "canary.txt").read_text() == "innermost"

    lp.remove_shim(link_a)  # cleanup, not part of the assertion


@win_only
def test_remove_shim_on_junction_targeting_a_drive_root(tmp_path):
    """A junction whose target IS a drive root. Content must never be
    touched -- proven by tmp_path itself (which lives on that same drive)
    surviving completely untouched."""
    drive_root = Path(os.path.splitdrive(str(tmp_path))[0] + "\\")
    link = tmp_path / "root_link"
    assert create_junction(drive_root, link) is True
    assert is_junction(link) is True

    marker = tmp_path / "still_here.txt"
    marker.write_text("proof the drive survived")

    assert lp.remove_shim(link) is True
    assert not os.path.lexists(str(link))
    assert drive_root.is_dir()
    assert marker.read_text() == "proof the drive survived"


@win_only
def test_remove_shim_toctou_swap_junction_for_nonempty_real_dir(tmp_path, monkeypatch):
    """Force the exact check-then-act window: is_junction() reports True,
    but before os.rmdir() runs, the object on disk has been swapped for a
    real, NON-EMPTY directory. os.rmdir() refuses a non-empty directory, so
    the canary should survive -- pinned empirically."""
    real_target = tmp_path / "swapped_in"
    real_target.mkdir()
    (real_target / "canary.txt").write_text("must survive the swap")

    link = tmp_path / "link"
    junction_target = tmp_path / "junction_target"
    junction_target.mkdir()
    assert create_junction(junction_target, link) is True

    real_is_junction = lp.is_junction

    def swap_then_check(path):
        result = real_is_junction(path)
        if str(path) == str(link):
            os.rmdir(link)
            os.rename(str(real_target), str(link))
        return result

    monkeypatch.setattr(lp, "is_junction", swap_then_check)

    result = lp.remove_shim(link)

    assert result is False
    assert (link / "canary.txt").read_text() == "must survive the swap"


@win_only
def test_remove_shim_toctou_swap_junction_for_empty_real_dir(tmp_path, monkeypatch):
    """Same window, but the swapped-in object is an EMPTY real directory.
    os.rmdir() does not refuse an empty directory regardless of whether it
    was a reparse point a moment ago -- so remove_shim deletes a real
    directory that was NOT a junction at the instant of deletion. No data
    is lost (the directory was empty), but this documents that the
    docstring's "closing the check-then-act window" claim is optimistic for
    this one interleaving: the check and the syscall are still two separate
    calls, not one atomic operation.
    """
    real_target = tmp_path / "swapped_in_empty"
    real_target.mkdir()  # deliberately empty

    link = tmp_path / "link2"
    junction_target = tmp_path / "junction_target2"
    junction_target.mkdir()
    assert create_junction(junction_target, link) is True

    real_is_junction = lp.is_junction

    def swap_then_check(path):
        result = real_is_junction(path)
        if str(path) == str(link):
            os.rmdir(link)
            os.rename(str(real_target), str(link))
        return result

    monkeypatch.setattr(lp, "is_junction", swap_then_check)

    result = lp.remove_shim(link)

    assert result is True and not os.path.lexists(str(link)), (
        "expected remove_shim to have deleted the swapped-in empty real "
        "directory, documenting the residual (bounded-impact) TOCTOU gap"
    )


@win_only
def test_resolve_shim_root_when_candidate_is_itself_a_junction(tmp_path):
    real_backing = tmp_path / "backing"
    real_backing.mkdir()
    root_link = tmp_path / "root_via_junction"
    assert create_junction(real_backing, root_link) is True

    got = lp.resolve_shim_root(candidates=[root_link])
    assert got == root_link
    assert not any(real_backing.iterdir())  # probe cleaned itself up
    assert is_junction(root_link) is True   # root itself must still be the junction


@win_only
def test_resolve_shim_root_when_candidate_is_a_directory_symlink(tmp_path):
    real_backing = tmp_path / "backing2"
    real_backing.mkdir()
    root_link = tmp_path / "root_via_symlink"
    try:
        os.symlink(str(real_backing), str(root_link), target_is_directory=True)
    except OSError as e:
        pytest.skip("no symlink privilege on this host: %s" % e)

    got = lp.resolve_shim_root(candidates=[root_link])
    assert got == root_link
    assert not any(real_backing.iterdir())


@win_only
def test_create_shim_when_link_parent_is_a_junction(tmp_path):
    """A shim root that is itself a junction -- the anchor/link machinery
    must work THROUGH it without corrupting either the root's real backing
    dir or the shim's own anchor."""
    root_backing = tmp_path / "root_backing"
    root_backing.mkdir()
    root_link = tmp_path / "root_junction"
    assert create_junction(root_backing, root_link) is True

    anchor = tmp_path / "anchor_dir"
    anchor.mkdir()
    (anchor / "canary.txt").write_text("nested-root canary")

    link = root_link / "abcd"
    assert lp.create_shim(
        lp.ShimPlan(original=anchor / "x", needed=True, anchor=anchor, link=link)
    ) is True
    assert (root_backing / "abcd" / "canary.txt").read_text() == "nested-root canary"

    assert lp.remove_shim(link) is True
    assert root_link.is_dir()
    assert is_junction(root_link) is True


@win_only
def test_reap_shims_does_not_recurse_into_nested_shim(tmp_path):
    """A shim inside a shim root inside another junction: reap_shims(root)
    is a single os.scandir() pass -- it must not discover or touch a
    second-level shim nested inside the first shim's target."""
    outer_root = tmp_path / "outer_root"
    outer_root.mkdir()

    outer_anchor = tmp_path / "outer_anchor"
    outer_anchor.mkdir()
    outer_link = outer_root / "aaaa"
    assert create_junction(outer_anchor, outer_link) is True

    inner_root = outer_anchor / "inner_root"
    inner_root.mkdir()
    inner_anchor = tmp_path / "inner_anchor"
    inner_anchor.mkdir()
    (inner_anchor / "canary.txt").write_text("inner")
    inner_link = inner_root / "bbbb"
    assert create_junction(inner_anchor, inner_link) is True

    removed = lp.reap_shims(outer_root, max_age_seconds=0, now=time.time() + 100_000)

    assert removed == [outer_link]
    assert not os.path.lexists(str(outer_link))
    assert is_junction(inner_link) is True
    assert (inner_anchor / "canary.txt").read_text() == "inner"


# ==========================================================================
# 4. CONCURRENCY
# ==========================================================================

@win_only
def test_concurrent_create_shim_same_anchor_from_multiple_threads(tmp_path):
    """Several threads race to mint the SAME shim (same anchor, same link).
    No thread should raise, the end state must be exactly one valid
    junction pointing at the correct anchor, and the anchor's content must
    be untouched."""
    anchor = tmp_path / "race_anchor"
    anchor.mkdir()
    (anchor / "canary.txt").write_text("race canary")
    link = tmp_path / "race_link"
    plan = lp.ShimPlan(original=anchor / "x", needed=True, anchor=anchor, link=link)

    errors = []

    def worker(_):
        try:
            return lp.create_shim(plan)
        except Exception as e:  # noqa: BLE001 -- we want to see ANYTHING that leaks
            errors.append(e)
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(worker, range(8)))

    assert not errors, "create_shim raised under concurrent same-anchor creation: %r" % errors
    assert is_junction(link) is True
    assert (anchor / "canary.txt").read_text() == "race canary"
    lp.remove_shim(link)


@win_only
def test_reap_shims_racing_against_create_shim(tmp_path):
    """One thread reaps aggressively (max_age=0) while another mints fresh
    shims for DIFFERENT anchors. No exception, and every anchor's canary
    content must be intact regardless of which shims survive the race."""
    root = tmp_path / "race_root"
    root.mkdir()
    anchors = []
    for i in range(6):
        a = tmp_path / ("anchor_%d" % i)
        a.mkdir()
        (a / "canary.txt").write_text("canary_%d" % i)
        anchors.append(a)

    stop = threading.Event()
    errors = []

    def reaper():
        while not stop.is_set():
            try:
                lp.reap_shims(root, max_age_seconds=0, now=time.time() + 100_000)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

    def creator():
        for i, a in enumerate(anchors):
            try:
                link = root / ("id%02d" % i)
                lp.create_shim(lp.ShimPlan(original=a / "x", needed=True, anchor=a, link=link))
            except Exception as e:  # noqa: BLE001
                errors.append(e)
            time.sleep(0.01)

    t_reap = threading.Thread(target=reaper)
    t_reap.start()
    creator()
    stop.set()
    t_reap.join(timeout=5)

    assert not errors, "exception during reap-vs-create race: %r" % errors
    for i, a in enumerate(anchors):
        assert (a / "canary.txt").read_text() == "canary_%d" % i


# ==========================================================================
# 5. ARITHMETIC BOUNDARIES -- exact edges the baseline suite doesn't pin.
# ==========================================================================

@win_only
def test_plan_shim_at_exactly_usable_path_fits():
    root = "C:\\.dzs"
    id_len = lp._ID_LEN
    link_len = len(root) + 1 + id_len
    filename_len = lp.USABLE_PATH - (link_len + 1)
    original = Path("D:\\") / ("f" * filename_len)
    plan = lp.plan_shim(original, root=root)
    assert plan.usable, plan.reason
    assert len(str(plan.shimmed)) == lp.USABLE_PATH
    assert plan.anchor == Path("D:\\")


@win_only
def test_plan_shim_one_char_over_usable_path_fails():
    root = "C:\\.dzs"
    id_len = lp._ID_LEN
    link_len = len(root) + 1 + id_len
    filename_len = lp.USABLE_PATH - (link_len + 1) + 1
    original = Path("D:\\") / ("f" * filename_len)
    plan = lp.plan_shim(original, root=root)
    assert plan.usable is False
    assert "no anchor fits" in plan.reason


@win_only
def test_plan_shim_two_chars_over_usable_path_fails():
    root = "C:\\.dzs"
    id_len = lp._ID_LEN
    link_len = len(root) + 1 + id_len
    filename_len = lp.USABLE_PATH - (link_len + 1) + 2
    original = Path("D:\\") / ("f" * filename_len)
    plan = lp.plan_shim(original, root=root)
    assert plan.usable is False


@win_only
def test_filename_exactly_name_max_is_not_reported_as_over():
    """255 == NAME_MAX must NOT trip the 'exceeds NAME_MAX' short-circuit."""
    name = ("z" * (lp.NAME_MAX - 4)) + ".pdf"
    assert len(name) == lp.NAME_MAX
    original = Path("D:\\x") / name
    plan = lp.plan_shim(original, root="C:\\.dzs")
    assert plan.needed is True
    assert "NAME_MAX" not in plan.reason


@win_only
def test_filename_one_over_name_max_is_reported():
    name = ("z" * (lp.NAME_MAX - 3)) + ".pdf"
    assert len(name) == lp.NAME_MAX + 1
    original = Path("D:\\x") / name
    plan = lp.plan_shim(original, root="C:\\.dzs")
    assert plan.needed is True
    assert plan.usable is False
    assert "NAME_MAX" in plan.reason


@win_only
def test_no_anchor_fits_even_at_shallowest_root():
    long_root = "C:\\Users\\ReallyLongAccountNameForTestingXYZ\\AppData\\Local\\SomeDeepApp\\longpath"
    name = "z" * 250 + ".pdf"
    original = Path("D:\\") / name
    plan = lp.plan_shim(original, root=long_root)
    assert plan.needed is True
    assert plan.usable is False
    assert "no anchor fits" in plan.reason


def test_budget_for_can_go_negative_without_crashing():
    huge_root = "C:\\" + "r" * 500
    b = lp.budget_for(huge_root)
    assert b < 0


@win_only
def test_plan_shim_no_anchor_fits_with_negative_budget_root():
    huge_root = "C:\\" + "r" * 500
    original = Path("D:\\") / ("f" * 250 + ".pdf")
    plan = lp.plan_shim(original, root=huge_root)
    assert plan.needed is True
    assert plan.usable is False
    assert "no anchor fits" in plan.reason


# ==========================================================================
# 6. resolve_shim_root EDGE CASES
# ==========================================================================

@win_only
def test_resolve_shim_root_when_every_candidate_is_unwritable():
    bogus1 = Path("Q:\\definitely\\not\\writable\\.dzs")
    bogus2 = Path("R:\\also\\not\\writable\\.dzs")
    got = lp.resolve_shim_root(candidates=[bogus1, bogus2])
    assert got is None


@win_only
def test_resolve_shim_root_when_candidate_exists_as_a_file(tmp_path):
    file_candidate = tmp_path / "occupied_by_a_file"
    file_candidate.write_text("not a directory")
    usable = tmp_path / "usable_root"

    got = lp.resolve_shim_root(candidates=[file_candidate, usable])
    assert got == usable
    assert file_candidate.is_file()
    assert file_candidate.read_text() == "not a directory"


@win_only
def test_candidate_roots_with_all_env_vars_missing_still_returns_something(monkeypatch):
    for var in ("SystemDrive", "USERPROFILE", "HOME", "TEMP", "TMP"):
        monkeypatch.delenv(var, raising=False)
    roots = lp.candidate_roots()
    assert roots
    assert str(roots[0]).upper().startswith("C:")


@win_only
def test_candidate_roots_with_empty_system_drive_falls_back_to_c(monkeypatch):
    """A present-but-EMPTY SystemDrive must not yield a drive-relative root.

    ``os.environ.get('SystemDrive', 'C:')`` substitutes its default only when
    the key is ABSENT, so an empty value produced a bare ``\\.dzs`` -- a root
    that resolves against whatever drive happens to be current at runtime, and
    therefore moves under the caller. Fixed in v0.4.0 by using ``or`` rather
    than a get() default.

    Asserted through candidate construction only, never probing: probing this
    candidate for real would create a directory at the root of whichever drive
    is current, which is exactly the hazard this file refuses to cause.
    """
    monkeypatch.setenv("SystemDrive", "")
    roots = [str(r) for r in lp.candidate_roots()]
    degenerate = "\\" + lp.SHIM_DIR_NAME
    assert degenerate not in roots, (
        "drive-relative root %r must never be offered -- it resolves against "
        "the current drive rather than a fixed one" % degenerate
    )
    assert ("C:\\" + lp.SHIM_DIR_NAME) in roots, (
        "expected the C: fallback when SystemDrive is empty, got %r" % (roots,)
    )


# ==========================================================================
# 7. create_shim EDGE CASES
# ==========================================================================

@win_only
def test_create_shim_link_occupied_by_real_directory_with_content(tmp_path):
    anchor = tmp_path / "anchor7a"
    anchor.mkdir()
    link = tmp_path / "occupied"
    link.mkdir()
    (link / "keep.txt").write_text("must survive")

    plan = lp.ShimPlan(original=anchor / "x", needed=True, anchor=anchor, link=link)
    assert lp.create_shim(plan) is False
    assert is_junction(link) is False
    assert (link / "keep.txt").read_text() == "must survive"


@win_only
def test_create_shim_anchor_does_not_exist(tmp_path):
    anchor = tmp_path / "does_not_exist_at_all"
    link = tmp_path / "link7b"
    plan = lp.ShimPlan(original=anchor / "x", needed=True, anchor=anchor, link=link)
    result = lp.create_shim(plan)
    assert result is False
    assert not os.path.lexists(str(link))


@win_only
def test_create_shim_anchor_is_a_file_not_a_directory(tmp_path):
    anchor = tmp_path / "anchor_is_a_file.txt"
    anchor.write_text("i am a file")
    link = tmp_path / "link7c"
    plan = lp.ShimPlan(original=anchor.parent / "x", needed=True, anchor=anchor, link=link)
    result = lp.create_shim(plan)
    assert result is False
    assert not os.path.lexists(str(link))
    assert anchor.read_text() == "i am a file"


# ==========================================================================
# 8. shim_path MUST NEVER RAISE, AND MUST NEVER RETURN SOMETHING WORSE
#    THAN THE ORIGINAL.
# ==========================================================================

_FUZZ_INPUTS = [
    "",
    "C:",
    "C:\\",
    "C:foo",
    "C:foo\\" + "b" * 260,
    "\\\\server\\share\\" + "x" * 260 + "\\f.pdf",
    "relative\\path\\" + "y" * 260 + "\\f.pdf",
    ".",
    "..",
    "C:\\a\\.\\..\\..\\" + "z" * 260 + "\\f.pdf",
    "C:\\" + "trailing_space " * 20 + "\\f.pdf",
    "C:\\" + "trailing.dot." * 20 + "\\f.pdf",
    "C:\\CON\\" + "n" * 260 + "\\f.pdf",
    "C:\\" + "n" * 260 + "\\CON",
    "C:\\" + "n" * 260 + "\\NUL.txt",
    "C:\\" + "n" * 260 + "\\LPT1",
    "C:\\" + ("\U0001F600" * 100) + "\\f.pdf",
    "C:\\" + "a" * 300,
    "C:\\a\\" * 60 + "f.pdf",
    "\\\\?\\C:\\" + "a" * 400 + "\\f.pdf",
]


@win_only
@pytest.mark.parametrize("raw", _FUZZ_INPUTS)
def test_shim_path_never_raises(raw, tmp_path):
    root = tmp_path / ".dzs"
    try:
        result = lp.shim_path(raw, root=root)
    except Exception as e:  # noqa: BLE001 -- this IS the assertion
        pytest.fail("shim_path(%r) raised %r" % (raw, e))
    assert isinstance(result, Path)


@win_only
def test_shim_path_never_raises_on_none():
    """None is a type-contract violation (signature says Union[str, Path]),
    but callers do pass None by accident. Documented as its own finding,
    separate from the string fuzz battery, because it's a different class
    of caller mistake.
    """
    with pytest.raises(TypeError):
        lp.shim_path(None)  # type: ignore[arg-type]
    # If this assertion ever fails (shim_path stops raising for None), that
    # is an IMPROVEMENT -- flip this test to assert no-raise at that point.


@win_only
def test_shim_path_never_raises_on_embedded_nul_in_filename(tmp_path):
    """A NUL embedded in the FILENAME tail (`rel`) never reaches a syscall:
    create_shim only ever touches `link` (root/id) via mkdir/create_junction
    -- it never creates `shimmed` (link/rel) itself, that's for the caller
    to open later. So this specific placement is safe. Contrast with
    test_shim_path_raises_on_embedded_nul_in_root below, where the NUL is
    in a component that DOES reach mkdir()."""
    bad = "C:\\" + "a" * 260 + "\\x\x00y.pdf"
    root = tmp_path / ".dzs"
    try:
        result = lp.shim_path(bad, root=root)
    except Exception as e:  # noqa: BLE001
        pytest.fail("shim_path(%r) raised %r instead of degrading to the original path" % (bad, e))
    assert isinstance(result, Path)


@win_only
def test_shim_path_raises_on_embedded_nul_in_root(tmp_path):
    """CONFIRMED DEFECT: a NUL embedded in the ROOT parameter DOES reach a
    real syscall (`link.parent.mkdir()` inside create_shim, since
    `link = root / id`). Python's os.mkdir on Windows raises ValueError for
    an embedded NUL -- NOT OSError -- so create_shim's `except OSError`
    does not catch it, and shim_path has no try/except of its own to stop
    it escaping to the caller. This breaks the "never raises" contract for
    a plausible (if unusual) caller input: a root path built from
    unsanitised config/env content.
    """
    anchor = tmp_path / "A"
    anchor.mkdir()

    bad_root = str(tmp_path) + "\\x\x00y"
    id_len = lp._ID_LEN
    budget = lp.USABLE_PATH - (len(bad_root) + 1 + id_len + 1)
    assert budget > 60, "test root too long on this host to leave a workable budget"
    name_len = min(budget - 4, 190)
    original = anchor / (("f" * name_len) + ".pdf")
    assert len(str(original)) > lp.DEFAULT_THRESHOLD

    try:
        result = lp.shim_path(original, root=bad_root)
    except Exception as e:  # noqa: BLE001 -- this IS the assertion
        pytest.fail(
            "shim_path(root=%r) raised %r -- the 'never raises' contract "
            "is violated when the ROOT parameter (not the path being "
            "shimmed) carries an embedded NUL byte" % (bad_root, e)
        )
    assert isinstance(result, Path)


@win_only
def test_candidate_roots_for_a_unc_target_uses_the_share_as_a_root_candidate():
    """Pure observation, no filesystem I/O (probe not invoked): a UNC
    target's candidate root sits ON the network share itself. Documented so
    callers relying on resolve_shim_root(target=unc_path) know a probe will
    attempt a real write to that share -- not exercised for real here."""
    roots = lp.candidate_roots(r"\\server\share\deep\file.pdf")
    shares = [r for r in roots if str(r).startswith("\\\\server\\share")]
    assert shares, "expected a UNC-share-rooted candidate, got %r" % roots
