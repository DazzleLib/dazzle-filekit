"""Does deleting a junction recursively destroy the TARGET's contents?

This is the load-bearing safety question for any shim design: the reaper deletes
junctions constantly, and if recursive removal follows the link, it eats real data.

dazzle_filekit.remove_directory(recursive=True) calls shutil.rmtree() with no
reparse-point guard, so this probe measures what actually happens.

FULLY SANDBOXED: everything happens under a fresh mkdtemp. No real path is touched.
"""
import os
import shutil
import subprocess
import sys
import tempfile

sandbox = tempfile.mkdtemp(prefix="jprobe_")
target = os.path.join(sandbox, "TARGET")
canary = os.path.join(target, "canary.txt")
os.makedirs(target)
with open(canary, "w") as fh:
    fh.write("if you can read this, the target survived\n")

results = []


def make_junction(link):
    ps = ("$ErrorActionPreference='Stop'; "
          f"New-Item -ItemType Junction -Path '{link}' -Target '{target}' | Out-Null")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, text=True)
    return r.returncode == 0 and os.path.exists(link)


def canary_alive():
    return os.path.exists(canary)


print("sandbox:", sandbox)
print("python :", sys.version.split()[0])
print()

# --- what Python thinks a junction IS (drives shutil's behaviour) ---
probe = os.path.join(sandbox, "probe_link")
if make_junction(probe):
    print("  os.path.islink(junction)          : %s" % os.path.islink(probe))
    print("  os.path.isdir(junction)           : %s" % os.path.isdir(probe))
    with os.scandir(sandbox) as it:
        for e in it:
            if e.name == "probe_link":
                print("  entry.is_dir(follow_symlinks=False): %s" % e.is_dir(follow_symlinks=False))
                print("  entry.is_symlink()                : %s" % e.is_symlink())
    print()

# --- TEST 1: raw shutil.rmtree on a junction ---
link1 = os.path.join(sandbox, "link_rmtree")
if make_junction(link1):
    try:
        shutil.rmtree(link1)
        err = None
    except Exception as exc:
        err = "%s: %s" % (type(exc).__name__, exc)
    results.append(("shutil.rmtree(junction)", canary_alive(), os.path.exists(link1), err))

# restore canary if it was eaten, so later tests are independent
if not canary_alive():
    os.makedirs(target, exist_ok=True)
    with open(canary, "w") as fh:
        fh.write("restored\n")

# --- TEST 2: dazzle_filekit.remove_directory(recursive=True) ---
try:
    from dazzle_filekit import remove_directory
    link2 = os.path.join(sandbox, "link_filekit")
    if make_junction(link2):
        rc = remove_directory(link2, recursive=True)
        results.append(("filekit remove_directory(recursive=True)",
                        canary_alive(), os.path.exists(link2), "returned %s" % rc))
except Exception as exc:
    results.append(("filekit remove_directory", None, None, "import/call failed: %s" % exc))

if not canary_alive():
    os.makedirs(target, exist_ok=True)
    with open(canary, "w") as fh:
        fh.write("restored\n")

# --- TEST 3: the SAFE form -- non-recursive rmdir on the reparse point ---
link3 = os.path.join(sandbox, "link_safe")
if make_junction(link3):
    try:
        os.rmdir(link3)          # removes the reparse point only
        err = None
    except Exception as exc:
        err = "%s: %s" % (type(exc).__name__, exc)
    results.append(("os.rmdir(junction)  [SAFE FORM]", canary_alive(), os.path.exists(link3), err))

print("  %-42s %-14s %-12s %s" % ("method", "TARGET SAFE?", "link gone?", "note"))
print("  " + "-" * 92)
for name, safe, link_left, note in results:
    verdict = {True: "YES", False: "*** NO -- DATA LOST ***", None: "?"}[safe]
    print("  %-42s %-14s %-12s %s" % (name, verdict, (not link_left), note or ""))

shutil.rmtree(sandbox, ignore_errors=True)
print("\nsandbox removed:", not os.path.exists(sandbox))
