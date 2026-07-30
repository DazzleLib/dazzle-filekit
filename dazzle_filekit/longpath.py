"""Long-path shims (L2).

This module answers one question: *"this path is too long for a MAX_PATH-bound
consumer -- what shorter path names the same bytes?"*

It exists because :func:`utils.validation.is_valid_path` already **detects** the
condition (it returns ``False`` for paths over 260 that lack a ``\\\\?\\`` prefix)
but nothing in filekit offered a remedy. This is that remedy.

Why a shim rather than the extended-length prefix
-------------------------------------------------
``\\\\?\\`` lifts the limit at the *Win32 API* layer, and that is enough for a
well-behaved caller. It is **not** enough for an application that builds the
correct extended path and then copies it into a fixed ``MAX_PATH`` buffer --
observed in the wild in more than one PDF reader, which truncates the tail and
then reports the file as missing. Nothing outside such an application can fix
its internal buffer. What *can* be changed is the length of the string handed
to it, and a directory junction at a short location does exactly that: same
bytes, shorter name, no cooperation required from the consumer.

Scope
-----
Windows-only in effect. ``PATH_MAX`` is 4096 on Linux and 1024 on macOS/BSD, so
the condition this module treats does not arise there; :func:`needs_shim`
returns ``False`` on POSIX and every other entry point degrades to a no-op.
Note that ``NAME_MAX`` is 255 on *every* platform -- a single path *component*
longer than that cannot be rescued by any amount of linking, because the
offending name must itself appear in the shimmed path. :func:`plan_shim`
reports that case rather than pretending to solve it.

Safety
------
Shim removal never recurses. :func:`remove_shim` re-verifies that its target is
a junction *immediately before* deleting (closing the check-then-act window)
and uses ``os.rmdir``, which removes the reparse point only. This matters
because every naive test misidentifies a junction: ``os.path.islink()`` is
``False``, ``os.path.isdir()`` is ``True``, and ``DirEntry.is_symlink()`` is
``False`` -- a junction presents as an ordinary directory. Deleting one
recursively through a careless code path would delete the target's contents.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Union

from .links import create_junction, read_link_target
from .utils.validation import is_junction

logger = logging.getLogger(__name__)

#: The Windows legacy path limit, inclusive of the terminating NUL.
MAX_PATH = 260

#: Longest path a MAX_PATH-bound consumer can actually hold (260 minus the NUL).
USABLE_PATH = 259

#: Default trigger length. Deliberately below :data:`USABLE_PATH`: some handlers
#: append to the path they are given (a ``.tmp`` suffix, a backup name), so a
#: path that merely *fits* can still overflow once the consumer touches it.
DEFAULT_THRESHOLD = 240

#: Longest single filename permitted by NTFS and by POSIX ``NAME_MAX`` alike.
NAME_MAX = 255

#: Directory name used for shim roots. Short by design -- every character here
#: is one taken away from the filename it has to accommodate.
SHIM_DIR_NAME = ".dzs"

#: Starting length of the generated per-anchor id, extended on collision.
_ID_LEN = 4

_EXTENDED_PREFIXES = ("\\\\?\\", "\\\\.\\")


def _is_windows() -> bool:
    return os.name == "nt"


def needs_shim(path: Union[str, Path],
               threshold: int = DEFAULT_THRESHOLD) -> bool:
    """Return ``True`` when *path* is long enough to break a MAX_PATH consumer.

    Returns ``False`` on non-Windows platforms, and ``False`` for a path that
    already carries an extended-length prefix (such a path has opted out of the
    limit and rewriting it would be pointless).
    """
    if not _is_windows():
        return False
    text = str(path)
    if text.startswith(_EXTENDED_PREFIXES):
        return False
    return len(text) > threshold


def candidate_roots(target: Optional[Union[str, Path]] = None) -> List[Path]:
    """Ordered shim-root candidates, shortest first.

    The root's own length is subtracted from the budget available to the
    filename, so this order is not cosmetic. A 49-character root
    (``%LOCALAPPDATA%\\dazzlecmd\\longpath``) leaves a 244-character filename
    needing 294 characters and still broken; a 7-character root does not.

    ``%USERPROFILE%`` is included because it is the one location guaranteed
    writable, but it is deliberately ranked below the drive roots: its length
    varies with the username, so the same code serves every file on one machine
    and silently drops the longest ones on another.
    """
    roots: List[Path] = []

    if target is not None:
        drive = os.path.splitdrive(os.path.abspath(str(target)))[0]
        if drive:
            roots.append(Path(drive + os.sep) / SHIM_DIR_NAME)

    # A present-but-empty SystemDrive would yield a drive-*relative* ``\.dzs``,
    # which resolves against whatever drive happens to be current at runtime --
    # a root that moves under the caller. Guarding only falsy values is not
    # enough: a truthy-but-malformed value ("C" without its colon, or pure
    # whitespace) is equally degenerate. Validate the result is genuinely
    # absolute and fall back to C: when it is not.
    system_drive = (os.environ.get("SystemDrive") or "").strip()
    system_root = Path(system_drive + os.sep) if system_drive else None
    if system_root is None or not system_root.is_absolute():
        system_root = Path("C:" + os.sep)
    roots.append(system_root / SHIM_DIR_NAME)

    for env in ("USERPROFILE", "HOME", "TEMP", "TMP"):
        value = os.environ.get(env)
        if value:
            roots.append(Path(value) / SHIM_DIR_NAME)

    seen, ordered = set(), []
    for r in roots:
        key = str(r).casefold()
        if key not in seen:
            seen.add(key)
            ordered.append(r)
    return ordered


def _probe_writable(root: Path) -> bool:
    """Can we create *root* and a directory inside it? Cleans up after itself.

    A child directory is probed, not just the root: the shim itself is created
    as a child, so root-writability alone would not prove what we need.
    """
    created_root = False
    probe = root / "_w"
    try:
        if not root.exists():
            root.mkdir(parents=True)
            created_root = True
        probe.mkdir(exist_ok=True)
        return True
    except OSError:
        return False
    finally:
        try:
            if probe.is_dir() and not is_junction(probe):
                os.rmdir(probe)
            if created_root and root.is_dir() and not any(root.iterdir()):
                os.rmdir(root)
        except OSError:
            pass


def resolve_shim_root(target: Optional[Union[str, Path]] = None,
                      candidates: Optional[Sequence[Path]] = None,
                      probe: bool = True) -> Optional[Path]:
    """Return the shortest writable shim root, or ``None`` if none is usable.

    With ``probe=False`` the first candidate is returned unchecked, which is
    what tests want when they are exercising the ordering rather than the
    filesystem.
    """
    if not _is_windows():
        return None
    for root in (candidates if candidates is not None else candidate_roots(target)):
        if not probe or _probe_writable(Path(root)):
            return Path(root)
    return None


def budget_for(root: Union[str, Path], id_len: int = _ID_LEN) -> int:
    """Longest filename a shim under *root* can serve.

    ``<root>\\<id>\\<filename>`` must fit in :data:`USABLE_PATH`.
    """
    return USABLE_PATH - (len(str(root)) + 1 + id_len + 1)


def _anchor_id(anchor: Path, length: int = _ID_LEN) -> str:
    """Stable short id for an anchor directory, so repeat opens reuse one shim.

    Case-folded because Windows paths are case-insensitive: two spellings of
    the same directory must not mint two junctions.
    """
    digest = hashlib.sha256(str(anchor).casefold().encode("utf-8")).hexdigest()
    return digest[:length]


@dataclass
class ShimPlan:
    """What (if anything) must exist for *original* to be openable."""

    original: Path
    needed: bool
    anchor: Optional[Path] = None       # directory to be junctioned
    link: Optional[Path] = None         # where the junction goes
    shimmed: Optional[Path] = None      # rewritten path to hand to the consumer
    reason: str = ""
    warnings: List[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """True when this plan yields a path a MAX_PATH consumer can open."""
        return self.shimmed is not None

    def resolved(self) -> Path:
        """The path to hand onward -- shimmed when possible, else the original.

        Never raises. A consumer that cannot be helped is still given its
        original path, so the caller degrades to today's behaviour rather than
        failing outright.
        """
        return self.shimmed if self.shimmed is not None else self.original


def plan_shim(path: Union[str, Path],
              root: Optional[Union[str, Path]] = None,
              threshold: int = DEFAULT_THRESHOLD,
              id_len: int = _ID_LEN) -> ShimPlan:
    """Decide how to shorten *path*, without touching the filesystem.

    Chooses the **shallowest** ancestor directory whose junction still brings
    the result under :data:`USABLE_PATH`. Shallowest rather than deepest so one
    shim covers as much of the tree as possible and repeat opens reuse it;
    where the filename is long enough that only its immediate parent fits, that
    is what gets chosen.
    """
    original = Path(path)

    if not needs_shim(original, threshold):
        return ShimPlan(original=original, needed=False, reason="under threshold")

    name = original.name
    if len(name) > NAME_MAX:
        return ShimPlan(
            original=original, needed=True,
            reason="filename exceeds NAME_MAX (%d > %d) -- no link can shorten "
                   "a single component" % (len(name), NAME_MAX),
        )

    if root is None:
        root = resolve_shim_root(original)
        if root is None:
            return ShimPlan(original=original, needed=True,
                            reason="no writable shim root available")
    root = Path(root)

    parent = original.parent
    ancestors = [parent] + list(parent.parents)   # deepest first
    ancestors.reverse()                            # shallowest first

    warnings: List[str] = []
    for anchor in ancestors:
        try:
            rel = original.relative_to(anchor)
        except ValueError:                         # pragma: no cover - defensive
            continue
        link = root / _anchor_id(anchor, id_len)
        shimmed = link / rel
        if len(str(shimmed)) <= USABLE_PATH:
            return ShimPlan(original=original, needed=True, anchor=anchor,
                            link=link, shimmed=shimmed,
                            reason="anchored at %s" % anchor,
                            warnings=warnings)

    return ShimPlan(
        original=original, needed=True,
        reason="no anchor fits: shim root %r is %d chars, leaving %d for a "
               "%d-char filename" % (str(root), len(str(root)),
                                     budget_for(root, id_len), len(name)),
        warnings=warnings,
    )


def _same_dir(a: Union[str, Path, None], b: Union[str, Path, None]) -> bool:
    """Do two path strings name the same directory?

    Windows-aware: case-insensitive, tolerant of trailing separators, and of
    the ``\\\\?\\`` / ``\\\\?\\UNC\\`` forms the kernel may hand back from a
    reparse buffer even when the link was created from a plain path.
    """
    if a is None or b is None:
        return False

    def norm(p: Union[str, Path]) -> str:
        s = str(p)
        for prefix in _EXTENDED_PREFIXES:
            if s.startswith(prefix):
                s = s[len(prefix):]
                if s.upper().startswith("UNC\\"):
                    s = "\\\\" + s[4:]
                break
        s = os.path.normcase(os.path.normpath(s))
        # Strip a trailing separator, but never the one that distinguishes a
        # drive ROOT from a drive-RELATIVE path: ``C:\`` and ``C:`` name
        # different things to Windows (``Path("C:") == Path("C:\\")`` is
        # False), and a blanket rstrip collapses them onto each other.
        drive, rest = os.path.splitdrive(s)
        if rest.strip("\\/"):
            rest = rest.rstrip("\\/")
        return drive + rest

    return norm(a) == norm(b)


def create_shim(plan: ShimPlan, max_id_len: int = 16) -> bool:
    """Materialise *plan*'s junction, reusing an existing one for the same anchor.

    **Anchor ids collide.** The id is a truncated hash, so two unrelated
    directories can map to the same link name -- at the 4-character default
    that is an even chance somewhere around three hundred distinct anchors, not
    a remote possibility on a large library. An earlier version treated *any*
    junction at the expected link as proof of a previous mint for this anchor
    and returned success; on a collision the caller then read a **different
    directory's** file, silently and with no error. Whether an existing
    junction points at *our* anchor is therefore verified, not assumed, and a
    collision is resolved by lengthening the id until a matching or free slot
    is found.

    On success the plan's ``link`` and ``shimmed`` are updated to whatever was
    actually used, so a caller that reads ``plan.shimmed`` afterwards is never
    handed a path the collision loop moved away from.
    """
    if not plan.needed or plan.link is None or plan.anchor is None:
        return False

    anchor = Path(plan.anchor)
    requested = Path(plan.link)
    root = requested.parent
    try:
        rel = Path(plan.original).relative_to(anchor)
    except ValueError:                       # pragma: no cover - defensive
        return False

    # The requested link is always tried first -- ``plan.link`` is a contract,
    # not a hint. Longer-id alternates exist only to escape a genuine hash
    # collision, and are never used to relocate a shim the caller sited itself.
    candidates = [requested]
    candidates.extend(root / _anchor_id(anchor, n)
                      for n in range(_ID_LEN + 1, max_id_len + 1))

    for link in candidates:
        shimmed = link / rel

        # A longer id costs characters; never trade a collision fix for an
        # over-length path, which would defeat the point of the shim entirely.
        if len(str(shimmed)) > USABLE_PATH:
            logger.warning("cannot place a shim for %s without exceeding "
                           "MAX_PATH", anchor)
            return False

        if is_junction(link):
            if _same_dir(read_link_target(link), anchor):
                plan.link, plan.shimmed = link, shimmed
                return True
            # Someone else's anchor holds this id. Try a longer one rather than
            # returning success for a junction pointing somewhere else.
            logger.debug("shim id collision at %s -- lengthening id", link)
            continue

        if link.exists():
            # Occupied by a real file or directory. Deliberately NOT worked
            # around: the caller named this location, and quietly siting the
            # shim elsewhere would be more surprising than failing.
            logger.warning("shim path occupied by a non-junction: %s", link)
            return False

        try:
            root.mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError) as exc:
            # ValueError, not OSError, is what Path.mkdir raises for an
            # embedded NUL -- catching only OSError let it escape a caller
            # documented never to raise.
            logger.error("cannot create shim root %s: %s", root, exc)
            return False

        # The return value is ADVISORY; what matters is what is on disk
        # afterwards. `create_junction` checks `link.exists()` and only then
        # shells out to PowerShell, so two callers can both pass that check --
        # and `New-Item -ItemType Junction` will replace an existing reparse
        # point, so the loser of that race can silently overwrite the winner's
        # junction with a different target. Trusting a True here is how a
        # caller ends up reading someone else's directory.
        create_junction(anchor, link)

        if is_junction(link):
            if _same_dir(read_link_target(link), anchor):
                plan.link, plan.shimmed = link, shimmed
                return True
            # Either another anchor won the race, or ours was replaced after
            # we made it. Advance to a longer id instead of giving up: the
            # remaining candidates were never tried.
            logger.debug("lost a shim creation race at %s -- lengthening id",
                         link)
            continue

        if link.exists():
            continue          # a non-junction landed here; try the next id

        return False          # nothing was created -- a genuine failure

    logger.warning("exhausted shim ids up to %d chars for %s", max_id_len, anchor)
    return False


def remove_shim(link: Union[str, Path]) -> bool:
    """Remove a shim junction, leaving its target untouched.

    **Refuses anything that is not a junction.** The check is made immediately
    before the delete rather than trusted from an earlier scan, so a directory
    swapped in after a listing is not removed.

    That **narrows** the check-then-act window; it does not close it. The check
    and the delete remain two calls, and there is no atomic "unlink only if
    still a reparse point" primitive to use instead. Measured consequence of
    the surviving race: if a real directory replaces the junction between the
    two calls, ``os.rmdir`` deletes it when it is **empty** and refuses it when
    it is **not** -- so the blast radius is bounded to an empty directory, and
    no file contents can be lost through this path.

    Uses ``os.rmdir``, which unlinks the reparse point without descending into
    it. Never call a recursive remove on a shim: a junction is reported as an
    ordinary directory by ``os.path.islink``, ``os.path.isdir`` and
    ``DirEntry.is_symlink``, so a recursive shell delete will happily walk into
    the real data.
    """
    p = Path(link)
    if not is_junction(p):
        logger.debug("refusing to remove non-junction: %s", p)
        return False
    try:
        os.rmdir(p)            # reparse point only -- never the target contents
        return True
    except OSError as exc:
        logger.warning("could not remove shim %s: %s", p, exc)
        return False


def reap_shims(root: Union[str, Path],
               max_age_seconds: float = 86400.0,
               now: Optional[float] = None) -> List[Path]:
    """Remove shims under *root* older than *max_age_seconds*.

    Only junctions are considered; anything else in the directory is left
    alone. Returns the shims actually removed.
    """
    root = Path(root)
    if not root.is_dir():
        return []

    now = time.time() if now is None else now
    removed: List[Path] = []

    try:
        entries = list(os.scandir(root))
    except OSError:
        return removed

    for entry in entries:
        candidate = Path(entry.path)
        if not is_junction(candidate):
            continue
        try:
            age = now - entry.stat(follow_symlinks=False).st_mtime
        except OSError:
            continue
        if age >= max_age_seconds and remove_shim(candidate):
            removed.append(candidate)

    return removed


def shim_path(path: Union[str, Path],
              root: Optional[Union[str, Path]] = None,
              threshold: int = DEFAULT_THRESHOLD) -> Path:
    """Convenience: return an openable path for *path*, creating a shim if needed.

    Falls back to the original path whenever a shim is unnecessary, impossible,
    or fails to materialise -- so a caller is never left worse off than if this
    module did not exist.

    **Never raises for a path-shaped input.** The whole body is guarded: a
    malformed *root* (an embedded NUL, for instance, which surfaces as
    ``ValueError`` rather than ``OSError``) degrades to the original path
    instead of propagating. A caller substituting this for a bare path must not
    have to grow an exception handler it did not previously need.
    """
    try:
        plan = plan_shim(path, root=root, threshold=threshold)
        if not plan.needed:
            return plan.original
        if plan.usable and create_shim(plan):
            return plan.shimmed
        if plan.reason:
            logger.debug("no shim for %s: %s", path, plan.reason)
        return plan.original
    except (OSError, ValueError) as exc:
        logger.warning("shim_path fell back to the original path for %r: %s",
                       path, exc)
        return Path(path)
