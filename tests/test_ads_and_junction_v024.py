"""v0.2.4: NTFS Alternate Data Streams detection + is_junction fix.

These tests lock in the Phase 7 additions:

  - ``dazzle_filekit.platform.windows.detect_alternate_streams`` via
    ctypes FindFirstStreamW / FindNextStreamW
  - ``dazzle_filekit.platform.windows.has_significant_ads`` thin wrapper
  - ``dazzle_filekit.utils.validation.is_junction`` fixed via
    DeviceIoControl(FSCTL_GET_REPARSE_POINT) + reparse tag check

See test_junction_detection_behavior.py for the characterization
proofs of the is_junction fix (junctions detected, symlinks not
misclassified).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="ADS and junctions are Windows-only NTFS features",
)


def _write_ads(path: Path, stream_name: str, content: str) -> bool:
    """Write to an NTFS alternate data stream via PowerShell.

    Returns True if successful, False if the filesystem doesn't support ADS.
    """
    result = subprocess.run(
        [
            "powershell", "-Command",
            f"Set-Content -Path '{path}' -Stream '{stream_name}' -Value '{content}'",
        ],
        capture_output=True, text=True,
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# detect_alternate_streams
# ---------------------------------------------------------------------------


class TestDetectAlternateStreams:
    def test_importable(self):
        from dazzle_filekit.platform.windows import detect_alternate_streams
        assert callable(detect_alternate_streams)

    def test_plain_file_has_no_significant_streams(self, tmp_path):
        """A freshly-created file has no non-default ADS."""
        from dazzle_filekit.platform.windows import detect_alternate_streams
        f = tmp_path / "plain.txt"
        f.write_text("hello")
        streams = detect_alternate_streams(str(f))
        assert isinstance(streams, list)
        # Filtered streams should not be in the result
        for s in streams:
            assert s not in ("::$DATA", ":Zone.Identifier:$DATA")

    def test_zone_identifier_filtered_out(self, tmp_path):
        """Browser Zone.Identifier streams are filtered from results."""
        from dazzle_filekit.platform.windows import detect_alternate_streams
        f = tmp_path / "download.txt"
        f.write_text("downloaded content")
        if not _write_ads(f, "Zone.Identifier", "[ZoneTransfer]\r\nZoneId=3\r\n"):
            pytest.skip("Cannot write ADS on this filesystem")

        streams = detect_alternate_streams(str(f))
        for s in streams:
            assert "Zone.Identifier" not in s

    def test_custom_stream_detected(self, tmp_path):
        """A custom (non-filtered) ADS should be returned."""
        from dazzle_filekit.platform.windows import detect_alternate_streams
        f = tmp_path / "tagged.txt"
        f.write_text("main content")
        if not _write_ads(f, "user.mycustom", "custom sidecar data"):
            pytest.skip("Cannot write ADS on this filesystem")

        streams = detect_alternate_streams(str(f))
        assert any("mycustom" in s for s in streams), (
            f"Expected ':user.mycustom' or similar in streams, got {streams}"
        )

    def test_returns_empty_on_nonexistent(self, tmp_path):
        from dazzle_filekit.platform.windows import detect_alternate_streams
        result = detect_alternate_streams(str(tmp_path / "nonexistent.txt"))
        assert result == []


# ---------------------------------------------------------------------------
# has_significant_ads
# ---------------------------------------------------------------------------


class TestHasSignificantAds:
    def test_importable(self):
        from dazzle_filekit.platform.windows import has_significant_ads
        assert callable(has_significant_ads)

    def test_plain_file_returns_false(self, tmp_path):
        from dazzle_filekit.platform.windows import has_significant_ads
        f = tmp_path / "plain.txt"
        f.write_text("x")
        assert has_significant_ads(str(f)) is False

    def test_zone_identifier_only_returns_false(self, tmp_path):
        """A file with ONLY Zone.Identifier is not 'significant'."""
        from dazzle_filekit.platform.windows import has_significant_ads
        f = tmp_path / "download.txt"
        f.write_text("x")
        if not _write_ads(f, "Zone.Identifier", "[ZoneTransfer]\r\nZoneId=3\r\n"):
            pytest.skip("Cannot write ADS on this filesystem")

        assert has_significant_ads(str(f)) is False

    def test_custom_stream_returns_true(self, tmp_path):
        from dazzle_filekit.platform.windows import has_significant_ads
        f = tmp_path / "tagged.txt"
        f.write_text("x")
        if not _write_ads(f, "sidecar", "some meta"):
            pytest.skip("Cannot write ADS on this filesystem")
        assert has_significant_ads(str(f)) is True


# ---------------------------------------------------------------------------
# is_junction correctness (v0.2.4 fix)
# ---------------------------------------------------------------------------


def _create_junction(link_path: str, target_path: str) -> bool:
    result = subprocess.run(
        [
            "powershell", "-Command",
            f"New-Item -ItemType Junction -Path '{link_path}' -Target '{target_path}'",
        ],
        capture_output=True, text=True,
    )
    return result.returncode == 0


class TestIsJunctionV024:
    def test_plain_directory_not_junction(self, tmp_path):
        from dazzle_filekit.utils.validation import is_junction
        d = tmp_path / "plain"
        d.mkdir()
        assert is_junction(d) is False

    def test_plain_file_not_junction(self, tmp_path):
        from dazzle_filekit.utils.validation import is_junction
        f = tmp_path / "plain.txt"
        f.write_text("x")
        assert is_junction(f) is False

    def test_nonexistent_not_junction(self, tmp_path):
        from dazzle_filekit.utils.validation import is_junction
        assert is_junction(tmp_path / "nope") is False

    def test_real_junction_detected(self, tmp_path):
        from dazzle_filekit.utils.validation import is_junction
        target = tmp_path / "target"
        target.mkdir()
        link = tmp_path / "jct"
        if not _create_junction(str(link), str(target)):
            pytest.skip("Cannot create junction")
        assert is_junction(link) is True

    def test_directory_symlink_not_junction(self, tmp_path):
        """Directory symlinks have ``IO_REPARSE_TAG_SYMLINK``, not
        ``IO_REPARSE_TAG_MOUNT_POINT`` -- v0.2.4 distinguishes them."""
        from dazzle_filekit.utils.validation import is_junction
        target = tmp_path / "target"
        target.mkdir()
        link = tmp_path / "sym"
        try:
            os.symlink(str(target), str(link), target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation requires admin on Windows")

        assert is_junction(link) is False, (
            "v0.2.4 is_junction must not misclassify symlinks as junctions"
        )
