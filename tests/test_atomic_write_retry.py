"""The os.replace bounded retry (WinError 5 AV contention -- observed in
dazzlecmd's suite, one random victim per full run)."""
import pytest
from unittest import mock
from dazzle_filekit.operations import atomic_write_text


def test_transient_permission_error_absorbed(tmp_path):
    target = tmp_path / "x.json"
    real_replace = __import__("os").replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(5, "Access is denied")
        return real_replace(src, dst)

    with mock.patch("dazzle_filekit.operations.os.replace", side_effect=flaky):
        atomic_write_text(target, "hello")
    assert target.read_text() == "hello"
    assert calls["n"] == 3


def test_persistent_permission_error_raises(tmp_path):
    target = tmp_path / "x.json"
    with mock.patch("dazzle_filekit.operations.os.replace",
                    side_effect=PermissionError(5, "Access is denied")):
        with pytest.raises(PermissionError):
            atomic_write_text(target, "hello")
