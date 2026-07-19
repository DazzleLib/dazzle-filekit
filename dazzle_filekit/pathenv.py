"""PATH-environment-value helpers -- declared-platform parsing and compare.

A PATH *value* is a string whose platform semantics are fixed by its
PROVENANCE, not by the host parsing it: a Windows registry ``Path``
value stays ``;``-separated, ``%VAR%``-bearing, and case-insensitive
even when a POSIX CI runner is the one reading it, and a POSIX ``PATH``
stays ``:``-separated everywhere. That is the opposite philosophy from
:func:`dazzle_filekit.paths.normalize_cross_platform_path`, which is
deliberately HOST-directional (it converts filesystem paths toward the
running OS's native form). Both philosophies are correct -- for their
own domain. This module is the declared-platform domain's home.

Origin: extracted from the dazzlecmd self-setup work (dazzlecmd#103),
where PATH membership had to be decided against Windows registry values
with normalized comparison (quotes, trailing slashes, ``%VAR%``
expansion, casefold) on any host. See the dazzlecmd stack-survey (C6)
for the layering rationale.

``platform`` arguments accept :data:`PLATFORM_WINDOWS`,
:data:`PLATFORM_POSIX`, or ``None`` meaning the running host. The
functions are pure string logic -- no filesystem I/O, no registry
access; persistence stays with callers.
"""

from __future__ import annotations

import ntpath
import os
from typing import List, Optional

PLATFORM_WINDOWS = "windows"
PLATFORM_POSIX = "posix"


def host_path_platform() -> str:
    """The running host's PATH dialect: ``"windows"`` or ``"posix"``."""
    return PLATFORM_WINDOWS if os.name == "nt" else PLATFORM_POSIX


def _resolve_platform(platform: Optional[str]) -> str:
    if platform is None:
        return host_path_platform()
    if platform not in (PLATFORM_WINDOWS, PLATFORM_POSIX):
        raise ValueError(
            f"platform must be {PLATFORM_WINDOWS!r}, {PLATFORM_POSIX!r}, "
            f"or None (host); got {platform!r}"
        )
    return platform


def split_path_value(value: str,
                     platform: Optional[str] = None) -> List[str]:
    """Split a PATH value into its non-empty entries.

    The separator follows the DECLARED platform (``;`` for windows,
    ``:`` for posix), never the host's ``os.pathsep`` -- a Windows
    registry value parsed on a POSIX runner still splits on ``;``.
    """
    sep = ";" if _resolve_platform(platform) == PLATFORM_WINDOWS else ":"
    return [p for p in value.split(sep) if p.strip()]


def normalize_path_entry(entry: str,
                         platform: Optional[str] = None) -> str:
    """Normalize ONE PATH entry for identity comparison.

    Windows dialect: strips whitespace and surrounding double quotes
    (quoted entries are legal in Windows PATH values), expands ``%VAR%``
    references the way the OS does for ``REG_EXPAND_SZ`` (via
    :mod:`ntpath` explicitly, so behavior is identical on any host),
    canonicalizes separators to ``\\``, drops trailing separators, and
    casefolds (Windows PATH lookup is case-insensitive). Note an
    inherited stdlib behavior, pinned by test: ``ntpath.expandvars``
    ALSO expands POSIX-spelled ``$VAR`` / ``${VAR}`` references, so
    those expand under this dialect too. Undefined references of either
    spelling stay literal.

    POSIX dialect: strips whitespace and quotes, canonicalizes
    separators to ``/``, drops trailing slashes; case is preserved.

    Output is deterministic for a given (entry, platform) pair
    regardless of the host running this code.
    """
    plat = _resolve_platform(platform)
    e = entry.strip().strip('"')
    if plat == PLATFORM_WINDOWS:
        e = ntpath.expandvars(e)
        e = e.replace("/", "\\")
        e = e.rstrip("\\")
        return e.casefold()
    e = e.replace("\\", "/")
    return e.rstrip("/")


def path_value_contains(value: str, directory: str,
                        platform: Optional[str] = None) -> bool:
    """True if ``directory`` is among ``value``'s entries.

    Membership by normalized identity: quotes and trailing separators
    ignored, ``%VAR%`` entries expanded, case-insensitive under the
    windows dialect.
    """
    target = normalize_path_entry(directory, platform=platform)
    return any(
        normalize_path_entry(p, platform=platform) == target
        for p in split_path_value(value, platform=platform)
    )


def append_path_value(value: str, directory: str,
                      platform: Optional[str] = None) -> str:
    """Return ``value`` with ``directory`` appended, if not already present.

    Pure string construction: no-op (returns ``value`` unchanged) when
    the directory is already a member under normalized identity; an
    empty ``value`` yields ``directory`` alone. The caller persists the
    result wherever it belongs (registry, rc file, environment) -- this
    module never does I/O.
    """
    if path_value_contains(value, directory, platform=platform):
        return value
    sep = ";" if _resolve_platform(platform) == PLATFORM_WINDOWS else ":"
    return (value.rstrip(sep) + sep + directory) if value else directory
