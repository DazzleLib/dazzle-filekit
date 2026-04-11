#!/usr/bin/env bash
# Run filekit's test suite on BOTH Windows and WSL Linux from a single command.
#
# Context: Phase 4-7 of v0.2.4 introduced platform-split path normalization
# (Windows-direction vs Unix-direction). A bug in `_prepare_path_format` that
# broke Linux behavior was missed on 2026-04-11 because the Windows-only test
# run was 208/208 green while WSL was silently broken. This script is the
# standing cross-platform gate to prevent the same class of bug.
#
# The test suite itself includes `tests/test_paths_platform_simulation.py`
# which monkeypatches `sys.platform` to exercise both branches from a single
# OS -- that's the first line of defense. This script is the second line:
# actually booting both OSes to exercise the real filesystem (xattrs,
# reparse points, pywin32, WSL mount points, etc.).
#
# Usage:
#     ./scripts/run-cross-platform-tests.sh
#     ./scripts/run-cross-platform-tests.sh --wsl-only
#     ./scripts/run-cross-platform-tests.sh --windows-only
#
# The script expects to be run from the filekit repo root, with:
#   - Python 3.9+ available as `python` on the host
#   - WSL with Ubuntu (or another Python-bearing distro) and `python3` inside

set -euo pipefail

REPO_ROOT=$(pwd)
WSL_DISTRO=${FILEKIT_WSL_DISTRO:-Ubuntu-22.04}

# Parse args
RUN_WIN=1
RUN_WSL=1
for arg in "$@"; do
    case $arg in
        --windows-only) RUN_WSL=0 ;;
        --wsl-only)     RUN_WIN=0 ;;
        --help|-h)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown arg: $arg (try --help)"
            exit 2
            ;;
    esac
done

WIN_STATUS=""
WSL_STATUS=""

if [ $RUN_WIN -eq 1 ]; then
    echo "=== Windows test run ==="
    if python -m pytest -q; then
        WIN_STATUS="[OK]"
    else
        WIN_STATUS="[FAIL]"
    fi
    echo ""
fi

if [ $RUN_WSL -eq 1 ]; then
    echo "=== WSL ($WSL_DISTRO) test run ==="
    # Convert the Windows path to a /mnt/c/... path for WSL
    WSL_REPO=$(wsl -d "$WSL_DISTRO" wslpath -a "$REPO_ROOT" 2>/dev/null || echo "/mnt/c${REPO_ROOT#C:}")
    WSL_REPO=$(echo "$WSL_REPO" | tr -d '\r')

    # Use -o addopts='' to override the --cov flag from pyproject.toml since
    # pytest-cov may not be installed inside the WSL distro. This keeps the
    # cross-check lightweight and doesn't require a Linux pip install.
    if wsl -d "$WSL_DISTRO" bash -c "cd '$WSL_REPO' && python3 -m pytest -q -o addopts='' 2>&1"; then
        WSL_STATUS="[OK]"
    else
        WSL_STATUS="[FAIL]"
    fi
    echo ""
fi

echo "=== Summary ==="
[ -n "$WIN_STATUS" ] && echo "  Windows: $WIN_STATUS"
[ -n "$WSL_STATUS" ] && echo "  WSL:     $WSL_STATUS"

if [ "$WIN_STATUS" = "[FAIL]" ] || [ "$WSL_STATUS" = "[FAIL]" ]; then
    exit 1
fi
