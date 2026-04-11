"""Characterization tests for metadata collection/application.

Documents the CURRENT behavior of:
  - dazzle_filekit.operations.collect_file_metadata / apply_file_metadata
  - safedel/_lib/preservelib/metadata.py collect_file_metadata / apply_file_metadata
    (the richer preservelib version)

POST-v0.3.2: filekit will have a new metadata.py module with the ported
preservelib functionality. The comparison matrix says OUR (preservelib)
version is strictly better -- these tests demonstrate the specific gaps.
"""

import os
import sys
import tempfile

import pytest

from dazzle_filekit.operations import (
    collect_file_metadata as filekit_collect,
    apply_file_metadata as filekit_apply,
)


# v0.2.4: ``_import_safedel_preservelib_metadata`` removed.
# The back-to-back cross-check against safedel's embedded preservelib was
# useful during Phase 2 to prove "their version is richer than ours"; now
# that the port has landed in ``dazzle_filekit.metadata``, the equivalent
# assertions live in ``TestFilekitMetadataModuleV024`` below and test
# filekit directly (no cross-repo hardcoded paths).


# ---------------------------------------------------------------------------
# Baseline: filekit.operations.collect_file_metadata
# ---------------------------------------------------------------------------


class TestFilekitCollectMetadataV024:
    """v0.2.4: filekit's collect_file_metadata is now backed by the rich
    metadata.py module (ported from preservelib). These assertions lock in
    the new capabilities so they can't silently regress.

    v0.2.3 had: mode, timestamps (floats only), platform dict.
    v0.2.4 has: mode, size, timestamps (+ ISO), SDDL ACLs, xattrs.
    """

    def test_captures_mode(self, tmp_path):
        f = tmp_path / "plain.txt"
        f.write_text("x")
        meta = filekit_collect(f)
        assert "mode" in meta

    def test_captures_timestamps_with_iso(self, tmp_path):
        f = tmp_path / "plain.txt"
        f.write_text("x")
        meta = filekit_collect(f)
        assert "timestamps" in meta
        ts = meta["timestamps"]
        assert "modified" in ts
        assert "accessed" in ts
        # v0.2.4 additions
        assert "modified_iso" in ts
        assert "created_iso" in ts

    def test_captures_size(self, tmp_path):
        """v0.2.4: 'size' is now in the metadata dict."""
        f = tmp_path / "plain.txt"
        f.write_text("hello")
        meta = filekit_collect(f)
        assert meta.get("size") == 5

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_captures_sddl_acls(self, tmp_path):
        """v0.2.4: SDDL security descriptor string is captured on Windows."""
        try:
            import win32security  # noqa: F401
        except ImportError:
            pytest.skip("pywin32 not installed")

        f = tmp_path / "plain.txt"
        f.write_text("x")
        meta = filekit_collect(f)
        windows_meta = meta.get("windows", {})
        assert "security_descriptor_sddl" in windows_meta, (
            "v0.2.4 should capture SDDL on Windows with pywin32"
        )
        # Should be a non-empty string (SDDL format)
        sddl = windows_meta["security_descriptor_sddl"]
        assert sddl is not None
        assert isinstance(sddl, str)
        assert len(sddl) > 0

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_captures_windows_attribute_flags(self, tmp_path):
        """v0.2.4: is_hidden/is_system/is_readonly/is_archive boolean flags."""
        try:
            import win32api  # noqa: F401
        except ImportError:
            pytest.skip("pywin32 not installed")

        f = tmp_path / "plain.txt"
        f.write_text("x")
        meta = filekit_collect(f)
        windows_meta = meta.get("windows", {})
        for flag in ("is_hidden", "is_system", "is_readonly", "is_archive"):
            assert flag in windows_meta, f"missing {flag}"
            assert isinstance(windows_meta[flag], bool)


# ---------------------------------------------------------------------------
# v0.2.4: functions ported from preservelib now live in dazzle_filekit.metadata
# ---------------------------------------------------------------------------


class TestFilekitMetadataModuleV024:
    """v0.2.4: the dazzle_filekit.metadata module is live with the rich
    capabilities ported byte-identically from preservelib. These tests
    lock in the new public surface.
    """

    def test_metadata_module_importable(self):
        import dazzle_filekit.metadata as md
        assert hasattr(md, "collect_file_metadata")
        assert hasattr(md, "apply_file_metadata")

    def test_restore_windows_creation_time_importable(self):
        from dazzle_filekit.metadata import restore_windows_creation_time
        assert callable(restore_windows_creation_time)

    def test_is_win32_available_importable(self):
        from dazzle_filekit.metadata import is_win32_available
        assert callable(is_win32_available)
        # The return type is bool
        assert isinstance(is_win32_available(), bool)

    def test_xattr_helpers_importable(self):
        from dazzle_filekit.metadata import _collect_unix_xattrs, _apply_unix_xattrs
        assert callable(_collect_unix_xattrs)
        assert callable(_apply_unix_xattrs)

    def test_compare_metadata_importable(self):
        from dazzle_filekit.metadata import compare_metadata
        # Identical dicts should diff to empty
        md = {"mode": 0o644, "size": 100}
        assert compare_metadata(md, md) == {}

    def test_metadata_to_json_importable(self):
        from dazzle_filekit.metadata import metadata_to_json
        result = metadata_to_json({"a": 1, "b": {"c": 2}})
        assert result == {"a": 1, "b": {"c": 2}}

    def test_top_level_metadata_attribute(self):
        """`from dazzle_filekit import metadata` must work as a submodule import."""
        from dazzle_filekit import metadata
        assert hasattr(metadata, "collect_file_metadata")

    def test_operations_wrappers_delegate_to_metadata(self, tmp_path):
        """operations.collect_file_metadata and metadata.collect_file_metadata
        should produce identical output (the operations version is now a
        thin wrapper)."""
        from dazzle_filekit.operations import collect_file_metadata as ops_collect
        from dazzle_filekit.metadata import collect_file_metadata as md_collect

        f = tmp_path / "plain.txt"
        f.write_text("x")

        meta1 = ops_collect(f)
        meta2 = md_collect(f)
        # The dicts should have the same keys
        assert set(meta1.keys()) == set(meta2.keys())
        assert meta1.get("size") == meta2.get("size")
        assert meta1.get("mode") == meta2.get("mode")
