"""
Tests for filetoolkit file verification.
"""
import os
import tempfile
import pytest
from pathlib import Path
from filetoolkit import (
    calculate_file_hash,
    verify_file_hash,
    calculate_directory_hashes,
    save_hashes_to_file,
    load_hashes_from_file,
    compare_directories
)


class TestHashCalculation:
    """Test hash calculation functions."""

    def test_calculate_file_hash_md5(self):
        """Test MD5 hash calculation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            Path(path).write_text("test content")

            hash_value = calculate_file_hash(path, algorithm="md5")
            assert hash_value is not None
            assert len(hash_value) == 32  # MD5 is 32 hex chars

    def test_calculate_file_hash_sha256(self):
        """Test SHA256 hash calculation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            Path(path).write_text("test content")

            hash_value = calculate_file_hash(path, algorithm="sha256")
            assert hash_value is not None
            assert len(hash_value) == 64  # SHA256 is 64 hex chars

    def test_calculate_file_hash_sha512(self):
        """Test SHA512 hash calculation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            Path(path).write_text("test content")

            hash_value = calculate_file_hash(path, algorithm="sha512")
            assert hash_value is not None
            assert len(hash_value) == 128  # SHA512 is 128 hex chars

    def test_calculate_file_hash_consistent(self):
        """Test hash calculation is consistent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            Path(path).write_text("test content")

            hash1 = calculate_file_hash(path, algorithm="sha256")
            hash2 = calculate_file_hash(path, algorithm="sha256")
            assert hash1 == hash2


class TestHashVerification:
    """Test hash verification functions."""

    def test_verify_file_hash_match(self):
        """Test hash verification with matching hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            Path(path).write_text("test content")

            # Calculate hash
            expected_hash = calculate_file_hash(path, algorithm="sha256")

            # Verify hash
            is_valid = verify_file_hash(path, expected_hash, algorithm="sha256")
            assert is_valid

    def test_verify_file_hash_mismatch(self):
        """Test hash verification with mismatched hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            Path(path).write_text("test content")

            # Use wrong hash
            wrong_hash = "0" * 64

            # Verify hash
            is_valid = verify_file_hash(path, wrong_hash, algorithm="sha256")
            assert not is_valid

    def test_verify_file_hash_modified_file(self):
        """Test hash verification detects file modification."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            Path(path).write_text("original content")

            # Calculate original hash
            original_hash = calculate_file_hash(path, algorithm="sha256")

            # Modify file
            Path(path).write_text("modified content")

            # Verify should fail
            is_valid = verify_file_hash(path, original_hash, algorithm="sha256")
            assert not is_valid


class TestDirectoryHashing:
    """Test directory-level hashing operations."""

    def test_calculate_directory_hashes(self):
        """Test calculating hashes for all files in directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            (Path(tmpdir) / "file1.txt").write_text("content1")
            (Path(tmpdir) / "file2.txt").write_text("content2")

            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()
            (subdir / "file3.txt").write_text("content3")

            # Calculate hashes
            hashes = calculate_directory_hashes(tmpdir, algorithm="sha256")
            assert len(hashes) == 3
            assert all(len(h) == 64 for h in hashes.values())

    def test_save_and_load_hashes(self):
        """Test saving and loading hash files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            (Path(tmpdir) / "file1.txt").write_text("content1")
            (Path(tmpdir) / "file2.txt").write_text("content2")

            # Calculate and save hashes
            hashes = calculate_directory_hashes(tmpdir, algorithm="sha256")
            hash_file = os.path.join(tmpdir, "hashes.txt")
            save_hashes_to_file(hashes, hash_file)

            # Load hashes
            loaded_hashes = load_hashes_from_file(hash_file)
            assert loaded_hashes == hashes


class TestDirectoryComparison:
    """Test directory comparison operations."""

    def test_compare_directories_identical(self):
        """Test comparing identical directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dir1 = os.path.join(tmpdir, "dir1")
            dir2 = os.path.join(tmpdir, "dir2")
            os.makedirs(dir1)
            os.makedirs(dir2)

            # Create identical files
            (Path(dir1) / "test.txt").write_text("content")
            (Path(dir2) / "test.txt").write_text("content")

            result = compare_directories(dir1, dir2)
            assert result["matching"] == 1
            assert result["different"] == 0
            assert result["only_in_dir1"] == 0
            assert result["only_in_dir2"] == 0

    def test_compare_directories_different_content(self):
        """Test comparing directories with different file content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dir1 = os.path.join(tmpdir, "dir1")
            dir2 = os.path.join(tmpdir, "dir2")
            os.makedirs(dir1)
            os.makedirs(dir2)

            # Create files with different content
            (Path(dir1) / "test.txt").write_text("content1")
            (Path(dir2) / "test.txt").write_text("content2")

            result = compare_directories(dir1, dir2)
            assert result["matching"] == 0
            assert result["different"] == 1

    def test_compare_directories_missing_files(self):
        """Test comparing directories with missing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dir1 = os.path.join(tmpdir, "dir1")
            dir2 = os.path.join(tmpdir, "dir2")
            os.makedirs(dir1)
            os.makedirs(dir2)

            # Create file only in dir1
            (Path(dir1) / "only_in_dir1.txt").write_text("content")

            # Create file only in dir2
            (Path(dir2) / "only_in_dir2.txt").write_text("content")

            result = compare_directories(dir1, dir2)
            assert result["only_in_dir1"] == 1
            assert result["only_in_dir2"] == 1
