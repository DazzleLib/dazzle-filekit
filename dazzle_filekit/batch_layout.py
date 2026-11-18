"""Lay out a batch of absolute paths under common bases, without collisions.

A tool that stages many items into one folder (a trash batch, a backup set)
has to give each a distinct place there. Using the bare name fails as soon as
two items share one (``a/x.json`` and ``b/x.json``). Using each item's full
path is safe but long. ``plan_batch`` keeps what is shared out of the stored
paths: for each root (a drive, a network share, the POSIX root) it finds the
common parent folder of the batch's items -- the *base* -- and gives every
item its path relative to that base.

    C:\\Users\\me\\.claude\\session-states\\1.json
    C:\\Users\\me\\claude\\context-window\\1.json
      -> base   C:\\Users\\me
         items  .claude/session-states/1.json
                claude/context-window/1.json

A batch of one item keeps just its name. A batch that spans roots gets one
base per root, and each item's path is prefixed with its base's number
(``0/...``, ``1/...``), so the result is still one tree with no collisions.

The function is pure: it reads no disk. Whether an item is a link is asked
through ``is_link``, a function the caller supplies.

Rules (each reported, never silent):
- exact duplicates, and on case-insensitive roots (drives, shares, WSL
  drives) duplicates that differ only by case, are merged -- a warning;
- an item inside another item of the batch is dropped, the ancestor carries
  it -- a warning; but an item under a LINK is an error, because the link
  would be staged as a link and the item is in the link's target;
- a root itself (``C:\\``, ``/``, a share) as an item is an error;
- two items that would still land on one relative path are an error;
- a path with no portable form is an error (see ``portable``).

When ``errors`` is non-empty the plan must not be executed.

Stdlib only, plus this package's ``portable`` module.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union
import os

from .portable import (
    PortablePathError,
    _check_flavor,
    _key_from,
    _needs_prefix,
    _split,
    key_to_relpath,
)


@dataclass
class BatchItem:
    """One item of the batch and where it goes."""
    original: str       # the path as given
    base_index: int     # index into BatchPlan.bases
    relpath: str        # "/"-joined path under the batch's content folder


@dataclass
class BatchPlan:
    bases: List[Dict[str, Optional[str]]] = field(default_factory=list)
    items: List[BatchItem] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    dropped: List[Dict[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when the plan may be executed."""
        return not self.errors


def _fold_case(parts: Sequence[str], insensitive: bool) -> Tuple[str, ...]:
    return tuple(p.casefold() for p in parts) if insensitive else tuple(parts)


def plan_batch(
    paths: Sequence[Union[str, "os.PathLike[str]"]],
    *,
    flavor: str,
    is_link: Optional[Callable[[str], bool]] = None,
    drop_nested: bool = True,
    target_flavor: Optional[str] = None,
) -> BatchPlan:
    r"""Plan where each of ``paths`` goes in one batch.

    Args:
        paths: absolute paths, in ``flavor``'s form.
        flavor: ``"windows"``, ``"wsl"`` or ``"posix"`` -- how to read them.
        is_link: optional ``path -> bool``; True for an item that is a link
            (symlink, junction). Only used for the nesting rule.
        drop_nested: drop an item that is inside another item (default). With
            False such a pair is an error instead.
        target_flavor: the filesystem the relative paths will be created on
            (default: ``flavor``); they are validated for it.

    Returns:
        A ``BatchPlan``. Check ``plan.ok`` before using ``plan.items``.

    >>> p = plan_batch([r"C:\a\x.json", r"C:\b\x.json"], flavor="windows")
    >>> [(i.relpath) for i in p.items], p.bases[0]["native"]
    (['a/x.json', 'b/x.json'], 'C:\\')
    """
    _check_flavor(flavor)
    target = flavor if target_flavor is None else target_flavor
    _check_flavor(target, "target_flavor")
    plan = BatchPlan()

    # 1. take each path apart; merge duplicates; refuse roots
    entries = []          # (original, split, root_key, folded_parts)
    seen = {}
    for raw in paths:
        original = os.fspath(raw)
        try:
            split = _split(original, flavor)
        except PortablePathError as exc:
            plan.errors.append(str(exc))
            continue
        if split.needs_prefix:
            bad = next(p for p in split.parts if _needs_prefix(p))
            plan.errors.append(
                f"component {bad!r} exists only under the \\\\?\\ prefix: "
                f"{original!r}")
            continue
        if not split.parts:
            plan.errors.append(
                f"a root cannot be an item of a batch: {original!r}")
            continue
        root_key = _fold_case(split.token, split.case_insensitive)
        folded = _fold_case(split.parts, split.case_insensitive)
        ident = (root_key, folded)
        if ident in seen:
            first = seen[ident]
            how = ("is given twice" if first == original
                   else f"is the same item as {first!r}")
            plan.warnings.append(f"{original!r} {how}; kept once")
            plan.dropped.append({"original": original, "reason": "duplicate"})
            continue
        seen[ident] = original
        entries.append((original, split, root_key, folded))

    # 2. nesting: an item inside another item of the batch
    kept = []
    for original, split, root_key, folded in entries:
        ancestor = None
        for o2, s2, r2, f2 in entries:
            if o2 is original or r2 != root_key:
                continue
            if len(f2) < len(folded) and folded[: len(f2)] == f2:
                if ancestor is None or len(f2) < len(ancestor[1]):
                    ancestor = (o2, f2)
        if ancestor is None:
            kept.append((original, split, root_key, folded))
            continue
        if is_link is not None and is_link(ancestor[0]):
            plan.errors.append(
                f"{original!r} is inside {ancestor[0]!r}, which is a link: "
                f"the link would be staged as a link, and this item is in "
                f"what it points at. Name one or the other")
        elif drop_nested:
            plan.warnings.append(
                f"{original!r} is inside {ancestor[0]!r}, which is also in "
                f"the batch and carries it; dropped")
            plan.dropped.append({"original": original, "reason": "nested"})
        else:
            plan.errors.append(
                f"{original!r} is inside {ancestor[0]!r}, which is also in "
                f"the batch")

    # 3. one base per root: the common parent of that root's items
    groups: Dict[Tuple[str, ...], List] = {}
    order: List[Tuple[str, ...]] = []
    for entry in kept:
        if entry[2] not in groups:
            groups[entry[2]] = []
            order.append(entry[2])
        groups[entry[2]].append(entry)
    multi_root = len(order) > 1

    used: Dict[str, str] = {}
    for index, root_key in enumerate(order):
        members = groups[root_key]
        first_split = members[0][1]
        parents = [m[3][:-1] for m in members]          # folded, for comparison
        common = len(parents[0])
        for parent in parents[1:]:
            n = 0
            while n < min(common, len(parent)) and parent[n] == parents[0][n]:
                n += 1
            common = n
        base_parts = first_split.parts[:common]         # as written by the first item
        sep = first_split.sep
        root_native = first_split.root_native
        native = (root_native if not base_parts
                  else root_native.rstrip(sep) + sep + sep.join(base_parts))
        try:
            key: Optional[str] = _key_from(first_split, base_parts)
            if base_parts:
                key_to_relpath(base_parts, target_flavor=target)
        except PortablePathError as exc:
            key = None
            plan.warnings.append(f"base {native!r} has no portable key: {exc}")
        plan.bases.append({"native": native, "key": key})

        for original, split, _root, folded in members:
            rel_parts = list(split.parts[common:])
            try:
                # validated for the target filesystem; STORED "/"-joined, so
                # a manifest reads the same on every runtime
                key_to_relpath(rel_parts, target_flavor=target)
            except PortablePathError as exc:
                plan.errors.append(f"{original!r}: {exc}")
                continue
            relpath = "/".join(rel_parts)
            if multi_root:
                relpath = f"{index}/{relpath}"
            clash_key = relpath.casefold()
            if clash_key in used:
                plan.errors.append(
                    f"{original!r} and {used[clash_key]!r} would both be "
                    f"stored at {relpath!r}")
                continue
            used[clash_key] = original
            plan.items.append(BatchItem(original=original, base_index=index,
                                        relpath=relpath))
    return plan


__all__ = ["BatchItem", "BatchPlan", "plan_batch"]
