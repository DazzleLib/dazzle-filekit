"""Does a colon-less SystemDrive value ("C" instead of "C:") reproduce the
SAME drive-relative hazard the `or "C:"` fix closed for the empty-string
case? Pure pathlib probe, no filesystem I/O.
"""
from pathlib import Path
import os

from dazzle_filekit import longpath as lp

p = Path("C" + os.sep) / ".dzs"
print("Path('C' + sep) / '.dzs' =", repr(str(p)))
print("is_absolute() =", p.is_absolute())
print("drive =", repr(p.drive), " root =", repr(p.root))

print()
saved = os.environ.get("SystemDrive")
try:
    os.environ["SystemDrive"] = "C"   # missing the colon
    roots = [str(r) for r in lp.candidate_roots()]
    print("candidate_roots() with SystemDrive='C' (no colon):", roots)
    print("first candidate absolute?", Path(roots[0]).is_absolute() if roots else None)
finally:
    if saved is None:
        os.environ.pop("SystemDrive", None)
    else:
        os.environ["SystemDrive"] = saved
