"""Fallback-aware operation retry across path-name variants.

This is the L1 (filekit) side of the STACK-MAP ``path_variant_resolver`` seam
(decision D7). A filekit file operation can optionally retry under alternative
names for a path -- e.g. a Windows UNC path (``\\\\server\\share\\f``) and its
mapped-drive equivalent (``Z:\\f``) name the same file, yet a security zone can
block opening/copying via one name while the other works, even though both
*exist*.

Who knows what a path's other names are is supplied by a
:class:`dazzle_lib.PathVariantResolver`. filekit's default resolver is backed by
unctools (a **hard** dependency, L1->L0): filekit is a cross-platform file-ops
toolkit and already requires pywin32 on Windows, so an extra small pure-Python
dependency is cheap and removes the awkwardness of optional discovery. The
Protocol is retained for what it actually buys: tests inject a fake resolver
(no real UNC/network needed), and a different identity source can be swapped in
via the ``resolver=`` parameter. The two layers meet at the resolver contract,
not in a shared object graph.

Design invariants:

- The default behaviour of every operation is unchanged: the retry path is only
  taken when a caller explicitly opts in (``try_path_variants=True``).
- A resolver is always available (unctools is a hard dep), so an opted-in
  fallback is never silently dropped -- it simply always runs.
- The retry runners re-raise the ORIGINAL error if every variant fails.
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional, TypeVar

from dazzle_lib import PathVariantResolver
from unctools import convert_to_local, convert_to_unc, is_unc_path

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Retry on these. PermissionError (the Windows security-zone case) is the
# motivating one; FileNotFoundError (a name not currently mounted) is the other.
# Both are OSError subclasses; listing them documents intent.
RETRYABLE = (PermissionError, FileNotFoundError, OSError)


class UnctoolsResolver:
    """filekit's default :class:`dazzle_lib.PathVariantResolver`, backed by
    unctools. Proposes a path's UNC<->mapped-drive alternate name using the
    system's live network mappings."""

    def variants(self, path: str) -> List[str]:
        out = [path]
        try:
            alt = str(convert_to_local(path)) if is_unc_path(path) else str(convert_to_unc(path))
            if alt and alt != path:
                out.append(alt)
        except Exception as e:  # a resolver must never raise into the operation
            logger.debug("unctools variant resolution failed for %r: %s", path, e)
        return out


# Module singleton -- stateless, so one instance is fine.
_DEFAULT_RESOLVER = UnctoolsResolver()


def default_resolver() -> PathVariantResolver:
    """Return filekit's default (unctools-backed) resolver. Always available;
    callers may still inject their own via ``resolver=``."""
    return _DEFAULT_RESOLVER


def variants_of(path: str, resolver: Optional[PathVariantResolver] = None) -> List[str]:
    """Ordered, de-duplicated candidate names for ``path`` (original first)."""
    r = resolver if resolver is not None else _DEFAULT_RESOLVER
    ordered: List[str] = []
    for cand in (path, *r.variants(path)):
        if cand and cand not in ordered:
            ordered.append(cand)
    return ordered


# ---------------------------------------------------------------------------
# Retry runners. They re-raise the ORIGINAL error if every variant fails.
# ---------------------------------------------------------------------------

def retry_single(op: Callable[[str], T], path: str, *, feature: str = "operation",
                 resolver: Optional[PathVariantResolver] = None,
                 exc=RETRYABLE) -> T:
    """Run ``op(path)``; on a retryable error, retry under each variant of
    ``path``; re-raise the first error if all attempts fail."""
    first_error: Optional[BaseException] = None
    for cand in variants_of(path, resolver):
        try:
            return op(cand)
        except exc as e:
            if first_error is None:
                first_error = e
            logger.debug("%s failed under %r: %s", feature, cand, e)
    assert first_error is not None  # variants_of always yields >= 1 candidate
    raise first_error


def retry_pair(op: Callable[[str, str], T], src: str, dst: str, *, feature: str = "operation",
               resolver: Optional[PathVariantResolver] = None,
               exc=RETRYABLE) -> T:
    """Run ``op(src, dst)``; on a retryable error, retry across the bounded
    cartesian product of src-variants x dst-variants (original pair first);
    re-raise the first error if all combinations fail.

    Mirrors the legacy ``unctools.safe_copy`` semantic: either endpoint may be
    the blocked name, so both are varied.
    """
    src_cands = variants_of(src, resolver)
    dst_cands = variants_of(dst, resolver)
    pairs = [(src, dst)] + [(s, d) for s in src_cands for d in dst_cands]
    tried = set()
    first_error: Optional[BaseException] = None
    for s, d in pairs:
        if (s, d) in tried:
            continue
        tried.add((s, d))
        try:
            return op(s, d)
        except exc as e:
            if first_error is None:
                first_error = e
            logger.debug("%s failed for %r -> %r: %s", feature, s, d, e)
    assert first_error is not None
    raise first_error


def retry_pair_bool(op_bool: Callable[[str, str], bool], src: str, dst: str, *,
                    feature: str = "operation",
                    resolver: Optional[PathVariantResolver] = None,
                    exc=RETRYABLE) -> bool:
    """Like :func:`retry_pair`, but for a **bool**-returning op (True = success).

    Tries the original ``(src, dst)`` pair, then the bounded product of
    src-variants x dst-variants, returning True on the first success. A falsy
    return OR a retryable exception means "try the next pair". Returns False if
    every pair fails -- matching the bool contract of ``copy_file``/``move_file``
    (which swallow errors to False rather than raising).
    """
    src_cands = variants_of(src, resolver)
    dst_cands = variants_of(dst, resolver)
    pairs = [(src, dst)] + [(s, d) for s in src_cands for d in dst_cands]
    tried = set()
    for s, d in pairs:
        if (s, d) in tried:
            continue
        tried.add((s, d))
        try:
            if op_bool(s, d):
                return True
        except exc as e:
            logger.debug("%s failed for %r -> %r: %s", feature, s, d, e)
    return False
