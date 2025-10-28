"""
Tests for filetoolkit path operations.
"""
import os
import tempfile
import pytest
from pathlib import Path
from filetoolkit import (
    normalize_path,
    is_same_file,
    get_relative_path,
    find_files,
    create_parent_dirs,
    ensure_unique_path
)


class TestPathNormalization:
    """Test path normalization functions."""

    def test_normalize_path_basic(self):
        """Test basic path normalization."""
        path = normalize_path("/some/path/../file.txt")
        assert path == os.path.normpath("/some/file.txt")

    def test_normalize_path_with_tilde(self):
        """Test path normalization with user home directory."""
        path = normalize_path("~/file.txt")
        assert path.startswith(os.path.expanduser("~"))

    def test_normalize_path_absolute(self):
        """Test absolute path handling."""
        path = normalize_path("C:/test/file.txt")
        assert os.path.isabs(path)


class TestPathComparison:
    """Test path comparison functions."""

    def test_is_same_file_identical(self):
        """Test identical file paths are detected as same."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            path1 = tmp.name
            path2 = tmp.name
            try:
                assert is_same_file(path1, path2)
            finally:
                os.unlink(path1)

    def test_is_same_file_different(self):
        """Test different files are detected as different."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp1:
            with tempfile.NamedTemporaryFile(delete=False) as tmp2:
                try:
                    assert not is_same_file(tmp1.name, tmp2.name)
                finally:
                    os.unlink(tmp1.name)
                    os.unlink(tmp2.name)


class TestRelativePaths:
    """Test relative path operations."""

    def test_get_relative_path_subdirectory(self):
        """Test getting relative path for subdirectory."""
        base = "/home/user/project"
        path = "/home/user/project/src/main.py"
        rel = get_relative_path(path, base)
        assert rel == os.path.join("src", "main.py")

    def test_get_relative_path_same_directory(self):
        """Test relative path when paths are in same directory."""
        base = "/home/user/project"
        path = "/home/user/project/file.txt"
        rel = get_relative_path(path, base)
        assert rel == "file.txt"


class TestFileDiscovery:
    """Test file finding operations."""

    def test_find_files_with_pattern(self):
        """Test finding files with glob pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test")

            other_file = Path(tmpdir) / "test.py"
            other_file.write_text("test")

            # Find only .txt files
            files = find_files(tmpdir, patterns=["*.txt"])
            assert len(files) == 1
            assert files[0].endswith("test.txt")

    def test_find_files_multiple_patterns(self):
        """Test finding files with multiple patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            (Path(tmpdir) / "test.txt").write_text("test")
            (Path(tmpdir) / "test.py").write_text("test")
            (Path(tmpdir) / "test.md").write_text("test")

            # Find .txt and .py files
            files = find_files(tmpdir, patterns=["*.txt", "*.py"])
            assert len(files) == 2


class TestDirectoryOperations:
    """Test directory creation operations."""

    def test_create_parent_dirs(self):
        """Test creating parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = os.path.join(tmpdir, "a", "b", "c", "file.txt")
            create_parent_dirs(nested_path)

            parent_dir = os.path.dirname(nested_path)
            assert os.path.exists(parent_dir)
            assert os.path.isdir(parent_dir)

    def test_ensure_unique_path_no_collision(self):
        """Test unique path when no collision exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            unique = ensure_unique_path(path)
            assert unique == path

    def test_ensure_unique_path_with_collision(self):
        """Test unique path when collision exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create existing file
            path = os.path.join(tmpdir, "test.txt")
            Path(path).write_text("test")

            # Get unique path
            unique = ensure_unique_path(path)
            assert unique != path
            assert "test" in unique
            assert unique.endswith(".txt")
