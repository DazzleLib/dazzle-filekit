"""Exploratory probe (not a test): what does os.path.normpath/normcase
actually do to the edge-case strings _same_dir's norm() feeds it, on THIS
real Windows host? Grounds the adversarial test design in observed
behaviour rather than assumption. No filesystem I/O -- pure string probe.
"""
import os.path as p

CASES = [
    ("drive root vs drive-relative", "C:\\", "C:"),
    ("trailing sep vs none", "C:\\Foo", "C:\\Foo\\"),
    ("dotdot collapse", "C:\\Foo\\Bar\\..", "C:\\Foo"),
    ("both empty", "", ""),
    ("mixed separators", "C:/Foo/Bar", "C:\\Foo\\Bar"),
    ("case", "C:\\FOO", "c:\\foo"),
    ("trailing dot", "C:\\Foo.", "C:\\Foo"),
    ("trailing space", "C:\\Foo ", "C:\\Foo"),
    ("UNC trailing sep", "\\\\server\\share", "\\\\server\\share\\"),
    ("8.3 vs long", "C:\\PROGRA~1", "C:\\Program Files"),
    ("relative vs absolute", "Foo\\Bar", "C:\\Foo\\Bar"),
    ("double backslash mid-path", "C:\\Foo\\\\Bar", "C:\\Foo\\Bar"),
    ("UNC root only", "\\\\server\\share", "\\\\server\\share\\."),
    ("just backslash", "\\", "\\"),
    ("drive root with dotdot", "C:\\Foo\\..", "C:\\"),
    ("drive root with dotdot no-trailing", "C:\\Foo\\..", "C:"),
]

print("%-32s %-22s -> %-16s | %-22s -> %-16s  EQUAL" % (
    "case", "a", "norm(a)", "b", "norm(b)"))
for label, a, b in CASES:
    na = p.normcase(p.normpath(a)).rstrip("\\/")
    nb = p.normcase(p.normpath(b)).rstrip("\\/")
    print("%-32s %-22s -> %-16s | %-22s -> %-16s  %s" % (
        label, repr(a), repr(na), repr(b), repr(nb), na == nb))
