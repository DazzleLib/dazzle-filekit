r"""Are filekit's two `is_unc_path` export sites really "one canonical def"?

docs/unctools-integration.md claims:

    "It is one canonical definition that delegates to `unctools.is_unc_path`
     (the L0 path-identity owner); the two filekit export sites
     (`dazzle_filekit.is_unc_path` and `dazzle_filekit.utils.is_unc_path`)
     both resolve to it."

and the v0.3.0 CHANGELOG describes collapsing "divergent copies" into one.
They are NOT the same object (`is` returns False), so this asks the question
that actually matters: do they ever DISAGREE? A second definition that always
agrees is a wording problem; one that diverges is the bug 0.3.0 claimed to fix.

Read-only, pure string inputs, no filesystem or network access.
"""
import dazzle_filekit as F
from dazzle_filekit.utils import is_unc_path as utils_impl

import unctools

top_impl = F.is_unc_path
unc_impl = unctools.is_unc_path

CASES = [
    r"\\server\share",
    r"\\server\share\folder\file.txt",
    "//server/share",
    "//server/share/folder/file.txt",
    r"C:\Users\foo",
    "/c/Users/foo",
    "/mnt/c/Users/foo",
    "",
    ".",
    r"\\",
    "//",
    r"\\?\UNC\server\share",
    r"\\?\C:\Users\foo",
    r"\\.\pipe\name",
    r"\\localhost\c$",
    "\\\\server",              # host only, no share
    r"\server\share",          # single leading slash
    "//server",
    r"\\server\share\..\other",
    "  \\\\server\\share  ",   # surrounding whitespace
]

print("  %-34s %-7s %-7s %-9s" % ("input", "top", "utils", "unctools"))
print("  " + "-" * 62)

diverge = []
for c in CASES:
    row = []
    for fn in (top_impl, utils_impl, unc_impl):
        try:
            row.append(repr(fn(c)))
        except Exception as exc:                       # noqa: BLE001
            row.append(type(exc).__name__)
    disagree = len(set(row)) != 1
    if disagree:
        diverge.append((c, row))
    print("  %-34r %-7s %-7s %-9s%s"
          % (c, row[0], row[1], row[2], "   <-- DIVERGES" if disagree else ""))

print()
print("  top IS utils   : %s" % (top_impl is utils_impl))
print("  cases compared : %d" % len(CASES))
print("  divergences    : %d" % len(diverge))
print()
if diverge:
    print("  VERDICT: the two export sites are NOT interchangeable. The doc's")
    print("  'one canonical definition' claim is wrong in substance.")
    for c, row in diverge:
        print("     %r -> top=%s utils=%s unctools=%s" % (c, row[0], row[1], row[2]))
else:
    print("  VERDICT: two distinct function objects, but behaviourally identical")
    print("  on every case tried. The doc's claim is right in substance and")
    print("  wrong only in the literal 'both resolve to it' -- they are separate")
    print("  definitions that agree, not one shared definition.")
