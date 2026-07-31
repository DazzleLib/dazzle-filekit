"""Delta-round-2 adversarial tests for :mod:`dazzle_filekit.longpath`.

Round 1 (``test_longpath_adversarial.py``) found 2 defects, since fixed. This
file attacks ONLY the code introduced or rewritten by that fix:
``_same_dir()`` (new), ``create_shim()`` (rewritten collision-resolution loop
+ race branch + mutation consistency), ``shim_path()``'s new outer
``except (OSError, ValueError)`` wrapper, and ``candidate_roots()``'s
``SystemDrive`` fallback. It does not re-test the baseline suite or the
round-1 battery -- those already pass and are out of scope for this round.

SAFETY COMMITMENT (same as ``test_longpath_adversarial.py``):
``candidate_roots()`` / ``resolve_shim_root(probe=True)`` / ``create_shim`` /
``reap_shims`` never run against unmodified real-drive candidates. Every
filesystem-touching call here either passes an explicit ``tmp_path``-scoped
``root=``/``link=``, or monkeypatches ``SystemDrive``/``USERPROFILE``/
``HOME``/``TEMP``/``TMP`` first. A few tests construct a ``ShimPlan`` whose
``anchor`` denotes the real drive root ("C:\\") -- they do this ONLY as a
``create_junction_raw`` TARGET STRING, which never needs to exist and is
never written to (the same "target need not exist" precedent already used by
the dangling-junction tests in ``test_longpath_adversarial.py``). No content
is ever read from or written to a real drive root anywhere in this file.
"""
from __future__ import annotations

import ctypes
import os
import threading
from pathlib import Path

import pytest

from dazzle_filekit import longpath as lp
from dazzle_filekit.links import create_junction, create_junction_raw, read_link_target
from dazzle_filekit.utils.validation import is_junction

WINDOWS = os.name == "nt"
win_only = pytest.mark.skipif(not WINDOWS, reason="junctions are Windows-only")


# ==========================================================================
# 1. _same_dir -- PURE FUNCTION BATTERY. Grounded in this host's actual
#    ntpath.normpath/normcase behaviour (see
#    tests/one-offs/thinking/probe_same_dir_normalization.py), not assumed.
# ==========================================================================

@win_only
def test_same_dir_none_handling():
    assert lp._same_dir(None, None) is False
    assert lp._same_dir(None, "C:\\x") is False
    assert lp._same_dir("C:\\x", None) is False


@win_only
def test_same_dir_trailing_separator_and_case():
    assert lp._same_dir("C:\\Foo\\Bar\\", "C:\\Foo\\Bar") is True
    assert lp._same_dir("C:\\FOO\\bar", "c:\\foo\\BAR") is True


@win_only
def test_same_dir_mixed_separators():
    assert lp._same_dir("C:/Foo/Bar", "C:\\Foo\\Bar") is True


@win_only
def test_same_dir_dotdot_collapse():
    assert lp._same_dir("C:\\Foo\\Bar\\..", "C:\\Foo") is True


@win_only
def test_same_dir_relative_vs_absolute_is_not_equal():
    """A relative spelling and an absolute one are NOT proven to be the same
    directory by string normalization alone -- correctly treated as
    different (the safe direction: a false negative, not a false positive)."""
    assert lp._same_dir("Foo\\Bar", "C:\\Foo\\Bar") is False


@win_only
def test_same_dir_unc_extended_prefix_form():
    assert lp._same_dir("\\\\?\\UNC\\server\\share\\dir",
                        "\\\\server\\share\\dir") is True


@win_only
def test_same_dir_drive_extended_prefix_form():
    assert lp._same_dir("\\\\?\\C:\\Foo\\Bar", "C:\\Foo\\Bar") is True


@win_only
def test_same_dir_trailing_dot_and_space_not_collapsed():
    """Win32 silently strips trailing dots/spaces from path components at the
    API layer; _same_dir does NOT emulate that (normpath doesn't either), so
    'C:\\Foo.' reads as different from 'C:\\Foo' even though the real
    filesystem treats them as the identical directory. Documented as the
    SAFE-direction false negative: a caller in this shape gets a redundant
    duplicate shim, never someone else's content."""
    assert lp._same_dir("C:\\Foo.", "C:\\Foo") is False
    assert lp._same_dir("C:\\Foo ", "C:\\Foo") is False


@win_only
def test_same_dir_short_vs_long_name_synthetic():
    """8.3-vs-long-name for the SAME real directory, pure-string form. Same
    safe-direction false negative as trailing dot/space -- confirmed for a
    REAL directory (not just this synthetic pair) in
    test_same_dir_real_8dot3_short_name_vs_long_name below."""
    assert lp._same_dir("C:\\PROGRA~1", "C:\\Program Files") is False


@win_only
def test_same_dir_bare_drive_letter_stays_distinct_from_drive_root():
    """FIXED in v0.4.0. Path("C:") is a DRIVE-RELATIVE path (root='', meaning
    "whatever the process's hidden per-drive cwd on C: is right now") --
    Windows explicitly treats it as a different path class from Path("C:\\\\")
    (root='\\\\', the actual filesystem root): Path("C:") == Path("C:\\\\") is
    False, Path("C:").is_absolute() is False, Path("C:\\\\").is_absolute() is
    True (see tests/one-offs/thinking/probe_bare_drive_relative_to.py).

    _same_dir originally normalized with `normcase(normpath(s)).rstrip("\\\\/")`.
    normpath("C:") == "C:" and normpath("C:\\\\") == "C:\\\\"; the blanket
    rstrip erased the ONE character distinguishing them, so both collapsed to
    "c:" and compared equal -- a false POSITIVE, the dangerous direction,
    because create_shim would then reuse a junction pointing somewhere else.

    The fix splits the drive off first and only strips a trailing separator
    when something follows the root, so a drive root and a drive-relative path
    can no longer collapse onto one another.
    """
    assert lp._same_dir("C:", "C:\\") is False
    assert lp._same_dir("C:\\Foo\\..", "C:") is False   # same route, via ..

    # ...while genuine equivalences must still match.
    assert lp._same_dir("C:\\", "C:\\") is True
    assert lp._same_dir("C:\\Foo", "C:\\Foo\\") is True
    assert lp._same_dir("C:\\Foo\\Bar\\..", "C:\\FOO") is True


# ==========================================================================
# 2. _same_dir -- REAL JUNCTION INTEGRATION. Confirms (or refutes) the
#    reachability of the two routes flagged as priority #1, using actual
#    read_link_target() output from actual junctions/directories on this
#    host, not just synthetic strings fed to _same_dir directly.
# ==========================================================================

@win_only
def test_same_dir_real_junction_plain_target_roundtrips(tmp_path):
    """Baseline: a junction created from a PLAIN (non-prefixed) target comes
    back from read_link_target() in plain form too -- no \\\\?\\ prefix
    appears spontaneously. Confirms the \\\\?\\-canonicalization route is NOT
    ambient behaviour of ordinary junctions."""
    anchor = tmp_path / "ANCHOR_PLAIN"
    anchor.mkdir()
    link = tmp_path / "link_plain"
    assert create_junction(anchor, link) is True
    raw = read_link_target(link)
    assert raw is not None
    assert not raw.startswith(("\\\\?\\", "\\\\.\\"))
    assert lp._same_dir(raw, anchor) is True


@win_only
def test_same_dir_real_junction_from_explicitly_prefixed_target(tmp_path):
    """CONFIRMED REACHABLE (and confirmed CLEAN): when the target GIVEN TO
    create_junction is itself \\\\?\\-prefixed, PowerShell's New-Item stores
    the PrintName WITH the prefix intact -- read_link_target() hands back
    the literal \\\\?\\-prefixed string. This is the real route flagged as
    "the realistic route in" for a kernel-canonicalized target. _same_dir
    strips it correctly here; no false positive OR false negative."""
    anchor = tmp_path / "ANCHOR_EXPLICIT_PREFIX"
    anchor.mkdir()
    link = tmp_path / "link_explicit_prefix"
    prefixed_target = "\\\\?\\" + str(anchor)
    assert create_junction(prefixed_target, link) is True

    raw = read_link_target(link)
    assert raw is not None
    assert raw.startswith("\\\\?\\"), (
        "expected New-Item to preserve the extended prefix in PrintName; "
        "got %r -- if this ever changes, the _same_dir prefix-stripping "
        "branch may have become untested dead code" % raw)
    assert lp._same_dir(raw, anchor) is True


@win_only
def test_same_dir_real_8dot3_short_name_vs_long_name(tmp_path):
    """Confirms the false-NEGATIVE (safe direction) for real 8.3-vs-long
    names of the SAME real directory -- not synthetic strings. Skips cleanly
    if this volume has 8.3 name generation disabled (environment-dependent;
    checked empirically per-run rather than assumed)."""
    long_dir = tmp_path / "A_Very_Long_Directory_Name_For_8dot3_Testing"
    long_dir.mkdir()
    buf = ctypes.create_unicode_buffer(4096)
    n = ctypes.windll.kernel32.GetShortPathNameW(str(long_dir), buf, 4096)
    short_form = buf.value if n else None
    if not short_form or short_form.upper() == str(long_dir).upper():
        pytest.skip("8.3 short-name generation is disabled on this volume; "
                    "no distinct short form available to compare against")
    assert lp._same_dir(short_form, long_dir) is False, (
        "if this starts passing True, _same_dir has started resolving 8.3 "
        "short names -- that would be a deliberate behaviour change worth "
        "documenting, not an accidental regression"
    )


# ==========================================================================
# 3. create_shim -- BARE-DRIVE-LETTER FALSE POSITIVE, full integration.
# ==========================================================================

@win_only
def test_create_shim_bare_drive_letter_no_longer_false_positive(tmp_path):
    """FULL create_shim()-LEVEL reproduction of the _same_dir bare-drive
    collapse, now asserting the v0.4.0 fix. create_shim() used to report
    success and reuse a pre-existing junction whose target is the literal
    drive root ("C:\\\\") for a request whose anchor is the DRIVE-RELATIVE
    bare form ("C:") -- two spellings Windows itself treats as distinct.
    It must now decline to reuse that junction.

    SAFETY: the pre-existing junction's target string is fabricated via
    create_junction_raw(), which explicitly never requires the target to
    exist (see its docstring, and the dangling-junction tests already in
    test_longpath_adversarial.py that rely on the same property). No real
    filesystem access to the actual C:\\\\ root occurs anywhere in this test
    -- "C:\\\\" is used purely as a STRING stored in a reparse buffer under
    tmp_path, never as something Windows has to resolve or that gets read.

    REACHABILITY CAVEAT (why this is narrow, not a headline defect):
    plan_shim()'s own ancestor walk NEVER produces a bare drive-relative
    anchor -- Path(...).parents on a rooted original always bottoms out at
    the qualified root form ("D:\\\\"), confirmed empirically in
    tests/one-offs/thinking/probe_bare_drive_relative_to.py. This is only
    reachable when a caller constructs a ShimPlan directly with an unrooted
    (drive-relative) original/anchor pair -- unusual, but a fully supported
    call shape: create_shim() accepts any ShimPlan, and the existing suite
    already builds ShimPlan objects by hand throughout (the normal idiom for
    testing create_shim() independent of plan_shim()). A ROOTED original is
    rejected earlier and more safely: Path(rooted_original).relative_to(
    Path("C:")) raises ValueError, which create_shim already catches and
    returns False for -- before _same_dir is ever reached.
    """
    link = tmp_path / "root_link"
    assert create_junction_raw("C:\\", link) is True
    assert is_junction(link) is True

    bare_anchor = Path("C:")
    original = Path("C:some_deep_name.pdf")   # drive-relative too, so
                                               # relative_to(bare_anchor)
                                               # succeeds instead of raising
    plan = lp.ShimPlan(original=original, needed=True, anchor=bare_anchor,
                       link=link, shimmed=link / "some_deep_name.pdf")

    result = lp.create_shim(plan)

    assert result is False, (
        "a junction targeting the drive ROOT must not be reused for a "
        "DRIVE-RELATIVE anchor -- Windows treats them as different paths, so "
        "reusing it would serve a different directory's content"
    )
    # The plan must be left untouched when nothing was created for it.
    assert plan.link == link
    assert plan.shimmed == link / "some_deep_name.pdf"


@win_only
def test_create_shim_race_branch_rejects_a_competitors_junction(tmp_path, monkeypatch):
    """The post-creation verification branch shares `_same_dir` with the
    first-check branch, so fixing the bare-drive collapse fixes both call
    sites at once -- there was never an independent bug in the race logic.

    This also pins the v0.4.0 race behaviour: a competitor's junction that
    does NOT point at our anchor must not be accepted, and must not end the
    search either -- create_shim advances to a longer id rather than giving
    up with candidates untried."""
    link = tmp_path / "race_root_link"
    assert not link.exists()

    def losing_create_junction(target, link_arg, *a, **k):
        # Simulate a competitor creating a DIFFERENT (root-targeting)
        # junction at this exact path between our is_junction() check and
        # our own create_junction() attempt, with our own call then
        # reporting failure (e.g. because the path now exists) -- the exact
        # TOCTOU shape the race branch exists to recover from.
        create_junction_raw("C:\\", link_arg)
        return False

    monkeypatch.setattr(lp, "create_junction", losing_create_junction)

    bare_anchor = Path("C:")
    original = Path("C:some_deep_name.pdf")
    plan = lp.ShimPlan(original=original, needed=True, anchor=bare_anchor,
                       link=link, shimmed=link / "some_deep_name.pdf")

    result = lp.create_shim(plan)
    assert result is False, (
        "a competitor's junction pointing at the drive ROOT must not be "
        "accepted for a DRIVE-RELATIVE anchor; reusing it would serve a "
        "different directory's content -- the original defect's signature"
    )
    # The competitor's junction is left alone -- create_shim never removes
    # a link it did not create.
    assert is_junction(link) is True


# ==========================================================================
# 4. plan.link / plan.shimmed MUTATION CONSISTENCY -- priority #2. A plan
#    whose `shimmed` disagrees with what actually landed on disk is a silent
#    wrong-file bug with the same signature as the original defect, arrived
#    by a different road.
# ==========================================================================

@win_only
def test_mutation_after_multi_anchor_collision_cascade_matches_disk(tmp_path, monkeypatch):
    """4 anchors forced onto the SAME base id, resolved one at a time. Each
    successive create_shim() call must land the winner's plan.link/
    plan.shimmed on the id that actually got a junction pointing at ITS OWN
    anchor -- and no two anchors may end up sharing a final link."""
    root = tmp_path / ".dzs"
    root.mkdir()

    anchors = []
    for tag in ("A", "B", "C", "D"):
        a = tmp_path / ("ANCHOR_%s" % tag)
        a.mkdir()
        (a / "doc.txt").write_text("FROM_%s" % tag)
        anchors.append((tag, a))

    # Collide only at the BASE length; a real, anchor-specific hash still
    # applies once lengthened, so each anchor's alternates are genuinely
    # distinct from one another (matching how a real hash collision behaves:
    # the birthday-bound clash is at one length, not at every length an
    # anchor might be pushed to). A monkeypatch that ignores `length`
    # entirely collapses every alternate onto the SAME id for every anchor,
    # which manufactures artificial total exhaustion rather than testing
    # collision *resolution* -- caught by this cascade test itself on the
    # first attempt (see git history of this file / the task's own probe
    # script for the same technique).
    real_anchor_id = lp._anchor_id
    monkeypatch.setattr(
        lp, "_anchor_id",
        lambda anchor, length=lp._ID_LEN: "cafe" if length <= lp._ID_LEN
        else real_anchor_id(anchor, length))

    seen_links = set()
    for tag, a in anchors:
        link = root / "cafe"
        plan = lp.ShimPlan(original=a / "doc.txt", needed=True, anchor=a,
                           link=link, shimmed=link / "doc.txt")
        result = lp.create_shim(plan, max_id_len=16)

        assert result is True, "anchor %s failed to get a shim in the cascade" % tag
        assert is_junction(plan.link) is True
        assert lp._same_dir(read_link_target(plan.link), a) is True
        assert plan.shimmed == plan.link / "doc.txt", (
            "plan.shimmed disagrees with plan.link for anchor %s" % tag
        )
        assert plan.shimmed.read_text() == "FROM_%s" % tag, (
            "anchor %s's plan.shimmed reads someone else's content" % tag
        )
        assert str(plan.link) not in seen_links, (
            "anchor %s ended up sharing plan.link=%s with an earlier "
            "winner in the cascade" % (tag, plan.link)
        )
        seen_links.add(str(plan.link))


@win_only
def test_mutation_left_untouched_after_id_exhaustion(tmp_path, monkeypatch):
    """Every candidate id collides with SOMEONE ELSE's anchor (all ids
    forced identical via the monkeypatch, occupied by an unrelated
    "blocker" directory). create_shim must return False WITHOUT ever
    mutating plan.link/plan.shimmed away from what the caller originally
    set -- a caller that ignores the return value and reads plan.shimmed
    anyway must not be handed a path minted for the wrong anchor."""
    root = tmp_path / ".dzs"
    root.mkdir()

    blocker = tmp_path / "BLOCKER"
    blocker.mkdir()
    monkeypatch.setattr(lp, "_anchor_id", lambda anchor, length=lp._ID_LEN: "beef")
    assert create_junction(blocker, root / "beef") is True

    anchor = tmp_path / "REAL_ANCHOR"
    anchor.mkdir()
    original_link = root / "beef"
    original_shimmed = original_link / "doc.txt"
    plan = lp.ShimPlan(original=anchor / "doc.txt", needed=True, anchor=anchor,
                       link=original_link, shimmed=original_shimmed)

    result = lp.create_shim(plan, max_id_len=6)

    assert result is False
    assert plan.link == original_link, "plan.link mutated despite failure"
    assert plan.shimmed == original_shimmed, "plan.shimmed mutated despite failure"


@win_only
def test_mutation_left_untouched_when_alternate_would_exceed_usable_path():
    """The length guard (`if len(str(shimmed)) > USABLE_PATH: return False`)
    fires INSIDE the candidate loop before any is_junction/create_junction
    call. No filesystem access occurs at all in this test -- the very first
    (requested) candidate already exceeds USABLE_PATH, so create_shim
    returns on the first loop iteration without touching disk."""
    root = Path("C:\\") / ("r" * 200)
    anchor = Path("D:\\SomeAnchorDir")
    original = anchor / ("f" * 60 + ".pdf")
    original_link = root / "abcd"
    original_shimmed = original_link / ("f" * 60 + ".pdf")
    plan = lp.ShimPlan(original=original, needed=True, anchor=anchor,
                       link=original_link, shimmed=original_shimmed)

    result = lp.create_shim(plan)

    assert result is False
    assert plan.link == original_link
    assert plan.shimmed == original_shimmed


# ==========================================================================
# 5. CONCURRENCY -- priority #3. Two+ threads resolving the SAME collision
#    simultaneously, each independently walking the lengthening loop.
# ==========================================================================

@win_only
def test_lengthening_loop_gives_up_on_race_loss_instead_of_advancing_to_next_id(tmp_path, monkeypatch):
    """CONFIRMED DEFECT (concurrency interaction, reproduced deterministically).

    When create_shim's OWN create_junction() call for a candidate id fails
    because a DIFFERENT anchor's junction won that exact slot in the interim
    (a genuine race outcome, not a hash collision detected up front via
    is_junction()), the loop does NOT advance to the next longer id -- it
    hard-returns False. The `continue` that lengthens the id only fires from
    the FIRST is_junction() check at the top of an iteration (someone else's
    junction was already fully there before this iteration started); the
    race-recovery branch after a failed create_junction() attempt has no
    matching `continue`, only `return True` or `return False`.

    Net effect: a caller who raced against a DIFFERENT anchor for the same
    lengthened id gets treated identically to "exhausted all ids" -- it
    loses its shim entirely, even though longer ids past the one it raced on
    were never tried. Bounded-impact (still fails SAFE -- plan.link/shimmed
    are left untouched below, and A's junction is verified correct -- never
    wrong content), but is a real gap in the "keep lengthening until you
    find a free or matching slot" contract create_shim's own docstring
    promises.
    """
    root = tmp_path / ".dzs"
    root.mkdir()

    anchor_a = tmp_path / "ANCHOR_A"
    anchor_a.mkdir()
    anchor_b = tmp_path / "ANCHOR_B"
    anchor_b.mkdir()
    (anchor_b / "doc.txt").write_text("FROM_B")

    monkeypatch.setattr(lp, "_anchor_id", lambda anchor, length=lp._ID_LEN: "cafe")
    contested_link = root / "cafe"
    real_create_junction = lp.create_junction

    def racing_create_junction(target, link_arg, *a, **k):
        real_create_junction(anchor_a, link_arg)  # A wins the slot first
        return False                               # B's own attempt fails

    monkeypatch.setattr(lp, "create_junction", racing_create_junction)

    plan_b = lp.ShimPlan(original=anchor_b / "doc.txt", needed=True,
                         anchor=anchor_b, link=contested_link,
                         shimmed=contested_link / "doc.txt")

    result = lp.create_shim(plan_b, max_id_len=16)

    assert result is False, (
        "confirms the gap: B gives up entirely rather than retrying at a "
        "longer id after losing the race for 'cafe' to a different anchor"
    )
    assert plan_b.link == contested_link
    assert plan_b.shimmed == contested_link / "doc.txt"
    assert is_junction(contested_link) is True
    assert lp._same_dir(read_link_target(contested_link), anchor_a) is True


@win_only
def test_concurrent_collision_resolution_multiple_anchors_same_base_id(tmp_path, monkeypatch):
    """N threads, N DIFFERENT anchors, all forced onto the SAME base id
    CONCURRENTLY (not sequentially, unlike the cascade test above). Each
    thread independently walks create_shim's lengthening loop at the same
    time.

    CONFIRMED DEFECT, caught by this test under real scheduling (observed
    failure rate roughly 35-40% across ~13 manual repeats on this host --
    NOT a rare/theoretical race). The signature every time this test fails:
    a thread's create_shim() call returns True with plan.link/plan.shimmed
    correctly pointing at ITS OWN anchor -- but by the time all threads have
    joined, the junction physically at that link now targets a DIFFERENT
    anchor entirely. i.e. a create_shim() call that was correct at the
    instant it returned gets its result silently invalidated by a LATER
    concurrent create_shim() call for a different anchor. Any caller that
    read plan.shimmed and opened the file shortly after getting `True` back
    would, in the failing interleaving, read a stranger's content -- the
    exact "reads a different directory's file, silently and with no error"
    signature create_shim's own docstring names as the defect the
    collision-verification fix was written to close, reproduced here via a
    TOCTOU in create_junction() rather than via a hash collision.

    Root cause (inferred from captured stderr on a failing run): PowerShell
    `New-Item -ItemType Junction -Path <path>` does not fail closed when the
    path already holds another thread's freshly-created, fully-formed
    junction -- one observed failure mode is `New-Item` attempting to
    remove the pre-existing item first and reporting "cannot be removed
    because it is not empty" (walking transparently through the reparse
    point to the other anchor's real content). create_junction()'s own
    Python-level guard (`if link_path.exists(): ... return False`) is a
    check-then-act race against this: `Path.exists()` can observe "nothing
    here yet" a moment before another thread's junction fully lands, after
    which this thread's own subprocess-latency-delayed New-Item call
    interacts with that now-present junction in a way that is not
    guaranteed to fail. create_shim() has no way to detect this after the
    fact -- it already returned True based on state that was accurate only
    at that instant.

    This test therefore asserts the SAFETY invariants unconditionally (no
    exceptions; whichever anchors show ok=True right now are individually
    correct RIGHT NOW and never share a link; every result -- True or False
    -- leaves the plan in a state consistent with what's presently on disk)
    rather than asserting every anchor succeeds. Given the defect above, DO
    NOT be surprised if this test fails intermittently -- a failure here IS
    the defect, not test flakiness to wave off; a maintainer investigating
    should re-run it a handful of times if it passes on a given run before
    concluding the race didn't manifest."""
    N = 4
    ATTEMPTS = 8   # single-attempt hit rate observed ~35-40% manually; this
                   # many independent attempts makes a single pytest
                   # invocation reproduce the race with very high probability
                   # (~1-(1-0.35)**8 =~ 97%) instead of depending on a human
                   # re-running pytest by hand to catch it.

    def run_one_attempt(trial):
        trial_root = tmp_path / ("trial_%d" % trial) / ".dzs"
        trial_root.mkdir(parents=True)

        anchors = []
        for i in range(N):
            a = tmp_path / ("trial_%d" % trial) / ("ANCHOR_%d" % i)
            a.mkdir()
            (a / "doc.txt").write_text("FROM_%d" % i)
            anchors.append(a)

        # Same base-length-only collision as the cascade test above --
        # alternates stay anchor-distinct once lengthened, so this genuinely
        # exercises concurrent independent lengthening rather than
        # manufacturing total exhaustion for everyone but the first thread
        # to land.
        real_anchor_id = lp._anchor_id
        monkeypatch.setattr(
            lp, "_anchor_id",
            lambda anchor, length=lp._ID_LEN: "cafe" if length <= lp._ID_LEN
            else real_anchor_id(anchor, length))

        errors = []
        results = {}
        lock = threading.Lock()

        def worker(i, a):
            try:
                link = trial_root / "cafe"
                plan = lp.ShimPlan(original=a / "doc.txt", needed=True, anchor=a,
                                   link=link, shimmed=link / "doc.txt")
                original_link, original_shimmed = plan.link, plan.shimmed
                ok = lp.create_shim(plan, max_id_len=16)
                with lock:
                    results[i] = (a, plan, ok, original_link, original_shimmed)
            except Exception as e:  # noqa: BLE001 -- we want to see ANYTHING that leaks
                with lock:
                    errors.append((i, e))

        threads = [threading.Thread(target=worker, args=(i, a)) for i, a in enumerate(anchors)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, (
            "create_shim raised under concurrent multi-anchor collision "
            "(trial %d): %r" % (trial, errors)
        )
        assert len(results) == N

        succeeded = 0
        seen_links = {}
        for i, (a, plan, ok, orig_link, orig_shimmed) in results.items():
            if ok:
                succeeded += 1
                assert is_junction(plan.link) is True
                assert lp._same_dir(read_link_target(plan.link), a) is True, (
                    "trial %d: anchor %d's create_shim() returned True, but "
                    "the junction NOW at plan.link=%s points at %r instead "
                    "of its own anchor %r -- a concurrent create_shim() call "
                    "for a DIFFERENT anchor silently overwrote it after this "
                    "one already reported success" % (
                        trial, i, plan.link, read_link_target(plan.link), str(a))
                )
                assert plan.shimmed.read_text() == "FROM_%d" % i, (
                    "trial %d: anchor %d's plan.shimmed reads someone "
                    "else's content under concurrency -- WRONG DATA, not "
                    "just a lost race" % (trial, i)
                )
                if str(plan.link) in seen_links:
                    other_i = seen_links[str(plan.link)]
                    pytest.fail(
                        "trial %d: anchors %d and %d ended up sharing link "
                        "%s under concurrency" % (trial, other_i, i, plan.link)
                    )
                seen_links[str(plan.link)] = i
            else:
                # A False result must never leave a half-mutated plan.
                assert plan.link == orig_link
                assert plan.shimmed == orig_shimmed

        assert succeeded >= 1, (
            "trial %d: no anchor got a shim at all -- suspicious total "
            "starvation" % trial
        )

    for trial in range(ATTEMPTS):
        run_one_attempt(trial)


# ==========================================================================
# 6. shim_path -- the new outer except(OSError, ValueError) wrapper.
# ==========================================================================

@win_only
def test_shim_path_returns_exact_original_not_a_half_built_shimmed_path(tmp_path):
    """When the wrapper's except clause fires, the fallback must be the
    EXACT original path object equivalent -- not a partially-constructed
    plan.shimmed left over from before the failure. Reuses the existing
    confirmed embedded-NUL-in-root trigger (test_longpath_adversarial.py's
    test_shim_path_raises_on_embedded_nul_in_root), but asserts on the VALUE
    returned rather than merely "did not raise"."""
    anchor = tmp_path / "A"
    anchor.mkdir()
    bad_root = str(tmp_path) + "\\x\x00y"
    id_len = lp._ID_LEN
    budget = lp.USABLE_PATH - (len(bad_root) + 1 + id_len + 1)
    assert budget > 60, "test root too long on this host to leave a workable budget"
    name_len = min(budget - 4, 190)
    original = anchor / (("f" * name_len) + ".pdf")
    assert len(str(original)) > lp.DEFAULT_THRESHOLD

    result = lp.shim_path(original, root=bad_root)

    assert result == Path(original), (
        "expected the exact original path back on fallback, got %r" % (result,)
    )


@win_only
def test_shim_path_never_raises_on_fuzz_battery_still_holds(tmp_path):
    """Sanity re-check (not a re-run of the round-1 parametrized battery)
    that the outer wrapper doesn't change behaviour for the ordinary
    passthrough case: a short path with a hostile root is still handed back
    byte-identical, untouched by plan_shim/create_shim at all."""
    f = tmp_path / "small.txt"
    f.write_text("hi")
    hostile_root = "C:\\" + "\x00" * 3 + "root"
    assert lp.shim_path(f, root=hostile_root) == f


# ==========================================================================
# 7. candidate_roots -- SystemDrive fallback degenerate-value battery.
# ==========================================================================

@win_only
@pytest.mark.parametrize("value", ["\\", "\\\\server\\share", "Q:", "c:", "C:\\"])
def test_candidate_roots_degenerate_but_properly_shaped_systemdrive_values_stay_absolute(monkeypatch, value):
    """A bare backslash, a UNC root, a non-existent (but well-formed) drive
    letter, lowercase, and an already-trailing-slash value must never yield
    a drive-RELATIVE (cwd-moving) root -- they may be unusable in practice
    (Q: doesn't exist, a UNC share may not be reachable), but "unusable" is
    safely handled elsewhere (resolve_shim_root skips unwritable
    candidates); "moves under you" is the specific hazard this battery
    checks for. These all stay absolute because each already starts with a
    separator or a genuine "X:" drive marker at position 0 -- contrast with
    the CONFIRMED-DEFECT cases below, which don't."""
    for var in ("USERPROFILE", "HOME", "TEMP", "TMP"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SystemDrive", value)
    roots = lp.candidate_roots()
    assert roots
    first = str(roots[0])
    assert Path(first).is_absolute(), (
        "SystemDrive=%r produced a non-absolute (cwd-relative) first "
        "candidate root: %r" % (value, first)
    )


@win_only
@pytest.mark.parametrize("value", ["C", "   "], ids=["colonless-drive-letter", "whitespace-only"])
def test_candidate_roots_malformed_systemdrive_falls_back_to_c(monkeypatch, value):
    """FIXED in v0.4.0, and broader than just "colon-less". The first `or "C:"`
    fallback guarded only against os.environ.get("SystemDrive") being FALSY
    (missing or empty); it did NOT validate that a present, non-empty value is
    actually SHAPED like a drive specifier or UNC root. Any truthy value that
    doesn't start with a separator and isn't colon-terminated bypassed the
    fallback and produced a path with no drive and no root component:

    - "C" (colon-less drive letter): plausible from a corrupted registry/
      env, a misconfigured sandbox, or any tool that sets SystemDrive
      without the trailing colon.
    - "   " (whitespace-only): plausible from a shell/launcher that exports
      an unset variable as spaces rather than leaving it truly empty.

    Both reproduced the EXACT "root that resolves against whatever
    drive/directory happens to be current at runtime" hazard the empty-string
    case already guarded -- just via a shape the truthiness check missed.
    The fix now validates that the constructed root `is_absolute()` and falls
    back to C: when it is not, so shape rather than truthiness decides."""
    for var in ("USERPROFILE", "HOME", "TEMP", "TMP"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SystemDrive", value)

    roots = [str(r) for r in lp.candidate_roots()]
    assert roots
    first = roots[0]

    assert Path(first).is_absolute(), (
        "a malformed SystemDrive must never yield a relative root that "
        "resolves against the current directory (SystemDrive=%r got %r)"
        % (value, first)
    )
    assert first == "C:\\" + lp.SHIM_DIR_NAME, (
        "expected the C: fallback for malformed SystemDrive=%r, got %r"
        % (value, first)
    )


# ==========================================================================
# 6. shim_path's guard must be interpreter-independent. The NUL-in-root case
#    surfaces as a DIFFERENT exception type depending on Python version:
#    3.12+ routes is_junction through os.path.isjunction (ValueError), while
#    3.9-3.11 falls back to a ctypes DeviceIoControl call and raises
#    ctypes.ArgumentError, which derives from Exception -- not ValueError.
#    Caught only by CI on windows-latest 3.9/3.10/3.11; invisible on a 3.13
#    dev box. These tests force each type so any interpreter catches a
#    regression.
# ==========================================================================

@pytest.mark.parametrize("exc", [
    ValueError("embedded null character"),
    ctypes.ArgumentError("argument 1: ValueError: embedded null character"),
    OSError("boom"),
], ids=["ValueError", "ctypes.ArgumentError", "OSError"])
def test_shim_path_swallows_every_guard_type_regardless_of_interpreter(
        tmp_path, monkeypatch, exc):
    """shim_path must return the ORIGINAL path, never propagate, whichever
    exception type the underlying platform call happens to raise."""
    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(lp, "is_junction", boom)

    original = tmp_path / ("z" * 200 + ".pdf")
    result = lp.shim_path(original, root=tmp_path / ".dzs",
                          threshold=10)      # force the shim path to be taken

    assert result == original, (
        "shim_path must degrade to the original path when the platform call "
        "raises %s, not propagate it" % type(exc).__name__
    )


def test_ctypes_argument_error_is_not_a_valueerror():
    """The reason the guard needed widening: ctypes.ArgumentError does NOT
    inherit from ValueError, so `except (OSError, ValueError)` misses it even
    though its own message says 'ValueError: embedded null character'."""
    assert not issubclass(ctypes.ArgumentError, ValueError)
    assert not issubclass(ctypes.ArgumentError, OSError)
    assert issubclass(ctypes.ArgumentError, Exception)
