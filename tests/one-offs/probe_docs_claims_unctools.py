"""Verify every factual claim in docs/unctools-integration.md by running it.

Docs rot silently: a claim that was true at v0.3.0 keeps reading as true after
the behaviour moves. This probe executes the documented examples and compares
against what the docs promise, so a mismatch is a test failure rather than a
reader's surprise.

Read-only: no filesystem mutation, no network. UNC examples use a
deliberately non-existent host, since every claim under test is about how a
path STRING is classified, not about reaching a server.
"""
import inspect
import os

import dazzle_filekit as F

results = []


def check(claim, got, expected, note=""):
    ok = got == expected
    results.append((ok, claim, got, expected, note))


# --- "UNC detection (delegates to the L0 owner)" -------------------------
check('is_unc_path(r"\\\\server\\share\\folder\\file.txt")',
      F.is_unc_path(r"\\server\share\folder\file.txt"), True)
check('is_unc_path("//server/share/folder/file.txt")  [claimed: True on EVERY platform]',
      F.is_unc_path("//server/share/folder/file.txt"), True)
check('is_unc_path(r"C:\\Users\\foo\\file.txt")',
      F.is_unc_path(r"C:\Users\foo\file.txt"), False)

# The two export sites: SEPARATE objects that AGREE, which is what the doc
# now says. An earlier draft claimed they were one shared definition; this
# pins the corrected wording so a future refactor cannot silently un-true it
# in either direction.
try:
    from dazzle_filekit.utils import is_unc_path as utils_is_unc
    check("the two export sites are separate objects (doc says so explicitly)",
          F.is_unc_path is not utils_is_unc, True)
    SAMPLE = [r"\\server\share", "//server/share", r"C:\Users\foo", "",
              r"\\?\C:\Users\foo", r"\\.\pipe\x", "  \\\\server\\share  "]
    check("...but agree on every sampled input",
          all(F.is_unc_path(s) == utils_is_unc(s) for s in SAMPLE), True,
          note="%d inputs; full 20-case sweep in "
               "tests/one-offs/thinking/probe_is_unc_path_two_definitions.py"
               % len(SAMPLE))
except ImportError as exc:
    check("dazzle_filekit.utils.is_unc_path importable", "ImportError: %s" % exc, True)

# "delegates to unctools.is_unc_path (the L0 path-identity owner)"
try:
    import unctools
    src = inspect.getsource(F.is_unc_path)
    check("filekit.is_unc_path delegates to unctools (mentions it in its body)",
          "unctools" in src, True,
          note="source-level check; see body if this flips")
except Exception as exc:                                    # noqa: BLE001
    check("unctools importable", "ERR %s" % exc, True)

# --- "Classifying a filesystem object vs. a path's origin" ---------------
home = os.path.expanduser("~")
check('classify_fs_object(<an existing directory>)',
      F.classify_fs_object(home), "directory")

try:
    from unctools import classify_path_origin
    check('unctools.classify_path_origin(r"\\\\server\\share")',
          classify_path_origin(r"\\server\share"), "unc")
except ImportError:
    check("unctools.classify_path_origin importable", "ImportError", True)

# --- "Normalization preserves UNC form" ----------------------------------
got = F.normalize_cross_platform_path(r"\\server\share\a\b\..\c\file.txt")
check('normalize_cross_platform_path collapses ".." and keeps the UNC prefix',
      str(got).replace("\\", "/"), "//server/share/a/c/file.txt",
      note="docs show WindowsPath('//server/share/a/c/file.txt')")

# --- "try_path_variants= / resolver= are available on ..." ---------------
DOCUMENTED = ["open_file", "copy_file", "move_file", "copy_files_with_path",
              "move_files_with_path", "process_files",
              "replace_in_file", "batch_replace_in_files"]
for name in DOCUMENTED:
    fn = getattr(F, name, None)
    if fn is None:
        check("%s exists" % name, False, True)
        continue
    params = inspect.signature(fn).parameters
    check("%s accepts try_path_variants= and resolver=" % name,
          ("try_path_variants" in params and "resolver" in params), True)

# --- "Because UNCtools is always installed" (a hard dependency) ----------
try:
    import unctools
    check("unctools importable without an extra", True, True,
          note="version %s" % getattr(unctools, "__version__", "?"))
    for fname in ("convert_to_local",):
        check("unctools.%s exists (used in docs Patterns 1 and 2)" % fname,
              hasattr(unctools, fname), True)
except ImportError:
    check("unctools importable without an extra", False, True)

# --- report --------------------------------------------------------------
width = max(len(c) for _, c, _, _, _ in results)
fails = 0
for ok, claim, got, expected, note in results:
    if not ok:
        fails += 1
    print("  [%s] %-*s" % ("OK" if ok else "XX", width, claim))
    if not ok:
        print("        got=%r  expected=%r" % (got, expected))
    elif note:
        print("        (%s)" % note)

print()
print("  %d claims checked, %d MISMATCH" % (len(results), fails))
if fails:
    print("  -> docs/unctools-integration.md overstates or misstates the above")
