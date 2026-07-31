# Recipes

Task-shaped examples. The [API reference](api-reference.md) tells you what each
function does; this page shows the combinations you actually reach for.

```{admonition} These examples are executed, not just written
:class: tip
`tests/one-offs/probe_docs_recipes.py` runs the substance of every recipe below
against a real temporary tree and checks the results. If a signature changes,
that probe fails — so these cannot quietly rot into fiction.
```

---

## Copy a tree and prove the copy is faithful

The default `copy_file` already preserves metadata. The interesting part is
*verifying* it afterwards, which is a different operation from doing it.

```python
from pathlib import Path
from dazzle_filekit import (
    find_files, copy_files_with_path, verify_copied_files, compare_directories,
)

src, dst = Path("D:/project"), Path("E:/backup/project")

files = find_files([src], patterns=["*.py", "*.md"])   # NOTE: a LIST of roots
copied = copy_files_with_path(files, source_base=src, dest_base=dst)

# Hash-compare what landed against what was read.
results = verify_copied_files(
    {str(p): p for p in files},
    {str(p): dst / p.relative_to(src) for p in files},
)
bad = [p for p, ok in results.items() if not ok]
print(f"{len(files) - len(bad)}/{len(files)} verified")

# Or compare the two trees wholesale, by existence + size + hash.
diff = compare_directories(src, dst)
```

`compare_directories` answers "are these the same?" for a whole tree;
`verify_copied_files` answers "did *this* copy succeed?" for a known pair set.
Reach for the second when you have the file list already — it does not re-walk.

---

## Open a file the application says does not exist

The symptom is an app reporting a missing or inaccessible file that Explorer
opens fine. On Windows that is usually `MAX_PATH`.

```python
from dazzle_filekit import needs_shim, plan_shim, shim_path

target = r"D:\Library\...\a 244-character filename.pdf"

# The one-liner: hand any application a path it can open.
subprocess.run([reader, str(shim_path(target))])
```

To understand *why* a path is or is not being shimmed, plan it without
touching the filesystem:

```python
plan = plan_shim(target)

if not plan.needed:
    print("under threshold; nothing to do")
elif plan.usable:
    print(f"anchor  : {plan.anchor}")     # the directory that gets junctioned
    print(f"link    : {plan.link}")       # where the junction goes
    print(f"shimmed : {plan.shimmed}")    # what to hand the application
else:
    print(f"cannot shim: {plan.reason}")  # e.g. filename exceeds NAME_MAX
```

`plan_shim` writes nothing. `plan.resolved()` gives you the shimmed path when
one is possible and the original otherwise, so it is always safe to use.

### Budgeting before you commit to a root

The shim root's own length is subtracted from the filename budget, so *where*
you put it decides how much it can serve:

```python
from dazzle_filekit import budget_for, resolve_shim_root, candidate_roots

budget_for(r"C:\.dzs")                          # 246 -- serves any real filename
budget_for(r"C:\Users\Somebody\AppData\Local")  # far less

resolve_shim_root(target)   # shortest WRITABLE root, probed at runtime
candidate_roots(target)     # the ordered candidates it chose from
```

### Cleaning up

```python
from dazzle_filekit import reap_shims, remove_shim

reap_shims(r"C:\.dzs", max_age_seconds=86400)   # drop shims older than a day
remove_shim(r"C:\.dzs\a1b2")                    # or one specific shim
```

Both refuse anything that is not a junction, and neither ever touches the
target's contents.

---

## Audit the links in a tree without following them

`os.walk` will happily march through a junction into another volume. Inspect
links as *objects* instead:

```python
from dazzle_filekit import analyze_link, detect_link_type, read_link_target

info = analyze_link(some_path)
if info.kind:                       # 'symlink' | 'junction' | 'hardlink' | None
    print(f"{info.kind:<9} -> {info.raw_target}")
    if info.is_broken:
        print("   target is unreadable or gone")
    if info.is_circular:
        print("   points at itself")

detect_link_type(some_path)   # just the kind
read_link_target(some_path)   # just the raw stored target
```

```{admonition} Why not os.path.islink()
:class: warning

For a **junction** it returns `False`. `os.path.isdir()` returns `True` and
`DirEntry.is_symlink()` returns `False` — a junction is indistinguishable from
an ordinary directory to every obvious check, which is how recursive deletes
end up walking into live data. `analyze_link` and `is_junction` read the
reparse tag.
```

### Creating and detaching links

```python
from dazzle_filekit import create_junction, create_junction_raw, create_hardlink, remove_link

create_junction(target=r"D:\real\dir", link=r"C:\short")     # PowerShell New-Item
create_hardlink(target=r"D:\file.bin", link=r"D:\alias.bin") # os.link, file-only

# create_junction_raw writes the reparse buffer directly: the target need NOT
# exist, so an intentionally-broken junction can be recreated when mirroring.
create_junction_raw(target=r"Z:\gone", link=r"C:\dangling")

remove_link(r"C:\short")   # detaches the link; the target is untouched
```

---

## Hash a large tree quickly, then re-verify it later

`hashlib` runs in the interpreter. A platform-native tool does the same work
outside it, which is materially faster on big files.

```python
from dazzle_filekit import (
    detect_native_hash_tool, calculate_file_hash_native,
    calculate_directory_hashes, save_hashes_to_file,
    load_hashes_from_file, verify_files_with_manifest,
)

detect_native_hash_tool("sha256")   # 'certutil' / 'sha256sum' / None

# The native path returns None when no tool is available -- it does NOT fall
# back for you. Do it explicitly:
digest = (calculate_file_hash_native("big.iso", algorithm="sha256")
          or calculate_file_hash("big.iso", algorithms=["sha256"])["sha256"])

# Manifest a whole tree, persist it, verify against it later.
hashes = calculate_directory_hashes("D:/archive", pattern="*", recursive=True)
save_hashes_to_file(hashes, "archive.sha256")

later = load_hashes_from_file("archive.sha256")

# Keys are RELATIVE to the scanned directory, and verification resolves them
# against the current working directory -- so verify from inside it.
os.chdir("D:/archive")
report = verify_files_with_manifest(later)
changed = [p for p, (ok, _, _) in report.items() if not ok]
```

```{admonition} Two traps in this recipe, both measured
:class: warning

**`calculate_file_hash_native` returns `None`** when no native tool is found.
Its docstring says "callers fall back to `calculate_file_hash`" — the *caller*
does, not the function.

**Manifest keys are relative.** `calculate_directory_hashes` keys on paths
relative to the directory it scanned, and `verify_files_with_manifest` resolves
them against the cwd. Verify from elsewhere and every file reports failed with
an actual hash of `None` — meaning "not found", not "changed".

Note also the sibling shapes: `calculate_file_hash` takes `algorithms` (a list)
and returns a **dict**; `calculate_file_hash_native` takes `algorithm` (a
string) and returns a **str**.
```

---

## Keep only paths that are real places

Anything scraping paths out of shell commands, logs, or config needs to discard
devices and sinks. `/dev/null` is a perfectly legal path — it is just not
somewhere a file lives.

```python
from dazzle_filekit import is_device_path, classify_fs_object
from dazzle_filekit.utils.validation import is_valid_path

candidates = ["/home/me/notes", "/dev/null", "NUL", "C:/tmp/nul.txt", "C:/code"]

places = [p for p in candidates if is_valid_path(p) and not is_device_path(p)]
# -> ['/home/me/notes', 'C:/code']

classify_fs_object("C:/code")   # 'directory' | 'file' | 'symlink' | 'nonexistent' | ...
```

Windows reserved names are matched wherever they appear and whatever the
extension — `C:\anywhere\nul.txt` resolves to the device, so it is filtered.

---

## Work with a PATH value from a different machine

A `PATH` value's platform semantics come from *where it was written*, not from
the host reading it. A Windows registry `Path` stays `;`-separated and
case-insensitive even when a Linux CI runner parses it.

```python
from dazzle_filekit import (
    split_path_value, path_value_contains, append_path_value,
    normalize_path_entry, host_path_platform, PLATFORM_WINDOWS,
)

raw = r"C:\Windows\system32;%USERPROFILE%\bin;C:\tools"

split_path_value(raw, platform=PLATFORM_WINDOWS)
# ['C:\\Windows\\system32', '%USERPROFILE%\\bin', 'C:\\tools']

# Membership by normalized identity, not string equality -- %VAR% is expanded
# and case is folded, on any host.
path_value_contains(raw, r"c:\TOOLS", platform=PLATFORM_WINDOWS)   # True

updated = append_path_value(raw, r"C:\newtool", platform=PLATFORM_WINDOWS)
# no-op if already present under normalized identity

host_path_platform()   # 'windows' or 'posix' -- the default when you omit platform
```

Nothing here touches disk or the environment; you get a string back and decide
where to persist it.

---

## Survive Git Bash, WSL, and native spellings of the same path

```python
from dazzle_filekit import (
    normalize_cross_platform_path, resolve_cross_platform_path,
    path_exists_cross_platform, is_wsl,
)

normalize_cross_platform_path("/c/Users/foo/file.txt")      # -> C:\Users\foo\file.txt
normalize_cross_platform_path("/mnt/c/Users/foo/file.txt")  # -> same

# When the normalized form does not exist, probe the alternative spellings.
resolve_cross_platform_path("/mnt/c/Users/foo/file.txt")

path_exists_cross_platform("/c/Users/foo/file.txt")
```

`normalize_*` is lexical and link-safe by default; pass `resolve=True` to
follow symlinks. `resolve_*` is existence-aware — it hits the filesystem.

---

## Write a config file that cannot be half-written

```python
from dazzle_filekit import atomic_write_json, atomic_write_text, AtomicStreamWriter

atomic_write_json("config.json", {"threshold": 240})   # tmp + rename
atomic_write_text("notes.txt", "content")

# For output too large to build in memory, stream it with the same guarantee.
with AtomicStreamWriter("manifest.txt") as w:
    for path, digest in hashes.items():
        w.write(f"{digest}  {path}\n")
# manifest.txt appears complete, or not at all -- never truncated
```

---

## Replace text across a tree without risking truncation

```python
from dazzle_filekit import replace_in_file, batch_replace_in_files

replace_in_file("setup.cfg", "0.4.1", "0.4.2")          # -> True if changed

results = batch_replace_in_files(
    "docs", old_text="0.4.1", new_text="0.4.2",
    pattern="*.md", recursive=True,
)
print(f"{sum(results.values())} of {len(results)} files changed")
```

Both are built on `open_file` + `atomic_write_text`, so a crash mid-write
cannot leave a truncated file behind. Both also accept
`try_path_variants=True` to retry under a path's
[other names](unctools-integration.md).

---

## Check there is room before a large operation

```python
from dazzle_filekit import (
    get_disk_usage, check_disk_space, ensure_disk_space,
    calculate_total_size, InsufficientSpaceError,
)

usage = get_disk_usage("E:/")
print(f"{usage.free / 1e9:.1f} GB free of {usage.total / 1e9:.1f} GB")

needed = calculate_total_size(["D:/project"])      # a LIST of roots

# check_disk_space returns a 4-TUPLE, not a bool.
has_room, required, available, message = check_disk_space("E:/", needed)
if not has_room:
    print(message)

# ensure_disk_space is the convenience form: give it the SOURCES, not a byte
# count, and it sizes them for you. It returns (bool, message) too.
ok, message = ensure_disk_space("E:/", ["D:/project"])

# To fail fast instead of branching, ask check_disk_space to raise.
try:
    check_disk_space("E:/", needed, raise_on_insufficient=True)
except InsufficientSpaceError as exc:
    print(exc)
```

```{admonition} Both return tuples — do not test them for truthiness
:class: warning

`check_disk_space` returns `(has_space, required, available, message)` and
`ensure_disk_space` returns `(has_space, message)`. A non-empty tuple is
always truthy, so `if check_disk_space(...):` passes **even when the disk is
full**. Unpack, or index `[0]`.

`InsufficientSpaceError` is raised only when you pass
`raise_on_insufficient=True`; neither function raises by default.
```
