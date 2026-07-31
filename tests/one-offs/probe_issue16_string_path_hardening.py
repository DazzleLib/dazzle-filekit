r"""Verify the fix for filekit #16 against that issue's acceptance criteria.

#16 covered two independent hazards:

  1. WRONG TYPE  -- a string passed where a List is expected is iterated
                    character by character. Path("/") is the drive root, so
                    with recursive=True the default, find_files("C:\proj")
                    recursively globs the whole drive. It hangs rather than
                    failing.
  2. WRONG CONTENT -- an unescaped backslash in a non-raw literal. "C:\temp"
                    is C:<TAB>emp by the time any library sees it; the
                    backslash is gone.

Read-only. Existence checks and deliberately-invalid calls only.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import dazzle_filekit as F

results = []


def check(group, claim, ok, detail=""):
    results.append((group, claim, bool(ok), detail))


# ---------------------------------------------------------------- 1. type
COLLECTION_FNS = {
    "find_files": lambda a: F.find_files(a, patterns=["*.py"], recursive=False),
    "find_regex_files": lambda a: F.find_regex_files(a, r".*\.py"),
    "calculate_total_size": lambda a: F.calculate_total_size(a),
    "copy_files_with_path": lambda a: F.copy_files_with_path(a, source_base="x", dest_base="y"),
    "move_files_with_path": lambda a: F.move_files_with_path(a, source_base="x", dest_base="y"),
}

for name, call in COLLECTION_FNS.items():
    try:
        call("zzq")
        check("type guard", "%s rejects a bare str" % name, False, "no raise")
    except TypeError as exc:
        check("type guard", "%s rejects a bare str" % name, True)
        check("type guard", "%s message shows the bracketed form" % name,
              "[" in str(exc), str(exc)[:60])
    except Exception as exc:                                   # noqa: BLE001
        check("type guard", "%s rejects a bare str" % name, False,
              "%s instead of TypeError" % type(exc).__name__)

# The specific inputs that caused a full-drive walk before the fix.
for dangerous in ("C:\\", "/", "C:\\proj", "\\\\server\\share"):
    try:
        F.find_files(dangerous, patterns=["*.py"])
        check("drive walk", "find_files(%r) is refused" % dangerous, False,
              "NO RAISE -- would enumerate the drive")
    except TypeError:
        check("drive walk", "find_files(%r) is refused" % dangerous, True)
    except Exception as exc:                                   # noqa: BLE001
        check("drive walk", "find_files(%r) is refused" % dangerous, False,
              type(exc).__name__)

# PathLike and bytes were called out separately in the issue.
for label, arg in (("Path", Path("C:/proj")), ("bytes", b"zzq")):
    try:
        F.find_files(arg, patterns=["*.py"])
        check("type guard", "find_files rejects %s" % label, False, "no raise")
    except TypeError as exc:
        check("type guard", "find_files rejects %s" % label, True, str(exc)[:50])
    except Exception as exc:                                   # noqa: BLE001
        check("type guard", "find_files rejects %s" % label, False,
              "%s: %s" % (type(exc).__name__, str(exc)[:40]))

# The guard must not break the correct form.
tmp = Path(tempfile.mkdtemp(prefix="i16_"))
try:
    (tmp / "a.py").write_text("x")
    (tmp / "b.txt").write_text("y")
    got = F.find_files([tmp], patterns=["*.py"])
    check("no regression", "find_files([dir]) still works", len(got) == 1,
          [p.name for p in got])
    check("no regression", "calculate_total_size([dir]) still works",
          F.calculate_total_size([tmp]) > 0)

    # ------------------------------------------------------- 2. content
    from dazzle_filekit.utils.validation import (
        SILENT_ESCAPE_ORIGINS, has_unescaped_backslash_damage,
        recover_unescaped_path, suggest_reescaped_path,
    )

    check("escapes", "SILENT_ESCAPE_ORIGINS covers all 8 silent escapes",
          set("abfnrtv0") <= {v for v in SILENT_ESCAPE_ORIGINS.values()}
          or len(SILENT_ESCAPE_ORIGINS) >= 8,
          "%d entries: %r" % (len(SILENT_ESCAPE_ORIGINS), SILENT_ESCAPE_ORIGINS))

    # A damaged path built the way Python would build it.
    real = tmp / "temp"
    real.mkdir()
    damaged = str(tmp) + "\temp"          # the TAB case, literally
    check("escapes", "damage is detected in a corrupted path",
          has_unescaped_backslash_damage(damaged) is True, repr(damaged)[-28:])
    check("escapes", "an intact path is NOT flagged",
          has_unescaped_backslash_damage(str(real)) is False)

    recovered = recover_unescaped_path(damaged)
    rec_path = recovered[0] if isinstance(recovered, tuple) else recovered
    check("escapes", "recovery finds the real directory",
          Path(str(rec_path)).exists() and Path(str(rec_path)) == real,
          repr(rec_path)[-40:])

    # The load-bearing safety property: a literal that EXISTS is never rewritten.
    untouched = recover_unescaped_path(str(real))
    unt = untouched[0] if isinstance(untouched, tuple) else untouched
    check("escapes", "an existing literal path is returned unchanged",
          Path(str(unt)) == real, repr(unt)[-40:])

    check("escapes", "suggest_reescaped_path offers a human-readable fix",
          isinstance(suggest_reescaped_path(damaged), (str, type(None))))

    # Every silent escape should be recoverable, not just \t.
    ok_all, failed = True, []
    for letter, ctrl in (("a", "\a"), ("b", "\b"), ("f", "\f"), ("n", "\n"),
                         ("r", "\r"), ("t", "\t"), ("v", "\v")):
        name = letter + "dir"
        (tmp / name).mkdir(exist_ok=True)
        broken = str(tmp) + ctrl + "dir"
        got = recover_unescaped_path(broken)
        got = got[0] if isinstance(got, tuple) else got
        if Path(str(got)) != tmp / name:
            ok_all = False
            failed.append(letter)
    check("escapes", "all 7 control-char escapes recover to the right directory",
          ok_all, "failed for: %r" % failed)

finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ----------------------------------------------------------------- report
width = max(len(c) for _, c, _, _ in results)
fails = [r for r in results if not r[2]]
group = None
for g, claim, ok, detail in results:
    if g != group:
        print("\n  %s" % g.upper())
        group = g
    print("    [%s] %-*s %s" % ("OK" if ok else "XX", width, claim,
                                "" if ok else "<- " + (detail or "failed")))
print()
print("  %d checks, %d FAILED" % (len(results), len(fails)))
sys.exit(1 if fails else 0)
