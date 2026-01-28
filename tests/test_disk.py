"""Tests for dazzle_filekit.utils.disk space checking utilities."""

import os
import tempfile
from pathlib import Path

import pytest

from dazzle_filekit.utils.disk import (
    DiskUsage,
    InsufficientSpaceError,
    get_disk_usage,
    check_disk_space,
    calculate_total_size,
    ensure_disk_space,
    _format_bytes,
)


class TestDiskUsage:
    """Tests for DiskUsage named tuple."""

    def test_basic_creation(self):
        usage = DiskUsage(total=1000, used=600, free=400)
        assert usage.total == 1000
        assert usage.used == 600
        assert usage.free == 400

    def test_used_percent(self):
        usage = DiskUsage(total=1000, used=600, free=400)
        assert usage.used_percent == 60.0

    def test_free_percent(self):
        usage = DiskUsage(total=1000, used=600, free=400)
        assert usage.free_percent == 40.0

    def test_zero_total(self):
        usage = DiskUsage(total=0, used=0, free=0)
        assert usage.used_percent == 0.0
        assert usage.free_percent == 0.0


class TestInsufficientSpaceError:
    """Tests for InsufficientSpaceError exception."""

    def test_basic_raise(self):
        with pytest.raises(InsufficientSpaceError) as exc_info:
            raise InsufficientSpaceError(
                message="Not enough space",
                required=1000,
                available=500,
                path="/tmp"
            )
        assert exc_info.value.required == 1000
        assert exc_info.value.available == 500
        assert exc_info.value.shortfall == 500
        assert exc_info.value.path == "/tmp"

    def test_is_exception_subclass(self):
        err = InsufficientSpaceError("msg", required=10, available=5)
        assert isinstance(err, Exception)


class TestGetDiskUsage:
    """Tests for get_disk_usage()."""

    def test_existing_directory(self):
        """Should return valid usage for existing directory."""
        with tempfile.TemporaryDirectory() as d:
            usage = get_disk_usage(d)
            assert isinstance(usage, DiskUsage)
            assert usage.total > 0
            assert usage.free >= 0
            assert usage.used >= 0

    def test_existing_file(self):
        """Should return disk usage for drive containing a file."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        try:
            usage = get_disk_usage(temp_path)
            assert usage.total > 0
        finally:
            os.unlink(temp_path)

    def test_nonexistent_path_walks_up(self):
        """Should walk up to find existing parent."""
        with tempfile.TemporaryDirectory() as d:
            nonexistent = Path(d) / "does" / "not" / "exist"
            usage = get_disk_usage(nonexistent)
            assert usage.total > 0

    def test_completely_invalid_path_raises(self):
        """Should raise OSError for paths where no parent exists."""
        # This is hard to trigger on real systems since / always exists
        # but we can test that a valid root still works
        if os.name == "nt":
            usage = get_disk_usage("C:\\")
        else:
            usage = get_disk_usage("/")
        assert usage.total > 0

    def test_home_directory(self):
        """Should work with home directory."""
        usage = get_disk_usage(Path.home())
        assert usage.total > 0
        assert usage.free > 0


class TestCheckDiskSpace:
    """Tests for check_disk_space()."""

    def test_sufficient_space(self):
        """Should return True when space is available."""
        has_space, required, available, message = check_disk_space(
            Path.home(), required_bytes=1, safety_margin=0.0
        )
        assert has_space is True
        assert available > 0
        assert "Sufficient" in message

    def test_insufficient_space(self):
        """Should return False when requesting unreasonable space."""
        has_space, required, available, message = check_disk_space(
            Path.home(),
            required_bytes=10**18,  # 1 exabyte
            safety_margin=0.0
        )
        assert has_space is False
        assert "Insufficient" in message

    def test_safety_margin_applied(self):
        """Safety margin should increase required bytes."""
        _, required_no_margin, _, _ = check_disk_space(
            Path.home(), required_bytes=1000, safety_margin=0.0
        )
        _, required_with_margin, _, _ = check_disk_space(
            Path.home(), required_bytes=1000, safety_margin=0.5
        )
        assert required_with_margin == 1500
        assert required_no_margin == 1000

    def test_raise_on_insufficient(self):
        """Should raise InsufficientSpaceError when requested."""
        with pytest.raises(InsufficientSpaceError):
            check_disk_space(
                Path.home(),
                required_bytes=10**18,
                raise_on_insufficient=True
            )

    def test_no_raise_by_default(self):
        """Should not raise by default even when insufficient."""
        has_space, _, _, _ = check_disk_space(
            Path.home(), required_bytes=10**18
        )
        assert has_space is False  # No exception raised


class TestCalculateTotalSize:
    """Tests for calculate_total_size()."""

    def test_single_file(self):
        """Should return file size."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"hello world")
            temp_path = f.name
        try:
            size = calculate_total_size([temp_path])
            assert size == 11
        finally:
            os.unlink(temp_path)

    def test_multiple_files(self):
        """Should sum sizes of multiple files."""
        files = []
        try:
            for content in [b"aaa", b"bbbbb", b"cc"]:
                f = tempfile.NamedTemporaryFile(delete=False)
                f.write(content)
                f.close()
                files.append(f.name)

            size = calculate_total_size(files)
            assert size == 10  # 3 + 5 + 2
        finally:
            for f in files:
                os.unlink(f)

    def test_directory(self):
        """Should recursively calculate directory size."""
        with tempfile.TemporaryDirectory() as d:
            f1 = Path(d) / "file1.txt"
            f1.write_bytes(b"12345")
            subdir = Path(d) / "sub"
            subdir.mkdir()
            f2 = subdir / "file2.txt"
            f2.write_bytes(b"67890")

            size = calculate_total_size([d])
            assert size == 10

    def test_nonexistent_skipped(self):
        """Should skip non-existent paths and return 0."""
        size = calculate_total_size(["/nonexistent/file.txt"])
        assert size == 0

    def test_empty_list(self):
        """Should return 0 for empty list."""
        assert calculate_total_size([]) == 0

    def test_mixed_files_and_dirs(self):
        """Should handle mix of files and directories."""
        with tempfile.TemporaryDirectory() as d:
            f1 = Path(d) / "file.txt"
            f1.write_bytes(b"abc")
            subdir = Path(d) / "sub"
            subdir.mkdir()
            f2 = subdir / "nested.txt"
            f2.write_bytes(b"de")

            # Pass both the file and subdirectory
            size = calculate_total_size([str(f1), str(subdir)])
            assert size == 5  # 3 + 2


class TestEnsureDiskSpace:
    """Tests for ensure_disk_space()."""

    def test_sufficient(self):
        """Should return True for tiny source files."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"tiny")
            temp_path = f.name
        try:
            has_space, message = ensure_disk_space(
                Path.home(), [temp_path], safety_margin=0.1
            )
            assert has_space is True
        finally:
            os.unlink(temp_path)

    def test_message_present(self):
        """Should return a descriptive message."""
        has_space, message = ensure_disk_space(
            Path.home(), [], safety_margin=0.1
        )
        assert isinstance(message, str)
        assert len(message) > 0


class TestFormatBytes:
    """Tests for _format_bytes() helper."""

    def test_bytes(self):
        assert _format_bytes(500) == "500.0 B"

    def test_kilobytes(self):
        assert _format_bytes(1024) == "1.0 KB"

    def test_megabytes(self):
        assert _format_bytes(1024 * 1024) == "1.0 MB"

    def test_gigabytes(self):
        assert _format_bytes(1024 ** 3) == "1.0 GB"

    def test_terabytes(self):
        assert _format_bytes(1024 ** 4) == "1.0 TB"

    def test_zero(self):
        assert _format_bytes(0) == "0.0 B"
