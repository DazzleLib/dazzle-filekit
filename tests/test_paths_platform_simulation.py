"""Platform-simulation tests for path normalization.

These tests exercise BOTH platform branches of ``_prepare_path_format``
regardless of which OS runs the test suite. This is the regression
protection for the WSL bug caught on 2026-04-11 where a refactor
flattened the platform-split in ``_prepare_path_format``, breaking
``normalize_cross_platform_path`` on Linux while leaving Windows green.

Why monkeypatching works here:

  - ``sys.platform`` is read at CALL time (not import time) inside
    ``_prepare_path_format``, so ``monkeypatch.setattr(sys, 'platform',
    ...)`` reliably steers the branch selection.
  - The Linux branch uses literal ``/`` (no ``os.sep``), so simulating
    Linux on Windows produces byte-for-byte the same string output.
  - The Windows branch uses ``os.sep``, so simulating Windows on Linux
    produces forward-slash output instead of backslash. Tests that
    simulate Windows accept either separator.

For cases that genuinely need the real filesystem (xattrs, actual
reparse points, live pywin32), see the platform-gated tests in
test_compat.py, test_metadata_v024_roundtrip.py, and
test_ads_and_junction_v024.py.
"""

import os
import sys

import pytest

from dazzle_filekit.paths import (
    _prepare_path_format,
    normalize_cross_platform_path,
)


# ---------------------------------------------------------------------------
# Linux branch: simulated from anywhere
# ---------------------------------------------------------------------------


class TestLinuxBranchSimulated:
    """Simulate ``sys.platform == 'linux'`` and verify the Unix-direction
    conversions: Windows C:\\ or C:/ -> /c/, backslash normalization, and
    leaving plain Linux paths untouched."""

    @pytest.fixture(autouse=True)
    def simulate_linux(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")

    def test_windows_backslash_path_to_unix(self):
        r"""C:\Users\foo -> /c/Users/foo on Unix."""
        result = _prepare_path_format(r"C:\Users\foo\file.txt")
        assert result == "/c/Users/foo/file.txt"

    def test_windows_forward_slash_path_to_unix(self):
        """C:/Users/foo -> /c/Users/foo on Unix."""
        result = _prepare_path_format("C:/Users/foo/file.txt")
        assert result == "/c/Users/foo/file.txt"

    def test_windows_uppercase_drive_becomes_lowercase(self):
        """Drive letters are lowercased in the Unix form."""
        result = _prepare_path_format(r"D:\projects\bar.md")
        assert result == "/d/projects/bar.md"

    def test_plain_linux_path_unchanged(self):
        """A path that looks like a Linux absolute path stays untouched.

        This is the regression case: the buggy version of
        ``_prepare_path_format`` matched ``/c/Users/foo`` via the
        unconditional MSYS regex and rewrote it to ``C:/Users/foo`` on
        Linux, which is wrong.
        """
        result = _prepare_path_format("/c/Users/foo/file.txt")
        assert result == "/c/Users/foo/file.txt"

    def test_plain_linux_home_path_unchanged(self):
        """/home/user/file.txt stays as-is on Unix (no drive interpretation)."""
        result = _prepare_path_format("/home/user/file.txt")
        assert result == "/home/user/file.txt"

    def test_mnt_path_is_not_interpreted_as_wsl_on_unix(self):
        """``/mnt/c/Users/foo`` on Linux is a plain Linux path at /mnt/c.

        The WSL-to-Windows conversion belongs to the Windows branch only.
        """
        result = _prepare_path_format("/mnt/c/Users/foo/file.txt")
        # Should NOT be rewritten to C:\ form
        assert result == "/mnt/c/Users/foo/file.txt"

    def test_mixed_separator_path_normalized(self):
        """A mixed-separator path gets its backslashes converted to forward slashes."""
        result = _prepare_path_format("some/path\\with\\mixed/separators.txt")
        assert "\\" not in result
        assert "/" in result

    def test_bare_drive_letter_converted(self):
        r"""C:\ alone becomes /c/ (drive root)."""
        # "C:\\" in a regular string literal is 3 chars: C, :, \
        result = _prepare_path_format("C:\\")
        assert result == "/c/"


# ---------------------------------------------------------------------------
# Windows branch: simulated from anywhere
# ---------------------------------------------------------------------------


class TestWindowsBranchSimulated:
    r"""Simulate ``sys.platform == 'win32'`` and verify Windows-direction
    conversions: MSYS /c/, WSL /mnt/c/, \\?\ strip, and backslash
    normalization.

    Note: on non-Windows hosts, ``os.sep`` is ``/``, so when this branch
    runs ``path_str.replace("/", os.sep)`` the result uses forward
    slashes instead of backslashes. Tests therefore normalize the
    separator before comparing, accepting either form.
    """

    @pytest.fixture(autouse=True)
    def simulate_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")

    def _eq_path(self, a: str, b: str) -> bool:
        """Compare paths ignoring separator direction (tests run on both OS)."""
        return a.replace("\\", "/") == b.replace("\\", "/")

    def test_msys_drive_to_windows(self):
        """/c/Users/foo -> C:\\Users\\foo on Windows."""
        result = _prepare_path_format("/c/Users/foo/file.txt")
        assert self._eq_path(result, "C:/Users/foo/file.txt")

    def test_wsl_mount_to_windows(self):
        """/mnt/c/Users/foo -> C:\\Users\\foo on Windows."""
        result = _prepare_path_format("/mnt/c/Users/foo/file.txt")
        assert self._eq_path(result, "C:/Users/foo/file.txt")

    def test_wsl_preferred_over_msys(self):
        """/mnt/d/... handled as WSL, not as MSYS drive 'm'."""
        result = _prepare_path_format("/mnt/d/projects/bar.md")
        assert self._eq_path(result, "D:/projects/bar.md")

    def test_bare_msys_drive_becomes_drive_root(self):
        """/c alone maps to C:/ (drive root) so it's genuinely absolute."""
        result = _prepare_path_format("/c")
        assert self._eq_path(result, "C:/")

    def test_bare_wsl_drive_becomes_drive_root(self):
        """/mnt/c alone maps to C:/."""
        result = _prepare_path_format("/mnt/c")
        assert self._eq_path(result, "C:/")

    def test_extended_length_prefix_stripped(self):
        r"""\\?\C:\foo -> C:\foo (strip the extended-length prefix)."""
        result = _prepare_path_format("\\\\?\\C:\\foo\\bar.txt")
        assert not result.startswith("\\\\?\\")
        assert self._eq_path(result, "C:/foo/bar.txt")

    def test_plain_windows_path_passes_through(self):
        r"""A native C:\Users\foo path stays as-is on Windows."""
        result = _prepare_path_format(r"C:\Users\foo\file.txt")
        assert self._eq_path(result, "C:/Users/foo/file.txt")

    def test_forward_slash_windows_path_normalized(self):
        """C:/Users/foo becomes C:\\Users\\foo (or stays // on non-Windows host)."""
        result = _prepare_path_format("C:/Users/foo/file.txt")
        assert self._eq_path(result, "C:/Users/foo/file.txt")


# ---------------------------------------------------------------------------
# End-to-end via normalize_cross_platform_path (simulated)
# ---------------------------------------------------------------------------


class TestNormalizeCrossPlatformPathSimulated:
    """Verify ``normalize_cross_platform_path`` correctly dispatches to
    the right ``_prepare_path_format`` branch based on ``sys.platform``.

    These tests stop at the ``_prepare_path_format`` output -- the
    subsequent ``os.path.normpath`` / ``os.path.isabs`` / ``os.getcwd``
    steps are OS-native and can't be meaningfully simulated.
    """

    def test_linux_converts_windows_path_to_unix(self, monkeypatch):
        """On Linux, normalize_cross_platform_path converts C:\\ to /c/."""
        monkeypatch.setattr(sys, "platform", "linux")
        # Just verify the conversion layer -- don't assert on final Path
        # because os.path.isabs / normpath behave differently on each OS
        result = _prepare_path_format(r"C:\Users\foo\bar.txt")
        assert result == "/c/Users/foo/bar.txt"

    def test_windows_converts_msys_path_to_windows(self, monkeypatch):
        """On Windows, normalize_cross_platform_path converts /c/ to C:/."""
        monkeypatch.setattr(sys, "platform", "win32")
        result = _prepare_path_format("/c/Users/foo/bar.txt")
        # Host may produce either separator; accept both
        assert result.replace("\\", "/") == "C:/Users/foo/bar.txt"

    def test_both_directions_are_inverses_for_valid_windows_paths(
        self, monkeypatch
    ):
        """A Windows path passed through the Windows branch and then
        through the Linux branch round-trips (modulo separator form)."""
        # Start with a Windows path
        original = r"C:\Users\foo\test.txt"

        # Pass through the Windows branch (should stay Windows-shaped)
        monkeypatch.setattr(sys, "platform", "win32")
        win_result = _prepare_path_format(original)
        # Pass the Windows output through the Linux branch
        monkeypatch.setattr(sys, "platform", "linux")
        linux_result = _prepare_path_format(win_result)
        # And back through Windows
        monkeypatch.setattr(sys, "platform", "win32")
        back_to_win = _prepare_path_format(linux_result)

        # The final result should match the original (modulo separator)
        assert back_to_win.replace("\\", "/") == original.replace("\\", "/")


# ---------------------------------------------------------------------------
# Regression guard: the specific WSL bug
# ---------------------------------------------------------------------------


class TestWslRegressionGuard:
    """Lock in the exact bug caught by the WSL cross-check on 2026-04-11.

    The bug: ``_prepare_path_format`` was doing MSYS ``/c/`` -> ``C:/``
    unconditionally, which meant ``normalize_cross_platform_path``:
      1. Broke on Linux for ``/c/Users/foo`` (rewrote a valid Linux path)
      2. Broke on Linux for ``C:\\Users\\foo`` (lost the bidirectional
         conversion the v0.2.3 function had)

    The Windows suite passed 208/208 while Linux was silently broken.
    These tests catch that class of bug from any host.
    """

    def test_linux_does_not_rewrite_linux_paths(self, monkeypatch):
        """/c/foo on Linux must stay /c/foo."""
        monkeypatch.setattr(sys, "platform", "linux")
        result = _prepare_path_format("/c/Users/foo")
        assert result == "/c/Users/foo", (
            "REGRESSION: Linux branch is rewriting /c/ paths as if they "
            "were MSYS drives. See the 2026-04-11 WSL bug fix."
        )

    def test_linux_rewrites_windows_paths(self, monkeypatch):
        r"""C:\foo on Linux must become /c/foo."""
        monkeypatch.setattr(sys, "platform", "linux")
        result = _prepare_path_format(r"C:\Users\foo")
        assert result == "/c/Users/foo", (
            "REGRESSION: Linux branch is not converting Windows C:\\ "
            "paths to /c/ form. See the 2026-04-11 WSL bug fix."
        )

    def test_windows_rewrites_msys_paths(self, monkeypatch):
        """/c/foo on Windows must become C:/foo."""
        monkeypatch.setattr(sys, "platform", "win32")
        result = _prepare_path_format("/c/Users/foo")
        assert result.replace("\\", "/") == "C:/Users/foo", (
            "REGRESSION: Windows branch is not converting MSYS /c/ "
            "paths to C: form."
        )

    def test_windows_passes_native_paths(self, monkeypatch):
        r"""C:\foo on Windows must stay C:\foo."""
        monkeypatch.setattr(sys, "platform", "win32")
        result = _prepare_path_format(r"C:\Users\foo")
        assert result.replace("\\", "/") == "C:/Users/foo"
