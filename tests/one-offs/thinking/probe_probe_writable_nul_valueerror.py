"""_probe_writable() only catches OSError around root.mkdir(parents=True):

    try:
        if not root.exists():
            root.mkdir(parents=True)
        ...
    except OSError:
        return False

Windows raises ValueError (not OSError) for an embedded NUL in a path passed
to mkdir -- this is the exact defect class the delta's item 3 already fixed
once for create_shim's own mkdir call. Does the SAME gap exist here, one
call removed, reachable via resolve_shim_root -> candidate_roots(SystemDrive
env var) -> _probe_writable? If so, shim_path's new outer except(OSError,
ValueError) is the ONLY thing standing between this and a raise escaping to
the caller -- which is worth confirming directly rather than assuming.

Uses monkeypatch-style manual os.environ mutation (restored in finally) --
SAFE: SystemDrive is set to a NUL-bearing bogus value, not a real drive
letter, so candidate_roots()/resolve_shim_root() here can never resolve to a
real usable root; the point is only to trigger the mkdir(ValueError) path,
which never succeeds regardless of the drive letter it's fed.
"""
import os
from pathlib import Path

from dazzle_filekit import longpath as lp

saved = {k: os.environ.get(k) for k in ("SystemDrive", "USERPROFILE", "HOME", "TEMP", "TMP")}
try:
    # Force EVERY candidate root to carry a NUL so _probe_writable is the
    # thing that gets exercised for all of them, not just the first.
    for k in ("USERPROFILE", "HOME", "TEMP", "TMP"):
        os.environ.pop(k, None)
    os.environ["SystemDrive"] = "C:\x00bogus"

    roots = lp.candidate_roots()
    print("candidate_roots() with NUL-bearing SystemDrive ->", [repr(str(r)) for r in roots])

    print()
    print("Calling resolve_shim_root() directly (probe=True, real filesystem probing) ...")
    try:
        got = lp.resolve_shim_root()
        print("resolve_shim_root() ->", got)
    except Exception as e:
        print("resolve_shim_root() RAISED:", type(e).__name__, e)

    print()
    print("Calling plan_shim() (root=None path) ...")
    long_path = "C:\\" + "a" * 300 + "\\f.pdf"
    try:
        plan = lp.plan_shim(long_path)
        print("plan_shim() ->", plan)
    except Exception as e:
        print("plan_shim() RAISED:", type(e).__name__, e)

    print()
    print("Calling shim_path() (should degrade to original, never raise) ...")
    try:
        result = lp.shim_path(long_path)
        print("shim_path() -> %r (never raised)" % (result,))
    except Exception as e:
        print("shim_path() RAISED:", type(e).__name__, e, "  <<< CONTRACT VIOLATION")
finally:
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    print("\nenv restored")
