"""Pure pathlib probe (no filesystem I/O): does Path.relative_to() raise for
a bare drive-letter anchor like Path("C:"), which would block create_shim's
`rel = Path(plan.original).relative_to(anchor)` line before _same_dir is
ever reached? Settles whether the drive-root-vs-drive-relative collapse found
in _same_dir's normpath probe is actually reachable through create_shim's
real call sequence, or only exists as a property of _same_dir in isolation.
"""
from pathlib import Path

p1 = Path("C:\\Foo\\file.pdf")
print("rooted original:", p1, " parents:", [str(x) for x in p1.parents])
try:
    r = p1.relative_to(Path("C:"))
    print("p1.relative_to(Path('C:')) =", r)
except ValueError as e:
    print("p1.relative_to(Path('C:')) raised ValueError:", e)

print()
p2 = Path("C:SomeDir\\file.pdf")
print("drive-relative original:", repr(p2), "anchor=", repr(p2.anchor),
      "root=", repr(p2.root), "drive=", repr(p2.drive))
print("drive-relative .parent:", repr(p2.parent))
print("drive-relative .parents:", [repr(x) for x in p2.parents])
try:
    r2 = p2.relative_to(Path("C:"))
    print("p2.relative_to(Path('C:')) =", r2)
except ValueError as e:
    print("p2.relative_to(Path('C:')) raised ValueError:", e)

print()
print("Path('C:').parts        =", Path("C:").parts)
print("Path('C:\\\\').parts      =", Path("C:\\").parts)
print("Path('C:').is_absolute()   =", Path("C:").is_absolute())
print("Path('C:\\\\').is_absolute() =", Path("C:\\").is_absolute())
print("Path('C:') == Path('C:\\\\') =", Path("C:") == Path("C:\\"))

print()
# Can plan_shim's own ancestor walk ever PRODUCE a bare-drive anchor?
# original.parent, then .parents, starting from a ROOTED original (the only
# kind plan_shim's caller realistically constructs from needs_shim()'s own
# over-threshold check, since Path(path) applied to a short/relative string
# wouldn't trip the length threshold in the first place at any real depth).
deep = Path("D:\\") / ("dirxxx" * 40) / ("f" * 40 + ".pdf")
ancestors = [deep.parent] + list(deep.parent.parents)
print("plan_shim-style ancestors for a rooted original:", [str(a) for a in ancestors])
