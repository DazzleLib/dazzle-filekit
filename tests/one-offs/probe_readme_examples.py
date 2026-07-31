"""Execute the README's Quick Start examples against a real temporary tree.

The README is the most-read page in the project and its examples were wrong in
two places that a reader would hit immediately:

  find_files("/directory", ...)      -- search_paths is a LIST. A string is
                                        iterated character by character, and
                                        Path("/") is the drive root, so with
                                        recursive=True this attempts to walk
                                        the entire filesystem. It hangs.
  calculate_file_hash(p, algorithm=) -- the parameter is `algorithms` (a list)
                                        and the return is a dict, not a string.
  verify_file_hash(p, h, algorithm=) -- takes a DICT of expected hashes and
                                        returns a (bool, dict) tuple.

Both raised TypeError or hung. This pins the corrected forms so the same class
of error cannot come back unnoticed.

Sandboxed under mkdtemp; no real path is read or written.
"""
import shutil
import sys
import tempfile
from pathlib import Path

import dazzle_filekit as F
from dazzle_filekit import (
    atomic_write_json,
    atomic_write_text,
    calculate_file_hash,
    calculate_file_hash_native,
    find_files,
    is_unc_path,
    normalize_cross_platform_path,
    verify_file_hash,
)

results = []


def check(claim, ok, detail=""):
    results.append((claim, bool(ok), detail))


sandbox = Path(tempfile.mkdtemp(prefix="readme_"))
try:
    (sandbox / "a.py").write_text("print('a')\n")
    (sandbox / "b.txt").write_text("b\n")
    (sandbox / "skip.md").write_text("# skip\n")

    # --- Path Operations -------------------------------------------------
    p = normalize_cross_platform_path("/some/path/../file.txt")
    check("normalize_cross_platform_path returns a Path", isinstance(p, Path), repr(p))

    files = find_files([sandbox], patterns=["*.py", "*.txt"])
    check("find_files([dir], patterns=...) finds exactly the 2 matches",
          len(files) == 2, sorted(x.name for x in files))
    check("...and returns Path objects, as the comment now says",
          all(isinstance(x, Path) for x in files))

    check("is_unc_path on a UNC string", is_unc_path(r"\\server\share") is True)

    # --- File Verification -----------------------------------------------
    target = sandbox / "a.py"

    hashes = calculate_file_hash(target)
    check("calculate_file_hash(p) returns a dict, default SHA256",
          isinstance(hashes, dict) and "SHA256" in hashes, repr(hashes)[:60])

    multi = calculate_file_hash(target, algorithms=["md5", "sha256"])
    check("calculate_file_hash(algorithms=[...]) returns one entry per algorithm",
          isinstance(multi, dict) and set(multi) == {"md5", "sha256"}, repr(multi)[:70])

    expected = {"sha256": multi["sha256"]}
    verdict = verify_file_hash(target, expected)
    check("verify_file_hash(p, dict) returns a (bool, dict) tuple",
          isinstance(verdict, tuple) and len(verdict) == 2, repr(verdict)[:60])
    check("...and reports a match as True", verdict[0] is True)

    wrong = verify_file_hash(target, {"sha256": "0" * 64})
    check("...and a mismatch as False", wrong[0] is False)

    # the documented caller-side fallback
    digest = (calculate_file_hash_native(target, algorithm="sha256")
              or calculate_file_hash(target, algorithms=["sha256"])["sha256"])
    check("the documented `native(p) or calculate_file_hash(p)` fallback yields a digest",
          isinstance(digest, str) and len(digest) == 64, repr(digest)[:70])

    # --- Atomic Writes ---------------------------------------------------
    atomic_write_text(sandbox / "t.txt", "content")
    check("atomic_write_text wrote the file",
          (sandbox / "t.txt").read_text() == "content")
    atomic_write_json(sandbox / "t.json", {"k": 1})
    check("atomic_write_json wrote valid JSON", '"k"' in (sandbox / "t.json").read_text())

finally:
    shutil.rmtree(sandbox, ignore_errors=True)

width = max(len(c) for c, _, _ in results)
fails = [r for r in results if not r[1]]
for claim, ok, detail in results:
    print("  [%s] %-*s %s" % ("OK" if ok else "XX", width, claim,
                              "" if ok else "<- %s" % (detail or "failed")))
print()
print("  %d README claims checked, %d FAILED" % (len(results), len(fails)))
sys.exit(1 if fails else 0)
