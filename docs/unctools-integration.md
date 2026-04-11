# Using dazzle-filekit with UNCtools

This guide explains how `dazzle_filekit` and [UNCtools](https://github.com/DazzleLib/UNCtools)
relate, what each provides, and how to compose them in your own code.

**Short version**: filekit *detects* UNC paths; UNCtools *converts* them.
There is no "deep integration" where filekit calls into UNCtools under the
hood -- by design, the two libraries are complementary primitives and
composition happens in the caller.

---

## What filekit gives you natively (no unctools install required)

filekit has first-class UNC detection helpers that work without any extra
dependency:

```python
from dazzle_filekit import is_unc_path

is_unc_path(r"\\server\share\folder\file.txt")  # True on any platform
is_unc_path(r"C:\Users\foo\file.txt")           # False
is_unc_path("/home/user/file.txt")              # False
```

It also detects the broader category via ``get_path_type``:

```python
from dazzle_filekit.paths import get_path_type

get_path_type(r"\\server\share\foo")  # "unc"
get_path_type(r"Z:\mapped\drive\foo") # "local" (filekit doesn't probe
                                      # whether Z: is a mapped network drive
                                      # or a subst -- that's unctools' job)
get_path_type("/home/user/foo")       # "local"
```

And filekit's path normalizers preserve UNC form faithfully:

```python
from dazzle_filekit import normalize_cross_platform_path

p = normalize_cross_platform_path(r"\\server\share\a\b\..\c\file.txt")
# -> WindowsPath('\\\\server\\share\\a\\c\\file.txt')
#    '..' is collapsed lexically, and the UNC prefix is preserved.
```

**What filekit does NOT do:**

- Convert a UNC path to a local drive letter (e.g., `\\server\share\` → `Z:\`)
- Detect whether a drive letter is a mapped network drive or a `subst`
- Query Windows security zones for UNC path access
- Resolve UNC paths to their underlying network share metadata

These capabilities live in **UNCtools**.

---

## What UNCtools adds

[UNCtools](https://github.com/DazzleLib/UNCtools) is a separate package that
handles the UNC ↔ drive-letter translation layer and related Windows quirks:

- `convert_to_local(unc_path)` → returns the mapped drive-letter form if
  the UNC share is mapped, else returns the UNC path unchanged
- `convert_to_unc(local_path)` → returns the UNC form of a mapped drive
  letter, if it came from a network share
- `is_network_drive(path)` / `is_subst_drive(path)` → detect drive-letter
  origin (mapped from a UNC vs. `subst`-created vs. real local disk)
- `get_path_type(path)` → returns `"unc"` / `"network"` / `"subst"` /
  `"local"` (finer-grained than filekit's detector)
- Windows security zone helpers for making UNC paths feel "local" to
  Windows Defender / SmartScreen

It has its own install:

```bash
pip install unctools           # core
pip install unctools[windows]  # with pywin32-backed Windows extras
```

Or you can pin it as an optional extra when installing filekit:

```bash
pip install 'dazzle-filekit[unctools]'
```

**Important**: the `[unctools]` extra just pulls UNCtools into your
environment as a peer package. filekit does not import from UNCtools at
runtime. The two libraries stay decoupled.

---

## Composition patterns

### Pattern 1: "Give me a local path if possible, otherwise the UNC"

The common case: you have a UNC path, you'd rather work with a drive
letter if the user has mapped it, and you want filekit's normalization
to handle the rest.

```python
from dazzle_filekit import normalize_cross_platform_path, is_unc_path

def to_usable_path(raw: str) -> str:
    """Normalize and prefer a local drive letter over a UNC form."""
    normalized = str(normalize_cross_platform_path(raw))

    if is_unc_path(normalized):
        try:
            from unctools import convert_to_local
            local = convert_to_local(normalized)
            return str(local)
        except ImportError:
            pass  # unctools not installed -- fall through to the UNC form

    return normalized
```

The `try/except ImportError` pattern keeps UNCtools optional: your code
still works if the user hasn't installed it, and automatically picks up
the drive-letter translation when they have.

### Pattern 2: "Convert before a cross-boundary operation"

When copying or moving files across a UNC boundary, UNCtools' drive
letter form can be faster and more reliable than the UNC equivalent.

```python
from dazzle_filekit import copy_file, is_unc_path

def smart_copy(src: str, dst: str) -> bool:
    """Copy with automatic UNC -> local drive translation."""
    try:
        from unctools import convert_to_local
        if is_unc_path(src):
            src = str(convert_to_local(src))
        if is_unc_path(dst):
            dst = str(convert_to_local(dst))
    except ImportError:
        pass

    return copy_file(src, dst)
```

### Pattern 3: "Detect everything, use native path operations"

For code that just needs to know whether the path is UNC and then pass
it to filekit as-is:

```python
from dazzle_filekit import (
    is_unc_path,
    normalize_cross_platform_path,
    collect_file_metadata,
)

def describe(path: str) -> dict:
    p = normalize_cross_platform_path(path)
    return {
        "path": str(p),
        "is_unc": is_unc_path(p),
        "metadata": collect_file_metadata(p),
    }
```

This works without UNCtools at all -- filekit handles UNC paths
transparently for most operations (it just doesn't translate them to
drive letters).

---

## Why no "deep integration"?

Philosophically, filekit is the **primitives** layer (file operations,
metadata, paths, disk space). UNCtools is a **different primitives**
layer (network path translation, security zones). Both are meant to be
composable with each other and with higher-level workflow libraries
like [preserve](https://github.com/DazzleTools/preserve).

If filekit imported unctools at runtime, it would:

1. Add a transitive dependency that many non-Windows users don't need
2. Make `pip install dazzle-filekit` pull in Windows-specific code
3. Couple two otherwise-independent libraries in a way that makes each
   harder to release independently
4. Introduce a circular-dependency risk if UNCtools ever wants to depend
   on filekit primitives

Instead, filekit declares UNCtools as an **optional peer** via the
`[unctools]` extra, and user code composes the two as shown above.

---

## Related tools in the DazzleLib ecosystem

- **[dazzlecmd/projects/core/fixpath](https://github.com/DazzleLib/dazzlecmd)** -- a CLI
  tool that demonstrates filekit + UNCtools composition for "fix this
  path that came from a shell/paste-buffer". It uses filekit's
  `resolve_cross_platform_path` plus UNCtools' `convert_to_local`, plus
  extra CLI-noise stripping (quotes, cmd.exe `>` artifacts, PowerShell
  `PS ` prefix, URL-encoded characters, etc.). Source:
  `dazzlecmd/projects/core/fixpath/fixpath.py`.
- **[preserve](https://github.com/DazzleTools/preserve)** -- workflow
  library built on filekit primitives; see
  [docs/preservelib-integration.md](preservelib-integration.md).
