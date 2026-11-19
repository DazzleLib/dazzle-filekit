r"""Portable path key: one literal, runtime-neutral encoding of an absolute path.

A store that keeps copies of files elsewhere (a trash, a backup) needs to map
an original absolute path to a place under its root, and back. This module
gives that mapping one canonical form, the *key*:

=====================================  ====================================
Input                                  Key
=====================================  ====================================
``X:\a\b``                             ``X/a/b`` (drive upper-cased)
``\\server\share\a``                   ``UNC/server/share/a``
``\\?\UNC\server\share\a``             ``UNC/server/share/a``
``\\?\X:\a``                           ``X/a``
``//server/share/a``                   UNC with ``flavor="windows"``;
                                       ``ROOT/server/share/a`` otherwise
``/mnt/<x>/a``                         ``X/a`` with ``flavor="wsl"``;
                                       ``ROOT/mnt/<x>/a`` otherwise
other POSIX absolute ``/a/b``          ``ROOT/a/b``
=====================================  ====================================

Refused with :class:`PortablePathError`: device paths (``\\.\``),
``\\?\Volume{...}``, ``\\?\GLOBALROOT``, ``\\server`` with no share,
relative and drive-relative (``C:foo``) paths, ``..`` that climbs above the
root, NUL anywhere, and -- for ``\\?\`` paths -- components that only exist
because the prefix disables Windows' name rules (trailing dot or space,
reserved device names).

Rules that hold for every key:

- **Literal.** No ``~`` or environment-variable expansion, no stripping of
  surrounding whitespace. (Use ``normalize_cross_platform_path`` for user
  input; this is for names that already exist.)
- **Lexical.** ``.`` parts are dropped and ``..`` is folded against the
  preceding part, without touching the filesystem; folding above the root
  is refused rather than clamped.
- **Never empty parts**, never ``.`` or ``..``; parts joined with ``/``.
- **``flavor`` is required**, because ``//x/y`` and ``/mnt/<x>`` mean
  different things on different runtimes, and a durable key must not depend
  on which Python wrote it.

:func:`key_to_relpath` is the only way a key (or any list of parts) becomes
a path on disk: it refuses parts the target filesystem cannot hold.

Pure: no I/O. UNC parsing delegates to ``unctools.get_unc_path_elements``;
the ``\\?\`` and ``\\.\`` prefixes are recognised here first, because
unctools reads them as an ordinary server named ``?`` or ``.``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Union

from dazzle_lib.exceptions import FileOperationError


FLAVORS =("windows", "wsl", "posix")

_DRIVE_RE = re.compile(r"^([A-Za-z]):(.*)$", re.DOTALL)
_WSL_DRIVE_RE = re.compile(r"^[A-Za-z]$")
_WIN_ILLEGAL = set('<>:"|?*\\/')
_RESERVED = (
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


class PortablePathError(FileOperationError, ValueError):
    """A path or key that cannot be expressed in, or converted from, the
    portable key form. The message names the part at fault.

    It is a ``ValueError`` (the argument was bad) and also sits under the
    stack's common root, ``dazzle_lib.DazzleError``, through
    ``FileOperationError`` -- so a caller can catch one root for every
    DazzleLib library."""


@dataclass(frozen=True)
class _Split:
    """An absolute path taken apart. ``token`` is the key's root part(s)
    (``("C",)``, ``("UNC", server, share)``, ``("ROOT",)``); ``root_native``
    is the literal root as written, so a native path can be rebuilt;
    ``parts`` are the lexically folded components; ``case_insensitive``
    marks roots whose names compare case-insensitively (Windows drives,
    UNC shares, WSL drive mounts); ``needs_prefix`` marks a ``\\?\`` path
    with a component Windows only accepts under that prefix."""

    token: Tuple[str, ...]
    root_native: str
    sep: str
    parts: Tuple[str, ...]
    case_insensitive: bool
    needs_prefix: bool = False


def _check_flavor(flavor: str, name: str = "flavor") -> None:
    if flavor not in FLAVORS:
        raise ValueError(f"{name} must be one of {FLAVORS}, not {flavor!r}")


def _as_str(path: Union[str, "os.PathLike[str]"]) -> str:
    s = os.fspath(path)
    if not isinstance(s, str):
        raise TypeError(f"expected a str path, got {type(s).__name__}")
    if "\x00" in s:
        raise PortablePathError(f"NUL in path {s!r}")
    if not s:
        raise PortablePathError("empty path")
    return s


def _fold(parts: Sequence[str], original: str) -> Tuple[str, ...]:
    out: List[str] = []
    for p in parts:
        if p in ("", "."):
            continue
        if p == "..":
            if not out:
                raise PortablePathError(f"'..' climbs above the root in {original!r}")
            out.pop()
            continue
        out.append(p)
    return tuple(out)


def _needs_prefix(part: str) -> bool:
    """True for a component Windows accepts only under ``\\?\``."""
    return part.endswith((".", " ")) or part.split(".")[0].upper() in _RESERVED


def _split_windows(s: str, original: str) -> _Split:
    s = s.replace("/", "\\")
    extended = False
    if s.startswith("\\\\?\\"):
        rest = s[4:]
        upper = rest.upper()
        if upper.startswith("UNC\\"):
            s = "\\\\" + rest[4:]
            extended = True
        elif upper.startswith("VOLUME{") or upper.startswith("GLOBALROOT"):
            raise PortablePathError(f"device-namespace path is not portable: {original!r}")
        elif _DRIVE_RE.match(rest):
            s = rest
            extended = True
        else:
            raise PortablePathError(f"unrecognised extended-length path: {original!r}")
    elif s.startswith("\\\\.\\"):
        raise PortablePathError(f"device path is not portable: {original!r}")

    if s.startswith("\\\\"):
        # Imported here, not at module top: filekit promises that
        # ``import dazzle_filekit`` works without unctools loaded.
        from unctools import get_unc_path_elements
        elements = get_unc_path_elements(s)
        if not elements or not elements[0] or not elements[1]:
            raise PortablePathError(f"UNC path needs a server and a share: {original!r}")
        server, share, rest = elements
        parts = _fold(rest.replace("/", "\\").split("\\"), original)
        split = _Split(
            token=("UNC", server, share),
            root_native=f"\\\\{server}\\{share}",
            sep="\\",
            parts=parts,
            case_insensitive=True,
            needs_prefix=extended and any(_needs_prefix(p) for p in parts),
        )
        return split

    m = _DRIVE_RE.match(s)
    if not m:
        raise PortablePathError(f"not an absolute Windows path: {original!r}")
    letter, rest = m.group(1), m.group(2)
    if not rest.startswith("\\"):
        raise PortablePathError(f"drive-relative path is not absolute: {original!r}")
    parts = _fold(rest.split("\\"), original)
    return _Split(
        token=(letter.upper(),),
        root_native=f"{letter}:\\",
        sep="\\",
        parts=parts,
        case_insensitive=True,
        needs_prefix=extended and any(_needs_prefix(p) for p in parts),
    )


def _split_posix(s: str, flavor: str, original: str) -> _Split:
    if not s.startswith("/"):
        raise PortablePathError(f"not an absolute path: {original!r}")
    parts = _fold(s.split("/"), original)
    if flavor == "wsl" and len(parts) >= 2 and parts[0] == "mnt" and _WSL_DRIVE_RE.match(parts[1]):
        return _Split(
            token=(parts[1].upper(),),
            root_native=f"/mnt/{parts[1]}",
            sep="/",
            parts=parts[2:],
            case_insensitive=True,
        )
    return _Split(token=("ROOT",), root_native="/", sep="/", parts=parts,
                  case_insensitive=False)


def _split(path: Union[str, "os.PathLike[str]"], flavor: str) -> _Split:
    """Take an absolute path apart under ``flavor``'s rules (shared by the
    encoder and the batch planner)."""
    _check_flavor(flavor)
    s = _as_str(path)
    windows_shaped = (
        s.startswith("\\\\")
        or bool(_DRIVE_RE.match(s))
        or (flavor == "windows" and (s.startswith("//") or s.startswith("/") or s.startswith("\\")))
    )
    if windows_shaped:
        return _split_windows(s, s)
    return _split_posix(s, flavor, s)


def _key_from(split: _Split, parts: Optional[Sequence[str]] = None) -> str:
    return "/".join(split.token + tuple(split.parts if parts is None else parts))


def encode_portable_path(path: Union[str, "os.PathLike[str]"], *, flavor: str) -> str:
    r"""Encode an absolute path as a portable key.

    >>> encode_portable_path(r"C:\Users\x\a.txt", flavor="windows")
    'C/Users/x/a.txt'
    >>> encode_portable_path("/mnt/c/Users/x", flavor="wsl")
    'C/Users/x'
    >>> encode_portable_path("/mnt/d/x", flavor="posix")
    'ROOT/mnt/d/x'

    Raises:
        PortablePathError: the path has no portable form (see module docs).
        ValueError: ``flavor`` is not one of ``FLAVORS``.
    """
    split = _split(path, flavor)
    if split.needs_prefix:
        bad = next(p for p in split.parts if _needs_prefix(p))
        raise PortablePathError(
            f"component {bad!r} exists only under the \\\\?\\ prefix "
            f"(trailing dot/space or a reserved name): {os.fspath(path)!r}"
        )
    return _key_from(split)


def _key_parts(key: str) -> List[str]:
    if not isinstance(key, str) or not key:
        raise PortablePathError(f"not a portable key: {key!r}")
    parts = key.split("/")
    for p in parts:
        if p in ("", ".", "..") or "\x00" in p:
            raise PortablePathError(f"invalid part {p!r} in key {key!r}")
    return parts


def decode_portable_path(key: str, *, runtime: str) -> Optional[str]:
    r"""The native path a key names on ``runtime``, or ``None`` when that
    runtime has no native form for it (a UNC key on POSIX, a ``ROOT`` key on
    Windows, a drive key on plain POSIX).

    >>> decode_portable_path("C/Users/x", runtime="windows")
    'C:\\Users\\x'
    >>> decode_portable_path("C/Users/x", runtime="wsl")
    '/mnt/c/Users/x'
    """
    _check_flavor(runtime, "runtime")
    parts = _key_parts(key)
    head, rest = parts[0], parts[1:]
    if head == "UNC":
        if len(parts) < 3:
            raise PortablePathError(f"UNC key needs a server and a share: {key!r}")
        if runtime != "windows":
            return None
        return "\\\\" + "\\".join(rest)
    if head == "ROOT":
        if runtime == "windows":
            return None
        return "/" + "/".join(rest)
    if len(head) == 1 and head.isalpha() and head.isupper():
        if runtime == "windows":
            return f"{head}:\\" + "\\".join(rest)
        if runtime == "wsl":
            return f"/mnt/{head.lower()}" + "".join("/" + p for p in rest)
        return None
    raise PortablePathError(f"unknown key root {head!r} in {key!r}")


def _check_part(part: str, target_flavor: str, where: str) -> None:
    if part in ("", ".", ".."):
        raise PortablePathError(f"invalid part {part!r} in {where}")
    if "\x00" in part or "/" in part:
        raise PortablePathError(f"part {part!r} contains NUL or '/' in {where}")
    if target_flavor == "windows":
        bad = sorted({c for c in part if c in _WIN_ILLEGAL or ord(c) < 32})
        if bad:
            raise PortablePathError(
                f"part {part!r} has characters Windows cannot store "
                f"({''.join(bad)!r}) in {where}"
            )
        if part.endswith((".", " ")):
            raise PortablePathError(f"part {part!r} ends in a dot or space in {where}")
        if part.split(".")[0].upper() in _RESERVED:
            raise PortablePathError(f"part {part!r} is a reserved Windows name in {where}")


def key_to_relpath(parts_or_key: Union[str, Sequence[str]], *, target_flavor: str) -> str:
    r"""Turn a key (``"C/Users/x"``) or a list of parts into a relative path
    for ``target_flavor``'s filesystem, refusing any part it cannot hold.

    This is the only way a key or relpath should become a disk path: join
    the result under a store root you own.

    >>> key_to_relpath("UNC/srv/share/a.txt", target_flavor="windows")
    'UNC\\srv\\share\\a.txt'
    >>> key_to_relpath("ROOT/home/u/a:b", target_flavor="windows")
    Traceback (most recent call last):
    ...
    dazzle_filekit.portable.PortablePathError: part 'a:b' has characters Windows cannot store (':') in 'ROOT/home/u/a:b'

    Refused everywhere: empty, ``.``, ``..``, NUL, ``/`` inside a part. On a
    Windows target also: ``\ / : * ? " < > |`` and control characters, a
    trailing dot or space, and reserved device names (``CON``, ``NUL.txt``).
    """
    _check_flavor(target_flavor, "target_flavor")
    if isinstance(parts_or_key, str):
        where = repr(parts_or_key)
        parts = parts_or_key.split("/") if parts_or_key else [""]
    else:
        parts = list(parts_or_key)
        where = repr("/".join(parts))
        if not parts:
            raise PortablePathError("no parts")
    for p in parts:
        _check_part(p, target_flavor, where)
    sep = "\\" if target_flavor == "windows" else "/"
    return sep.join(parts)


__all__ = [
    "FLAVORS",
    "PortablePathError",
    "encode_portable_path",
    "decode_portable_path",
    "key_to_relpath",
]
