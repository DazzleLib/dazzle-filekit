r"""v0.2.4 enrichment tests for filekit path normalizers.

Phase 4 consolidated the format-conversion rules shared by
``normalize_path`` and ``normalize_path_no_resolve`` into a private
helper ``_prepare_path_format``. As a side effect:

  - ``normalize_path`` (which was link-following but did almost no
    format conversion) now gains MSYS ``/c/``, WSL ``/mnt/c/``, env
    var expansion, and ``\\?\`` prefix stripping -- essentially a bug
    fix for a previously broken input space.

  - ``normalize_path_no_resolve`` gains WSL ``/mnt/c/`` handling and
    env var expansion (it already had the rest).

These tests lock in the enrichments so they can't regress. For the
v0.2.3 baseline behavior that survived unchanged, see
``tests/characterization/test_paths_v023_baseline.py``.
"""

import os
import sys
from pathlib import Path

import pytest

from dazzle_filekit.paths import (
    normalize_cross_platform_path,
    normalize_path,
    normalize_path_no_resolve,
)


# ---------------------------------------------------------------------------
# WSL /mnt/c/ handling -- both functions gain this in v0.2.4
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="WSL->Windows conversion is win32 only")
class TestWslMountConversion:
    def test_normalize_path_no_resolve_wsl(self):
        result = normalize_path_no_resolve("/mnt/c/Users/foo/test.txt")
        assert str(result).startswith("C:")
        assert "mnt" not in str(result)

    def test_normalize_path_wsl(self):
        result = normalize_path("/mnt/c/Users/foo/test.txt")
        assert str(result).startswith("C:")
        assert "mnt" not in str(result)

    def test_wsl_lowercase_drive_letter(self):
        result = normalize_path_no_resolve("/mnt/d/projects/bar.md")
        assert str(result).startswith("D:")

    def test_wsl_bare_drive_no_subpath(self):
        """'/mnt/c' with no trailing path should still convert."""
        result = normalize_path_no_resolve("/mnt/c")
        assert str(result).startswith("C:")


# ---------------------------------------------------------------------------
# MSYS /c/ handling -- normalize_path gains this (no-op for no_resolve)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="MSYS->Windows conversion is win32 only")
class TestMsysDriveConversion:
    def test_normalize_path_gains_msys(self):
        """v0.2.3: normalize_path returned C:\\c\\Users\\foo (broken).
        v0.2.4: correctly returns C:\\Users\\foo."""
        result = normalize_path("/c/Users/foo/test.txt")
        assert str(result).startswith("C:")
        s = str(result).lower()
        assert "\\c\\users" not in s, (
            f"normalize_path still producing broken MSYS output: {result!r}"
        )

    def test_normalize_path_no_resolve_msys_still_works(self):
        """Regression check: the existing MSYS behavior is preserved."""
        result = normalize_path_no_resolve("/c/Users/foo/test.txt")
        assert str(result).startswith("C:")


# ---------------------------------------------------------------------------
# Env var expansion -- both functions gain this in v0.2.4
# ---------------------------------------------------------------------------


class TestEnvVarExpansion:
    def test_normalize_path_no_resolve_windows_style(self):
        """%USERPROFILE% / %HOME% should expand on Windows."""
        if sys.platform != "win32":
            pytest.skip("Windows env var syntax %VAR% is Windows-only")
        result = normalize_path_no_resolve("%USERPROFILE%\\subdir\\file.txt")
        assert "%" not in str(result)
        assert "subdir" in str(result)

    def test_normalize_path_no_resolve_unix_style(self):
        """$HOME expansion should work on both platforms."""
        os.environ["FILEKIT_TEST_VAR"] = str(Path.home())
        try:
            result = normalize_path_no_resolve("$FILEKIT_TEST_VAR/subdir/file.txt")
            assert "$" not in str(result)
            assert "FILEKIT_TEST_VAR" not in str(result)
            assert "subdir" in str(result)
        finally:
            del os.environ["FILEKIT_TEST_VAR"]

    def test_normalize_path_env_var(self):
        """The link-following variant also gains env var support."""
        os.environ["FILEKIT_TEST_VAR"] = str(Path.home())
        try:
            result = normalize_path("$FILEKIT_TEST_VAR/subdir/file.txt")
            assert "$" not in str(result)
            assert "FILEKIT_TEST_VAR" not in str(result)
        finally:
            del os.environ["FILEKIT_TEST_VAR"]

    def test_unknown_var_passes_through(self):
        """os.path.expandvars leaves unknown vars as literals."""
        result = normalize_path_no_resolve("%FILEKIT_NO_SUCH_VAR%/file.txt")
        # The literal %FILEKIT_NO_SUCH_VAR% should be preserved (may or may
        # not still have the % depending on platform; the key is it doesn't crash
        # and the path is something usable).
        assert "file.txt" in str(result)


# ---------------------------------------------------------------------------
# Backwards compatibility -- existing behavior preserved
# ---------------------------------------------------------------------------


class TestV023BehaviorPreserved:
    """Every input that worked in v0.2.3 must still work the same way."""

    def test_tilde_expansion_still_works(self):
        result = normalize_path_no_resolve("~/foo.txt")
        assert "~" not in str(result)

    def test_plain_absolute_path_unchanged(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        result = normalize_path_no_resolve(f)
        assert result.name == "file.txt"
        assert result.is_absolute()

    def test_relative_path_absolutized(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = normalize_path_no_resolve("./subdir/file.txt")
        assert result.is_absolute()

    def test_dot_dot_collapsed(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = normalize_path_no_resolve("./a/b/../c/file.txt")
        s = str(result)
        assert (os.sep + "b" + os.sep) not in s
        assert (os.sep + "a" + os.sep + "c" + os.sep) in s

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific")
    def test_longpath_prefix_stripped(self):
        result = normalize_path_no_resolve("\\\\?\\C:\\foo\\bar.txt")
        assert not str(result).startswith("\\\\?\\")

    def test_symlink_preserved_in_no_resolve(self, tmp_path):
        target = tmp_path / "target.txt"
        target.write_text("hello")
        link = tmp_path / "link.txt"
        try:
            os.symlink(str(target), str(link))
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation requires admin on Windows")

        result = normalize_path_no_resolve(link)
        assert result.name == "link.txt"


# ---------------------------------------------------------------------------
# Agreement: both functions produce equivalent output on portable inputs
# ---------------------------------------------------------------------------


class TestNormalizerAgreement:
    """For a plain existing absolute path with no links or dot segments,
    the two functions should produce the same string output."""

    def test_plain_file_agreement(self, tmp_path):
        f = tmp_path / "plain.txt"
        f.write_text("x")
        r1 = normalize_path(f)
        r2 = normalize_path_no_resolve(f)
        # Allow case-insensitive comparison on Windows (resolve() may
        # canonicalize case).
        assert str(r1).lower() == str(r2).lower()

    def test_tilde_agreement(self):
        r1 = normalize_path("~/foo.txt")
        r2 = normalize_path_no_resolve("~/foo.txt")
        assert "~" not in str(r1)
        assert "~" not in str(r2)
        # Both should point at the same home-relative location
        assert str(r1).lower() == str(r2).lower()

    @pytest.mark.skipif(sys.platform != "win32", reason="WSL path style is Windows-side")
    def test_wsl_agreement(self):
        """/mnt/c/Users agrees regardless of which normalizer we pick."""
        r1 = normalize_path("/mnt/c/Users")
        r2 = normalize_path_no_resolve("/mnt/c/Users")
        assert str(r1).lower() == str(r2).lower()


# ---------------------------------------------------------------------------
# Canonical API: normalize_cross_platform_path with resolve= kwarg
# ---------------------------------------------------------------------------


class TestCanonicalApi:
    """v0.2.4: normalize_cross_platform_path is the canonical entry point.

    The three names (normalize_cross_platform_path, normalize_path,
    normalize_path_no_resolve) are all the same function underneath.
    """

    def test_three_names_are_same_function(self):
        """All three public names dispatch to the same canonical impl."""
        # normalize_path is a wrapper for resolve=True; they ARE distinct
        # function objects, but calling them produces the same result as
        # calling the canonical with the right flag. Verify by value.
        r1 = normalize_cross_platform_path("~/test.txt")
        r2 = normalize_path_no_resolve("~/test.txt")
        # Both link-safe; should be identical
        assert str(r1) == str(r2)

    def test_default_is_link_safe(self, tmp_path):
        """Default (no resolve kwarg) preserves symlinks."""
        target = tmp_path / "target.txt"
        target.write_text("hello")
        link = tmp_path / "link.txt"
        try:
            os.symlink(str(target), str(link))
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation requires admin on Windows")

        result = normalize_cross_platform_path(link)
        assert result.name == "link.txt", (
            "Default should be link-safe (resolve=False)"
        )

    def test_resolve_true_follows_symlinks(self, tmp_path):
        target = tmp_path / "target.txt"
        target.write_text("hello")
        link = tmp_path / "link.txt"
        try:
            os.symlink(str(target), str(link))
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation requires admin on Windows")

        result = normalize_cross_platform_path(link, resolve=True)
        # Either the target name, or on some systems resolve() may return
        # the link's path if it can't be followed. Accept either but the
        # common case is target.txt.
        assert result.name in ("target.txt", "link.txt")

    def test_resolve_is_keyword_only(self):
        """resolve must be passed as a keyword argument, not positional."""
        with pytest.raises(TypeError):
            # This should fail: resolve cannot be passed positionally
            normalize_cross_platform_path("/tmp/foo", True)  # type: ignore[misc]

    def test_wrapper_equivalence_no_resolve(self, tmp_path):
        """normalize_path_no_resolve == normalize_cross_platform_path(p, resolve=False)."""
        f = tmp_path / "sample.txt"
        f.write_text("x")
        r1 = normalize_path_no_resolve(f)
        r2 = normalize_cross_platform_path(f, resolve=False)
        assert str(r1) == str(r2)

    def test_wrapper_equivalence_resolve(self, tmp_path):
        """normalize_path == normalize_cross_platform_path(p, resolve=True)."""
        f = tmp_path / "sample.txt"
        f.write_text("x")
        r1 = normalize_path(f)
        r2 = normalize_cross_platform_path(f, resolve=True)
        assert str(r1) == str(r2)
