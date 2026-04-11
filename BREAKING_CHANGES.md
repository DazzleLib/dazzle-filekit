# Breaking Changes Log

This document tracks every breaking change in `dazzle_filekit`. If you are
updating a downstream tool across filekit versions, read this file top-to-
bottom and apply each migration in order.

The rule for landing a breaking change is: **never casually.** A break
requires

1. A justification line in the relevant version section below.
2. A migration path (new-alongside-old, deprecation warning, or compat shim).
3. A grep across `C:\code\` (and `C:\code\claude-projects\`) to find every
   caller, plus a commit updating each one in the same release window.
4. An update to `API_STABILITY.md` removing the old symbol from the Locked
   tables (or adding the replacement).
5. An update to `tests/test_import_stability.py` reflecting the new surface.

The session-logger incident on 2026-04-10 is the cautionary tale we keep
citing: a rename of `normalize_cross_platform_path` silently broke four
copies of `log-command.py` across `claude-session-logger/`. Do not repeat.

---

## v0.2.4 (additive consolidation, no breaks)

**Summary**: Pure enrichment release. No names removed, no signatures
tightened, no behavior removed. Downstream tools need no changes.

### Added

- `utils.compat.is_wsl()` -- returns True when running inside WSL
  (checks `WSL_DISTRO_NAME` and `/proc/version`).
- `operations.atomic_write_text(path, content, *, encoding='utf-8')`
  -- tmp-file + `os.replace` atomic write.
- `operations.atomic_write_json(path, data, *, indent=2, sort_keys=False)`
  -- thin wrapper over `atomic_write_text`.
- `operations.copy_tree_preserving_links(src, dst, *, dirs_exist_ok=False)`
  -- `shutil.copytree(symlinks=True)` with reparse-point guard on Windows.
- `dazzle_filekit.metadata` module -- rich metadata capture/apply:
  - `collect_file_metadata(path, *, include_acls=True, include_xattrs=True)`
  - `apply_file_metadata(path, metadata, *, skip_quarantine=True)`
  - `restore_windows_creation_time(path, ctime_float)`
  - `is_win32_available()`
  - Internal `_collect_unix_xattrs`, `_apply_unix_xattrs`
- `platform.windows.detect_alternate_streams(path)` -- NTFS ADS enumeration
  via `FindFirstStreamW` (ctypes).
- `platform.windows.has_significant_ads(path)` -- returns True if any ADS
  exists that isn't `:Zone.Identifier`.
- New keyword-only parameters on existing functions (all default to the
  old behavior):
  - Phase 4 path functions -- TBD during implementation.

### Changed (behavior, not API)

- `collect_file_metadata(path)` now returns a richer dict:
  - On Windows: includes `security_descriptor_sddl`, `creation_time` (high
    precision via `pywin32.GetFileTime`).
  - On Linux/macOS: includes `xattrs` dict.
  - Old fields (`mode`, `mtime`, `atime`, `owner`, `group`) unchanged.
  - **Callers that read the dict by key are unaffected** -- new keys are
    additive.
- `apply_file_metadata(path, metadata)` now honors the new fields when
  present. Old manifests without the new keys still restore correctly.
- `validation.is_junction(path)` is fixed to use
  `DeviceIoControl(FSCTL_GET_REPARSE_POINT)` and correctly returns True
  only for mount-point reparse tags. Previously it silently returned
  False for everything (the `win32file.FILE_ATTRIBUTE_REPARSE_POINT`
  constant it referenced doesn't exist, and the bare `except` clause
  swallowed the AttributeError). **This is a bug fix, not an API break**
  -- no caller could have been relying on the broken behavior, because
  it was broken.
- Path normalizers (`normalize_path_no_resolve`,
  `normalize_cross_platform_path`) each gain the capabilities the other
  had, unifying their feature sets. See Phase 4 target list below.

### NOT changed (locked)

- All top-level symbol names in `API_STABILITY.md`.
- All positional parameters on existing functions.
- All return types on existing functions (dicts may grow keys; callers
  reading specific keys are unaffected).

### New dependency

- `pywin32 ; sys_platform == "win32"` -- required for SDDL ACL handling,
  `SetFileTime` ctime restoration, `DeviceIoControl` junction detection,
  and `FindFirstStreamW` ADS enumeration.
  pywin32 installs without admin for non-admin users.

### Phase 4 path-normalization targets (fixpath edge-case catalog)

`dazzlecmd/projects/core/fixpath/fixpath.py:fix_path()` handles a superset
of what filekit's path normalizers do today. Phase 4 will pull the
following into filekit's `normalize_path_no_resolve` and
`normalize_cross_platform_path`:

| Edge case | Today in filekit? | Target |
|-----------|-------------------|--------|
| MSYS `/c/Users/...` | both functions | keep |
| WSL `/mnt/c/Users/...` | only `normalize_cross_platform_path` | add to `normalize_path_no_resolve` |
| MSYS-mangled WSL `C:\Program Files\Git\mnt\c\...` | no | add to both |
| Extended-length `\\?\` prefix | only `normalize_path_no_resolve` | add to `normalize_cross_platform_path` |
| Extended UNC `\\?\UNC\server\share` | no | add |
| Forward-slash UNC `//server/share` | no | add |
| Tilde `~/foo` | only `normalize_path_no_resolve` | add to `normalize_cross_platform_path` |
| Env vars `%USERPROFILE%`, `$HOME` | no | add to both (documented) |
| Relative path → absolute (no follow) | only `normalize_path_no_resolve` | add to `normalize_cross_platform_path` |
| `os.path.normpath` collapsing | only `normalize_path_no_resolve` | add to `normalize_cross_platform_path` |
| Surrounding quotes/backticks | no | NOT added (stays in fixpath's CLI layer) |
| cmd.exe `>` prompt artifact | no | NOT added (CLI-layer concern) |
| URL-decoded `%20` | no | NOT added (CLI-layer concern) |
| PowerShell `PS ` prefix | no | NOT added (CLI-layer concern) |
| Trailing shell artifacts `$#` | no | NOT added (CLI-layer concern) |

The split rule: **filekit handles cross-platform path *formats*; fixpath
handles *human input noise*.** Anything a program writes to disk or
passes between systems belongs in filekit; anything a human pastes into
a terminal stays in fixpath.

---

## Future breaks (uncommitted)

None currently planned. Any future rename/removal must be proposed here
with a migration plan before landing.
