"""
Smoke tests for dazzle-filekit package.

These tests verify basic functionality and that all modules can be imported.
"""
import tempfile
from pathlib import Path
import dazzle_filekit


class TestImports:
    """Test that all modules can be imported."""

    def test_import_main_package(self):
        """Test main package import."""
        assert dazzle_filekit is not None
        assert hasattr(dazzle_filekit, '__version__')

    def test_import_paths(self):
        """Test paths module functions are available."""
        assert hasattr(dazzle_filekit, 'normalize_path')
        assert hasattr(dazzle_filekit, 'find_files')
        assert hasattr(dazzle_filekit, 'is_unc_path')

    def test_import_operations(self):
        """Test operations module functions are available."""
        assert hasattr(dazzle_filekit, 'copy_file')
        assert hasattr(dazzle_filekit, 'move_file')
        assert hasattr(dazzle_filekit, 'collect_file_metadata')

    def test_import_verification(self):
        """Test verification module functions are available."""
        assert hasattr(dazzle_filekit, 'calculate_file_hash')
        assert hasattr(dazzle_filekit, 'verify_file_hash')
        assert hasattr(dazzle_filekit, 'compare_directories')


class TestBasicOperations:
    """Test basic operations work."""

    def test_normalize_path_returns_path_object(self):
        """Test normalize_path returns Path object."""
        result = dazzle_filekit.normalize_path("/some/path")
        assert isinstance(result, Path)

    def test_copy_file_basic(self):
        """Test basic file copy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.txt"
            dst = Path(tmpdir) / "dest.txt"

            # Create source
            src.write_text("test content")

            # Copy
            success = dazzle_filekit.copy_file(str(src), str(dst))
            assert success
            assert dst.exists()
            assert dst.read_text() == "test content"
