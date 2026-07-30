"""What does read_link_target() ACTUALLY return for a REAL junction created
from a plain path -- does the kernel/PowerShell ever hand back a \\?\\-prefixed
PrintName on its own, or does that only happen if something explicitly writes
it that way (create_junction_raw with a pre-prefixed raw target)?

This settles reachability for the #1 priority false-positive route the
coordinator flagged: "the kernel canonicalizing a plain-path junction target
to \\?\\ form is the realistic route in" for _same_dir(). If PrintName never
comes back prefixed on its own, that route requires create_junction_raw
(a real but narrower door) rather than being ambient behaviour of ordinary
junctions.

Also checks whether 8.3 short-name generation is available on this volume
(TEMP), since fsutil already reported it disabled -- if so, a live short-vs-
long real-directory _same_dir test cannot be constructed on this host and
that limitation gets reported rather than silently skipped.

SANDBOXED under tempfile.mkdtemp(); shutil.rmtree at the end is fine per the
round-1 empirical finding (rmtree refuses to walk a reparse point -- it
cannot eat the target through the junction).
"""
import ctypes
import os
import shutil
import tempfile
from pathlib import Path

from dazzle_filekit import longpath as lp
from dazzle_filekit.links import create_junction, create_junction_raw, read_link_target
from dazzle_filekit.utils.validation import is_junction

sandbox = Path(tempfile.mkdtemp(prefix="realjunc_"))
print("sandbox:", sandbox)

try:
    # --- 1. Plain-path junction: what PrintName actually comes back ---
    anchor = sandbox / "ANCHOR_PLAIN"
    anchor.mkdir()
    link1 = sandbox / "link_plain"
    ok = create_junction(anchor, link1)
    print("\n[1] create_junction(plain anchor) ->", ok)
    if ok:
        raw = read_link_target(link1)
        print("    read_link_target(link1)      =", repr(raw))
        print("    starts with extended prefix? =", raw is not None and raw.startswith(("\\\\?\\", "\\\\.\\")))
        print("    _same_dir(raw, anchor)       =", lp._same_dir(raw, anchor))

    # --- 2. create_junction with an EXPLICIT \\?\-prefixed target string ---
    # (organic route would require a caller to pass a pre-prefixed anchor to
    # create_junction; plan_shim itself never does, since needs_shim() short-
    # circuits extended-prefixed originals to needed=False before an anchor is
    # ever computed -- but create_junction as a primitive doesn't know that,
    # so test it directly as a lower-level probe.)
    anchor2 = sandbox / "ANCHOR_EXPLICIT_PREFIX"
    anchor2.mkdir()
    link2 = sandbox / "link_explicit_prefix"
    prefixed_target = "\\\\?\\" + str(anchor2)
    ok2 = create_junction(prefixed_target, link2)
    print("\n[2] create_junction(target='\\\\?\\...') ->", ok2)
    if ok2:
        raw2 = read_link_target(link2)
        print("    read_link_target(link2)      =", repr(raw2))
        print("    starts with extended prefix? =", raw2 is not None and raw2.startswith(("\\\\?\\", "\\\\.\\")))
        print("    _same_dir(raw2, anchor2)     =", lp._same_dir(raw2, anchor2))

    # --- 3. create_junction_raw with a DOUBLY-prefixed raw target, to force a
    # PrintName that genuinely starts with \\?\ after the single strip ---
    anchor3 = sandbox / "ANCHOR_RAW_DOUBLE"
    anchor3.mkdir()
    link3 = sandbox / "link_raw_double"
    double_prefixed = "\\\\?\\" + "\\\\?\\" + str(anchor3)
    ok3 = create_junction_raw(double_prefixed, link3)
    print("\n[3] create_junction_raw(double-prefixed) ->", ok3)
    if ok3:
        raw3 = read_link_target(link3)
        print("    read_link_target(link3)      =", repr(raw3))
        print("    starts with extended prefix? =", raw3 is not None and raw3.startswith(("\\\\?\\", "\\\\.\\")))
        print("    _same_dir(raw3, anchor3)     =", lp._same_dir(raw3, anchor3))
        print("    is_junction(link3)           =", is_junction(link3))

    # --- 4. 8.3 short name availability on this volume ---
    print("\n[4] 8.3 short-name probe on sandbox volume")
    long_dir = sandbox / ("A_Very_Long_Directory_Name_For_8dot3_Testing")
    long_dir.mkdir()
    buf = ctypes.create_unicode_buffer(4096)
    n = ctypes.windll.kernel32.GetShortPathNameW(str(long_dir), buf, 4096)
    short_form = buf.value if n else None
    print("    long_dir  =", long_dir)
    print("    short form via GetShortPathNameW =", repr(short_form))
    if short_form and short_form.upper() != str(long_dir).upper():
        print("    DISTINCT short name available -- live short-vs-long _same_dir test IS constructible")
        print("    _same_dir(short_form, long_dir) =", lp._same_dir(short_form, long_dir))
    else:
        print("    NO distinct short name (8dot3 disabled on this volume, matches fsutil query) --")
        print("    live short-vs-long test NOT constructible on this host; falling back to synthetic strings")

finally:
    shutil.rmtree(sandbox, ignore_errors=True)
    print("\nsandbox removed:", not sandbox.exists())
