"""normalize_cross_platform_path(expand=False): take the path literally.

By default the normalizer strips whitespace and expands ``~`` and environment
variables, which is right for text a person typed into a config. It is wrong
for a path a program was handed as an argument: the shell has already expanded
what the user meant to expand, so a ``~`` that arrives names a real folder
called ``~``. A deletion tool that expanded it again would aim at the home
folder. ``expand=False`` normalizes the format only.

No file is created or removed; the paths are only computed.
"""
import os
import sys
from pathlib import Path

import pytest

from dazzle_filekit.paths import normalize_cross_platform_path

VAR = "%USERPROFILE%" if sys.platform == "win32" else "$HOME"


def test_default_still_expands_tilde_and_variables():
    home = Path(os.path.expanduser("~"))
    assert normalize_cross_platform_path("~") == home
    assert normalize_cross_platform_path(VAR) == home


@pytest.mark.parametrize("literal", ["~", VAR, "~/notes"])
def test_expand_false_leaves_tilde_and_variables_as_names(literal, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    got = normalize_cross_platform_path(literal, expand=False)

    home = Path(os.path.expanduser("~"))
    assert got != home                                   # never the home folder itself
    assert got == Path(os.getcwd()) / literal            # a name under the current folder
    assert not str(got).startswith(str(home / "notes"))  # nor something inside it by expansion


def test_expand_false_keeps_surrounding_whitespace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert normalize_cross_platform_path("name ", expand=False).name == "name "
    assert normalize_cross_platform_path("name ").name == "name"          # default strips


@pytest.mark.skipif(sys.platform != "win32", reason="Windows drive forms")
def test_expand_false_still_normalizes_the_format():
    assert normalize_cross_platform_path("/c/Users/x", expand=False) == Path(r"C:\Users\x")
    assert normalize_cross_platform_path("/mnt/c/Users/x", expand=False) == Path(r"C:\Users\x")
    assert normalize_cross_platform_path(r"\\?\C:\Users\x", expand=False) == Path(r"C:\Users\x")
