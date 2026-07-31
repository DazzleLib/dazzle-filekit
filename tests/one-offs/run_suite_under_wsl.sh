#!/usr/bin/env bash
# Run the filekit suite under real Linux, from a Windows dev box, via WSL.
#
# WHY THIS EXISTS
# The CI matrix is [ubuntu-latest, windows-latest, macos-latest], and this repo
# has now shipped a POSIX-only failure twice:
#
#   v0.3.3  "the promoted probe suite was Windows-host-locked ... caught by
#            ubuntu CI on the v0.3.3 push"
#   v0.4.0  twelve longpath tests asserted Windows path semantics without
#           @win_only; 11 failed on ubuntu-latest and macos-latest
#
# Both were invisible to a Windows-only pytest run. os.path is ntpath on
# Windows and posixpath elsewhere, so normcase/normpath/splitdrive silently
# change meaning -- a test can pass locally and assert something false on CI.
#
# USAGE (from Git Bash / PowerShell on the Windows host)
#     bash tests/one-offs/run_suite_under_wsl.sh              # whole suite
#     bash tests/one-offs/run_suite_under_wsl.sh tests/test_longpath_delta2.py
#
# PREREQUISITE, one time, inside the distro:
#     sudo apt install -y python3-venv
# Debian/Ubuntu ship a python3 whose `venv` module is packaged separately, and
# mark the system environment PEP-668 externally-managed, so without it this
# script fails at venv creation and pip then refuses to touch system packages.
# UNVERIFIED as of v0.4.1: written after the ubuntu/macos CI failure but not yet
# run to completion on this box (python3-venv was absent). The wiring is
# straightforward; treat a first run as needing a shakeout.
#
# The repo is mounted read-only in effect: filekit is imported via PYTHONPATH
# rather than pip-installed, so nothing (no egg-info, no build artifacts) is
# written into the Windows working tree. The venv lives inside WSL at /tmp.
set -u

DISTRO="${WSL_DISTRO:-Ubuntu}"
REPO_WIN="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# /c/code/... (Git Bash) -> /mnt/c/code/... (WSL)
REPO_WSL="$(printf '%s' "$REPO_WIN" | sed -E 's#^/([a-zA-Z])/#/mnt/\1/#')"
TARGET="${1:-tests/}"

echo "  distro : $DISTRO"
echo "  repo   : $REPO_WSL"
echo "  target : $TARGET"
echo

wsl.exe -d "$DISTRO" -- bash -lc "
set -u
VENV=/tmp/dazzle-filekit-venv
if [ ! -x \"\$VENV/bin/python\" ]; then
    echo '  creating venv ...'
    python3 -m venv \"\$VENV\" || exit 1
    \"\$VENV/bin/pip\" install -q --upgrade pip
    # deps only -- filekit itself is supplied via PYTHONPATH
    \"\$VENV/bin/pip\" install -q pytest 'dazzle-lib>=0.2.0' || exit 1
fi
cd '$REPO_WSL' || exit 1
PYTHONPATH='$REPO_WSL' \"\$VENV/bin/python\" -m pytest '$TARGET' -q --no-cov -p no:cacheprovider
"
rc=$?
echo
if [ "$rc" -eq 0 ]; then
    echo "  LINUX RESULT: pass"
else
    echo "  LINUX RESULT: FAIL (exit $rc) -- this is what ubuntu-latest CI will do"
fi
exit "$rc"
