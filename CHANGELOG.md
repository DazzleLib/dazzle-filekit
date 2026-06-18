# Changelog

All notable changes to dazzle-filekit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-06-17

Restores the file-operation capabilities unctools shed in its 0.2.0
"probe-not-mutate" split (STACK-MAP D7): content I/O has no home in the
path-identity layer, so it lands here in L1 -- as the **Option D resolver
edge**, where filekit's operations optionally consult a
`dazzle_lib.PathVariantResolver` (default: unctools) to retry under a path's
alternative names (UNC <-> mapped drive). Refs DazzleLib/dazzle-filekit#15.

### Added
- `open_file(path, ..., *, try_path_variants=False, resolver=None, **kwargs)` -- fallback-aware `open()` (forwards kwargs, returns the handle); reproduces unctools' removed `safe_open`.
- `process_files(directory, callback, pattern='*', recursive=True, *, try_path_variants=False, resolver=None)` -- flat batch-apply over a glob set with directory-name fallback; reproduces `unctools.process_files`.
- `dazzle_filekit.content` module -- `replace_in_file` / `batch_replace_in_files`: read-modify-write text replacement built on `open_file` + `atomic_write_text` (crash-safe) + `process_files`; reproduces unctools' removed `replace_in_file` family.
- `path_exists_case_sensitive` / `get_case_sensitive_path` in `utils.compat` (beside `fix_path_case`) -- absorb unctools' removed case-sensitivity helpers.

**Intrinsic link primitives (#15 Phase A)** -- the L1 home of preservelib's intrinsic link analysis and junction/hardlink creation (relational, destination-relative analysis stays at L3):
- `dazzle_filekit.links` module -- `LinkInfo` (intrinsic-only: `kind` / `raw_target` / `resolved_target` / `is_broken` / `is_circular`; no destination parameter) and `analyze_link(link_path)`.
- `detect_link_type` (`'symlink'` / `'junction'` / `'hardlink'` via `st_nlink > 1` / `None`) and `read_link_target` (symlinks via `os.readlink`; junctions via the reparse buffer -- no `cmd /c dir /al`).
- `create_junction` (PowerShell `New-Item -ItemType Junction`, not `cmd /c mklink /j`) and `create_hardlink` (`os.link`, file-only, cross-device aware).
- `utils.validation.read_junction_target` -- reads a junction's target from its `DeviceIoControl(FSCTL_GET_REPARSE_POINT)` reparse buffer.
- `paths.compute_relative_path(target, start)` -- `os.path.relpath`-based `..`-traversing relative path with a Windows cross-drive fallback. Distinct from `get_relative_path` (subpath-containment only).
- Ported from `preserve/preservelib/links.py` with three coverage/correctness improvements: DeviceIoControl junction detection (vs attribute-only), no banned `cmd` shell-outs, and hardlinks reported as valid (not `is_broken`).

### Changed
- `copy_file` / `move_file` / `copy_files_with_path` / `move_files_with_path` gain `try_path_variants=` / `resolver=` keyword-only args: when set, the operation retries across path-name variant combinations (reproduces unctools' `safe_copy` / `batch_copy` fallback). Default off -- existing behavior is unchanged.
- **`dazzle-lib>=0.2.0` and `unctools>=0.2.2` are now hard dependencies** (previously `unctools` was an optional `[unctools]` extra). filekit already requires pywin32 on Windows and unctools' base is pure-Python, so the cost is small; this removes the optional-load awkwardness and makes the fallback always available. (`unctools>=0.2.2` carries the drive-map enrichment that absorbed the removed `get_drive_mappings`.)
- **`create_symlink` (Windows) absorbed dazzlelink's escalation chain (#15 Phase B)**: `_create_windows_symlink` now inlines the `win32file.CreateSymbolicLink` unprivileged-create API path and the PowerShell `Start-Process -Verb RunAs` elevation path, and **no longer imports `dazzlelink`** (the L1->L2 upward edge is cut). filekit's bool contract is preserved -- total failure returns `False` (dazzlelink raised).

### Removed
- **`utils.compat.get_drive_mappings()` (#15 Phase B / stack V9)**: drive↔UNC mapping is path-identity knowledge owned by the L0 layer. Its `win32wnet.WNetGetUniversalName` provider-chain scan was folded into `unctools`' `UNCConverter` (unctools 0.2.2) so no coverage is lost. Use `unctools.get_mappings()` / `unctools.get_reverse_mappings()`. (Zero callers in the ecosystem; not previously exported from the top-level package.)

### Notes
- `normalize_path`'s separator normalization is preserved: `convert_to_local` / `convert_to_unc` perform the same `/`->`\` step internally.

## [0.2.4] - 2026-04-11

### Added

**`dazzle_filekit.metadata` module** (byte-identical port from preservelib, now public):
- Rich `collect_file_metadata()` and `apply_file_metadata()` delegates that capture a strict superset of v0.2.3's output
- `restore_windows_creation_time()` -- NTFS ctime restoration via `pywin32.SetFileTime` with `FILE_WRITE_ATTRIBUTES=0x100`, `FILE_FLAG_BACKUP_SEMANTICS` for directories, and the readonly-clear-then-restore dance
- `is_win32_available()` -- cached pywin32 availability probe
- `compare_metadata()` / `metadata_to_json()` / `get_metadata_summary()` -- diffing and JSON-safe projection helpers
- `collect_timestamp_info()` / `apply_timestamp_strategy()` -- timestamp-only workflow helpers
- SDDL ACL round-trip on Windows (JSON-serializable, replaces non-serializable pywin32 handle objects)
- Unix xattrs capture/apply via `os.listxattr`/`getxattr`/`setxattr` (skips `com.apple.quarantine` on restore to avoid security surprises)
- Windows attribute flag booleans (`is_hidden`, `is_system`, `is_readonly`, `is_archive`) derived from the attribute bitmask
- Owner/group as `DOMAIN\Name` strings
- File `size` field, ISO timestamp projections (`modified_iso`, `accessed_iso`, `created_iso`)

**`dazzle_filekit.operations` primitives:**
- `atomic_write_text(path, content, *, encoding='utf-8', newline=None)` -- tmp+`os.replace` atomic text write; creates parent dirs; atomic on Windows since Python 3.3
- `atomic_write_json(path, data, *, indent=2, sort_keys=False, default=str, trailing_newline=True)` -- thin JSON wrapper; `default=str` handles `Path`/`datetime`/etc. out of the box
- `copy_tree_preserving_links(src, dst, *, dirs_exist_ok=False, ignore=None, ignore_dangling_symlinks=False)` -- `shutil.copytree` wrapper with `symlinks=True` hard-wired and documented intent

**`dazzle_filekit.platform.windows`** (NTFS alternate data streams):
- `detect_alternate_streams(path)` -- enumerates ADS via ctypes `FindFirstStreamW`/`FindNextStreamW`; filters out `::$DATA` and `:Zone.Identifier:$DATA` (browser download markers)
- `has_significant_ads(path)` -- returns True if any non-ignored stream exists

**`dazzle_filekit.utils.compat`:**
- `is_wsl()` -- WSL detection via `WSL_DISTRO_NAME` env var + `/proc/version` scan; returns False on non-Linux platforms

**New runtime dependency:**
- `pywin32 >= 305` on Windows (conditional marker, no-op on Linux/macOS). Powers SDDL ACLs, ctime restoration, junction detection, and ADS enumeration. The module falls back to `attrib` command if pywin32 is missing, but the rich feature set requires it.

### Changed

**Path normalization consolidated via shared `_prepare_path_format` helper:**
- `normalize_cross_platform_path(path, *, resolve=False)` is now the **canonical** path normalizer. The new `resolve=` keyword-only parameter optionally follows symlinks via `Path.resolve()`.
- `normalize_path(path)` and `normalize_path_no_resolve(path)` are now **thin backwards-compatibility wrappers** around the canonical function. They preserve their v0.2.3 signatures and behavior; their docstrings note that `normalize_cross_platform_path` is the preferred entry point for new code.
- `normalize_cross_platform_path` gained tilde expansion, env var expansion (`%USERPROFILE%` / `$HOME`), relative-to-absolute via cwd, `os.path.normpath` `..` collapsing, and `\\?\` extended-length prefix stripping on Windows. This was the v0.2.3 behavior gap that made it less capable than `normalize_path_no_resolve`; now they're equivalent.
- `normalize_path` and `normalize_path_no_resolve` gained WSL `/mnt/c/` conversion (only `normalize_cross_platform_path` had it in v0.2.3).
- Platform-direction drive conversion is now **platform-aware and bidirectional**: on Windows, `/mnt/c/Users/foo` and `/c/Users/foo` become `C:\Users\foo`; on Linux, `C:\Users\foo` and `C:/Users/foo` become `/c/Users/foo`. A legitimate Linux path like `/c/Users/foo` is no longer misinterpreted as an MSYS drive on Linux.
- Bare `/c` (MSYS drive with no subpath) now maps to drive root `C:\` rather than the drive-relative `C:` (which `os.path.isabs` doesn't consider absolute).

**Metadata API is now richer by default:**
- `operations.collect_file_metadata` and `operations.apply_file_metadata` delegate to the new `metadata.py` module. No signature changes; the returned dict is a strict superset.

### Fixed

**`validation.is_junction(path)`** -- the v0.2.3 implementation referenced `win32file.FILE_ATTRIBUTE_REPARSE_POINT`, which does not exist (the constant lives in `win32con`). The bare `except:` clause silently swallowed the `AttributeError` and returned `False` for everything -- including real junctions. Fixed in v0.2.4 by porting the correct `DeviceIoControl(FSCTL_GET_REPARSE_POINT)` implementation from `dazzlecmd/projects/core/links/links.py`. The fix also correctly distinguishes junctions (`IO_REPARSE_TAG_MOUNT_POINT`) from directory symlinks (`IO_REPARSE_TAG_SYMLINK`), which the original version would have misclassified even if the attribute lookup had worked.

**`normalize_path()` / `normalize_cross_platform_path(..., resolve=True)` on Python 3.9 Windows** -- `Path.resolve()` on Python 3.9 Windows returns a *relative* `WindowsPath` for nonexistent relative inputs instead of prepending cwd. This is a Python 3.9 behavior quirk that was fixed in 3.10+, but it left `normalize_path("./a/b/file.txt")` returning `Path("a/b/file.txt")` on Python 3.9 Windows -- callers expecting an absolute path got a surprise. Caught by `tests/characterization/test_paths_v023_baseline.py::test_relative_path_resolved_against_cwd` on the v0.2.4 CI matrix (Windows Python 3.9 failed, 14 other jobs green). Fixed by pre-absolutizing via `Path.absolute()` before `.resolve()` in the `resolve=True` branch of `normalize_cross_platform_path`. On Python 3.10+ this is a no-op since `.resolve()` handles absolutization itself. Latent bug also existed in v0.2.3 but was never tested.

### Infrastructure

- `docs/api-stability.md` + `tests/test_import_stability.py` -- locked-in public API surface with 54 canary assertions covering every external caller (claude-session-logger, dazzlecmd safedel/fixpath/links, github-traffic-tracker, preservelib, README examples). (Moved from repo root to `docs/` during the v0.2.4 doc-organization pass; contributor-facing, not consumer-facing.)
- `BREAKING_CHANGES.md` -- forward-looking log with Phase 4 edge-case target matrix and migration procedures.
- `docs/preservelib-integration.md` -- guide for preservelib to depend on filekit and the layering contract (primitives vs workflow).
- `tests/test_paths_platform_simulation.py` -- 23 tests that monkeypatch `sys.platform` to exercise both the Windows-direction and Unix-direction branches of `_prepare_path_format` from a single host OS. Catches the exact class of bug that broke WSL on 2026-04-11 while the Windows suite was 208/208 green.
- `scripts/run-cross-platform-tests.sh` -- convenience wrapper for running the suite on both Windows and WSL from a single command, for local dev cross-checking.
- Test count: **241 passing + 9 skipped on Windows**, **200 passing + 50 skipped on Linux (WSL)**. Zero failures on either platform. Stability canary: 54 assertions green.

### Out of scope (deferred)

- safedel migration to the new filekit primitives (`atomic_write_json`, `copy_tree_preserving_links`, `metadata` module). filekit v0.2.4 is backwards-compatible, so safedel continues to work unmodified. A follow-up commit can rewire safedel's internal atomic-write helpers and its `_lib/preservelib/metadata.py` copy to point at filekit.
- Renaming or removing any locked symbol in `docs/api-stability.md`.
- Upstream `C:\code\preserve\preservelib\` reconciliation with safedel's diverged rich copy.

## [0.2.3] - 2026-04-10

### Added
- `normalize_path_no_resolve()` - Normalize paths without resolving symlinks or junctions
  - Handles MSYS (`/c/`), tilde, extended-length prefix (`\\?\`), relative paths
  - Uses `os.path.normpath()` instead of `Path.resolve()` to preserve link identity
  - Use case: tools that need the literal path to a link, not its target (e.g., safe-delete, link management)

### Fixed
- Synced version strings across `pyproject.toml`, `__init__.py`, and `setup.py` (were 0.2.2, 0.2.1, 0.2.0 respectively)

## [0.2.2] - 2026-03-18

### Added
- `resolve_cross_platform_path()` - Bidirectional path probing that tries alternate platform formats when the normalized path doesn't exist
  - On Windows: probes WSL `/mnt/c/` → `C:\`, MSYS `/c/` → `C:\`, and MSYS-mangled WSL paths (where Git Bash prepends its install dir to `/mnt/c/...`)
  - On Linux/macOS: probes Windows `C:\` → `/mnt/c/` (WSL) or `/c/` (MSYS)
  - Returns the first existing candidate, or the normalized form if none exist

### Changed
- `path_exists_cross_platform()` now uses `resolve_cross_platform_path()` for more accurate existence checks across platform boundaries

## [0.2.1] - 2026-01-29

### Added
- `create_symlink()` - Cross-platform symbolic link creation with Windows fallbacks
  - Unix: Uses `os.symlink` directly
  - Windows: Tries `os.symlink`, then `dazzlelink` library, then `mklink` command
  - Supports `force` parameter to replace existing links
  - Auto-detects target type (file vs directory) when not specified

### Changed
- Updated PyPI badge from badge.fury.io to shields.io (badge.fury.io was not working)

## [0.2.0] - 2026-01-24

### Added
- `normalize_cross_platform_path()` - Normalize paths from Git Bash style (`/c/...`), WSL style (`/mnt/c/...`), and Windows style (`C:\...`) to native platform format
- `path_exists_cross_platform()` - Check if a path exists, handling cross-platform path formats
- Export `is_windows()` and `is_unix()` from main package for convenience
- Disk space utilities: `get_disk_usage()`, `check_disk_space()`, `calculate_total_size()`, `ensure_disk_space()`
- `DiskUsage` named tuple with `used_percent` and `free_percent` properties
- `InsufficientSpaceError` exception for disk space validation
- 53 unit tests for compat and disk modules
- Platform support documentation (`docs/platform-support.md`)
- CHANGELOG.md

### Fixed
- Added missing `Dict` import to `utils/compat.py` for proper type annotations

## [0.1.1] - 2026-01-15

### Changed
- Version bump for initial PyPI release preparation

## [0.1.0] - 2026-01-10

### Added
- Initial release
- Path operations: `normalize_path`, `is_same_file`, `split_drive_letter`, `is_unc_path`, `get_relative_path`, `create_dest_path`, `find_files`, `find_regex_files`, `collect_files_from_include_file`, `create_parent_dirs`, `ensure_unique_path`, `get_path_type`
- File operations: `copy_file`, `move_file`, `collect_file_metadata`, `apply_file_metadata`, `copy_files_with_path`, `move_files_with_path`, `create_directory_structure`, `remove_file`, `remove_directory`
- Verification functions: `calculate_file_hash`, `verify_file_hash`, `verify_files_with_manifest`, `calculate_directory_hashes`, `save_hashes_to_file`, `load_hashes_from_file`, `compare_directories`, `verify_copied_files`
- Utility functions: `is_windows`, `is_unix`, `is_admin`, `is_root`, `fix_path_separators`, `fix_path_case`, `get_system_encoding`, `get_system_temp_dir`, `get_home_dir`, `get_app_data_dir`
- Validation functions: `is_valid_path`, `is_safe_path`, `validate_path_chars`, `is_absolute_path`, `is_relative_path`, `is_hidden_path`, `is_symlink`, `is_junction`
- Cross-platform support for Windows, Linux, and macOS
- Optional UNC path support via unctools integration
