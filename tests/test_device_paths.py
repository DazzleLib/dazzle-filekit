"""Tests for `is_device_path` -- "is this string a PLACE?" (v0.4.2).

Distinct from `is_valid_path`, which answers "is this string LEGAL?".
`/dev/null` is a legal POSIX path -- is_valid_path returns True for it --
yet nothing is ever stored there. Consumers that harvest paths out of shell
commands, configs, or logs need the place question, not the legality one.

Driven by Claude-Session-Backup #56, where `2>/dev/null` appearing in
harvested Bash commands was indexed as a session's TOP working directory
(119 hits, outranking the real repository).
"""

import pytest

from dazzle_filekit import (
    POSIX_DEVICE_PATHS,
    WINDOWS_INVALID_NAMES,
    is_device_path,
)
# is_valid_path is intentionally NOT part of the package's public surface;
# reach for it where it lives. (The contrast between the two predicates is
# the point of test_device_paths_are_still_valid_paths below.)
from dazzle_filekit.utils.validation import is_valid_path


# ── POSIX devices and sinks ───────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "/dev/null",
    "/dev/zero",
    "/dev/stdout",
    "/dev/stderr",
    "/dev/stdin",
    "/dev/tty",
    "/dev/urandom",
    "/dev/console",
])
def test_posix_devices_detected(path):
    assert is_device_path(path) is True


def test_posix_device_with_trailing_slash():
    assert is_device_path("/dev/null/") is True


def test_posix_device_backslash_spelling():
    """A Windows host reading a Git-Bash command may have normalized the
    separators already; the answer must not change."""
    assert is_device_path("\\dev\\null") is True


@pytest.mark.parametrize("path", [
    "/proc/self/status",
    "/sys/class/net",
    "/dev/fd/3",
])
def test_pseudo_filesystems_detected(path):
    assert is_device_path(path) is True


# ── Windows reserved device names ─────────────────────────────────────

@pytest.mark.parametrize("path", ["NUL", "nul", "CON", "aux", "PRN", "COM1", "lpt9"])
def test_windows_reserved_names_detected(path):
    assert is_device_path(path) is True


def test_windows_reserved_name_with_extension():
    """Windows resolves `nul.txt` to the device -- the extension is ignored."""
    assert is_device_path("nul.txt") is True


def test_windows_reserved_name_with_directory_prefix():
    """Reserved names are position-independent: C:\\tmp\\nul IS the device."""
    assert is_device_path(r"C:\tmp\nul") is True
    assert is_device_path("C:/tmp/nul") is True


# ── Real places must NOT be flagged ───────────────────────────────────

@pytest.mark.parametrize("path", [
    r"C:\code\dazzle-filekit",
    r"C:\code\dazzle-filekit\tests",
    "/home/user/code",
    "/usr/local/lib",
    "/c/code/project",
    "/mnt/c/code/project",
    r"Z:\wintools",
    "relative/path",
])
def test_real_paths_not_flagged(path):
    assert is_device_path(path) is False


def test_substring_matches_are_not_devices():
    """`null` / `con` appearing INSIDE a longer name is not a device."""
    assert is_device_path("/home/user/dev/null-handling") is False
    assert is_device_path(r"C:\code\console-app") is False
    assert is_device_path(r"C:\code\connection") is False
    assert is_device_path("/var/log/nullify") is False


def test_uppercase_posix_is_not_a_device():
    """POSIX is case-sensitive: /DEV/NULL is an ordinary (if odd) path."""
    assert is_device_path("/DEV/NULL") is False


# ── Degenerate input ──────────────────────────────────────────────────

@pytest.mark.parametrize("value", [None, "", "   ", '""'])
def test_degenerate_input_is_not_a_device(value):
    assert is_device_path(value) is False


def test_accepts_pathlib(tmp_path):
    from pathlib import Path
    assert is_device_path(Path("/dev/null")) is True
    assert is_device_path(tmp_path) is False


def test_quoted_paths_are_unwrapped():
    assert is_device_path('"/dev/null"') is True


# ── The distinction from is_valid_path (the whole reason this exists) ──

def test_reserved_names_list_alone_cannot_answer_the_place_question():
    """The reason this predicate exists.

    `WINDOWS_INVALID_NAMES` -- the pre-existing list a consumer might be
    tempted to reuse -- knows nothing about POSIX devices. Reusing it
    would have missed `/dev/null`, which was the single largest source of
    junk in the Claude-Session-Backup #56 measurement (119 hits, ranked
    #1). `is_device_path` covers both families.
    """
    posix_device = "/dev/null"
    stem = posix_device.rsplit("/", 1)[-1].lower()
    assert stem not in WINDOWS_INVALID_NAMES       # the old list misses it
    assert is_device_path(posix_device) is True    # the new predicate does not


def test_device_paths_are_still_valid_paths():
    """The two predicates answer DIFFERENT questions and must not be
    conflated: `/dev/null` is a perfectly LEGAL path that is not a PLACE.

    (This contrast was unobservable before the separator fix in the same
    release: `_is_valid_windows_path` split on backslash only, so every
    forward-slash path -- including this one -- was reported invalid for
    an unrelated reason. See test_valid_path_separators.py.)
    """
    assert is_valid_path("/dev/null") is True      # legal
    assert is_device_path("/dev/null") is True     # ...but not a place


def test_ordinary_paths_are_valid_and_not_devices():
    """The common case: a real directory is both legal and a place."""
    assert is_valid_path("C:/code/project") is True
    assert is_device_path("C:/code/project") is False


def test_public_constants_exported():
    assert "/dev/null" in POSIX_DEVICE_PATHS
    assert "nul" in WINDOWS_INVALID_NAMES
    assert "com1" in WINDOWS_INVALID_NAMES
    assert "lpt9" in WINDOWS_INVALID_NAMES
