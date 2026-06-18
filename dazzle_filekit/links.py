"""Intrinsic link primitives (L1).

This module answers the *intrinsic* question about a single filesystem object:
"what is this link, by looking only at it?" -- its kind, its raw and resolved
target, whether it is broken, and whether it is a direct self-reference. It also
creates the three link kinds (symlink lives in :mod:`operations`; junctions and
hardlinks live here).

It deliberately does NOT answer *relational* questions ("is this link's target
inside some destination root?", "what should we do with it during a move?").
Those depend on a second path and a policy -- they are L3 (preservelib) concerns.
See the dazzle-filekit #15 completion design.

Provenance: the detection/creation logic is ported from
``preserve/preservelib/links.py`` (``detect_link_type``, ``get_link_target``,
``analyze_link``, ``_create_junction``, ``_create_hard_link``), with three
changes that improve coverage/correctness without losing a code-path:

* junction *detection* uses filekit's :func:`utils.validation.is_junction`
  (DeviceIoControl reparse-tag) instead of preservelib's attribute-only check,
  which misclassified directory symlinks as junctions;
* junction *target reading* and *creation* use the DeviceIoControl reparse
  buffer and PowerShell ``New-Item`` respectively, replacing preservelib's
  banned ``cmd /c dir /al`` and ``cmd /c mklink /j`` shell-outs;
* a hardlink (detected via ``st_nlink > 1``) is reported as a valid link with
  no traversable target -- it is NOT marked ``is_broken`` (preservelib's
  ``analyze_link`` marked it broken because ``get_link_target`` returns None).
"""
from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Union

from .utils.validation import is_junction, read_junction_target

logger = logging.getLogger(__name__)

# Link kinds reported by :func:`detect_link_type` / :class:`LinkInfo`.
LINK_SYMLINK = "symlink"
LINK_JUNCTION = "junction"
LINK_HARDLINK = "hardlink"


@dataclass
class LinkInfo:
    """Intrinsic facts about a single link (no destination relationship).

    Fields:
        link_path: the link itself.
        kind: ``'symlink'`` | ``'junction'`` | ``'hardlink'`` | ``None`` (not a link).
        raw_target: target as stored in the link (readlink result for symlinks,
            the reparse PrintName for junctions). ``None`` for hardlinks (which
            have no single target) and for non-links.
        resolved_target: absolute target after resolution (``None`` when there is
            no resolvable target).
        is_broken: a symlink/junction whose target cannot be read or does not
            exist. A hardlink is never broken.
        is_circular: direct self-reference only -- the resolved target IS the
            link's own path. Chain-cycle detection requires walking the chain and
            is a traversal (L3 / dazzletreelib) concern, intentionally not done here.
        metadata: free-form extra context for callers.
    """

    link_path: Path
    kind: Optional[str] = None
    raw_target: Optional[str] = None
    resolved_target: Optional[Path] = None
    is_broken: bool = False
    is_circular: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a plain dict for JSON serialization / reporting."""
        return {
            "link_path": str(self.link_path),
            "kind": self.kind,
            "raw_target": self.raw_target,
            "resolved_target": str(self.resolved_target) if self.resolved_target else None,
            "is_broken": self.is_broken,
            "is_circular": self.is_circular,
        }


def detect_link_type(path: Union[str, Path]) -> Optional[str]:
    """Detect what kind of link ``path`` is, or ``None`` if it is not a link.

    Returns ``'symlink'``, ``'junction'`` (Windows), or ``'hardlink'`` (a file
    whose ``st_nlink > 1``). Hard links are otherwise indistinguishable from
    regular files, so a single-name file is reported as ``None``.
    """
    p = Path(path)

    if not p.exists() and not p.is_symlink():
        return None

    if p.is_symlink():
        return LINK_SYMLINK

    if os.name == "nt" and is_junction(p):
        return LINK_JUNCTION

    try:
        if p.is_file():
            stat_info = p.stat()
            if getattr(stat_info, "st_nlink", 1) > 1:
                return LINK_HARDLINK
    except OSError:
        pass

    return None


def _strip_extended_prefix(target: str) -> str:
    """Strip the Windows ``\\\\?\\`` extended-length prefix that ``os.readlink``
    returns for absolute symlink targets (``\\\\?\\UNC\\`` -> ``\\\\``)."""
    if target.startswith("\\\\?\\UNC\\"):
        return "\\\\" + target[len("\\\\?\\UNC\\"):]
    if target.startswith("\\\\?\\"):
        return target[len("\\\\?\\"):]
    return target


def read_link_target(path: Union[str, Path]) -> Optional[str]:
    """Return the raw target of a symlink or junction, or ``None``.

    Symlinks use :func:`os.readlink`; junctions read the reparse buffer via
    :func:`utils.validation.read_junction_target`. Hardlinks and non-links
    return ``None`` (a hardlink has no distinct target). On Windows the
    ``\\\\?\\`` extended-length prefix is stripped so the target is canonical.
    """
    p = Path(path)
    try:
        if p.is_symlink():
            target = str(os.readlink(p))
            return _strip_extended_prefix(target) if os.name == "nt" else target
        if os.name == "nt" and is_junction(p):
            return read_junction_target(p)
    except OSError as e:
        logger.debug(f"read_link_target({p}) failed: {e}")
    return None


def analyze_link(link_path: Union[str, Path]) -> LinkInfo:
    """Analyze a single link intrinsically (no destination relationship).

    See :class:`LinkInfo` for the meaning of each field. This never takes a
    destination path -- relational analysis belongs at L3.
    """
    p = Path(link_path)
    info = LinkInfo(link_path=p)

    info.kind = detect_link_type(p)
    if info.kind is None:
        return info  # not a link

    if info.kind == LINK_HARDLINK:
        # A hardlink is a valid second name for the file; it has no traversable
        # target and is never "broken".
        return info

    info.raw_target = read_link_target(p)
    if info.raw_target is None:
        # A symlink/junction whose target cannot be read is genuinely broken.
        info.is_broken = True
        return info

    rt = Path(info.raw_target)
    # The target's absolute path WITHOUT following the link itself (so a
    # self-loop doesn't trip ELOOP). Relative targets are joined to the
    # link's parent.
    if rt.is_absolute():
        target_unfollowed = os.path.abspath(str(rt))
    else:
        target_unfollowed = os.path.abspath(str(p.parent / rt))

    # Intrinsic self-reference: the link points directly at its own path.
    # Computed by path comparison (no resolution), so it is robust against
    # self-loops. Chain cycles (A -> B -> A) require walking the chain and are
    # a traversal (L3 / dazzletreelib) concern, intentionally not detected here.
    if os.path.normcase(target_unfollowed) == os.path.normcase(os.path.abspath(str(p))):
        info.is_circular = True

    try:
        resolved = Path(target_unfollowed).resolve()
        info.resolved_target = resolved
        if not resolved.exists():
            info.is_broken = True
    except (OSError, RuntimeError, ValueError) as e:
        # RuntimeError: Path.resolve() raises it on a symlink loop (Py3.12+);
        # such a target cannot resolve to a real file -> broken.
        logger.debug(f"Error resolving link target {info.raw_target} for {p}: {e}")
        info.is_broken = True

    return info


def _remove_existing(link: Path) -> bool:
    """Remove an existing link/empty target at ``link`` so a new one can be
    created. Returns True on success."""
    try:
        if link.is_symlink() or link.is_file():
            link.unlink()
        elif link.is_dir():
            # A junction or directory symlink is removed with rmdir without
            # touching its target; a real (empty) directory is removed too.
            os.rmdir(link)
        return True
    except OSError as e:
        logger.error(f"Failed to remove existing path {link}: {e}")
        return False


def create_junction(
    target: Union[str, Path],
    link: Union[str, Path],
    force: bool = False,
) -> bool:
    """Create a Windows NTFS junction at ``link`` pointing to ``target``.

    Uses PowerShell ``New-Item -ItemType Junction`` (per the house rule that
    junctions/symlinks are created via PowerShell, never ``cmd /c mklink``).
    Junctions are directory-only and Windows-only.

    Returns True on success, False otherwise.
    """
    target_path = Path(target)
    link_path = Path(link)

    if os.name != "nt":
        logger.error("Junctions are only supported on Windows")
        return False

    if link_path.exists() or link_path.is_symlink():
        if not force:
            logger.warning(f"Link path already exists: {link_path}")
            return False
        if not _remove_existing(link_path):
            return False

    try:
        link_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"Failed to create parent directories for {link_path}: {e}")
        return False

    # Single-quote the paths for PowerShell, doubling any embedded single quote.
    link_ps = str(link_path).replace("'", "''")
    target_ps = str(target_path).replace("'", "''")
    ps = (
        "$ErrorActionPreference='Stop'; "
        f"New-Item -ItemType Junction -Path '{link_ps}' -Target '{target_ps}' | Out-Null"
    )

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0:
            logger.debug(f"Created junction: {link_path} -> {target_path}")
            return True
        logger.warning(f"New-Item junction failed: {result.stderr.strip()}")
        return False
    except Exception as e:  # noqa: BLE001 - subprocess/env failures are non-fatal
        logger.warning(f"PowerShell junction creation failed: {e}")
        return False


def create_hardlink(
    target: Union[str, Path],
    link: Union[str, Path],
    force: bool = False,
) -> bool:
    """Create a hard link at ``link`` pointing to the file ``target``.

    Hard links are file-only and cannot cross filesystem boundaries. Returns
    True on success, False otherwise.
    """
    target_path = Path(target)
    link_path = Path(link)

    if not target_path.is_file():
        logger.error(f"Hard links can only be created for files, not directories: {target_path}")
        return False

    if link_path.exists() or link_path.is_symlink():
        if not force:
            logger.warning(f"Link path already exists: {link_path}")
            return False
        if not _remove_existing(link_path):
            return False

    try:
        link_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"Failed to create parent directories for {link_path}: {e}")
        return False

    try:
        os.link(str(target_path), str(link_path))
        logger.debug(f"Created hard link: {link_path} -> {target_path}")
        return True
    except OSError as e:
        if getattr(e, "errno", None) == 18:  # EXDEV - cross-device link
            logger.error(f"Hard links cannot cross filesystem boundaries: {link_path}")
        else:
            logger.error(f"Failed to create hard link {link_path}: {e}")
        return False
