"""Which calls inside create_shim's per-candidate loop raise for a NUL-
embedded `link` path, and are any of them NOT already wrapped by create_shim's
own try/except (OSError, ValueError) around mkdir? Anything that raises here
and is NOT internally caught is only saved by shim_path's NEW outer wrapper --
exactly what item 3 of the delta asks to verify.

Pure exploration, no real junctions created (NUL paths can't be created
anyway -- that's the point).
"""
from pathlib import Path

from dazzle_filekit.utils.validation import is_junction

bad = "C:\\somewhere\\x\x00y"

print("Path(bad).exists() ->", end=" ")
try:
    print(Path(bad).exists())
except Exception as e:
    print("RAISED", type(e).__name__, e)

print("is_junction(bad) ->", end=" ")
try:
    print(is_junction(bad))
except Exception as e:
    print("RAISED", type(e).__name__, e)

print("Path(bad).is_dir() ->", end=" ")
try:
    print(Path(bad).is_dir())
except Exception as e:
    print("RAISED", type(e).__name__, e)

# what create_shim actually does with a NUL-bearing `link` argument built from
# a NUL-bearing root: link = root / _anchor_id(...)  (id itself is a clean
# hex digest, so the NUL only ever arrives via root)
import dazzle_filekit.longpath as lp
bad_root = "C:\\tmp\x00root"
link = Path(bad_root) / "abcd"
print()
print("simulated create_shim link:", repr(str(link)))
print("is_junction(link) ->", end=" ")
try:
    print(is_junction(link))
except Exception as e:
    print("RAISED", type(e).__name__, e)
print("link.exists() ->", end=" ")
try:
    print(link.exists())
except Exception as e:
    print("RAISED", type(e).__name__, e)
