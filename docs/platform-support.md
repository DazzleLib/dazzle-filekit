# Platform Support

filetoolkit is designed for cross-platform file operations across Windows, Linux, macOS, and BSD systems.

## Support Matrix

| Platform | Status | Notes |
|----------|--------|-------|
| **Windows 10/11** | Tested | Primary development platform |
| **Linux** (Ubuntu, Debian, Fedora, Arch) | Tested | Full POSIX support |
| **macOS** (Intel & Apple Silicon) | Expected to work | Community testing welcome |
| **FreeBSD / OpenBSD** | Expected to work | Community testing welcome |
| **WSL / WSL2** | Tested | Cross-platform path handling supported |

## Platform-Specific Features

### Windows
- NTFS metadata preservation (timestamps, attributes)
- UNC path support via optional `unctools` dependency
- Network drive detection and mapping
- Long path support (>260 characters)
- Junction point detection
- Cross-platform path normalization (Git Bash `/c/...` and WSL `/mnt/c/...` paths)

### Linux / Unix
- Full POSIX permission preservation
- Symlink handling
- Extended attributes
- Case-sensitive filesystem support

### macOS
- HFS+ and APFS support
- Extended attributes preservation
- Case-insensitive filesystem handling

## Cross-Platform Path Handling

filetoolkit includes built-in support for normalizing paths across different environments:

| Input Format | On Windows | On Linux/macOS |
|---|---|---|
| `C:\Users\foo` | `C:\Users\foo` (unchanged) | `/c/Users/foo` |
| `C:/Users/foo` | `C:\Users\foo` | `/c/Users/foo` |
| `/c/Users/foo` (Git Bash) | `C:\Users\foo` | `/c/Users/foo` (unchanged) |
| `/mnt/c/Users/foo` (WSL) | `C:\Users\foo` | `/mnt/c/Users/foo` (unchanged) |

## Installation Variants

```bash
# Standard installation (all platforms)
pip install dazzle-filekit

# Windows with UNC path support
pip install dazzle-filekit[unctools]
```

## Testing on Your Platform

We welcome community testing. To verify filetoolkit works on your platform:

```bash
pip install dazzle-filekit[dev]
pytest tests/ -v
```

Please share results via [GitHub Discussions](https://github.com/DazzleLib/dazzle-filekit/discussions).
