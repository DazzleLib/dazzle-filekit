# API Stability Matrix

This document enumerates the public API surface of `dazzle_filekit` that is
**known to be imported by external callers**. Any change to a name or
signature in the "Locked" section must be treated as a breaking change and
must include a migration commit in the downstream caller(s) listed below.

`tests/test_import_stability.py` is the automated canary for this document.
If you rename or remove a locked symbol, that test will fail.

Last audited: 2026-06-17 (filekit v0.3.0, #15 complete -- link primitives, D4 renames, V9 fold).

> **v0.3.0 (#15) is a deliberate clean break.** Unlike the deprecation-shim
> migration procedure at the bottom of this doc, 0.3.0 removed/renamed locked
> symbols **without shims** and migrated every in-tree consumer in the same
> cycle. The rubric was coverage-completeness over backward-compatibility. 0.3.0
> had not shipped to PyPI when these landed, so no released contract broke
> mid-stream.

### v0.3.0 breaking changes (#15)

| Old symbol | Replacement | Migrated consumer(s) |
|------------|-------------|----------------------|
| `paths.normalize_path(p)` | `normalize_cross_platform_path(p, resolve=True)` (link-following) | dazzlecmd `dazzlecmd_lib/core/links/_detect.py` |
| `paths.normalize_path_no_resolve(p)` | `normalize_cross_platform_path(p)` (default `resolve=False`, link-safe) | dazzlecmd `dazzlecmd_lib/core/safedel/_classifier.py` |
| `paths.get_path_type(p)` | `paths.classify_fs_object(p)` (identical behavior) | (no external caller) |
| `paths.is_unc_path` / `utils.validation.is_unc_path` (divergent copies) | one canonical def delegating to `unctools.is_unc_path` -- `//server/share` is now True on every platform | (behavior superset; no caller broke) |
| `utils.compat.get_drive_mappings()` | `unctools.converter.get_mappings()` / `UNCConverter().get_reverse_mappings()` (V9 fold into unctools 0.2.2) | (no caller; never exported) |

---

## Locked top-level surface (`from dazzle_filekit import ...`)

### v0.2.3 and earlier (locked since v0.2.3)

| Symbol | Callers |
|--------|---------|
| `normalize_cross_platform_path` | claude-session-logger `log-command.py`, `rename_session.py` (× all 4 copies). The canonical path normalizer with an optional `resolve=` keyword arg. **0.3.0**: the `normalize_path` / `normalize_path_no_resolve` wrappers were removed (clean break) -- use `resolve=True` / the default. |
| `create_symlink` | claude-session-logger `log-command.py` (× all 4 copies) |
| `copy_file` | claude-session-logger `rename_session.py` (× all 4 copies) |
| `resolve_cross_platform_path` | dazzlecmd `projects/core/fixpath/fixpath.py:197` |
| `calculate_file_hash` | github-traffic-tracker `plan_lib/file_ops.py:26` |
| `collect_file_metadata` | github-traffic-tracker `plan_lib/file_ops.py:26`. **v0.2.4 note**: returned dict is now a strict superset (adds `size`, ISO timestamps, SDDL ACLs, xattrs). |
| `apply_file_metadata` | preservelib workflows. **v0.2.4 note**: honors the new fields when present. **v0.3.0**: `metadata=` param typed as `dazzle_lib.FileMetadataDict`. |
| ~~`normalize_path`~~ | **Removed in 0.3.0 (clean break)** -> `normalize_cross_platform_path(path, resolve=True)`. dazzlecmd migrated in-cycle. |
| `is_same_file` | README example |
| `find_files` | README example |
| `is_unc_path` | README example. **v0.3.0**: platform-independent (`//server/share` -> True everywhere). **Now a thin convenience wrapper delegating to the L0 owner `unctools.is_unc_path`; may be deprecated in 0.4.0** -- prefer `unctools.is_unc_path` directly. |
| `classify_fs_object` | **v0.3.0** (renamed from `get_path_type`): classifies WHAT a filesystem object is. |
| `get_disk_usage`, `check_disk_space`, `ensure_disk_space` | README example |
| `verify_file_hash`, `verify_copied_files` | README example |
| `configure_logging`, `enable_verbose_logging` | README example |

### v0.3.0 additions (locked as of v0.3.0)

Restored from unctools' 0.2.0 split (STACK-MAP D7), as the Option D resolver edge.

| Symbol | Description |
|--------|-------------|
| `open_file(path, mode='r', encoding=None, *, try_path_variants=False, resolver=None, **kwargs)` | Fallback-aware `open()` (R1 / unctools `safe_open`) |
| `copy_file`/`move_file`/`copy_files_with_path`/`move_files_with_path` -- new `try_path_variants=`/`resolver=` keyword-only args | Path-variant fallback (R2 / `safe_copy`/`batch_copy`); additive, default off |
| `process_files(directory, callback, pattern='*', recursive=True, *, try_path_variants=False, resolver=None)` | Flat batch-apply over a glob set (R3 / unctools `process_files`) |
| `replace_in_file` / `batch_replace_in_files` (also `dazzle_filekit.content`) | Read-modify-write text replace (R4) |
| `path_exists_case_sensitive` / `get_case_sensitive_path` / `fix_path_case` (`utils.compat`) | Case-sensitivity helpers (R6) |

**Intrinsic link primitives (#15 Phase A):**

| Symbol | Description |
|--------|-------------|
| `dazzle_filekit.links` (submodule) + `LinkInfo` / `analyze_link(link_path)` | Intrinsic link analysis (no destination param); `LinkInfo.to_dict()` -> `dazzle_lib.LinkTargetDict` |
| `detect_link_type` / `read_link_target` | Link kind (`symlink`/`junction`/`hardlink`/`None`) + target read (DeviceIoControl for junctions) |
| `create_junction` / `create_hardlink` | PowerShell junction + `os.link` hardlink |
| `paths.compute_relative_path(target, start)` | `..`-traversing relative path (distinct from `get_relative_path`) |
| `utils.validation.read_junction_target` | Junction target via the reparse buffer |

**Cross-layer schemas consumed (#15 Phase D):** `collect_file_metadata` -> `dazzle_lib.FileMetadataDict`, `collect_timestamp_info` -> `TimestampsDict`, `LinkInfo.to_dict` -> `LinkTargetDict` (STACK-MAP D10).

**Dependency change (0.3.0):** `dazzle-lib>=0.2.0` and `unctools>=0.2.2` are now required (the `PathVariantResolver` seam + the V9 drive-map fold); the optional `[unctools]` extra is removed.

### v0.2.4 additions (locked as of v0.2.4)

| Symbol | Description |
|--------|-------------|
| `atomic_write_text(path, content, *, encoding, newline)` | Atomic text file write via tmp+rename |
| `atomic_write_json(path, data, *, indent, sort_keys, default, trailing_newline)` | Atomic JSON write; `default=str` handles `Path`/`datetime` |
| `copy_tree_preserving_links(src, dst, *, dirs_exist_ok, ignore, ignore_dangling_symlinks)` | `shutil.copytree(symlinks=True)` wrapper with documented intent |
| `is_wsl()` | WSL detection (Linux-only, False elsewhere) |
| `is_win32_available()` | Cached pywin32 availability probe (for rich Windows metadata features) |
| `restore_windows_creation_time(path, created)` | NTFS ctime restoration via pywin32 `SetFileTime` |
| `compare_metadata(md1, md2)` | Metadata diff with 2s timestamp tolerance |
| `metadata_to_json(md)` | JSON-safe projection of a metadata dict |
| `metadata` | Public submodule: `from dazzle_filekit import metadata` |

**Rule**: Signatures may be enriched with additional keyword-only arguments
(`def f(existing_arg, *, new_kwarg=default)`), but positional parameters and
existing keyword names must not be removed or repurposed.

---

## Locked submodule imports

### `dazzle_filekit.paths`

| Symbol | Callers |
|--------|---------|
| `normalize_cross_platform_path` | **canonical entry point** (`resolve=True` -> link-following; default -> link-safe); re-exported via `utils.compat`. dazzlecmd migrated to this in 0.3.0. |
| `classify_fs_object` | v0.3.0, renamed from `get_path_type` |
| `compute_relative_path` | v0.3.0 (#15 Phase A); distinct from `get_relative_path` (subpath-only) |

> `normalize_path` / `normalize_path_no_resolve` were **removed in 0.3.0** (clean break, no shims) -- see the v0.3.0 breaking-changes table near the top.

### `dazzle_filekit.utils.disk`

| Symbol | Callers |
|--------|---------|
| `get_disk_usage` | dazzlecmd `projects/core/safedel/_volumes.py:29` |
| `check_disk_space` | dazzlecmd `projects/core/safedel/_platform.py:392` (aliased as `fk_check`) |
| `calculate_total_size` | dazzlecmd `projects/core/safedel/_platform.py:410` |

### `dazzle_filekit.utils.compat`

| Symbol | Callers |
|--------|---------|
| `is_windows` | dazzlecmd `projects/core/safedel/_store.py:60` |
| `is_wsl` | v0.2.4 addition; platform detection helper |
| `normalize_cross_platform_path` | re-exported from `paths.py` so `from dazzle_filekit.utils.compat import normalize_cross_platform_path` still works |
| `resolve_cross_platform_path`, `path_exists_cross_platform` | dazzlecmd fixpath |

### `dazzle_filekit.metadata` (new in v0.2.4)

Full rich metadata module ported from preservelib. Public submodule: callers can `from dazzle_filekit import metadata` or `from dazzle_filekit.metadata import ...`.

| Symbol | Purpose |
|--------|---------|
| `collect_file_metadata(path)` | Rich capture incl. SDDL + xattrs + ctime |
| `apply_file_metadata(path, md)` | Rich apply |
| `restore_windows_creation_time(path, created)` | NTFS ctime restore |
| `is_win32_available()` | Cached pywin32 probe |
| `compare_metadata(md1, md2)` | Diff helper |
| `metadata_to_json(md)` | JSON-safe projection |
| `get_metadata_summary(md)` | Human-friendly summary |
| `collect_timestamp_info(path)` | Timestamp-only capture |
| `apply_timestamp_strategy(path, strategy, ...)` | Strategy-based timestamp apply |

### `dazzle_filekit.operations` (primitives added in v0.2.4)

| Symbol | Purpose |
|--------|---------|
| `atomic_write_text(path, content, *, encoding, newline)` | tmp+rename atomic text write |
| `atomic_write_json(path, data, *, indent, sort_keys, default, trailing_newline)` | atomic JSON wrapper |
| `copy_tree_preserving_links(src, dst, *, dirs_exist_ok, ignore, ignore_dangling_symlinks)` | `shutil.copytree(symlinks=True)` with intent documented |

### `dazzle_filekit.platform.windows` (new capabilities in v0.2.4)

| Symbol | Purpose |
|--------|---------|
| `detect_alternate_streams(path)` | NTFS ADS enumeration via ctypes `FindFirstStreamW` |
| `has_significant_ads(path)` | True if any non-ignored stream exists |

### Module attributes (wildcard imports)

`preservelib` (three copies: `C:\code\preserve\preservelib\`,
`C:\code\dazzlecmd\github\projects\core\safedel\_lib\preservelib\`,
`C:\code\github-traffic-tracker\local\src\ghtraf\lib\preserve_lib\`) uses:

```python
from dazzle_filekit import paths, operations, verification
```

This means the **modules themselves** (`dazzle_filekit.paths`,
`dazzle_filekit.operations`, `dazzle_filekit.verification`) must remain
importable and must continue to expose the functions preservelib reaches
for. See `tests/test_import_stability.py::test_preservelib_module_shapes`
for the concrete list.

---

## Allowed changes (non-breaking)

- Adding new functions.
- Adding new modules.
- Adding new keyword-only parameters to existing functions.
- Enriching the behavior of existing functions when the external contract
  (return type, raised exceptions on the happy path, side effects on the
  target file) stays compatible.
- Adding new positional arguments that default to an existing value are
  **not** safe if a caller uses keyword-only invocation -- prefer keyword-
  only additions.

## Forbidden without a migration plan

- Renaming any symbol in the Locked tables.
- Removing any symbol in the Locked tables.
- Changing a function from a module-level function to a method on a class.
- Changing the return type in a way that breaks existing callers.
- Making a previously optional parameter required.

## Migration procedure for a locked symbol

If a locked symbol genuinely needs to change:

1. Add the new function alongside the old one.
2. Update every downstream caller in the same working-set (grep across
   `C:\code\` to confirm).
3. Mark the old symbol `@deprecated` with a one-release grace window.
4. Ship.
5. Remove the old symbol in the release **after** the grace window.

Do not skip steps 2-4 even if you own all the callers -- the session-logger
incident on 2026-04-10 is the baseline cautionary tale.
