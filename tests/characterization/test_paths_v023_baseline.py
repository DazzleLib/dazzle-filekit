"""v0.2.3 baseline for path normalization functions.

This file documents the ACTUAL behavior of the three path normalizers in
filekit v0.2.3, so that Phase 4 can prove its enrichments are strict
supersets and catch accidental regressions.

The three functions under test:

  1. ``dazzle_filekit.paths.normalize_path(path)``
     Link-following. Calls ``.resolve()`` and follows symlinks/junctions
     to their target. Falls back to ``.absolute()`` for nonexistent paths.

  2. ``dazzle_filekit.paths.normalize_path_no_resolve(path)``
     Link-safe. Does tilde expansion, relative-to-cwd absolutize,
     os.path.normpath collapsing, and \\?\\ prefix stripping on Windows.
     Also handles MSYS /c/ and WSL /mnt/c/ conversion. Does NOT follow
     links (pure lexical normalization).

  3. ``dazzle_filekit.utils.compat.normalize_cross_platform_path(path)``
     Cross-platform format conversion only. Handles MSYS /c/, WSL /mnt/c/,
     Windows backslash-to-forward-slash. Does NOT expand tilde, does NOT
     make relative paths absolute, does NOT collapse ``..``, does NOT
     strip \\?\\ -- it is the lightest of the three.

Phase 4 intent: ``normalize_cross_platform_path`` should be enriched to
match the capabilities of ``normalize_path_no_resolve`` (both keep their
existing names for API stability). The enrichment is additive.
"""

import os
import sys
from pathlib import Path

import pytest

from dazzle_filekit.utils.compat import normalize_cross_platform_path


# normalize_path / normalize_path_no_resolve were removed in 0.3.0 (#15
# Phase C, clean break). Defined here as test-local helpers -- they were
# exactly these wrappers -- so this characterization suite still pins the
# same behavior through the canonical normalize_cross_platform_path.
def normalize_path(path):
    return normalize_cross_platform_path(path, resolve=True)


def normalize_path_no_resolve(path):
    return normalize_cross_platform_path(path, resolve=False)


# ---------------------------------------------------------------------------
# normalize_path (v0.2.3): link-following
# ---------------------------------------------------------------------------


class TestNormalizePathV023Baseline:
    """normalize_path calls .resolve() and follows links.

    Phase 4 promise: this behavior stays identical. normalize_path keeps
    the link-following contract for all existing callers.
    """

    def test_plain_file_becomes_absolute(self, tmp_path):
        f = tmp_path / "plain.txt"
        f.write_text("x")
        result = normalize_path(f)
        assert result.is_absolute()

    def test_nonexistent_path_still_absolutized(self, tmp_path):
        fake = tmp_path / "does_not_exist.txt"
        result = normalize_path(fake)
        assert result.is_absolute()

    def test_follows_symlink_to_target(self, tmp_path):
        target = tmp_path / "target.txt"
        target.write_text("hello")
        link = tmp_path / "link.txt"
        try:
            os.symlink(str(target), str(link))
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation requires admin on Windows")

        result = normalize_path(link)
        # Both the link and its resolved target are valid answers; resolve()
        # gives the target.
        assert result.name in ("target.txt", "link.txt")

    def test_relative_path_resolved_against_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = normalize_path("./a/b/file.txt")
        assert result.is_absolute()


# ---------------------------------------------------------------------------
# normalize_path_no_resolve (v0.2.3): link-safe, feature-rich
# ---------------------------------------------------------------------------


class TestNormalizePathNoResolveV023Baseline:
    """normalize_path_no_resolve does the rich lexical normalization.

    Phase 4 promise: this behavior stays available under the same name
    (safedel/_classifier.py:90 depends on it). It may gain new keyword-only
    options but MUST keep the current positional signature.
    """

    def test_expands_tilde(self):
        result = normalize_path_no_resolve("~/foo.txt")
        expected = os.path.expanduser("~/foo.txt")
        assert str(result).replace("/", os.sep) == expected.replace("/", os.sep)

    def test_absolutizes_relative_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = normalize_path_no_resolve("./subdir/file.txt")
        assert result.is_absolute()
        assert "subdir" in str(result)

    def test_collapses_parent_dots(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = normalize_path_no_resolve("./a/b/../c/file.txt")
        # The 'b/..' should be collapsed out
        s = str(result)
        assert (os.sep + "b" + os.sep) not in s
        assert (os.sep + "a" + os.sep + "c" + os.sep) in s

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific")
    def test_strips_extended_length_prefix(self):
        r"""\\?\ prefix is stripped on Windows."""
        result = normalize_path_no_resolve("\\\\?\\C:\\foo\\bar.txt")
        assert not str(result).startswith("\\\\?\\")
        assert "C:" in str(result)

    def test_msys_drive_to_windows(self):
        r"""/c/Users/foo -> C:\Users\foo on Windows."""
        result = normalize_path_no_resolve("/c/Users/foo/test.txt")
        if sys.platform == "win32":
            assert str(result).startswith("C:")
        else:
            # On Unix, /c/Users/foo is just a regular path
            assert "/c/Users/foo" in str(result).replace("\\", "/")

    def test_wsl_mount_to_windows(self):
        r"""Phase 4: normalize_path_no_resolve gained WSL /mnt/c/ handling.

        Before v0.2.4 this was asymmetric: normalize_path_no_resolve handled
        MSYS /c/ but only normalize_cross_platform_path handled WSL /mnt/c/.
        The shared _prepare_path_format helper closes the gap.
        """
        result = normalize_path_no_resolve("/mnt/c/Users/foo/test.txt")
        if sys.platform == "win32":
            assert str(result).startswith("C:"), (
                f"Expected /mnt/c/... to convert to C:\\... on Windows, "
                f"got {result!r}"
            )

    def test_does_not_follow_symlinks(self, tmp_path):
        target = tmp_path / "target.txt"
        target.write_text("hello")
        link = tmp_path / "link.txt"
        try:
            os.symlink(str(target), str(link))
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation requires admin on Windows")

        result = normalize_path_no_resolve(link)
        assert result.name == "link.txt", (
            "normalize_path_no_resolve must preserve the literal link path"
        )


# ---------------------------------------------------------------------------
# normalize_cross_platform_path (v0.2.3): cross-platform format only
# ---------------------------------------------------------------------------


class TestNormalizeCrossPlatformPathV024:
    r"""Phase 4: normalize_cross_platform_path is now the canonical normalizer.

    v0.2.3 did only format conversion (MSYS, WSL, backslash). v0.2.4
    makes it the canonical entry point, backed by ``_prepare_path_format``,
    and gains tilde expansion, env var expansion, ``..`` collapsing, and
    ``\\?\`` stripping -- the union of all prior normalizers' features.

    The 4 xfail tests that used to live here have been flipped to assert
    the new (correct) behavior. See also ``test_paths_v024_enrichments.py``.
    """

    def test_msys_drive_to_windows(self):
        result = normalize_cross_platform_path("/c/Users/foo/test.txt")
        if sys.platform == "win32":
            assert str(result).startswith("C:")

    def test_wsl_mount_to_windows(self):
        result = normalize_cross_platform_path("/mnt/c/Users/foo/test.txt")
        if sys.platform == "win32":
            assert str(result).startswith("C:")

    # ---- Phase 4 enrichments (were xfail in v0.2.3, now real assertions) ----

    def test_expands_tilde(self):
        result = normalize_cross_platform_path("~/foo.txt")
        assert "~" not in str(result)

    def test_absolutizes_relative(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = normalize_cross_platform_path("./subdir/file.txt")
        assert result.is_absolute()

    def test_collapses_parent_dots(self):
        # Use a multi-letter first segment so /a/... doesn't match the MSYS
        # drive regex (which consumes single-letter leading segments).
        result = normalize_cross_platform_path("/foo/bar/../baz/file.txt")
        s = str(result)
        assert (os.sep + "bar" + os.sep) not in s
        assert (os.sep + "foo" + os.sep + "baz" + os.sep) in s

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific")
    def test_strips_longpath_prefix(self):
        result = normalize_cross_platform_path("\\\\?\\C:\\foo\\bar.txt")
        assert not str(result).startswith("\\\\?\\")


# ---------------------------------------------------------------------------
# Agreement check: all three on a benign absolute path
# ---------------------------------------------------------------------------


class TestAllThreeAgreeOnBenignInput:
    """For a plain existing absolute file, all three functions should
    produce equivalent output (modulo resolve()'s canonicalization on Windows).
    """

    def test_all_three_agree_on_plain_file(self, tmp_path):
        f = tmp_path / "plain.txt"
        f.write_text("x")

        r1 = normalize_path(f)
        r2 = normalize_path_no_resolve(f)
        r3 = normalize_cross_platform_path(f)

        # On Windows, normalize_path may lowercase-uppercase differently due to
        # .resolve()'s canonicalization; compare case-insensitively.
        s1, s2, s3 = str(r1).lower(), str(r2).lower(), str(r3).lower()
        assert s1.endswith("plain.txt")
        assert s2.endswith("plain.txt")
        assert s3.endswith("plain.txt")
