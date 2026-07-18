"""Native checksum-tool backend (contributed from dazzlesum).

Covers:
  - detect_native_hash_tool: platform tool candidates, per-process cache
  - calculate_file_hash_native: per-tool output parsing (subprocess
    monkeypatched -- fsum, certutil, sha256sum, shasum formats), the
    None-on-failure contract, and real-tool equivalence with the
    pure-Python calculate_file_hash where a tool actually exists.
"""

import hashlib
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from dazzle_filekit import (
    calculate_file_hash,
    calculate_file_hash_native,
    detect_native_hash_tool,
)
from dazzle_filekit import verification as verification_mod

HELLO = b"Hello, native tools!\n"
HELLO_SHA256 = hashlib.sha256(HELLO).hexdigest()
HELLO_MD5 = hashlib.md5(HELLO).hexdigest()


@pytest.fixture()
def hello_file(tmp_path):
    p = tmp_path / "hello.txt"
    p.write_bytes(HELLO)
    return p


@pytest.fixture(autouse=True)
def clear_tool_cache():
    verification_mod._NATIVE_TOOL_CACHE.clear()
    yield
    verification_mod._NATIVE_TOOL_CACHE.clear()


def _fake_run(stdout, returncode=0, stderr=""):
    """Return a subprocess.run replacement producing a fixed result."""
    def run(cmd, **kwargs):
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)
    return run


# ---------------------------------------------------------------------------
# Parser correctness (subprocess monkeypatched -- no tools required)
# ---------------------------------------------------------------------------


def test_parse_hashsum_output(hello_file, monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        _fake_run(f"{HELLO_SHA256}  {hello_file}\n"))
    digest = calculate_file_hash_native(hello_file, "sha256", tool="sha256sum")
    assert digest == HELLO_SHA256


def test_parse_shasum_output(hello_file, monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        _fake_run(f"{HELLO_SHA256}  {hello_file}\n"))
    digest = calculate_file_hash_native(hello_file, "sha256", tool="shasum")
    assert digest == HELLO_SHA256


def test_parse_fsum_output(hello_file, monkeypatch):
    out = (
        "SlavaSoft Optimizing Checksum Utility - fsum 2.52.00337\n"
        "; Generated on 07/17/26\n"
        f"{HELLO_MD5} *hello.txt\n"
    )
    monkeypatch.setattr(subprocess, "run", _fake_run(out))
    digest = calculate_file_hash_native(hello_file, "md5", tool="fsum")
    assert digest == HELLO_MD5


def test_parse_certutil_output(hello_file, monkeypatch):
    out = (
        f"SHA256 hash of {hello_file}:\n"
        f"{HELLO_SHA256}\n"
        "CertUtil: -hashfile command completed successfully.\n"
    )
    monkeypatch.setattr(subprocess, "run", _fake_run(out))
    digest = calculate_file_hash_native(hello_file, "sha256", tool="certutil")
    assert digest == HELLO_SHA256


def test_uppercase_digest_is_lowered(hello_file, monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        _fake_run(f"{HELLO_SHA256.upper()}  {hello_file}\n"))
    digest = calculate_file_hash_native(hello_file, "sha256", tool="sha256sum")
    assert digest == HELLO_SHA256


# ---------------------------------------------------------------------------
# Failure contract: None, never an exception
# ---------------------------------------------------------------------------


def test_tool_failure_returns_none(hello_file, monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        _fake_run("", returncode=1, stderr="boom"))
    assert calculate_file_hash_native(hello_file, "sha256", tool="sha256sum") is None


def test_unparseable_output_returns_none(hello_file, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run("garbage output\n"))
    assert calculate_file_hash_native(hello_file, "sha256", tool="certutil") is None


def test_unsupported_tool_returns_none(hello_file):
    assert calculate_file_hash_native(hello_file, "md5", tool="md5") is None


def test_no_tool_detected_returns_none(hello_file, monkeypatch):
    monkeypatch.setattr(verification_mod, "_native_tool_available",
                        lambda tool: False)
    assert calculate_file_hash_native(hello_file, "sha256") is None


# ---------------------------------------------------------------------------
# Detection and cache
# ---------------------------------------------------------------------------


def test_detection_caches_per_algorithm(monkeypatch):
    calls = []

    def fake_available(tool):
        calls.append(tool)
        return tool in ("sha256sum", "certutil")

    monkeypatch.setattr(verification_mod, "_native_tool_available", fake_available)
    first = detect_native_hash_tool("sha256")
    probes_after_first = len(calls)
    second = detect_native_hash_tool("sha256")

    assert first == second
    assert first in ("sha256sum", "certutil")
    assert len(calls) == probes_after_first  # cache hit: no re-probe


def test_detection_none_when_no_tools(monkeypatch):
    monkeypatch.setattr(verification_mod, "_native_tool_available",
                        lambda tool: False)
    assert detect_native_hash_tool("sha256") is None
    # The negative result is cached too
    assert verification_mod._NATIVE_TOOL_CACHE["sha256"] is None


def test_unknown_algorithm_has_no_candidates(monkeypatch):
    if sys.platform == "win32":
        pytest.skip("Windows candidates are algorithm-independent")
    monkeypatch.setattr(verification_mod, "_native_tool_available",
                        lambda tool: True)
    assert detect_native_hash_tool("blake2b") is None


# ---------------------------------------------------------------------------
# Real-tool equivalence (skips where no tool exists)
# ---------------------------------------------------------------------------


def test_native_matches_python_with_real_tool(hello_file):
    tool = None
    if sys.platform == "win32":
        if shutil.which("certutil"):
            tool = "certutil"
    elif shutil.which("sha256sum"):
        tool = "sha256sum"
    elif shutil.which("shasum"):
        tool = "shasum"
    if tool is None:
        pytest.skip("no native sha256 tool on this system")

    native = calculate_file_hash_native(hello_file, "sha256", tool=tool)
    python = calculate_file_hash(hello_file, ["sha256"], preserve_case=False)["SHA256"]
    assert native == python.lower() == HELLO_SHA256
