"""Run the 0.5.0 examples in docs/api-reference.md and compare with what the page says.

Pure functions only; nothing is read from or written to disk.
Usage: python tests/one-offs/probe_doc_examples_v050.py   (exit 0 = every line matches)
"""
import sys

from dazzle_filekit import (
    decode_portable_path,
    encode_portable_path,
    key_to_relpath,
    plan_batch,
)

plan = plan_batch([r"C:\proj\a\docs", r"C:\proj\b\docs"], flavor="windows")

CLAIMS = [
    (encode_portable_path(r"C:\Users\x\a.txt", flavor="windows"), "C/Users/x/a.txt"),
    (encode_portable_path("/mnt/c/Users/x/a.txt", flavor="wsl"), "C/Users/x/a.txt"),
    (encode_portable_path("/mnt/c/Users/x/a.txt", flavor="posix"), "ROOT/mnt/c/Users/x/a.txt"),
    (encode_portable_path(r"\\srv\share\a", flavor="windows"), "UNC/srv/share/a"),
    (decode_portable_path("C/Users/x", runtime="wsl"), "/mnt/c/Users/x"),
    (decode_portable_path("C/Users/x", runtime="posix"), None),
    (key_to_relpath(["a", "b.txt"], target_flavor="windows"), "a\\b.txt"),
    (plan.ok, True),
    (plan.bases, [{"native": "C:\\proj", "key": "C/proj"}]),
    ([i.relpath for i in plan.items], ["a/docs", "b/docs"]),
]

bad = 0
for got, said in CLAIMS:
    ok = got == said
    bad += not ok
    print("ok  " if ok else "DIFF", repr(got), "" if ok else "(page says %r)" % (said,))
print("%d of %d match" % (len(CLAIMS) - bad, len(CLAIMS)))
sys.exit(1 if bad else 0)
