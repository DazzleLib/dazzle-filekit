"""Unit tests for the path-variant fallback machinery (dazzle_filekit._fallback).

Covers the Option-D acceptance checks at the helper level (see the 2026-06-14
resolver-edge DWP, hard-dep refinement):
  AC-SEM       operation-retry succeeds under a variant when the original fails
  AC-INJECT    an arbitrary hand-written resolver drives the retry (swappability)
  default      unctools (a hard dep) is always available as the default resolver
"""

import pytest

from dazzle_lib import PathVariantResolver
from dazzle_filekit import _fallback


# A hand-written resolver: no dazzle_lib import, no subclassing -- structural.
class FakeResolver:
    """Maps a 'blocked' UNC-ish name to a 'working' mapped-drive-ish name."""

    def __init__(self, mapping):
        self._mapping = mapping  # {blocked_path: working_path}

    def variants(self, path):
        out = [path]
        if path in self._mapping:
            out.append(self._mapping[path])
        return out


def test_fakeresolver_satisfies_protocol():
    assert isinstance(FakeResolver({}), PathVariantResolver)


# --- variants_of: ordering + dedup ----------------------------------------

def test_variants_of_dedups_and_orders_original_first():
    r = FakeResolver({"\\\\srv\\sh\\f": "Z:\\f"})
    assert _fallback.variants_of("\\\\srv\\sh\\f", r) == ["\\\\srv\\sh\\f", "Z:\\f"]
    # original with no known alt -> just itself
    assert _fallback.variants_of("Z:\\f", r) == ["Z:\\f"]


def test_variants_of_falls_back_to_default_resolver():
    # no explicit resolver -> uses the unctools-backed default; a plain local
    # path resolves to at least itself, never crashes.
    out = _fallback.variants_of("C:\\x\\f.txt")
    assert out[0] == "C:\\x\\f.txt"


# --- AC-SEM / AC-INJECT: retry under a variant succeeds --------------------

def test_retry_single_uses_variant_on_permission_error():
    blocked, working = "\\\\srv\\sh\\f", "Z:\\f"
    r = FakeResolver({blocked: working})
    calls = []

    def op(path):
        calls.append(path)
        if path == blocked:
            raise PermissionError("security zone blocks the UNC name")
        return f"opened {path}"

    # red: the bare op fails on the blocked name
    with pytest.raises(PermissionError):
        op(blocked)
    calls.clear()

    # green: the fallback retries under the working variant
    result = _fallback.retry_single(op, blocked, feature="open_file", resolver=r)
    assert result == "opened Z:\\f"
    assert calls == [blocked, working]  # tried original first, then the variant


def test_retry_single_reraises_first_error_when_all_fail():
    r = FakeResolver({"a": "b"})

    def op(path):
        raise PermissionError(f"no good: {path}")

    with pytest.raises(PermissionError) as ei:
        _fallback.retry_single(op, "a", feature="open_file", resolver=r)
    assert "no good: a" in str(ei.value)  # ORIGINAL error, not the variant's


# --- AC-SEM (copy): both endpoints varied ---------------------------------

def test_retry_pair_tries_src_and_dst_combos():
    # only the (mapped-src, mapped-dst) pair works
    r = FakeResolver({"\\\\s\\a": "X:\\a", "\\\\s\\b": "Y:\\b"})
    good = ("X:\\a", "Y:\\b")

    def op(s, d):
        if (s, d) == good:
            return "copied"
        raise PermissionError(f"blocked {s}->{d}")

    result = _fallback.retry_pair(op, "\\\\s\\a", "\\\\s\\b", feature="copy_file", resolver=r)
    assert result == "copied"


def test_retry_pair_original_pair_first():
    r = FakeResolver({"\\\\s\\a": "X:\\a"})
    seen = []

    def op(s, d):
        seen.append((s, d))
        return "ok"  # original works immediately

    assert _fallback.retry_pair(op, "\\\\s\\a", "D:\\b", feature="copy_file", resolver=r) == "ok"
    assert seen == [("\\\\s\\a", "D:\\b")]  # never needed a variant


# --- default resolver: unctools is a hard dep, always present --------------

def test_default_resolver_is_always_present_and_conforming():
    r = _fallback.default_resolver()
    assert isinstance(r, PathVariantResolver)
    assert "C:\\x" in r.variants("C:\\x")  # at least round-trips to itself
