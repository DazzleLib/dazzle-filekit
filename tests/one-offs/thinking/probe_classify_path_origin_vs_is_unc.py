r"""Does `classify_path_origin` actually distinguish the cases `is_unc_path` conflates?

docs/unctools-integration.md now tells readers:

    "If you need 'is this genuinely a network location' rather than 'does this
     start with \\', use unctools.classify_path_origin, which probes the drive
     rather than reading the prefix."

That is a recommendation, so it needs to be true. `is_unc_path` returns True
for an extended-length LOCAL path (\\?\C:\...) and for a device path
(\\.\pipe\...). If classify_path_origin says 'unknown' for those rather than
something more useful, the advice is weaker than written and the wording has
to change.

Read-only. Uses a non-existent server; every case is about string
classification, except the local ones which touch only the drive letter.
"""
from unctools import classify_path_origin
import dazzle_filekit as F

CASES = [
    (r"\\server\share",        "genuine UNC"),
    (r"\\?\UNC\server\share",  "extended-length UNC"),
    (r"\\?\C:\Users\foo",      "extended-length LOCAL -- is_unc_path says True"),
    (r"\\.\pipe\name",         "device path -- is_unc_path says True"),
    (r"C:\Users\foo",          "plain local"),
    (r"\\",                    "bare prefix -- is_unc_path says True"),
    ("//server/share",         "forward-slash UNC"),
]

print("  %-26s %-8s %-10s %s" % ("input", "is_unc", "origin", "note"))
print("  " + "-" * 74)
for p, note in CASES:
    try:
        unc = repr(F.is_unc_path(p))
    except Exception as exc:                              # noqa: BLE001
        unc = type(exc).__name__
    try:
        origin = repr(classify_path_origin(p))
    except Exception as exc:                              # noqa: BLE001
        origin = type(exc).__name__
    print("  %-26r %-8s %-10s %s" % (p, unc, origin, note))

print()
print("  Question the doc rests on: does origin separate the two rows where")
print("  is_unc_path is True but the path is NOT a network location?")
local_ext = classify_path_origin(r"\\?\C:\Users\foo")
device = classify_path_origin(r"\\.\pipe\name")
real_unc = classify_path_origin(r"\\server\share")
print("     \\\\?\\C:\\Users\\foo -> %r" % (local_ext,))
print("     \\\\.\\pipe\\name     -> %r" % (device,))
print("     \\\\server\\share     -> %r" % (real_unc,))
print()
if local_ext != real_unc and device != real_unc:
    print("  VERDICT: yes -- origin separates them; the doc's advice stands.")
else:
    print("  VERDICT: NO -- origin does not separate them. Soften the doc:")
    print("  classify_path_origin is not a reliable 'is this really network?' test")
    print("  for these shapes, and the reader needs a different answer.")


# --- follow-up: what DOES separate them? ---------------------------------
print()
print(r"  Follow-up: strip the extended-length prefix first, then classify.")
print(r"  The discriminator is what follows \\?\ -- 'UNC\' means network,")
print(r"  a drive letter means local.")
print()


def strip_extended(p):
    r"""Return p without a \\?\ / \\.\ prefix, restoring plain UNC form."""
    for pre in ("\\\\?\\", "\\\\.\\"):
        if p.startswith(pre):
            rest = p[len(pre):]
            if rest.upper().startswith("UNC\\"):
                return "\\\\" + rest[4:]
            return rest
    return p


for p in [r"\\?\C:\Users\foo", r"\\?\UNC\server\share", r"\\.\pipe\name",
          r"\\server\share", r"C:\Users\foo"]:
    s = strip_extended(p)
    print("  %-26r -> %-26r origin=%r" % (p, s, classify_path_origin(s)))
