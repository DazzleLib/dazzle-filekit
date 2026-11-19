"""create_dest_path(path_style="absolute") keeps every destination under dest_base.

dazzle-filekit#19: a UNC source (\\\\server\\share\\...) has no drive letter,
and joining it onto dest_base returned the source path itself -- a destination
outside the store. Since 0.5.2 UNC sources go through the portable key
(dest_base\\UNC\\server\\share\\...). Drive paths must keep today's layout byte
for byte, so no existing destination moves.

Pure path computation; nothing is created. The UNC paths name a server that
need not exist.
"""
import sys

import pytest

from dazzle_filekit.paths import create_dest_path

pytestmark = pytest.mark.skipif(sys.platform != "win32",
                                reason="the absolute style's Windows branch")

DEST = "C:\\dest"


def _abs(source):
    return str(create_dest_path(source, "C:\\x", DEST, path_style="absolute"))


@pytest.mark.parametrize("source, expected", [
    ("\\\\server\\share\\a.txt", "C:\\dest\\UNC\\server\\share\\a.txt"),
    ("\\\\server\\share\\d\\e\\a.txt", "C:\\dest\\UNC\\server\\share\\d\\e\\a.txt"),
    ("\\\\?\\UNC\\server\\share\\a.txt", "C:\\dest\\UNC\\server\\share\\a.txt"),
])
def test_a_unc_source_lands_under_dest_base(source, expected):
    assert _abs(source) == expected


@pytest.mark.parametrize("source, expected", [
    # Recorded from 0.5.1 before the change (tests/one-offs/probe_create_dest_path_absolute_unc.py).
    ("C:\\x\\a.txt", "C:\\dest\\C\\x\\a.txt"),
    ("c:\\x\\sub\\a.txt", "C:\\dest\\C\\x\\sub\\a.txt"),
    ("E:\\code\\a b\\c.txt", "C:\\dest\\E\\code\\a b\\c.txt"),
    ("\\\\?\\C:\\x\\a.txt", "C:\\dest\\C\\x\\a.txt"),
])
def test_drive_sources_keep_the_layout_they_had(source, expected):
    assert _abs(source) == expected


@pytest.mark.parametrize("source", [
    "\\\\server\\share\\a.txt", "\\\\?\\UNC\\server\\share\\a.txt", "C:\\x\\a.txt",
])
def test_no_absolute_style_destination_leaves_dest_base(source):
    assert _abs(source).lower().startswith(DEST.lower() + "\\")
