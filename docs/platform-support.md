# Platform Support

`dazzle-filekit` is designed for cross-platform file operations across
Windows, Linux, and macOS. Each platform gets platform-specific
optimizations where they matter (NTFS metadata on Windows, POSIX
permissions and extended attributes on Linux/macOS) while the
cross-platform API stays consistent.

## Support Matrix

| Platform | Status | Notes |
|----------|--------|-------|
| **Windows 10 / 11** | Tested (primary) | NTFS; full SDDL/ctime/ADS/junction support with pywin32 |
| **Linux** (Ubuntu, Debian, Fedora, Arch) | Tested | Full POSIX; extended attributes on ext4/btrfs/xfs |
| **WSL / WSL2** (Ubuntu-22.04) | Tested | Bidirectional path conversion to/from Windows; DrvFs awareness via `is_wsl()` |
| **macOS** (Intel & Apple Silicon) | Expected to work | APFS/HFS+ extended attributes; skips `com.apple.quarantine` on restore |

"Tested" means the CI matrix runs the test suite on that platform.
"Expected to work" means the code paths are present and exercised by
unit tests using platform-simulation, but we don't have a physical box
in the CI loop -- community bug reports welcome.

## Test Counts (v0.2.4)

| Suite | Windows | WSL (Ubuntu-22.04) |
|-------|---------|---------------------|
| filekit | 241 passed, 9 skipped | 200 passed, 50 skipped |

Skip counts differ because platform-specific features (SDDL/ctime/ADS on
Windows, xattrs/is_wsl env detection on Linux) skip on the other
platform. The platform-simulation suite
(`tests/test_paths_platform_simulation.py`) exercises both Windows and
Unix branches of `_prepare_path_format` from a single host OS using
`monkeypatch` -- regression protection that fires regardless of which
platform runs the suite.

## Platform-Specific Features

### Windows (NTFS)

Rich metadata features that require `pywin32` (declared as a conditional
runtime dependency in v0.2.4 -- installed automatically via
`pip install dazzle-filekit`):

- **SDDL ACL round-trip** -- `metadata.collect_file_metadata` captures
  security descriptors as SDDL strings (JSON-safe), and
  `apply_file_metadata` restores them via
  `ConvertStringSecurityDescriptorToSecurityDescriptorW`
- **NTFS creation time restoration** --
  `metadata.restore_windows_creation_time(path, created)` via
  `SetFileTime` with `FILE_WRITE_ATTRIBUTES=0x100` and
  `FILE_FLAG_BACKUP_SEMANTICS` for directories
- **Alternate Data Stream (ADS) enumeration** --
  `platform.windows.detect_alternate_streams(path)` via ctypes
  `FindFirstStreamW`; `has_significant_ads(path)` filters out browser
  `Zone.Identifier` noise
- **Correct junction detection** -- `utils.validation.is_junction(path)`
  uses `DeviceIoControl(FSCTL_GET_REPARSE_POINT)` to distinguish
  `IO_REPARSE_TAG_MOUNT_POINT` (true junctions) from
  `IO_REPARSE_TAG_SYMLINK` (directory symlinks). v0.2.3 had a silent
  bug here that always returned False; v0.2.4 fixes it.
- **Windows attribute flags** -- `is_hidden`, `is_system`, `is_readonly`,
  `is_archive` booleans alongside the raw attribute bitmask
- **Owner / group as `DOMAIN\Name`** strings (with SID fallback)
- **Long path support** -- `\\?\` extended-length prefix stripping in
  `normalize_cross_platform_path`
- **Cross-platform path conversion** -- Git Bash `/c/Users/...` and
  WSL `/mnt/c/Users/...` automatically convert to `C:\Users\...`
- **Symbolic link creation with fallbacks** -- `os.symlink` → dazzlelink
  library → `mklink` command (`operations.create_symlink`)

`pywin32` is a hard dependency on Windows as of v0.2.4. The previous
best-effort `attrib`-command fallback is retained for environments
where pywin32 still can't be imported, but it only covers the coarse
attribute flags, not SDDL / ctime / ADS.

### Linux / Unix

- **POSIX mode preservation** (`st_mode` captured and restored via
  `os.chmod`)
- **Owner / group preservation** (`uid` / `gid` via `os.chown`, requires
  appropriate privileges)
- **Extended attributes (xattrs)** -- `metadata._collect_unix_xattrs` /
  `_apply_unix_xattrs` via stdlib `os.listxattr` / `getxattr` /
  `setxattr`. Values are base64-encoded so the manifest stays JSON-safe.
  Works with Linux `user.*` / `security.*` / `trusted.*` namespaces.
- **Symbolic link preservation** -- `operations.copy_tree_preserving_links`
  wraps `shutil.copytree(symlinks=True)` so link identity is kept
  through directory copies
- **Cross-platform path conversion** -- Windows `C:\Users\...` or
  `C:/Users/...` automatically converts to `/c/Users/...` on Linux
- **WSL awareness** -- `utils.compat.is_wsl()` detects WSL via
  `WSL_DISTRO_NAME` env var or `/proc/version` scan. Useful for
  deciding whether `/mnt/c/...` paths should be treated as the Windows
  side's drives.

### macOS (APFS / HFS+)

Everything Linux gets, plus:

- **`com.apple.quarantine` skip-on-restore** -- when applying metadata
  captured from a downloaded file, filekit deliberately does NOT
  re-apply the quarantine xattr. This prevents recovered files from
  triggering Gatekeeper "Are you sure you want to open this?"
  prompts that are irrelevant to the restore operation.
- **Case-insensitive filesystem** awareness via `is_same_file`
- **APFS extended attributes** treated the same as Linux xattrs

## Cross-Platform Path Handling

v0.2.4 consolidates path normalization into a single canonical function
`normalize_cross_platform_path(path, *, resolve=False)` with
platform-aware bidirectional conversion. The `resolve=True` variant
follows symlinks via `Path.resolve()`; the default (`resolve=False`)
preserves the literal link path.

| Input Format | On Windows | On Linux/macOS |
|---|---|---|
| `C:\Users\foo` | `C:\Users\foo` (unchanged) | `/c/Users/foo` |
| `C:/Users/foo` | `C:\Users\foo` | `/c/Users/foo` |
| `/c/Users/foo` (Git Bash / MSYS) | `C:\Users\foo` | `/c/Users/foo` (plain Linux path, unchanged) |
| `/mnt/c/Users/foo` (WSL) | `C:\Users\foo` | `/mnt/c/Users/foo` (plain Linux path, unchanged) |
| `~/foo` | `C:\Users\<me>\foo` | `/home/<me>/foo` |
| `%USERPROFILE%/foo` | `C:\Users\<me>\foo` | *(env var left literal if not set)* |
| `$HOME/foo` | `C:\Users\<me>\foo` | `/home/<me>/foo` |
| `\\?\C:\foo` | `C:\foo` (prefix stripped) | -- |
| `C:\a\b\..\c\file.txt` | `C:\a\c\file.txt` (normpath collapses) | `/c/a/c/file.txt` |

`normalize_cross_platform_path(path, *, resolve=False)` is the single public
entry point: `resolve=True` follows symlinks, the default `resolve=False` is
link-safe. (The `normalize_path` / `normalize_path_no_resolve` wrappers were
removed in 0.3.0 -- clean break.)

## Installation Variants

```bash
# Standard installation. Pulls in the stack bedrock dazzle-lib>=0.2.0 and the
# L0 path-identity layer unctools>=0.2.2 (both required as of 0.3.0), plus
# pywin32 on Windows.
pip install dazzle-filekit

# Development tools
pip install 'dazzle-filekit[dev]'
```

> As of 0.3.0, UNCtools is a **hard dependency** (the `PathVariantResolver`
> resolver edge), not an optional `[unctools]` extra. See
> [docs/unctools-integration.md](unctools-integration.md).

## Testing on Your Platform

We welcome community testing. To verify dazzle-filekit works on your
platform:

```bash
pip install 'dazzle-filekit[dev]'
pytest tests/ -v
```

Cross-platform cross-check (runs both Windows and WSL from a single
command; useful when developing path-normalization code):

```bash
./scripts/run-cross-platform-tests.sh            # both
./scripts/run-cross-platform-tests.sh --wsl-only
./scripts/run-cross-platform-tests.sh --windows-only
```

Please share results -- especially on macOS and BSD, where we have
unit-test coverage but no runtime hardware -- via
[GitHub Discussions](https://github.com/DazzleLib/dazzle-filekit/discussions).
