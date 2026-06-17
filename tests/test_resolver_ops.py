"""End-to-end tests for the resolver-driven fallback on the real file ops
(copy_file / move_file / open_file), the Option D L1 consumer.

Uses real files in tmp_path with a hand-written resolver (AC-INJECT): the
"blocked" name simply does not exist, and the resolver maps it to the real
one -- so the variant retry is exercised without needing actual UNC/network
paths. Covers AC-SEM (operation succeeds under a variant), AC-NOREG (defaults
unchanged), AC-INJECT (an arbitrary resolver drives it).
"""

import pytest

from dazzle_lib import PathVariantResolver
from dazzle_filekit import copy_file, move_file, open_file


class FakeResolver:
    """Maps a non-existent 'blocked' name to the real working path."""

    def __init__(self, mapping):
        self._mapping = mapping

    def variants(self, path):
        out = [path]
        if path in self._mapping:
            out.append(self._mapping[path])
        return out


def test_fakeresolver_satisfies_protocol():
    assert isinstance(FakeResolver({}), PathVariantResolver)


# --- AC-NOREG: defaults are byte-identical to before ----------------------

def test_copy_file_default_behavior_unchanged(tmp_path):
    src = tmp_path / "a.txt"; src.write_text("hello")
    dst = tmp_path / "b.txt"
    assert copy_file(str(src), str(dst)) is True
    assert dst.read_text() == "hello"
    # missing source still returns False with no flag
    assert copy_file(str(tmp_path / "missing.txt"), str(tmp_path / "c.txt")) is False


def test_open_file_default_behaves_like_open(tmp_path):
    f = tmp_path / "x.txt"; f.write_text("data")
    with open_file(str(f)) as fh:
        assert fh.read() == "data"


# --- AC-SEM / AC-INJECT: the fallback uses a variant ----------------------

def test_copy_file_falls_back_to_variant(tmp_path):
    real = tmp_path / "real.txt"; real.write_text("payload")
    blocked = str(tmp_path / "blocked.txt")   # does not exist
    dst = tmp_path / "out.txt"
    r = FakeResolver({blocked: str(real)})
    # red: without fallback, the blocked name fails (source missing)
    assert copy_file(blocked, str(dst)) is False
    # green: with fallback, the variant (real) is used
    assert copy_file(blocked, str(dst), try_path_variants=True, resolver=r) is True
    assert dst.read_text() == "payload"


def test_copy_file_flag_without_useful_resolver_returns_false(tmp_path):
    blocked = str(tmp_path / "nope.txt")
    dst = tmp_path / "out.txt"
    assert copy_file(blocked, str(dst), try_path_variants=True, resolver=FakeResolver({})) is False
    assert not dst.exists()


def test_move_file_falls_back_to_variant(tmp_path):
    real = tmp_path / "real.txt"; real.write_text("mv")
    blocked = str(tmp_path / "blocked.txt")
    dst = tmp_path / "moved.txt"
    r = FakeResolver({blocked: str(real)})
    assert move_file(blocked, str(dst)) is False
    assert move_file(blocked, str(dst), try_path_variants=True, resolver=r) is True
    assert dst.read_text() == "mv"
    assert not real.exists()   # the variant was actually moved


def test_open_file_falls_back_to_variant(tmp_path):
    real = tmp_path / "real.txt"; real.write_text("opened")
    blocked = str(tmp_path / "blocked.txt")
    r = FakeResolver({blocked: str(real)})
    # red: without fallback -> FileNotFoundError
    with pytest.raises(FileNotFoundError):
        open_file(blocked)
    # green: with fallback -> opens the variant, returns a real handle
    with open_file(blocked, try_path_variants=True, resolver=r) as fh:
        assert fh.read() == "opened"


def test_open_file_forwards_kwargs_and_returns_handle(tmp_path):
    f = tmp_path / "enc.txt"; f.write_text("café", encoding="utf-8")
    fh = open_file(str(f), "r", encoding="utf-8")
    try:
        assert fh.read() == "café"   # **kwargs (encoding) forwarded; handle returned
    finally:
        fh.close()


def test_open_file_reraises_original_when_all_fail(tmp_path):
    blocked = str(tmp_path / "missing.txt")
    r = FakeResolver({blocked: str(tmp_path / "also-missing.txt")})
    with pytest.raises(FileNotFoundError):
        open_file(blocked, try_path_variants=True, resolver=r)
