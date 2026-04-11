"""v0.2.4 metadata roundtrip tests.

These tests verify that the rich metadata capabilities added in v0.2.4
actually work end-to-end -- capture, apply, and observe the result on
disk. They complement the gap/characterization tests by proving the
new features aren't just "present as names" but produce correct output.

Scope per platform:
  - Windows: mode/size/SDDL roundtrip, ctime restoration via pywin32
  - Linux/macOS: xattrs capture + apply (runs in WSL CI)
  - Cross-platform: compare_metadata diff semantics, metadata_to_json

These tests require pywin32 on Windows. On Linux, xattr tests will be
skipped if the filesystem doesn't support extended attributes.
"""

import datetime
import os
import sys
import time

import pytest

from dazzle_filekit.metadata import (
    apply_file_metadata,
    collect_file_metadata,
    compare_metadata,
    is_win32_available,
    metadata_to_json,
    restore_windows_creation_time,
)


# ---------------------------------------------------------------------------
# Cross-platform roundtrip basics
# ---------------------------------------------------------------------------


class TestBasicRoundtrip:
    """Verify capture-then-apply doesn't lose platform-agnostic fields."""

    def test_mode_roundtrip(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("hello")
        # Set a recognizable mode
        os.chmod(src, 0o644)
        md = collect_file_metadata(src)
        assert md.get("mode") is not None

        dst = tmp_path / "dst.txt"
        dst.write_text("hello")
        os.chmod(dst, 0o600)  # different mode
        apply_file_metadata(dst, md)

        new_md = collect_file_metadata(dst)
        # On Windows, stat's mode comes from file attributes, so it may
        # not exactly preserve Unix-style permission bits. Check that
        # both modes are equal (whatever they are).
        assert new_md.get("mode") == md.get("mode")

    def test_size_captured(self, tmp_path):
        f = tmp_path / "sample.txt"
        f.write_text("0123456789")
        md = collect_file_metadata(f)
        assert md.get("size") == 10

    def test_timestamps_have_iso_projections(self, tmp_path):
        f = tmp_path / "sample.txt"
        f.write_text("x")
        md = collect_file_metadata(f)
        ts = md["timestamps"]
        for key in ("modified", "accessed", "created"):
            assert key in ts
            assert f"{key}_iso" in ts
            # ISO should be a parseable string
            datetime.datetime.fromisoformat(ts[f"{key}_iso"])


# ---------------------------------------------------------------------------
# Windows: SDDL ACL roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
class TestSddlRoundtrip:
    """Windows ACL round-trip via SDDL string (JSON-safe)."""

    def test_sddl_captured_on_plain_file(self, tmp_path):
        if not is_win32_available():
            pytest.skip("pywin32 not installed")
        f = tmp_path / "plain.txt"
        f.write_text("x")
        md = collect_file_metadata(f)
        windows = md.get("windows", {})
        sddl = windows.get("security_descriptor_sddl")
        assert sddl is not None
        assert isinstance(sddl, str)
        assert len(sddl) > 0
        # SDDL strings start with O: or D: or S:
        assert sddl.startswith("O:") or sddl.startswith("D:") or sddl.startswith("S:")

    def test_sddl_roundtrip_preserves_aces(self, tmp_path):
        """Capture SDDL from source, apply to dest, verify ACEs match.

        Note: SetFileSecurity() clears the top-level ``AI``
        (SE_DACL_AUTO_INHERITED) flag when we explicitly set a DACL, so
        the raw SDDL strings may differ in the ``D:AI`` vs ``D:`` prefix.
        The individual ACEs (still marked ``ID`` for inherited) are
        preserved identically -- and that's what matters for recovery.
        """
        import re
        if not is_win32_available():
            pytest.skip("pywin32 not installed")

        src = tmp_path / "src.txt"
        src.write_text("x")
        md_src = collect_file_metadata(src)
        sddl_src = md_src["windows"]["security_descriptor_sddl"]

        dst = tmp_path / "dst.txt"
        dst.write_text("x")
        apply_file_metadata(dst, md_src)

        md_dst = collect_file_metadata(dst)
        sddl_dst = md_dst["windows"]["security_descriptor_sddl"]

        def _extract_aces(sddl: str) -> str:
            """Return the ACE body of the DACL, ignoring DACL-level flags."""
            # Match D:<flags>(aces...) and return (aces...)
            m = re.search(r"D:[A-Z]*(\(.*\))?", sddl)
            return m.group(1) if m and m.group(1) else ""

        aces_src = _extract_aces(sddl_src)
        aces_dst = _extract_aces(sddl_dst)

        # The ACE list must be identical (that's what actually controls access)
        assert aces_dst == aces_src, (
            f"DACL ACEs differ after roundtrip:\n"
            f"  src = {aces_src!r}\n  dst = {aces_dst!r}"
        )

        # The owner and group prefixes should also match
        def _extract_owner_group(sddl: str) -> tuple:
            o = re.search(r"O:[^GD]+", sddl)
            g = re.search(r"G:[^D]+", sddl)
            return (o.group(0) if o else "", g.group(0) if g else "")

        assert _extract_owner_group(sddl_src) == _extract_owner_group(sddl_dst)

    def test_sddl_is_json_serializable(self, tmp_path):
        """The SDDL string (unlike raw pywin32 handles) must be JSON-safe."""
        import json
        if not is_win32_available():
            pytest.skip("pywin32 not installed")
        f = tmp_path / "plain.txt"
        f.write_text("x")
        md = collect_file_metadata(f)
        # If this raises, the SDDL capture path is broken
        s = json.dumps(metadata_to_json(md))
        assert "security_descriptor_sddl" in s


# ---------------------------------------------------------------------------
# Windows: creation time restoration
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
class TestCtimeRestoration:
    """Windows NTFS creation time round-trip via SetFileTime."""

    def test_restore_creation_time_on_file(self, tmp_path):
        if not is_win32_available():
            pytest.skip("pywin32 not installed")

        f = tmp_path / "sample.txt"
        f.write_text("hello")

        # Wait a moment, then try to set creation time to 1 hour ago
        target_time = time.time() - 3600
        result = restore_windows_creation_time(f, target_time)
        assert result is True

        # Re-stat and check
        new_stat = f.stat()
        # Allow 2s tolerance for filesystem precision
        delta = abs(new_stat.st_ctime - target_time)
        assert delta < 2.0, (
            f"ctime not restored: expected ~{target_time}, got "
            f"{new_stat.st_ctime} (delta={delta}s)"
        )

    def test_restore_creation_time_on_directory(self, tmp_path):
        """Directories need FILE_FLAG_BACKUP_SEMANTICS -- verify that path works."""
        if not is_win32_available():
            pytest.skip("pywin32 not installed")

        d = tmp_path / "subdir"
        d.mkdir()

        target_time = time.time() - 7200  # 2 hours ago
        result = restore_windows_creation_time(d, target_time)
        assert result is True

        new_stat = d.stat()
        delta = abs(new_stat.st_ctime - target_time)
        assert delta < 2.0

    def test_restore_ctime_accepts_datetime(self, tmp_path):
        """The API accepts either epoch float or datetime object."""
        if not is_win32_available():
            pytest.skip("pywin32 not installed")

        f = tmp_path / "sample.txt"
        f.write_text("x")

        target_dt = datetime.datetime.now() - datetime.timedelta(hours=3)
        result = restore_windows_creation_time(f, target_dt)
        assert result is True

        new_stat = f.stat()
        target_epoch = target_dt.timestamp()
        delta = abs(new_stat.st_ctime - target_epoch)
        assert delta < 2.0

    def test_full_metadata_roundtrip_preserves_ctime(self, tmp_path):
        """End-to-end: capture metadata, modify ctime, restore metadata,
        verify ctime matches the captured value."""
        if not is_win32_available():
            pytest.skip("pywin32 not installed")

        f = tmp_path / "sample.txt"
        f.write_text("x")

        # Capture original ctime
        md = collect_file_metadata(f)
        original_ctime = md["timestamps"]["created"]

        # Perturb ctime to something else
        restore_windows_creation_time(f, time.time())

        # Re-apply the captured metadata -- should restore ctime
        apply_file_metadata(f, md)

        new_stat = f.stat()
        delta = abs(new_stat.st_ctime - original_ctime)
        assert delta < 2.0, (
            f"ctime not preserved through metadata roundtrip: "
            f"original={original_ctime}, got={new_stat.st_ctime}"
        )


# ---------------------------------------------------------------------------
# Linux/macOS: xattrs roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="xattrs are Unix-only")
class TestXattrsRoundtrip:
    """Extended attribute capture and apply on Linux/macOS."""

    def _xattrs_supported(self, tmp_path) -> bool:
        """Probe whether the filesystem supports xattrs."""
        if not hasattr(os, "setxattr"):
            return False
        probe = tmp_path / "xattr_probe.txt"
        probe.write_text("x")
        try:
            os.setxattr(probe, "user.filekit_probe", b"yes")
            return True
        except OSError:
            return False

    def test_xattr_capture(self, tmp_path):
        if not self._xattrs_supported(tmp_path):
            pytest.skip("filesystem does not support user xattrs")

        f = tmp_path / "sample.txt"
        f.write_text("x")
        os.setxattr(f, "user.filekit_test", b"hello world")

        md = collect_file_metadata(f)
        assert "xattrs" in md
        assert "user.filekit_test" in md["xattrs"]

    def test_xattr_roundtrip(self, tmp_path):
        if not self._xattrs_supported(tmp_path):
            pytest.skip("filesystem does not support user xattrs")

        src = tmp_path / "src.txt"
        src.write_text("x")
        os.setxattr(src, "user.filekit_k1", b"v1")
        os.setxattr(src, "user.filekit_k2", b"v2 binary \x00\xff")

        md = collect_file_metadata(src)

        dst = tmp_path / "dst.txt"
        dst.write_text("x")
        apply_file_metadata(dst, md)

        assert os.getxattr(dst, "user.filekit_k1") == b"v1"
        assert os.getxattr(dst, "user.filekit_k2") == b"v2 binary \x00\xff"

    def test_quarantine_xattr_skipped_on_restore(self, tmp_path):
        """com.apple.quarantine must NOT be re-applied on restore."""
        if not self._xattrs_supported(tmp_path):
            pytest.skip("filesystem does not support user xattrs")

        src = tmp_path / "src.txt"
        src.write_text("x")
        # Simulate a manifest that includes com.apple.quarantine
        import base64
        fake_md = {
            "xattrs": {
                "com.apple.quarantine": base64.b64encode(b"0082;00000000;Firefox;").decode(),
            }
        }

        dst = tmp_path / "dst.txt"
        dst.write_text("x")
        apply_file_metadata(dst, fake_md)

        # Quarantine should NOT be present on dst
        try:
            os.getxattr(dst, "com.apple.quarantine")
            pytest.fail("com.apple.quarantine was re-applied (should be skipped)")
        except OSError:
            pass  # expected


# ---------------------------------------------------------------------------
# compare_metadata: diff semantics
# ---------------------------------------------------------------------------


class TestCompareMetadata:
    def test_identical_dicts_diff_to_empty(self):
        md = {"mode": 0o644, "size": 100, "timestamps": {"modified": 1000, "accessed": 1000, "created": 1000}}
        assert compare_metadata(md, md) == {}

    def test_size_difference_reported(self):
        md1 = {"size": 100}
        md2 = {"size": 200}
        diff = compare_metadata(md1, md2)
        assert "size" in diff
        assert diff["size"]["old"] == 100
        assert diff["size"]["new"] == 200

    def test_mode_difference_reported_with_octal(self):
        md1 = {"mode": 0o644}
        md2 = {"mode": 0o755}
        diff = compare_metadata(md1, md2)
        assert "mode" in diff
        assert diff["mode"]["old_octal"] == oct(0o644)
        assert diff["mode"]["new_octal"] == oct(0o755)

    def test_small_timestamp_difference_ignored(self):
        """<=2s timestamp diff is treated as noise (filesystem precision)."""
        md1 = {"timestamps": {"modified": 1000.0, "accessed": 1000.0, "created": 1000.0}}
        md2 = {"timestamps": {"modified": 1001.5, "accessed": 1001.5, "created": 1001.5}}
        assert compare_metadata(md1, md2) == {}

    def test_large_timestamp_difference_reported(self):
        md1 = {"timestamps": {"modified": 1000.0, "accessed": 1000.0, "created": 1000.0}}
        md2 = {"timestamps": {"modified": 2000.0, "accessed": 2000.0, "created": 2000.0}}
        diff = compare_metadata(md1, md2)
        assert "timestamps" in diff
        assert "modified" in diff["timestamps"]
