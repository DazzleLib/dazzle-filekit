"""Tests for dazzle_filekit.utils.compat cross-platform path utilities."""

import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from dazzle_filekit.utils.compat import (
    normalize_cross_platform_path,
    path_exists_cross_platform,
    is_windows,
    is_unix,
    fix_path_separators,
)


class TestNormalizeCrossPlatformPath:
    """Tests for normalize_cross_platform_path()."""

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only test")
    def test_git_bash_to_windows(self):
        """Git Bash style /c/Users/... -> C:\\Users\\... on Windows."""
        result = normalize_cross_platform_path("/c/Users/foo/file.txt")
        assert str(result) == r"C:\Users\foo\file.txt"

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only test")
    def test_git_bash_uppercase_drive(self):
        """Git Bash /D/path -> D:\\path on Windows."""
        result = normalize_cross_platform_path("/D/some/path")
        assert str(result) == r"D:\some\path"

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only test")
    def test_git_bash_lowercase_drive(self):
        """Git Bash /d/path -> D:\\path on Windows (drive letter uppercased)."""
        result = normalize_cross_platform_path("/d/some/path")
        assert str(result) == r"D:\some\path"

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only test")
    def test_wsl_to_windows(self):
        """WSL style /mnt/c/Users/... -> C:\\Users\\... on Windows."""
        result = normalize_cross_platform_path("/mnt/c/Users/foo/file.txt")
        assert str(result) == r"C:\Users\foo\file.txt"

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only test")
    def test_windows_backslash_passthrough(self):
        """Windows paths with backslashes stay as-is on Windows."""
        result = normalize_cross_platform_path(r"C:\Users\foo\file.txt")
        assert str(result) == r"C:\Users\foo\file.txt"

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only test")
    def test_windows_forward_slash_normalized(self):
        """Windows paths with forward slashes get backslashes on Windows."""
        result = normalize_cross_platform_path("C:/Users/foo/file.txt")
        assert str(result) == r"C:\Users\foo\file.txt"

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only test")
    def test_git_bash_drive_only(self):
        """Git Bash /c with no trailing path."""
        result = normalize_cross_platform_path("/c")
        assert str(result) == "C:"

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only test")
    def test_git_bash_drive_with_slash(self):
        """Git Bash /c/ with trailing slash."""
        result = normalize_cross_platform_path("/c/")
        assert str(result).startswith("C:")

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only test")
    def test_windows_to_unix(self):
        """Windows C:\\path -> /c/path on Unix."""
        result = normalize_cross_platform_path("C:\\Users\\foo\\file.txt")
        assert str(result) == "/c/Users/foo/file.txt"

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only test")
    def test_windows_forward_to_unix(self):
        """Windows C:/path -> /c/path on Unix."""
        result = normalize_cross_platform_path("C:/Users/foo/file.txt")
        assert str(result) == "/c/Users/foo/file.txt"

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only test")
    def test_unix_path_passthrough(self):
        """Unix paths stay as-is on Unix."""
        result = normalize_cross_platform_path("/home/user/file.txt")
        assert str(result) == "/home/user/file.txt"

    def test_accepts_path_object(self):
        """Should accept Path objects as input."""
        p = Path("some/relative/path")
        result = normalize_cross_platform_path(p)
        assert isinstance(result, Path)

    def test_relative_path_passthrough(self):
        """Relative paths without drive letters pass through."""
        result = normalize_cross_platform_path("some/relative/path")
        assert isinstance(result, Path)

    def test_empty_string(self):
        """Empty string produces a Path."""
        result = normalize_cross_platform_path("")
        assert isinstance(result, Path)
        assert str(result) == "."


class TestPathExistsCrossPlatform:
    """Tests for path_exists_cross_platform()."""

    def test_existing_file(self):
        """Returns True for existing files."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        try:
            assert path_exists_cross_platform(temp_path) is True
        finally:
            os.unlink(temp_path)

    def test_nonexistent_file(self):
        """Returns False for non-existent files."""
        assert path_exists_cross_platform("/nonexistent/path/file.txt") is False

    def test_existing_directory(self):
        """Returns True for existing directories."""
        with tempfile.TemporaryDirectory() as d:
            assert path_exists_cross_platform(d) is True

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only test")
    def test_git_bash_style_existing(self):
        """Git Bash style paths for real files work on Windows."""
        # tempdir on Windows starts with C:\ or similar
        with tempfile.NamedTemporaryFile(delete=False) as f:
            win_path = f.name
        try:
            # Convert to git bash style: C:\temp\foo -> /c/temp/foo
            drive = win_path[0].lower()
            rest = win_path[2:].replace("\\", "/")
            git_bash_path = f"/{drive}{rest}"
            assert path_exists_cross_platform(git_bash_path) is True
        finally:
            os.unlink(win_path)

    def test_invalid_path_returns_false(self):
        """Clearly non-existent paths return False instead of raising."""
        assert path_exists_cross_platform("/no/such/path/ever/abc123xyz") is False


class TestIsWindowsIsUnix:
    """Tests for platform detection functions."""

    def test_is_windows_matches_os_name(self):
        """is_windows() should match os.name == 'nt'."""
        # On Windows, os.name is 'nt' and platform.system() is 'Windows'
        if os.name == "nt":
            assert is_windows() is True
            assert is_unix() is False
        else:
            assert is_windows() is False

    def test_is_unix_matches_non_windows(self):
        """is_unix() should be True on Linux/macOS."""
        if os.name == "posix":
            assert is_unix() is True
            assert is_windows() is False


class TestFixPathSeparators:
    """Tests for fix_path_separators()."""

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only test")
    def test_forward_to_back_on_windows(self):
        result = fix_path_separators("C:/Users/foo/file.txt")
        assert result == r"C:\Users\foo\file.txt"

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only test")
    def test_back_to_forward_on_unix(self):
        result = fix_path_separators("C:\\Users\\foo\\file.txt")
        assert result == "C:/Users/foo/file.txt"
