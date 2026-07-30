"""What does candidate_roots() actually produce for various edge-shaped
SystemDrive env values? Grounds the pytest assertions for item 4 (whitespace,
bare backslash, UNC root, non-existent drive letter) in observed behaviour.
No filesystem I/O -- candidate_roots() itself never touches disk.
"""
import os

from dazzle_filekit import longpath as lp

CASES = [
    ("missing", None),
    ("empty", ""),
    ("whitespace only", "   "),
    ("bare backslash", "\\"),
    ("UNC root", "\\\\server\\share"),
    ("nonexistent drive letter", "Q:"),
    ("lowercase drive", "c:"),
    ("drive without colon", "C"),
    ("trailing slash already", "C:\\"),
]

saved = {k: os.environ.get(k) for k in ("SystemDrive", "USERPROFILE", "HOME", "TEMP", "TMP")}
try:
    for k in ("USERPROFILE", "HOME", "TEMP", "TMP"):
        os.environ.pop(k, None)

    for label, value in CASES:
        if value is None:
            os.environ.pop("SystemDrive", None)
        else:
            os.environ["SystemDrive"] = value
        roots = lp.candidate_roots()
        first = str(roots[0]) if roots else None
        is_drive_relative = bool(first) and (first.startswith("\\") and not first.startswith("\\\\"))
        print("%-28s SystemDrive=%-18r -> first root=%-30r  drive-relative-danger=%s"
              % (label, value, first, is_drive_relative))
finally:
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
