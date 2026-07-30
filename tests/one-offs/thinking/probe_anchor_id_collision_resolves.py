"""Does the collision FIX actually resolve, or merely fail safely?

The adversarial test asserts the caller never gets the wrong directory's
content. Returning False satisfies that too -- and would mean every colliding
anchor silently loses its shim and falls back to an unopenable path. That is a
much quieter failure than the bug it replaced, so it is worth measuring rather
than assuming.

Sandboxed under mkdtemp; no real path touched.
"""
import os
import shutil
import tempfile
from pathlib import Path

from dazzle_filekit import longpath as lp

sandbox = Path(tempfile.mkdtemp(prefix="collide_"))
root = sandbox / ".dzs"
root.mkdir()

a = sandbox / "ANCHOR_A"
b = sandbox / "ANCHOR_B"
for d, text in ((a, "FROM_A"), (b, "FROM_B")):
    d.mkdir()
    (d / "doc.txt").write_text(text)

# Force both anchors onto the SAME 4-char id, then let the fix cope.
real_anchor_id = lp._anchor_id


def colliding(anchor, length=lp._ID_LEN):
    if length <= lp._ID_LEN:
        return "cafe"                      # every anchor collides at 4 chars
    return real_anchor_id(anchor, length)  # distinct once lengthened


lp._anchor_id = colliding
try:
    plan_a = lp.ShimPlan(original=a / "doc.txt", needed=True, anchor=a,
                         link=root / "cafe", shimmed=root / "cafe" / "doc.txt")
    plan_b = lp.ShimPlan(original=b / "doc.txt", needed=True, anchor=b,
                         link=root / "cafe", shimmed=root / "cafe" / "doc.txt")

    ok_a = lp.create_shim(plan_a)
    ok_b = lp.create_shim(plan_b)

    print("  create_shim(A) -> %s   link=%s" % (ok_a, plan_a.link.name))
    print("  create_shim(B) -> %s   link=%s" % (ok_b, plan_b.link.name))
    print()

    read_a = Path(plan_a.shimmed).read_text() if ok_a else "(no shim)"
    print("  A reads: %-10s  expected FROM_A   %s"
          % (read_a, "OK" if read_a == "FROM_A" else "*** WRONG ***"))

    if ok_b:
        read_b = Path(plan_b.shimmed).read_text()
        verdict = "OK" if read_b == "FROM_B" else "*** WRONG -- SERVED A ***"
        print("  B reads: %-10s  expected FROM_B   %s" % (read_b, verdict))
        print()
        print("  VERDICT: collision RESOLVED -- B got its own shim at %r"
              % plan_b.link.name)
    else:
        print("  B reads: (no shim -- create_shim returned False)")
        print()
        print("  VERDICT: collision only FAILED SAFELY. No wrong data, but B "
              "loses its shim entirely and falls back to an unopenable path.")
finally:
    lp._anchor_id = real_anchor_id
    for child in root.iterdir() if root.is_dir() else []:
        try:
            if lp.is_junction(child):
                os.rmdir(child)
        except OSError:
            pass
    shutil.rmtree(sandbox, ignore_errors=True)
    print("\n  sandbox removed: %s" % (not sandbox.exists()))
