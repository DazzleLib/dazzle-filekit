"""v0.3.0 (#15 Phase B): symlink absorb + V9 get_drive_mappings removal.

  - AC-5: filekit's get_drive_mappings is gone; the drive-map capability is
          reachable via unctools (the fold target).
  - AC-6: _create_windows_symlink no longer imports dazzlelink (the L1->L2 edge
          is cut); it absorbs the win32file API + PowerShell elevation methods,
          and keeps filekit's bool contract (returns False, never raises).
"""

import ast
import inspect
import textwrap

import pytest

import dazzle_filekit.operations as ops
import dazzle_filekit.utils.compat as compat
from dazzle_filekit import create_symlink


def _func_tree(func):
    """Parse a function's AST (docstring-prose-proof source inspection)."""
    return ast.parse(textwrap.dedent(inspect.getsource(func)))


# ---------------------------------------------------------------------------
# AC-5: get_drive_mappings removed; capability lives in unctools
# ---------------------------------------------------------------------------


def test_get_drive_mappings_removed_from_filekit():
    assert not hasattr(compat, "get_drive_mappings"), (
        "get_drive_mappings was folded into unctools (V9) and must be removed "
        "from filekit"
    )


def test_drive_mapping_capability_lives_in_unctools():
    from unctools.converter import UNCConverter
    # The folded enrichment method exists...
    assert hasattr(UNCConverter, "_get_mappings_with_wnetuniversalname")
    # ...and the public read surface is intact.
    assert hasattr(UNCConverter, "get_mappings")
    assert hasattr(UNCConverter, "get_reverse_mappings")


# ---------------------------------------------------------------------------
# AC-6: symlink absorb -- no dazzlelink import, bool contract preserved
# ---------------------------------------------------------------------------


def test_create_windows_symlink_has_no_dazzlelink_import():
    """No actual dazzlelink import node (the docstring may still *mention* it)."""
    tree = _func_tree(ops._create_windows_symlink)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "dazzlelink" in node.module:
            pytest.fail("the L1->L2 dazzlelink soft-import must be cut (absorbed inline)")
        if isinstance(node, ast.Import):
            assert not any("dazzlelink" in a.name for a in node.names)


def test_create_windows_symlink_absorbed_methods_present():
    src = inspect.getsource(ops._create_windows_symlink)
    # win32file API path (absorbed from dazzlelink method 2)
    assert "CreateSymbolicLink" in src
    # PowerShell elevation path (absorbed from dazzlelink method 4)
    assert "RunAs" in src


def test_create_windows_symlink_keeps_bool_contract():
    """filekit returns False on total failure; it must not raise (dazzlelink did).

    Checked on the AST -- no ``raise`` statement node -- so the docstring's
    prose ("dazzlelink raised") doesn't false-positive.
    """
    tree = _func_tree(ops._create_windows_symlink)
    assert not any(isinstance(n, ast.Raise) for n in ast.walk(tree)), (
        "filekit's symlink helper returns False on failure -- it must not raise"
    )


def test_create_symlink_succeeds_when_privileged(tmp_path):
    target = tmp_path / "t.txt"
    target.write_text("x")
    link = tmp_path / "s.txt"
    if not create_symlink(target, link):
        pytest.skip("symlink creation requires admin/Developer Mode")
    assert link.is_symlink()
    # bool contract: second create without force returns False, does not raise.
    assert create_symlink(target, link, force=False) is False
