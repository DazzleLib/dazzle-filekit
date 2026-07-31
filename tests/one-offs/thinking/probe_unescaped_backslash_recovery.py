r"""How bad is the unescaped-backslash problem, and is recovery unambiguous?

A user writes this in Python source:

    find_files("C:\temp")

`\t` is a TAB. By the time any library sees the argument the escape is already
resolved, so the string is "C:<TAB>emp" -- the backslash is gone and cannot be
recovered by inspecting the source. What CAN be done is notice that the string
contains a control character where a path separator plausibly belongs, and test
whether re-inserting the backslash names something real.

This probe answers three questions before any of that is designed:

  1. WHICH escapes corrupt a path silently (vs. raising SyntaxError)?
  2. How often does the corruption land on a plausible real directory name?
  3. Is the recovery UNAMBIGUOUS -- can the literal and the recovered path
     both exist, so that "fixing" it would pick the wrong one?

Read-only. Existence checks only; nothing is created, written, or deleted.
"""
import os
from pathlib import Path

# Every single-character escape Python recognizes in a normal string literal.
# The ones that RAISE (\x, \u, \U, \N with bad payloads) are loud and therefore
# not the problem; the silent ones are what corrupt paths.
SILENT = {
    "a": "\a", "b": "\b", "f": "\f", "n": "\n",
    "r": "\r", "t": "\t", "v": "\v", "0": "\0",
}
# \p, \d, \s, \w ... are NOT escapes: Python leaves the backslash intact.
INERT = list("cdegijklmopqsuwyz")

print("  1. WHICH escapes bite")
print("     silent corruption (backslash vanishes):",
      " ".join("\\" + k for k in SILENT))
print("     left intact by Python           :",
      " ".join("\\" + c for c in INERT[:10]), "...")
print()

print("  2. PLAUSIBLE directory names that start with a silent escape letter")
victims = {
    "t": ["temp", "tools", "test", "tmp", "tasks"],
    "b": ["bin", "build", "backup", "bak"],
    "n": ["new", "notes", "node_modules"],
    "a": ["app", "assets", "archive"],
    "r": ["repo", "resources", "releases"],
    "f": ["files", "fonts"],
    "v": ["var", "video", "vendor"],
    "0": ["0-inbox"],
}
total = sum(len(v) for v in victims.values())
print("     %d common names across %d escape letters -- e.g. C:\\temp, C:\\bin,"
      % (total, len(victims)))
print("     C:\\new, C:\\app, C:\\repo all corrupt silently.")
print()

print("  3. WHAT THE CORRUPTED STRING LOOKS LIKE")
for letter in ("t", "b", "n"):
    name = victims[letter][0]
    literal = "C:" + SILENT[letter] + name[1:]     # what Python actually builds
    intended = "C:\\" + name
    print("     source  %-14s -> received %-22r  intended %r"
          % ('"C:\\%s"' % name, literal, intended))
print()

print("  4. IS RECOVERY UNAMBIGUOUS?")
print("     Recovery rule: if the literal does NOT exist, re-insert a backslash")
print("     before the control char and test that. Ambiguity would mean BOTH")
print("     exist. A path containing a raw control character is essentially")
print("     never created deliberately on Windows -- NTFS forbids chars < 0x20")
print("     in filenames outright.")
print()
forbidden = all(ord(c) < 0x20 for c in SILENT.values() if c != "\0")
print("     all silent-escape chars are < 0x20 (NTFS-illegal in a name):", forbidden)
print("     -> the literal interpretation can never name a real NTFS file,")
print("        so recovery cannot pick the wrong one of two valid paths.")
print()

print("  5. DOES THE HAZARD SURVIVE THE FIX? (the find_files case)")
print("     Even with recovery, a STRING passed where a LIST is expected is")
print("     still iterated character by character. Recovery addresses the")
print("     wrong-content problem; it does not address the wrong-TYPE problem.")
print("     Both need handling, and the type check is the cheaper of the two.")
print()

print("  6. LIVE CHECK on this machine")
probe_pairs = [("C:" + SILENT["t"] + "emp", r"C:\temp"),
               ("C:" + SILENT["b"] + "in", r"C:\bin"),
               ("C:" + SILENT["a"] + "pp", r"C:\app")]
for literal, intended in probe_pairs:
    print("     %-18r exists=%-5s | %-10s exists=%s"
          % (literal, os.path.exists(literal), intended, os.path.exists(intended)))
