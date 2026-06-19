# Using dazzle-filekit with UNCtools

This guide explains how `dazzle_filekit` (L1, file-operation primitives) and
[UNCtools](https://github.com/DazzleLib/UNCtools) (L0, path-identity) relate in
the DazzleLib stack, and how to use the seam between them.

**Short version**: as of filekit **0.3.0**, UNCtools is a **hard dependency**.
filekit owns *what you do to a file*; UNCtools owns *what a path's name is*
(UNC ↔ mapped-drive identity). filekit's operations can optionally retry under a
path's other names by consulting UNCtools through a small, well-defined seam (the
`PathVariantResolver`), and filekit's `is_unc_path` delegates to UNCtools as the
single source of truth.

---

## What you get out of the box

Installing filekit installs UNCtools (and the stack bedrock `dazzle-lib`)
automatically:

```bash
pip install dazzle-filekit        # also pulls dazzle-lib>=0.2.0, unctools>=0.2.2
pip install dazzle-filekit[windows]  # + pywin32 for the rich Windows features
```

There is no longer an optional `[unctools]` extra -- UNCtools' base is
pure-Python, and filekit already requires pywin32 on Windows, so making it a hard
dependency costs little and removes the optional-load awkwardness.

### UNC detection (delegates to the L0 owner)

```python
from dazzle_filekit import is_unc_path

is_unc_path(r"\\server\share\folder\file.txt")  # True
is_unc_path("//server/share/folder/file.txt")   # True on every platform (0.3.0)
is_unc_path(r"C:\Users\foo\file.txt")            # False
```

`is_unc_path` normalizes `/` → `\` and then checks the `\\` prefix -- so
forward-slash UNC is recognized everywhere. It is one canonical definition that
delegates to `unctools.is_unc_path` (the L0 path-identity owner); the two filekit
export sites (`dazzle_filekit.is_unc_path` and `dazzle_filekit.utils.is_unc_path`)
both resolve to it.

### Classifying a filesystem object vs. a path's origin

These answer two *different* questions -- note which layer owns which:

```python
from dazzle_filekit import classify_fs_object   # L1: WHAT the object IS
from unctools import classify_path_origin        # L0: WHERE the path's name comes from

classify_fs_object(r"C:\Users\foo")     # 'directory'  (file/directory/symlink/...)
classify_fs_object(some_junction)       # 'directory'  (use links.analyze_link for link-kind)

classify_path_origin(r"\\server\share") # 'unc'
classify_path_origin(r"Z:\mapped")      # 'network' / 'subst' / 'local' (unctools probes the drive)
```

> `classify_fs_object` was named `get_path_type` before 0.3.0. It classifies the
> *object kind* (`'file'`, `'directory'`, `'symlink'`, ...), NOT the path's
> network origin -- that is `unctools.classify_path_origin`'s job.

### Normalization preserves UNC form

```python
from dazzle_filekit import normalize_cross_platform_path

p = normalize_cross_platform_path(r"\\server\share\a\b\..\c\file.txt")
# -> WindowsPath('//server/share/a/c/file.txt') -- '..' collapsed lexically,
#    UNC prefix preserved (pass resolve=True to follow symlinks instead).
```

---

## The resolver edge: UNC ↔ mapped-drive fallback

The reason UNCtools is a hard dependency is the **resolver edge**. filekit's file
operations can optionally retry an operation under a path's *other* names -- if a
copy fails on the UNC form (`\\server\share\...`), filekit can retry on the mapped
drive (`Z:\...`) and vice-versa. This is opt-in per call via `try_path_variants=`:

```python
from dazzle_filekit import copy_file, open_file

# Default: behave exactly as before (no fallback).
copy_file(src, dst)

# Opt in: on PermissionError/FileNotFoundError/OSError, retry across the path's
# UNC <-> mapped-drive variants (resolved by unctools, the default resolver).
copy_file(src, dst, try_path_variants=True)

with open_file(unc_path, "rb", try_path_variants=True) as fh:
    data = fh.read()
```

`try_path_variants=` / `resolver=` are available on `open_file`, `copy_file`,
`move_file`, `copy_files_with_path`, `move_files_with_path`, `process_files`, and
the `content.*` helpers. The resolver is a `dazzle_lib.PathVariantResolver`
(structural Protocol); unctools is the default, but you can pass your own
`resolver=` to supply alternative path names.

---

## Composition patterns (explicit UNC ↔ drive conversion)

When you want to convert *eagerly* (not just as a fallback), use UNCtools directly.
Because UNCtools is always installed, the old `try/except ImportError` dance is no
longer required.

### Pattern 1: "Give me a local path if possible, otherwise the UNC"

```python
from dazzle_filekit import normalize_cross_platform_path, is_unc_path
from unctools import convert_to_local

def to_usable_path(raw: str) -> str:
    """Normalize and prefer a mapped drive letter over a UNC form."""
    normalized = str(normalize_cross_platform_path(raw))
    if is_unc_path(normalized):
        return str(convert_to_local(normalized))  # unchanged if not mapped
    return normalized
```

### Pattern 2: "Convert before a cross-boundary operation"

```python
from dazzle_filekit import copy_file, is_unc_path
from unctools import convert_to_local

def smart_copy(src: str, dst: str) -> bool:
    if is_unc_path(src):
        src = str(convert_to_local(src))
    if is_unc_path(dst):
        dst = str(convert_to_local(dst))
    return copy_file(src, dst)

# Or, equivalently, let the resolver edge handle it lazily:
#     copy_file(src, dst, try_path_variants=True)
```

### Pattern 3: "Detect everything, use native path operations"

```python
from dazzle_filekit import is_unc_path, normalize_cross_platform_path, collect_file_metadata

def describe(path: str) -> dict:
    p = normalize_cross_platform_path(path)
    return {
        "path": str(p),
        "is_unc": is_unc_path(p),
        "metadata": collect_file_metadata(p),  # -> dazzle_lib.FileMetadataDict
    }
```

---

## Why a hard dependency (the layered design)

In the frozen [DazzleLib STACK-MAP](https://github.com/DazzleLib/.github/blob/main/docs/STACK-MAP.md),
UNCtools is **L0** (path identity: UNC ↔ drive, origin classification) and filekit
is **L1** (file-operation primitives). L1 may depend on L0. The seam between them
is the `PathVariantResolver` Protocol in the **bedrock** package `dazzle-lib` (D7):
filekit depends on the *Protocol*, and unctools *satisfies* it. This keeps the two
libraries composable without filekit reaching into unctools' internals -- filekit
only ever asks "what are this path's other names?" through the seam.

UNCtools also owns drive↔UNC *mapping tables* (it absorbed filekit's former
`get_drive_mappings` in 0.3.0 / stack V9):

```python
from unctools.converter import get_mappings, UNCConverter

get_mappings()                          # {unc: drive}  -- the global converter
UNCConverter().get_reverse_mappings()   # {drive: unc}  -- the direction the old
                                        #                  get_drive_mappings returned
```

---

## Related tools in the DazzleLib ecosystem

- **[dazzlecmd/projects/core/fixpath](https://github.com/DazzleLib/dazzlecmd)** -- a CLI
  tool that composes filekit + UNCtools for "fix this path that came from a
  shell/paste-buffer". It uses filekit's `resolve_cross_platform_path` plus
  UNCtools' `convert_to_local`, with extra CLI-noise stripping.
- **[preserve](https://github.com/DazzleTools/preserve)** -- workflow library built
  on filekit primitives; see [docs/preservelib-integration.md](preservelib-integration.md).
