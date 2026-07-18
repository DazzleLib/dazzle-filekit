"""AtomicStreamWriter: the streaming sibling of atomic_write_text.

Contributed from dazzlesum, generalized from its MonolithicWriter
(streaming checksum-manifest writer). Pins the atomicity contract:

  - success  -> tmp renamed over the destination via os.replace, no tmp left
  - failure  -> destination untouched (old contents preserved), tmp removed
  - resume_from_existing -> tmp seeded with current contents, opened append
  - fsync_on_flush -> flush also fsyncs (failures swallowed)
"""

import os
from pathlib import Path

import pytest

from dazzle_filekit import AtomicStreamWriter


def test_streaming_write_success(tmp_path):
    dest = tmp_path / "out.txt"
    with AtomicStreamWriter(dest) as w:
        w.write("line 1\n")
        w.write("line 2\n")
        w.flush()
        w.write("line 3\n")
    assert dest.read_text() == "line 1\nline 2\nline 3\n"
    assert not w.tmp_path.exists()


def test_failure_preserves_old_contents(tmp_path):
    dest = tmp_path / "out.txt"
    dest.write_text("original contents\n")
    with pytest.raises(RuntimeError):
        with AtomicStreamWriter(dest) as w:
            w.write("half-written replacement")
            raise RuntimeError("boom")
    assert dest.read_text() == "original contents\n"
    assert not w.tmp_path.exists()


def test_explicit_abort(tmp_path):
    dest = tmp_path / "out.txt"
    dest.write_text("keep me\n")
    w = AtomicStreamWriter(dest).open()
    w.write("discard me")
    w.close(success=False)
    assert dest.read_text() == "keep me\n"
    assert not w.tmp_path.exists()


def test_tmp_is_sibling_during_write(tmp_path):
    """The in-progress file is the .tmp sibling; the destination is not
    created until successful close (fresh-write case)."""
    dest = tmp_path / "out.txt"
    with AtomicStreamWriter(dest) as w:
        w.write("data")
        w.flush()
        assert w.tmp_path == tmp_path / "out.txt.tmp"
        assert w.tmp_path.exists()
        assert not dest.exists()
    assert dest.exists()


def test_resume_from_existing_appends(tmp_path):
    dest = tmp_path / "out.txt"
    dest.write_text("first run\n")
    with AtomicStreamWriter(dest, resume_from_existing=True) as w:
        w.write("second run\n")
    assert dest.read_text() == "first run\nsecond run\n"


def test_resume_without_existing_is_fresh_write(tmp_path):
    dest = tmp_path / "out.txt"
    with AtomicStreamWriter(dest, resume_from_existing=True) as w:
        w.write("only run\n")
    assert dest.read_text() == "only run\n"


def test_creates_parent_directories(tmp_path):
    dest = tmp_path / "deep" / "er" / "out.txt"
    with AtomicStreamWriter(dest) as w:
        w.write("data")
    assert dest.read_text() == "data"


def test_fsync_on_flush_smoke(tmp_path):
    dest = tmp_path / "out.txt"
    with AtomicStreamWriter(dest, fsync_on_flush=True) as w:
        w.write("durable\n")
        w.flush()
    assert dest.read_text() == "durable\n"


def test_close_is_idempotent(tmp_path):
    dest = tmp_path / "out.txt"
    w = AtomicStreamWriter(dest).open()
    w.write("once\n")
    w.close()
    w.close()  # no error, no double-replace
    assert dest.read_text() == "once\n"


def test_write_before_open_raises(tmp_path):
    w = AtomicStreamWriter(tmp_path / "out.txt")
    with pytest.raises(ValueError):
        w.write("nope")
    with pytest.raises(ValueError):
        w.flush()


def test_newline_control(tmp_path):
    r"""newline='' disables translation (the caller owns line endings),
    matching atomic_write_text's parameter contract."""
    dest = tmp_path / "out.txt"
    with AtomicStreamWriter(dest, newline="") as w:
        w.write("a\n")
    assert dest.read_bytes() == b"a\n"
    with AtomicStreamWriter(dest, newline="") as w:
        w.write("a\r\n")
    assert dest.read_bytes() == b"a\r\n"


def test_overwrite_replaces_atomically(tmp_path):
    dest = tmp_path / "out.txt"
    dest.write_text("old")
    with AtomicStreamWriter(dest) as w:
        w.write("new")
    assert dest.read_text() == "new"
    assert not (tmp_path / "out.txt.tmp").exists()
