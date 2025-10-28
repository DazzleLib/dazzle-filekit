"""
Smoke tests for filetoolkit package.

These tests verify basic functionality and that all modules can be imported.
"""
import tempfile
from pathlib import Path
import filetoolkit


class TestImports:
    """Test that all modules can be imported."""

    def test_import_main_package(self):
        """Test main package import."""
        assert filetoolkit is not None
        assert hasattr(filetoolkit, '__version__')

    def test_import_paths(self):
        """Test paths module functions are available."""
        assert hasattr(filetoolkit, 'normalize_path')
        assert hasattr(filetoolkit, 'find_files')
        assert hasattr(filetoolkit, 'is_unc_path')

    def test_import_operations(self):
        """Test operations module functions are available."""
        assert hasattr(filetoolkit, 'copy_file')
        assert hasattr(filetoolkit, 'move_file')
        assert hasattr(filetoolkit, 'collect_file_metadata')

    def test_import_verification(self):
        """Test verification module functions are available."""
        assert hasattr(filetoolkit, 'calculate_file_hash')
        assert hasattr(filetoolkit, 'verify_file_hash')
        assert hasattr(filetoolkit, 'compare_directories')


class TestBasicOperations:
    """Test basic operations work."""

    def test_normalize_path_returns_path_object(self):
        """Test normalize_path returns Path object."""
        result = filetoolkit.normalize_path("/some/path")
        assert isinstance(result, Path)

    def test_copy_file_basic(self):
        """Test basic file copy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.txt"
            dst = Path(tmpdir) / "dest.txt"

            # Create source
            src.write_text("test content")

            # Copy
            success = filetoolkit.copy_file(str(src), str(dst))
            assert success
            assert dst.exists()
            assert dst.read_text() == "test content"
