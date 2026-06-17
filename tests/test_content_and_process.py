"""Parity tests for the restored capabilities in filekit:
process_files (R3), content.replace_in_file / batch_replace_in_files (R4),
and the case-sensitivity helpers (R6) -- the unctools functions gutted in its
0.2.0 split, now homed in dazzle-filekit with the new interfaces.
"""

import pytest

from dazzle_filekit import (
    process_files,
    replace_in_file,
    batch_replace_in_files,
    path_exists_case_sensitive,
    get_case_sensitive_path,
)


# --- R3: process_files ----------------------------------------------------

def test_process_files_applies_callback_recursively(tmp_path):
    (tmp_path / "a.txt").write_text("1")
    (tmp_path / "b.txt").write_text("22")
    sub = tmp_path / "sub"; sub.mkdir()
    (sub / "c.txt").write_text("333")
    results = process_files(str(tmp_path), lambda p: p.read_text(), pattern="*.txt", recursive=True)
    assert len(results) == 3
    assert sorted(len(v) for v in results.values()) == [1, 2, 3]


def test_process_files_non_recursive(tmp_path):
    (tmp_path / "top.txt").write_text("x")
    sub = tmp_path / "sub"; sub.mkdir(); (sub / "deep.txt").write_text("y")
    results = process_files(str(tmp_path), lambda p: True, pattern="*.txt", recursive=False)
    assert list(results) == [str(tmp_path / "top.txt")]


def test_process_files_swallows_per_file_errors_to_none(tmp_path):
    (tmp_path / "ok.txt").write_text("ok")
    (tmp_path / "bad.txt").write_text("bad")

    def cb(p):
        if p.name == "bad.txt":
            raise ValueError("boom")
        return "good"

    results = process_files(str(tmp_path), cb, pattern="*.txt")
    assert results[str(tmp_path / "ok.txt")] == "good"
    assert results[str(tmp_path / "bad.txt")] is None   # swallowed, not raised


def test_process_files_missing_dir_returns_empty(tmp_path):
    assert process_files(str(tmp_path / "nope"), lambda p: 1) == {}


# --- R4: replace_in_file / batch_replace_in_files -------------------------

def test_replace_in_file_modifies_and_returns_true(tmp_path):
    f = tmp_path / "f.txt"; f.write_text("hello world")
    assert replace_in_file(str(f), "world", "filekit") is True
    assert f.read_text() == "hello filekit"


def test_replace_in_file_not_found_returns_false_and_leaves_file(tmp_path):
    f = tmp_path / "f.txt"; f.write_text("hello")
    assert replace_in_file(str(f), "absent", "x") is False
    assert f.read_text() == "hello"


def test_batch_replace_in_files(tmp_path):
    (tmp_path / "a.txt").write_text("foo here")
    (tmp_path / "b.txt").write_text("no match")
    res = batch_replace_in_files(str(tmp_path), "foo", "bar", pattern="*.txt")
    assert res[str(tmp_path / "a.txt")] is True
    assert res[str(tmp_path / "b.txt")] is False
    assert (tmp_path / "a.txt").read_text() == "bar here"


# --- R6: case-sensitivity helpers -----------------------------------------

def test_path_exists_case_sensitive(tmp_path):
    f = tmp_path / "real.txt"; f.write_text("x")
    assert path_exists_case_sensitive(str(f)) is True
    assert path_exists_case_sensitive(str(tmp_path / "missing.txt")) is False


def test_get_case_sensitive_path_existing_and_missing(tmp_path):
    f = tmp_path / "File.txt"; f.write_text("x")
    assert get_case_sensitive_path(str(f)).lower().endswith("file.txt")
    missing = str(tmp_path / "nope.txt")
    assert get_case_sensitive_path(missing) == missing   # unchanged when absent
