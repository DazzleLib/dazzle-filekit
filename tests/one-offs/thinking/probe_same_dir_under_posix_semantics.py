"""Would the ungated `_same_dir` tests pass on Linux / macOS CI?

`_same_dir` is built on `os.path.normcase` / `normpath` / `splitdrive`, all of
which are POSIX no-ops or behave differently off Windows:

  posixpath.splitdrive("C:")  -> ("", "C:")      # no drive concept
  posixpath.normcase(s)       -> s               # no case folding
  posixpath.normpath("C:\\")  -> "C:\\"          # backslash is an ordinary char

So a test asserting Windows semantics without `@win_only` will run on the
ubuntu-latest and macos-latest legs of the CI matrix and can fail there. This
repo has been bitten before -- v0.3.3 shipped a Windows-host-locked probe suite
that ubuntu CI caught on push.

Read-only: swaps `os.path` for `posixpath` in-process, restores it, touches
nothing on disk.
"""
import os
import posixpath

from dazzle_filekit import longpath as lp

CASES = [
    ("C:", "C:\\", False),                     # drive-relative vs drive root
    ("C:\\Foo\\..", "C:", False),
    ("C:\\", "C:\\", True),
    ("C:\\Foo", "C:\\Foo\\", True),
    ("C:\\Foo\\Bar\\..", "C:\\FOO", True),     # case-insensitive
]

real_path = os.path
print("  %-22s %-12s %-9s %-9s %s" % ("a", "b", "windows", "posix", "verdict"))
print("  " + "-" * 68)

rows = []
for a, b, expected in CASES:
    os.path = real_path
    win = lp._same_dir(a, b)
    os.path = posixpath
    try:
        pos = lp._same_dir(a, b)
    finally:
        os.path = real_path
    diverges = win != pos
    rows.append(diverges)
    print("  %-22r %-12r %-9s %-9s %s"
          % (a, b, win, pos, "DIVERGES -- would fail CI" if diverges else "same"))

print()
print("  cases whose result changes off Windows: %d of %d"
      % (sum(rows), len(rows)))
print("  => any test asserting these MUST carry @win_only"
      if any(rows) else "  => safe to run unGated")
