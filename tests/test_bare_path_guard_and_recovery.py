"""Tests for issue #16: bare strings where collections are expected, and
unescaped-backslash path recovery.

Two independent problems that compound:

1. A ``str`` passed to a ``List[path]`` parameter is iterated character by
   character; any realistic path contains a separator, ``Path("/")`` is the
   drive root, and ``recursive=True`` turns that into a whole-drive walk.
2. ``"C:\\temp"`` written without a raw string is ``C:`` + TAB + ``emp``
   before any library sees it. Eight escapes bite silently; NTFS forbids
   control characters in names, so the mangled path can never be real.

Recovery fixes wrong CONTENT; the type guard fixes wrong TYPE. Only the
guard stops the drive walk, which is why it exists on all five
collection-taking entry points.
"""

import logging
import os
from pathlib import Path

import pytest


from dazzle_filekit import (
    SILENT_ESCAPE_ORIGINS,
    calculate_total_size,
    copy_files_with_path,
    ensure_path_collection,
    find_files,
    find_regex_files,
    has_unescaped_backslash_damage,
    move_files_with_path,
    recover_unescaped_path,
    suggest_reescaped_path,
)


# Recovery re-inserts a BACKSLASH, which is a path separator on Windows and an
# ordinary filename character everywhere else. A test that creates a real
# directory and expects a backslash-joined string to resolve to it therefore
# asserts Windows semantics and must be gated -- on POSIX the candidate names
# one file called "x\tdir", not a directory "x/tdir".
#
# The TYPE GUARD tests below are deliberately NOT gated: rejecting a bare
# string is platform-independent and must hold everywhere.
#
# This is the third POSIX-only CI failure in this repo (v0.3.3's
# Windows-host-locked probe suite, v0.4.0's twelve _same_dir tests, and this
# file). See CONTRIBUTING.md, "The one thing most likely to trip you up", and
# tests/one-offs/run_suite_under_wsl.sh to reproduce the Linux leg locally.
windows_separator_only = pytest.mark.skipif(
    os.sep != "\\",
    reason="recovery re-inserts a backslash; only a path separator on Windows",
)


# ── the type guard: every collection-taking entry point ──────────────

def _call(fn_name, first_arg, tmp_path):
    """Invoke each guarded function with `first_arg` in the guarded slot."""
    if fn_name == "find_files":
        return find_files(first_arg, patterns=["*.py"], recursive=False)
    if fn_name == "find_regex_files":
        return find_regex_files(first_arg, [r".*\.py$"], recursive=False)
    if fn_name == "calculate_total_size":
        return calculate_total_size(first_arg)
    if fn_name == "copy_files_with_path":
        return copy_files_with_path(first_arg, tmp_path, tmp_path / "out")
    if fn_name == "move_files_with_path":
        return move_files_with_path(first_arg, tmp_path, tmp_path / "out")
    raise AssertionError(fn_name)


GUARDED = ["find_files", "find_regex_files", "calculate_total_size",
           "copy_files_with_path", "move_files_with_path"]


@pytest.mark.parametrize("fn_name", GUARDED)
def test_bare_string_raises_with_bracketed_suggestion(fn_name, tmp_path):
    with pytest.raises(TypeError) as exc:
        _call(fn_name, "C:\\proj", tmp_path)
    msg = str(exc.value)
    assert "Did you mean [" in msg
    assert "C:\\\\proj" in msg or "C:\\proj" in repr(msg)


@pytest.mark.parametrize("fn_name", GUARDED)
def test_bare_path_object_raises_too(fn_name, tmp_path):
    """A bare Path currently dies with "'WindowsPath' object is not
    iterable" -- correct, but a long way from "add brackets"."""
    with pytest.raises(TypeError) as exc:
        _call(fn_name, Path("C:/proj"), tmp_path)
    assert "Did you mean [" in str(exc.value)


def test_drive_root_string_raises_instead_of_walking():
    """THE regression this issue exists for. ``find_files("C:\\")`` used to
    iterate the string, hit the separator character, and recursively glob
    the entire drive -- a hang that looks like slowness, not a mistake.
    If this test is slow, the guard is gone."""
    with pytest.raises(TypeError):
        find_files("C:\\", patterns=["*"], recursive=True)


def test_list_form_still_works(tmp_path):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    found = find_files([tmp_path], patterns=["*.py"], recursive=False)
    assert [f.name for f in found] == ["a.py"]


def test_other_iterables_pass_the_guard(tmp_path):
    """The guard rejects str/bytes/PathLike specifically -- a tuple or
    generator of paths is a legitimate collection."""
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    assert find_files((tmp_path,), patterns=["*.py"], recursive=False)
    assert ensure_path_collection([tmp_path]) == [tmp_path]


# ── the recovery helper ──────────────────────────────────────────────
#
# Fixture strategy: for each silent escape, create a REAL directory whose
# name begins with the escape letter, then hand the helper the string a
# caller would have produced by forgetting the raw-string prefix.
# ``str(tmp) + "\\temp"`` mistyped is ``str(tmp) + TAB + "emp"``.

@windows_separator_only
@pytest.mark.parametrize("ch,letter", sorted(SILENT_ESCAPE_ORIGINS.items()))
def test_recovery_for_every_silent_escape(tmp_path, ch, letter):
    real = tmp_path / (letter + "dir")
    real.mkdir()
    mangled = str(tmp_path) + ch + "dir"

    recovered, did = recover_unescaped_path(mangled)

    assert did is True
    assert recovered == str(real)


def test_literal_wins_when_the_path_exists(tmp_path):
    """Recovery never overrides a working interpretation -- step 1 is
    'try it exactly as given'."""
    real = tmp_path / "plain"
    real.mkdir()
    assert recover_unescaped_path(str(real)) == (str(real), False)


def test_no_damage_no_recovery(tmp_path):
    missing = str(tmp_path / "nope")
    assert recover_unescaped_path(missing) == (missing, False)


def test_neither_exists_returns_original(tmp_path):
    """No evidence either way -> hand back exactly what was passed. The
    caller's failure stays the caller's failure."""
    mangled = str(tmp_path) + "\t" + "otally-absent"
    assert recover_unescaped_path(mangled) == (mangled, False)


@windows_separator_only
def test_multiple_escapes_in_one_path(tmp_path):
    """``"C:\\temp\\new"`` mistyped carries a TAB and a NEWLINE; the
    candidate re-escapes all of them at once."""
    deep = tmp_path / "temp" / "new"
    deep.mkdir(parents=True)
    mangled = str(tmp_path) + "\temp\new"  # deliberate: TAB + ... + LF + ...

    recovered, did = recover_unescaped_path(mangled)

    assert did is True
    assert recovered == str(deep)


def test_suggest_is_purely_lexical():
    assert suggest_reescaped_path("C:\temp") == "C:\\temp"
    assert has_unescaped_backslash_damage("C:\temp")
    assert not has_unescaped_backslash_damage(r"C:\temp")


# ── warn-only wiring in find_files ───────────────────────────────────

def test_find_files_diagnoses_mangled_search_path(tmp_path, caplog):
    """The diagnosis is the expensive part of this bug. A miss caused by an
    unescaped backslash must say so, and name the path the caller meant."""
    mangled = str(tmp_path) + "\temp"  # TAB: does not and cannot exist
    with caplog.at_level(logging.WARNING):
        out = find_files([mangled], patterns=["*"], recursive=False)

    assert out == []
    text = caplog.text
    assert "unescaped" in text
    assert "did you mean" in text
    assert "temp" in text


def test_find_files_does_not_diagnose_ordinary_misses(tmp_path, caplog):
    """A plain missing path keeps the plain warning -- no false accusation
    of escape damage."""
    with caplog.at_level(logging.WARNING):
        find_files([str(tmp_path / "absent")], patterns=["*"], recursive=False)
    assert "unescaped" not in caplog.text
