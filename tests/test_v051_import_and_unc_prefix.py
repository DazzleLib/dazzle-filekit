"""0.5.1: two properties the 0.5.0 placement review found broken.

1. ``import dazzle_filekit`` must work without unctools being importable
   (docs/index.md promises it; 0.5.0's portable module imported unctools at
   module top, so the promise broke unnoticed -- no test pinned it).
2. ``\\\\?\\UNC\\srv\\share\\x`` is the network path ``\\\\srv\\share\\x``. The
   normalizer stripped only ``\\\\?\\`` and so produced ``UNC\\srv\\share\\x``,
   a relative path that then landed under the current folder.

The import check runs in a child Python so blocking unctools cannot leak into
the test process. Nothing is read from or written to disk.
"""
import subprocess
import sys
from pathlib import Path

import pytest

from dazzle_filekit.paths import normalize_cross_platform_path

BLOCKED = (
    "import sys\n"
    "sys.modules['unctools'] = None\n"      # any 'import unctools' now raises
    "import dazzle_filekit\n"
    "from dazzle_filekit import encode_portable_path, plan_batch\n"
    "print(encode_portable_path('C:/a/b', flavor='windows'))\n"
)


def test_the_package_imports_without_unctools():
    out = subprocess.run([sys.executable, "-c", BLOCKED], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-400:]
    assert out.stdout.strip() == "C/a/b"            # drive paths need no unctools at all


def test_a_plain_import_does_not_load_unctools():
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys, dazzle_filekit; print('unctools' in sys.modules)"],
        capture_output=True, text=True)
    assert out.stdout.strip() == "False", out.stderr[-400:]


def test_the_path_key_error_sits_under_the_stacks_common_root():
    from dazzle_lib.exceptions import DazzleError
    from dazzle_filekit import PortablePathError, encode_portable_path

    with pytest.raises(DazzleError):                 # one root for the whole stack
        encode_portable_path("relative/path", flavor="posix")
    assert issubclass(PortablePathError, ValueError)  # and still a bad-argument error


windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows path forms")


@windows_only
@pytest.mark.parametrize("given, expected", [
    ("\\\\?\\UNC\\srv\\share\\a", "\\\\srv\\share\\a"),
    ("\\\\?\\unc\\srv\\share\\a", "\\\\srv\\share\\a"),       # the marker is not case-sensitive
    ("//?/UNC/srv/share/a", "\\\\srv\\share\\a"),             # forward slashes too
    ("\\\\?\\C:\\Users\\x", "C:\\Users\\x"),                  # unchanged behaviour
    ("\\\\srv\\share\\a", "\\\\srv\\share\\a"),               # unchanged behaviour
])
def test_extended_length_prefix_is_unwrapped(given, expected, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for expand in (True, False):
        got = normalize_cross_platform_path(given, expand=expand)
        assert got == Path(expected)
        assert tmp_path not in got.parents          # never a path under the current folder
