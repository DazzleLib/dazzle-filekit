"""Probe: what target string does Windows actually store for symlinks/junctions
created via (1) os.symlink, (2) win32file.CreateSymbolicLink, (3) ctypes
CreateSymbolicLinkW, and (4) PowerShell New-Item junction?

Motivation (2026-07-21, linkmirror design): mirroring links from D: to B: must
reproduce the raw reparse target verbatim. An earlier scratch test showed
os.symlink storing an absolute target as \\?\-prefixed. This probe measures
all creation methods against relative / absolute / dotted / broken targets so
create_symlink's verbatim mode is designed from data, not assumption.

Run: python tests/one-offs/probe_symlink_target_fidelity.py
"""
import ctypes
import os
import shutil
import subprocess
import tempfile

BASE = tempfile.mkdtemp(prefix="fidelity_probe_")

CASES = [
    ("rel_simple", r"sub\file.txt"),
    ("rel_dotted", r"..\other\file.txt"),
    ("rel_broken", r"sub\nonexistent.txt"),
    ("abs_short", r"C:\Windows\notepad.exe"),
    ("abs_broken", r"C:\no\such\path.txt"),
    ("abs_prefixed", "\\\\?\\C:\\Windows\\notepad.exe"),
]


def report(label, link):
    try:
        raw = os.readlink(link)
    except OSError as e:
        raw = "<readlink failed: %s>" % e
    print("  %-14s stored=%r" % (label, raw))


def probe_os_symlink():
    print("[os.symlink]")
    d = os.path.join(BASE, "os_symlink")
    os.makedirs(d)
    for name, target in CASES:
        link = os.path.join(d, name)
        try:
            os.symlink(target, link)
        except OSError as e:
            print("  %-14s CREATE FAILED: %s" % (name, e))
            continue
        print("  %-14s given =%r" % (name, target))
        report(name, link)


def probe_ctypes():
    print("[ctypes CreateSymbolicLinkW, flags=ALLOW_UNPRIVILEGED]")
    d = os.path.join(BASE, "ctypes_csl")
    os.makedirs(d)
    fn = ctypes.windll.kernel32.CreateSymbolicLinkW
    fn.restype = ctypes.c_ubyte
    for name, target in CASES:
        link = os.path.join(d, name)
        ok = fn(link, target, 0x2)  # file symlink, unprivileged
        if not ok:
            print("  %-14s CREATE FAILED: winerror=%d" % (name, ctypes.get_last_error()))
            continue
        print("  %-14s given =%r" % (name, target))
        report(name, link)


def probe_pywin32():
    print("[win32file.CreateSymbolicLink]")
    try:
        import win32file
    except ImportError:
        print("  pywin32 not available")
        return
    d = os.path.join(BASE, "win32_csl")
    os.makedirs(d)
    for name, target in CASES:
        link = os.path.join(d, name)
        try:
            win32file.CreateSymbolicLink(link, target, 0x2)
        except Exception as e:
            print("  %-14s CREATE FAILED: %s" % (name, e))
            continue
        print("  %-14s given =%r" % (name, target))
        report(name, link)


def probe_junction():
    print("[PowerShell New-Item Junction]")
    d = os.path.join(BASE, "junctions")
    os.makedirs(d)
    tgt = os.path.join(BASE, "junction_target")
    os.makedirs(tgt)
    link = os.path.join(d, "junc1")
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "New-Item -ItemType Junction -Path '%s' -Target '%s' | Out-Null" % (link, tgt)],
        capture_output=True, text=True)
    if r.returncode != 0:
        print("  CREATE FAILED: %s" % r.stderr.strip())
        return
    print("  given =%r" % tgt)
    report("junc1", link)


if __name__ == "__main__":
    print("base: %s" % BASE)
    probe_os_symlink()
    probe_ctypes()
    probe_pywin32()
    probe_junction()
    shutil.rmtree(BASE, ignore_errors=True)
    print("done (cleaned up)")
