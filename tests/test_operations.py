"""
Tests for filetoolkit file operations.
"""
import os
import tempfile
import pytest
from pathlib import Path
from filetoolkit import (
    copy_file,
    move_file,
    collect_file_metadata,
    apply_file_metadata,
    create_directory_structure,
    remove_file,
    remove_directory
)


class TestFileCopy:
    """Test file copy operations."""

    def test_copy_file_basic(self):
        """Test basic file copy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "source.txt")
            dst = os.path.join(tmpdir, "dest.txt")

            # Create source file
            Path(src).write_text("test content")

            # Copy file
            success = copy_file(src, dst)
            assert success
            assert os.path.exists(dst)
            assert Path(dst).read_text() == "test content"

    def test_copy_file_with_metadata(self):
        """Test file copy with metadata preservation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "source.txt")
            dst = os.path.join(tmpdir, "dest.txt")

            # Create source file
            Path(src).write_text("test content")

            # Copy with metadata
            success = copy_file(src, dst, preserve_metadata=True)
            assert success
            assert os.path.exists(dst)

            # Check metadata preserved
            src_stat = os.stat(src)
            dst_stat = os.stat(dst)
            assert abs(src_stat.st_mtime - dst_stat.st_mtime) < 2  # Allow 2s difference

    def test_copy_file_to_nested_directory(self):
        """Test copying file to nested directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "source.txt")
            dst = os.path.join(tmpdir, "a", "b", "c", "dest.txt")

            # Create source file
            Path(src).write_text("test content")

            # Copy file (should create parent dirs)
            success = copy_file(src, dst)
            assert success
            assert os.path.exists(dst)


class TestFileMove:
    """Test file move operations."""

    def test_move_file_basic(self):
        """Test basic file move."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "source.txt")
            dst = os.path.join(tmpdir, "dest.txt")

            # Create source file
            Path(src).write_text("test content")

            # Move file
            success = move_file(src, dst)
            assert success
            assert not os.path.exists(src)
            assert os.path.exists(dst)
            assert Path(dst).read_text() == "test content"

    def test_move_file_with_metadata(self):
        """Test file move with metadata preservation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "source.txt")
            dst = os.path.join(tmpdir, "dest.txt")

            # Create source file and record mtime
            Path(src).write_text("test content")
            src_mtime = os.stat(src).st_mtime

            # Move with metadata
            success = move_file(src, dst, preserve_metadata=True)
            assert success
            assert not os.path.exists(src)
            assert os.path.exists(dst)

            # Check metadata preserved
            dst_mtime = os.stat(dst).st_mtime
            assert abs(src_mtime - dst_mtime) < 2


class TestFileMetadata:
    """Test file metadata operations."""

    def test_collect_file_metadata(self):
        """Test collecting file metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            Path(path).write_text("test content")

            metadata = collect_file_metadata(path)
            assert "size" in metadata
            assert "mtime" in metadata
            assert metadata["size"] == 12  # "test content" is 12 bytes

    def test_apply_file_metadata(self):
        """Test applying metadata to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "source.txt")
            dst = os.path.join(tmpdir, "dest.txt")

            # Create files
            Path(src).write_text("test")
            Path(dst).write_text("test")

            # Collect and apply metadata
            metadata = collect_file_metadata(src)
            apply_file_metadata(dst, metadata)

            # Verify metadata applied
            src_mtime = os.stat(src).st_mtime
            dst_mtime = os.stat(dst).st_mtime
            assert abs(src_mtime - dst_mtime) < 2


class TestDirectoryStructure:
    """Test directory structure operations."""

    def test_create_directory_structure(self):
        """Test creating nested directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "a", "b", "c", "d")
            create_directory_structure(nested)

            assert os.path.exists(nested)
            assert os.path.isdir(nested)

    def test_create_directory_structure_existing(self):
        """Test creating directory that already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create directory
            nested = os.path.join(tmpdir, "a", "b")
            os.makedirs(nested)

            # Should not fail when creating again
            create_directory_structure(nested)
            assert os.path.exists(nested)


class TestFileRemoval:
    """Test file and directory removal operations."""

    def test_remove_file(self):
        """Test removing a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            Path(path).write_text("test")

            success = remove_file(path)
            assert success
            assert not os.path.exists(path)

    def test_remove_directory_empty(self):
        """Test removing empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "subdir")
            os.makedirs(subdir)

            success = remove_directory(subdir, recursive=False)
            assert success
            assert not os.path.exists(subdir)

    def test_remove_directory_recursive(self):
        """Test removing directory with contents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "subdir")
            os.makedirs(subdir)

            # Add file to directory
            file_path = os.path.join(subdir, "test.txt")
            Path(file_path).write_text("test")

            success = remove_directory(subdir, recursive=True)
            assert success
            assert not os.path.exists(subdir)
