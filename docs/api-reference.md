# API Reference

Full function reference for `dazzle_filekit`. For a quick-start walkthrough,
see the [README](https://github.com/DazzleLib/dazzle-filekit/blob/main/README.md). For the locked public API surface that
external tools depend on, see [api-stability.md](api-stability.md).

**Documents v0.4.3** — last reviewed 2026-07-31.

## Table of Contents

- [Cross-Platform Utilities](#cross-platform-utilities)
- [Path Functions](#path-functions)
- [Content Operations](#content-operations-v030-dazzle_filekitcontent)
- [PATH Environment Values](#path-environment-values-v033-dazzle_filekitpathenv)
- [File Operations](#file-operations)
- [Metadata Module](#metadata-module)
- [Platform-Specific (Windows)](#platform-specific-windows)
- [Disk Space Functions](#disk-space-functions)
- [Verification Functions](#verification-functions)
- [Utility Functions](#utility-functions)
- [Validation Functions](#validation-functions)
- [Is this a *place*?](#is-this-a-place-v042)
- [Long-Path Shims](#long-path-shims-v040-dazzle_filekitlongpath)
- [Logging Configuration](#logging-configuration)

---

```{admonition} Several functions take a LIST where you would expect one path
:class: warning

`find_files`, `find_regex_files`, `calculate_total_size`,
`copy_files_with_path` and `move_files_with_path` all take a **collection** as
their first argument, not a single path. Passing a bare string does not raise
— a string is iterable, so it is consumed one character at a time. Each
character becomes a search root, and since `Path("/")` is the drive root with
`recursive=True` the default, `find_files("/some/dir")` can attempt to walk the
entire filesystem.

Always wrap: `find_files([src], ...)`, `calculate_total_size([src])`.
```

## Cross-Platform Utilities

All three path normalizers live in `dazzle_filekit.paths` and are
re-exported at the top level. In v0.2.4 they all route through the
same canonical implementation.

- `normalize_cross_platform_path(path, *, resolve=False)` — **Canonical**
  path normalizer (v0.2.4). Handles Git Bash `/c/`, WSL `/mnt/c/`,
  Windows `C:\` / `C:/`, tilde (`~/`), env vars (`%USERPROFILE%` /
  `$HOME`), `\\?\` extended-length prefix, and platform-direction
  conversion. With `resolve=True`, follows symlinks via `Path.resolve()`.
  Bare drive letters (e.g. `/c`) map to the drive root (`C:\`) so the
  result is genuinely absolute.
- `resolve_cross_platform_path(path)` — Normalize and probe alternate
  platform formats when the result doesn't exist on disk (existence-
  aware). Used by filekit's own path-recovery workflows and by
  `dazzlecmd/projects/core/fixpath` for CLI-noise handling.
- `path_exists_cross_platform(path)` — Check path existence across
  cross-platform formats.
- `is_windows()` / `is_unix()` / `is_wsl()` — Platform detection.
  `is_wsl()` (v0.2.4) returns True when running inside WSL (checks
  `WSL_DISTRO_NAME` env var + `/proc/version` scan).

### Path Functions

The following path helpers live in `dazzle_filekit.paths`:

- `normalize_cross_platform_path(path, *, resolve=False)` — the canonical
  normalizer. `resolve=True` follows symlinks (`Path.resolve()`); the default
  `resolve=False` is link-safe (lexical). (The `normalize_path` /
  `normalize_path_no_resolve` wrappers were **removed in 0.3.0** — clean break;
  use `resolve=True` / the default respectively.)
- `is_same_file(path1, path2)` — Check if two paths refer to the same
  underlying file (via `os.path.samefile()` semantics).
- `split_drive_letter(path)` — Split drive letter from path (Windows).
- `is_unc_path(path)` — Check if path is UNC format. Platform-independent
  (delegates to `unctools.is_unc_path`): `//server/share` is True everywhere.
- `get_relative_path(path, base)` — Relative path from `base` **only when
  `path` is a subpath of `base`** (`Path.relative_to`); returns None otherwise.
- `compute_relative_path(target, start, fallback_to_absolute=True)` — **v0.3.0**:
  the `..`-traversing relative path from `start` to `target` (`os.path.relpath`),
  with a Windows cross-drive fallback. Distinct from `get_relative_path`.
- `find_files(search_paths, patterns=None, recursive=True, exclude_patterns=None)`
  — Find files matching glob patterns. **`search_paths` is a LIST of
  directories**, not a single one. Passing a bare string iterates it character
  by character, and since `Path("/")` is the drive root with `recursive=True`
  the default, `find_files("/some/dir")` will attempt to glob the entire
  filesystem. Always pass a list: `find_files([src], patterns=["*.py"])`.
- `find_regex_files(directory, pattern)` — Find files matching a regex.
- `collect_files_from_include_file(include_file)` — Read a list of
  files from an include file (for batch operations).
- `create_parent_dirs(path)` — Create parent directories for a path.
- `ensure_unique_path(path)` — Generate a unique path by appending
  a counter if the original exists.
- `create_dest_path(src, src_base, dst_base, path_style, include_base)` —
  Build a destination path for batch file operations.
- `classify_fs_object(path)` — **v0.3.0** (renamed from `get_path_type`):
  classify WHAT a filesystem object is (`'file'`, `'directory'`, `'symlink'`,
  `'socket'`, `'pipe'`, `'block_device'`, `'char_device'`, `'nonexistent'`,
  `'unknown'`). A junction reports `'directory'` — use `analyze_link` below for
  link-kind. (For a path's network *origin* — `unc`/`network`/`subst`/`local` —
  use `unctools.classify_path_origin`.)

### Link Primitives (v0.3.0, `dazzle_filekit.links`)

Intrinsic link analysis and junction/hardlink creation (relational,
destination-relative analysis lives at L3/preservelib):

- `analyze_link(link_path)` → `LinkInfo` — intrinsic facts about one link (no
  destination parameter): `kind` (`'symlink'`/`'junction'`/`'hardlink'`/`None`),
  `raw_target`, `resolved_target`, `is_broken`, `is_circular` (direct
  self-reference only). `LinkInfo.to_dict()` → `dazzle_lib.LinkTargetDict`.
- `detect_link_type(path)` — the `kind` value alone, or `None`.
- `read_link_target(path)` — raw target (symlink via `os.readlink`; junction via
  the DeviceIoControl reparse buffer).
- `create_junction(target, link, force=False)` — Windows NTFS junction via
  PowerShell `New-Item` (directory-only, no elevation).
- `create_junction_raw(target, link, force=False)` — **v0.3.4**: the same
  junction, written straight into the mount-point reparse buffer
  (`FSCTL_SET_REPARSE_POINT`, pure ctypes, no subprocess). Two differences that
  matter: the target does **not** need to exist, so intentionally-broken
  junctions can be recreated when mirroring a tree, and the
  SubstituteName/PrintName pair is stored without normalization, so
  `os.readlink` round-trips byte-for-byte. Unprivileged, directory-only,
  Windows-only.
- `create_hardlink(target, link, force=False)` — `os.link` (file-only,
  cross-device aware).
- `remove_link(path)` → `bool` — detach a symlink, junction, or hard link
  **without deleting what it points at**. The distinction matters more than it
  looks: a junction is reported as an ordinary directory by `os.path.islink`,
  `os.path.isdir` and `DirEntry.is_symlink` alike, so a careless recursive
  delete can walk through one into real data.

---

## Content Operations (v0.3.0, `dazzle_filekit.content`)

Read-modify-write text replacement, built on `open_file` +
`atomic_write_text` so a crash mid-write cannot truncate the original. The L1
home of the `replace_in_file` family unctools shed in its 0.2.0
probe-not-mutate split.

- `replace_in_file(file_path, old_text, new_text, *, encoding='utf-8', try_path_variants=False, resolver=None)`
  → `bool` — replace every occurrence in one file. Returns whether anything
  changed.
- `batch_replace_in_files(directory, old_text, new_text, pattern='*.txt', recursive=True, *, encoding='utf-8', try_path_variants=False, resolver=None)`
  → `dict[str, bool]` — the same over a glob set, mapping each path to whether
  it changed.

Both accept the `try_path_variants` / `resolver` seam described under
[unctools integration](unctools-integration.md), so a UNC path that fails can
be retried under its mapped-drive spelling.

---

## PATH Environment Values (v0.3.3, `dazzle_filekit.pathenv`)

Helpers for `PATH`-style environment **values** — the `;`- or `:`-separated
strings themselves, not the filesystem paths inside them. Pure string logic,
no I/O.

**The distinction that gives this module its reason to exist:** a PATH value's
platform semantics are fixed by *where it came from*, not by the host reading
it. A Windows registry `Path` stays `;`-separated, `%VAR%`-bearing, and
case-insensitive even when a POSIX CI runner parses it. Every function
therefore takes an explicit `platform` argument, defaulting to the host only
when you do not say otherwise. This is the deliberate mirror of
`normalize_cross_platform_path`'s host-*directional* behaviour — the two module
docstrings cross-reference the difference.

- `split_path_value(value, platform=None)` → `list[str]` — split into non-empty
  entries, on `;` or `:` according to the declared platform.
- `normalize_path_entry(entry, platform=None)` → `str` — normalize one entry
  for identity comparison (expands `%VAR%` via `ntpath` for Windows values, and
  case-folds where the platform is case-insensitive).
- `path_value_contains(value, directory, platform=None)` → `bool` — is
  `directory` already among the entries, compared by normalized identity rather
  than string equality.
- `append_path_value(value, directory, platform=None)` → `str` — the value with
  `directory` appended if not already present; unchanged otherwise.
- `host_path_platform()` → `str` — the running host's dialect, `'windows'` or
  `'posix'`.
- `PLATFORM_WINDOWS` (`'windows'`) / `PLATFORM_POSIX` (`'posix'`) — the accepted
  `platform` values.

Persistence stays with the caller: this module computes the new value and never
writes it anywhere.

---

## File Operations

Core operations live in `dazzle_filekit.operations` and are re-exported
at the top level.

> **Resolver edge (v0.3.0).** `open_file`, `copy_file`, `move_file`,
> `copy_files_with_path`, `move_files_with_path`, `process_files`, and the
> `content.*` helpers accept keyword-only `try_path_variants=False` /
> `resolver=None`. When `try_path_variants=True`, a retryable failure
> (`PermissionError` / `FileNotFoundError` / `OSError`) is retried under the
> path's other names (UNC ↔ mapped drive), resolved by a
> `dazzle_lib.PathVariantResolver` (default: unctools). Default off — existing
> behavior is unchanged. See [unctools-integration.md](unctools-integration.md).

### Basic copy, move, remove

- `copy_file(src, dst, preserve_attrs=True, overwrite=False)` — Copy
  a single file with optional attribute preservation. On Windows,
  uses robocopy as a fallback for rich attribute handling when
  pywin32 is available.
- `move_file(src, dst, preserve_attrs=True, overwrite=False)` — Move
  a single file with optional attribute preservation.
- `copy_files_with_path(source_files, source_base, dest_base, path_style='relative', include_base=False, preserve_attrs=True, overwrite=False)` —
  Batch copy with path style control (`relative`, `absolute`, `flat`).
- `move_files_with_path(source_files, source_base, dest_base, ...)` —
  Batch move counterpart.
- `create_directory_structure(dest_path, directory_paths)` — Create
  a directory tree from a list.
- `remove_file(path, force=False)` — Remove a file safely.
- `remove_directory(path, recursive=True, force=False)` — Remove a
  directory.
- `create_symlink(target, link, force=False, target_is_directory=None)` —
  Create a symbolic link. On Windows, uses `os.symlink` with fallbacks:
  `dazzlelink` library → `mklink` command.

### Metadata convenience wrappers

These delegate to the rich `dazzle_filekit.metadata` module as of v0.2.4:

- `collect_file_metadata(path)` — Collect rich file metadata. Returns
  a dict with SDDL ACLs on Windows, xattrs on Unix, NTFS ctime,
  attribute flags, owner/group, ISO timestamps, and size.
- `apply_file_metadata(path, metadata)` — Apply metadata to a file.
  Honors all rich fields (SDDL, ctime, xattrs) when present.

### Atomic write primitives (v0.2.4)

- `atomic_write_text(path, content, *, encoding='utf-8', newline=None)` —
  Tmp+rename atomic text write. Creates parent directories if needed.
  Atomic on POSIX and Windows (Python ≥ 3.3).
- `atomic_write_json(path, data, *, indent=2, sort_keys=False, default=str, trailing_newline=True)` —
  Atomic JSON write. `default=str` handles `Path`/`datetime`/other
  non-JSON-native types out of the box.
- `copy_tree_preserving_links(src, dst, *, dirs_exist_ok=False, ignore=None, ignore_dangling_symlinks=False)` —
  `shutil.copytree(symlinks=True)` wrapper with documented intent.
  Never traverses junctions on Windows.
- `AtomicStreamWriter(path, *, encoding='utf-8', newline=None)` — the streaming
  form of the same tmp+rename guarantee, for output too large to build in
  memory first (ported from dazzlesum's `MonolithicWriter`). Use it as a
  context manager and write incrementally; the destination is replaced in one
  rename on clean exit, and left untouched if the block raises.

  ```python
  from dazzle_filekit import AtomicStreamWriter

  with AtomicStreamWriter("manifest.txt") as w:
      for path, digest in hashes.items():
          w.write(f"{digest}  {path}\n")
  # manifest.txt appears complete, or not at all
  ```

---

## Metadata Module

Rich metadata capture and application. Import via
`from dazzle_filekit import metadata` or
`from dazzle_filekit.metadata import ...`.

### Main entry points

- `metadata.collect_file_metadata(path)` — Rich capture. On Windows
  returns a dict with SDDL security descriptor string, attribute
  flag booleans (`is_hidden`, `is_system`, `is_readonly`, `is_archive`),
  owner/group as `DOMAIN\Name` strings, creation time, ISO timestamp
  projections, and size. On Linux/macOS returns POSIX mode, owner/group
  (uid/gid), extended attributes (xattrs) as a base64-encoded dict,
  and ISO timestamps.
- `metadata.apply_file_metadata(path, md)` — Rich apply. Honors SDDL
  ACLs via `ConvertStringSecurityDescriptorToSecurityDescriptorW`,
  ctime via `SetFileTime`, and xattrs via `os.setxattr` (skipping
  `com.apple.quarantine` on restore).

### Windows-specific helpers

- `metadata.restore_windows_creation_time(path, created)` — NTFS ctime
  restoration via pywin32 `SetFileTime`. Handles directories via
  `FILE_FLAG_BACKUP_SEMANTICS` and readonly files via a
  clear-then-restore dance.
- `metadata.is_win32_available()` — Cached pywin32 availability probe.

### Diff / projection helpers

- `metadata.compare_metadata(md1, md2)` — Diff two metadata dicts.
  Returns only the differences. Allows a 2-second timestamp tolerance
  to account for filesystem precision.
- `metadata.metadata_to_json(md)` — JSON-safe projection of a metadata
  dict (recursively converts non-JSON types to strings or base64).
- `metadata.get_metadata_summary(md)` — Human-readable summary with
  formatted size, timestamps, permissions, and attribute list.

### Timestamp-only helpers

- `metadata.collect_timestamp_info(path)` — Timestamp-only capture
  (without the rest of the metadata).
- `metadata.apply_timestamp_strategy(path, strategy, link_timestamps=None, target_timestamps=None)` —
  Strategy-based timestamp apply for symlink restoration workflows.
  Strategies: `'current'`, `'symlink'`, `'target'`, `'preserve-all'`.

### Private helpers (not in `__all__`, but reachable)

- `metadata._collect_unix_xattrs(path)` — Linux/macOS xattrs via
  `os.listxattr` / `os.getxattr`, base64-encoded.
- `metadata._apply_unix_xattrs(path, xattrs)` — Apply xattrs, skipping
  `com.apple.quarantine`.

---

## Platform-Specific (Windows)

Import via `from dazzle_filekit.platform import windows`. All functions
return safe defaults (empty list / False) when pywin32 or ctypes aren't
available.

### Admin detection

- `windows.is_admin()` — Check if the current process has admin
  privileges via `win32security.IsUserAnAdmin`.

### NTFS Alternate Data Streams (v0.2.4)

- `windows.detect_alternate_streams(path)` — Enumerate NTFS ADS via
  ctypes `FindFirstStreamW` / `FindNextStreamW`. Filters out `::$DATA`
  (the main data stream) and `:Zone.Identifier:$DATA` (browser
  download marker).
- `windows.has_significant_ads(path)` — Returns True if any non-ignored
  stream exists. Useful as a warning check before cross-device copy
  (ADS are lost on non-NTFS destinations).

---

## Disk Space Functions

Disk space checking and size calculation. All functions are cross-
platform via `shutil.disk_usage`.

- `get_disk_usage(path)` — Get `DiskUsage` (named tuple with `total`,
  `used`, `free`, plus `used_percent` / `free_percent` properties).
- `check_disk_space(dest_path, required_bytes, safety_margin=0.1, raise_on_insufficient=False)` —
  Check if destination has sufficient space. Returns
  `(has_space, required_with_margin, available, message)`. Set
  `raise_on_insufficient=True` to raise `InsufficientSpaceError`
  instead of returning `False`.
- `calculate_total_size(paths, follow_symlinks=True)` — Calculate
  total size of files/directories (recursive for directories).
- `ensure_disk_space(dest_path, source_paths, safety_margin=0.1)` —
  Verify space for a copy operation: computes total size of sources,
  checks destination. Returns `(has_space, message)`.

### Classes and exceptions

- `DiskUsage` — Named tuple with `total`, `used`, `free`, `used_percent`,
  `free_percent`.
- `InsufficientSpaceError(Exception)` — Raised when destination lacks
  space (when `raise_on_insufficient=True`).

---

## Verification Functions

File content verification via hash algorithms. Supports MD5, SHA1,
SHA256, SHA512 and other `hashlib`-compatible algorithms.

- `calculate_file_hash(file_path, algorithms=None, buffer_size=65536, preserve_case=False)`
  → `dict` — hash a file with **one or more** algorithms. Note the plural: it
  takes a *list* and returns a **dict** keyed by algorithm name, defaulting to
  `['SHA256']`.

  ```python
  calculate_file_hash("x.txt")                        # {'SHA256': '2cf24dba...'}
  calculate_file_hash("x.txt", algorithms=["md5", "sha256"])
  ```
- `detect_native_hash_tool(algorithm='sha256')` — Locate a platform-native
  checksum binary (`certutil` on Windows, `sha256sum`/`shasum` on POSIX), or
  `None` when none is usable. Ported from dazzlesum.
- `calculate_file_hash_native(file_path, algorithm='sha256', tool=None)`
  → `str | None` — hash via a platform-native binary instead of `hashlib`,
  which is materially faster on large files because the work happens outside
  the interpreter. **Returns `None` when no tool is available or the tool
  fails** — it does *not* fall back on your behalf. The caller decides:

  ```python
  digest = (calculate_file_hash_native(p, "sha256")
            or calculate_file_hash(p, algorithms=["sha256"])["sha256"])
  ```

  Note the shape difference from its sibling: this one takes `algorithm`
  (singular, a string) and returns a string; `calculate_file_hash` takes
  `algorithms` (a list) and returns a dict.
- `verify_file_hash(file_path, expected_hashes)` → `(bool, dict)` — verify a
  file against a **dict** of expected hashes, in the shape
  `calculate_file_hash` returns. The result is a tuple: overall pass/fail, plus
  a per-algorithm breakdown.

  ```python
  expected = calculate_file_hash("x.txt")     # {'SHA256': '...'}
  ok, detail = verify_file_hash("x.txt", expected)
  ```
```{admonition} Singular vs plural is not a typo
:class: warning

`calculate_file_hash` takes **`algorithms`** (a list) and returns a dict.
`calculate_file_hash_native` takes **`algorithm`** (a string) and returns a
string. They are different functions with different shapes; the names are
one character apart.
```

- `verify_files_with_manifest(manifest_path)` — Verify files against
  a saved hash manifest.
- `calculate_directory_hashes(directory, algorithm='sha256')` — Hash
  all files in a directory tree.
- `save_hashes_to_file(hashes, output_file)` — Persist a hash dict to
  a file.
- `load_hashes_from_file(hash_file)` — Load a persisted hash dict.

```{admonition} Manifest keys are relative, and verification is cwd-sensitive
:class: warning

`calculate_directory_hashes` returns keys **relative to the directory it
scanned** (`'a.py'`, not `'D:/proj/a.py'`), and `verify_files_with_manifest`
resolves them against the **current working directory**. Verifying from
anywhere else silently reports every file as failed, with the actual hash
`None` — because the file was never found, not because it changed.

Either `chdir` into the scanned directory before verifying, or re-key the dict
to absolute paths first.
```
- `compare_directories(dir1, dir2)` — Compare directory contents by
  file existence, size, and hash.
- `verify_copied_files(src_dir, dst_dir)` — Verify a copy operation
  produced matching files in the destination.

---

## Utility Functions

### Platform detection (`utils.compat`)

- `is_windows()` / `is_unix()` / `is_wsl()` — Platform detection.
- `is_admin()` / `is_root()` — Privilege detection.
- `fix_path_separators(path)` — Normalize path separators to OS native.
- `fix_path_case(path)` — Normalize case where the filesystem is
  case-insensitive.
- `get_case_sensitive_path(path)` → `str` — **v0.3.0**: the path as the
  filesystem actually stores it on Windows (so `c:\users\foo` comes back
  `C:\Users\Foo`), and unchanged elsewhere. Useful when a path is about to be
  displayed, logged, or compared against something the OS produced.
- `path_exists_case_sensitive(path)` → `bool` — **v0.3.0**: does the path exist
  *with the exact case given*. On a case-insensitive filesystem `os.path.exists`
  answers `True` for a spelling the disk does not use; this does not. Absorbed
  from unctools' removed case-sensitivity helpers.
- `get_system_encoding()` — Get the filesystem encoding.
- `get_system_temp_dir()` — Cross-platform temp directory.
- `get_home_dir()` — Current user's home directory.
- `get_app_data_dir(app_name)` — Application data directory
  (`%APPDATA%\<app>` on Windows, `~/.config/<app>` on Linux,
  `~/Library/Application Support/<app>` on macOS).
- `get_drive_mappings()` — **removed in 0.3.0** ([DazzleLib stack](https://github.com/DazzleLib/.github/blob/main/docs/STACK-MAP.md) V9). Drive↔UNC
  mapping is path-identity knowledge owned by L0; its `win32wnet` provider-chain
  scan was folded into `unctools` (≥0.2.2). Use
  `unctools.converter.get_mappings()` (UNC→drive) or
  `unctools.converter.UNCConverter().get_reverse_mappings()` (drive→UNC).

### Low-level disk helpers (`utils.disk`)

Same surface as the top-level disk functions above, plus internal
helpers that aren't typically used directly.

---

## Validation Functions

Path validation helpers in `dazzle_filekit.utils.validation`.

- `is_valid_path(path)` — Check if a path string is valid for the
  current platform.
- `is_safe_path(path, base_path)` — Check if a path is safely contained
  within a base path (prevents directory traversal).
- `validate_path_chars(path)` — Check for invalid characters.
- `is_absolute_path(path)` / `is_relative_path(path)` — Absolute/
  relative check.
- `is_unc_path(path)` — UNC path detection (also exported at top level).
- `is_hidden_path(path)` — Hidden file detection (platform-aware).
- `is_symlink(path)` — Symlink detection.
- `is_junction(path)` — Junction detection (Windows). **Fixed in
  v0.2.4** to use `DeviceIoControl(FSCTL_GET_REPARSE_POINT)` and
  correctly distinguish junctions (`IO_REPARSE_TAG_MOUNT_POINT`)
  from directory symlinks (`IO_REPARSE_TAG_SYMLINK`).
- `read_junction_target(path)` — **v0.3.0**: the junction's target, read from
  its reparse buffer (same DeviceIoControl machinery as `is_junction`).

### Is this a *place*? (v0.4.2)

- `is_device_path(path)` → `bool` — does this path name a device or sink rather
  than somewhere a file can actually live?
- `POSIX_DEVICE_PATHS` — recognized POSIX devices and shell sinks
  (`/dev/null`, `/dev/stdout`, `/dev/tty`, …).
- `WINDOWS_INVALID_NAMES` — reserved Windows device names (`NUL`, `CON`, `AUX`,
  `COM1`–`COM9`, `LPT1`–`LPT9`, …).

**A different question from `is_valid_path`**, and the difference is the whole
point:

| | asks | verdict on `/dev/null` |
|---|---|---|
| `is_valid_path` | is this string **legal**? | `True` — a perfectly legal POSIX path |
| `is_device_path` | is this string a **place**? | `True` — and so *not* somewhere a file lives |

Anything that harvests paths out of shell commands, config files, or logs needs
the second question. Recognized: POSIX devices and sinks, kernel
pseudo-filesystems (`/proc/…`, `/sys/…`, `/dev/fd/N`), and Windows reserved
names — the last **position-independent and extension-blind**, because Windows
resolves `C:\anywhere\nul.txt` to the device wherever it appears.

```python
from dazzle_filekit import is_device_path

is_device_path("/dev/null")       # True
is_device_path("NUL")             # True
is_device_path("C:/tmp/nul.txt")  # True   -- still the device
is_device_path("/home/me/notes")  # False
is_device_path("console-app")     # False  -- substring, not a device
```

Both platforms' names are recognized on **both** platforms deliberately: a
Windows host routinely parses Git-Bash or WSL commands containing
`2>/dev/null`, and a POSIX host may read Windows-authored scripts. The question
is about the string, not the host.

```{admonition} Why this exists
:class: note

Added for [Claude-Session-Backup #56](https://github.com/DazzleML/Claude-Session-Backup/issues/56),
where `2>/dev/null` — scraped out of shell commands while working out which
folders a session had touched — was being ranked as that session's **top
working directory**, at 119 hits, outranking the actual repository.
```

---

## Long-Path Shims (v0.4.0, `dazzle_filekit.longpath`)

The remedy for the condition `is_valid_path` above merely *detects*: a path
over `MAX_PATH` without a `\\?\` prefix. Windows-only in effect — `PATH_MAX` is
4096 on Linux and 1024 on macOS/BSD, so `needs_shim` returns `False` there and
every entry point degrades to a no-op.

**Why not just use `\\?\`.** The extended-length prefix lifts the limit at the
Win32 API layer, which is enough for a well-behaved caller. It does not help an
application that builds the correct prefixed path and then copies it into a
fixed 260-byte buffer, truncating the tail and reporting the file missing —
measured in two independent PDF readers. A `longPathAware` manifest does not
reach it either, because the limit is internal to the application rather than
at the API gate. Nothing outside such an application can repair its buffer;
what *can* change is the length of the string handed to it. A directory
junction at a short root does that with no cooperation from the consumer —
which is also why it fixes readers that are not yet installed.

### The one-call entry point

- `shim_path(path, root=None, threshold=240)` → `Path` — an openable path for
  `path`, creating a junction if one is needed. **Never raises for a
  path-shaped input**: an unnecessary shim, an impossible plan, an unwritable
  root, or a failed junction all fall back to the original path, so a caller
  substituting this for a bare path needs no new exception handling.

```python
from dazzle_filekit import shim_path

p = shim_path(r"D:\deep\...\a 244-character filename.pdf")
subprocess.run([reader, str(p)])     # a MAX_PATH-bound reader can open it
```

### Deciding whether a shim is needed

- `needs_shim(path, threshold=DEFAULT_THRESHOLD)` → `bool` — `False` on POSIX,
  and `False` for a path already carrying an extended-length prefix (it has
  opted out of the limit, so rewriting it would be pointless).
- `plan_shim(path, root=None, threshold=..., id_len=4)` → `ShimPlan` — a pure
  decision with **no filesystem writes**. Anchors at the *shallowest* ancestor
  whose junction still brings the result under `USABLE_PATH`, so one shim
  covers the widest subtree and repeat opens reuse it; where the filename is
  long enough that only its immediate parent fits, that is chosen instead.

`ShimPlan` carries `original`, `needed`, `anchor` (directory to junction),
`link` (where the junction goes), `shimmed` (the rewritten path), `reason` and
`warnings`, plus `plan.usable` (an openable path exists) and `plan.resolved()`
(the shimmed path when possible, else the original — never raises).

A component longer than `NAME_MAX` is reported in `plan.reason` rather than
faked: no link shortens a single path component, because the offending name
must still appear in the shimmed path.

### Choosing where shims live

- `resolve_shim_root(target=None, candidates=None, probe=True)` → `Path | None`
  — the shortest **writable** root, probed at runtime. `probe=False` returns
  the first candidate unchecked.
- `candidate_roots(target=None)` → `list[Path]` — the ordered candidates,
  shortest first.
- `budget_for(root, id_len=4)` → `int` — the longest filename a shim under
  `root` can serve.

**The root's own length is load-bearing** — it is subtracted from the
filename's budget, so the ordering is not cosmetic. Measured against a corpus
whose longest filename is 244 characters:

| Root | Length | Files still broken |
|---|---|---|
| `C:\.dzs` | 7 | 0 |
| `%USERPROFILE%\.dzs` (user `Extreme`) | 21 | 1 |
| `%USERPROFILE%\.dzs` (user `Administrator`) | 27 | 4 |
| `%LOCALAPPDATA%\dazzlecmd\longpath` | 49 | 64 |

The obvious choice is the broken one, and it fails silently on only the longest
names. `%USERPROFILE%` is offered as the one tier guaranteed writable but ranks
*below* the drive roots, because its length varies with the username: identical
code serves every file on one machine and drops the longest on another.

### Shim lifecycle

- `create_shim(plan, max_id_len=16)` → `bool` — materialises the junction,
  reusing an existing one **for the same anchor**. Updates `plan.link` and
  `plan.shimmed` to whatever was actually used.
- `remove_shim(link)` → `bool` — removes a shim, leaving its target untouched.
- `reap_shims(root, max_age_seconds=86400, now=None)` → `list[Path]` — removes
  shims older than the threshold; considers only junctions and leaves anything
  else in the directory alone.

**Two correctness notes worth knowing before extending this.**

*Anchor ids collide.* The id is a truncated hash, so two unrelated directories
can map to one link name — at the 4-character default that is an even chance
around three hundred distinct anchors. `create_shim` therefore verifies that an
existing junction points at the requested anchor and lengthens the id on
collision, rather than treating any junction at the expected link as proof of a
previous mint for it. It also treats `create_junction`'s return value as
advisory and re-checks what landed on disk, because that function's `exists()`
test is not atomic with its creation call and a concurrent caller can replace
the result.

*Deletion never recurses.* `remove_shim` re-checks that its target is a
junction immediately before deleting and uses `os.rmdir`, which unlinks the
reparse point without descending into it. That is guarded rather than assumed
because every naive test misidentifies a junction: `os.path.islink()` is
`False`, `os.path.isdir()` is `True`, and `DirEntry.is_symlink()` is `False`.

### Constants

- `MAX_PATH` (260) — the Windows legacy limit, inclusive of the terminating NUL.
- `USABLE_PATH` (259) — the longest path a MAX_PATH-bound consumer can hold.
- `DEFAULT_THRESHOLD` (240) — the default trigger, deliberately below
  `USABLE_PATH`: some handlers append to the path they are given, so a path
  that merely *fits* can still overflow once the consumer touches it.
- `NAME_MAX` (255) — the longest single filename, on **every** platform.
- `SHIM_DIR_NAME` (`.dzs`) — the directory name used for shim roots. Short by
  design; every character here is one taken from a filename.

---

## Logging Configuration

- `configure_logging(level=logging.INFO, log_file=None)` — Configure
  package-level logging. Optionally log to a file.
- `enable_verbose_logging()` — Shortcut for `configure_logging(DEBUG)`.

---

## Version

- `__version__` — Package version string.

**This reference documents v0.4.1** (last reviewed 2026-07-30). Anything added
after that release is in [`CHANGELOG.md`](https://github.com/DazzleLib/dazzle-filekit/blob/main/CHANGELOG.md) but may not have
reached this page yet — check there first if a symbol you expected is missing.

> Maintainers: bump the line above when you add to the public surface, the same
> way `api-stability.md` carries its `Last audited:` marker. It was left reading
> `'0.3.0'` across four releases, which is how `content` (v0.3.0) and `pathenv`
> (v0.3.3) both went undocumented here without anyone noticing.
