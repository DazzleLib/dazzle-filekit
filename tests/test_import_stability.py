"""API stability canary.

This test asserts that every symbol listed in docs/api-stability.md is
importable under its documented name. If a rename or removal sneaks into
a future release, this test fails loudly.

Do NOT relax these assertions to make the test pass. Fix the underlying
change (add a compatibility shim, revert the rename, etc.) or, if the
change is genuinely necessary, follow the migration procedure documented
in docs/api-stability.md and update both the doc and this test in the same
commit.
"""

import importlib
import pytest


# ---------------------------------------------------------------------------
# Top-level public surface -- `from dazzle_filekit import X`
# ---------------------------------------------------------------------------

TOP_LEVEL_LOCKED = [
    # Path utilities used by claude-session-logger
    "normalize_cross_platform_path",
    "resolve_cross_platform_path",
    "create_symlink",
    "copy_file",
    # Used by github-traffic-tracker
    "calculate_file_hash",
    "collect_file_metadata",
    # Referenced by README examples / docs
    "normalize_path",
    "is_same_file",
    "find_files",
    "is_unc_path",
    "get_disk_usage",
    "check_disk_space",
    "ensure_disk_space",
    "verify_file_hash",
    "verify_copied_files",
    "configure_logging",
    "enable_verbose_logging",
    # v0.2.4 additions (new public surface, locked going forward)
    "atomic_write_text",
    "atomic_write_json",
    "copy_tree_preserving_links",
    "is_wsl",
    "is_win32_available",
    "restore_windows_creation_time",
    "compare_metadata",
    "metadata_to_json",
    "metadata",  # the submodule
    # v0.3.0 additions (Option D resolver edge -- restored unctools capabilities)
    "open_file",
    "process_files",
    "replace_in_file",
    "batch_replace_in_files",
    "content",  # the submodule
    "path_exists_case_sensitive",
    "get_case_sensitive_path",
    "fix_path_case",
    # v0.3.0 additions (#15 Phase A -- intrinsic link primitives)
    "LinkInfo",
    "analyze_link",
    "detect_link_type",
    "read_link_target",
    "create_junction",
    "create_hardlink",
    "compute_relative_path",
    "links",  # the submodule
]


@pytest.mark.parametrize("symbol", TOP_LEVEL_LOCKED)
def test_top_level_symbol_importable(symbol):
    """Every locked top-level symbol must be reachable via `dazzle_filekit`."""
    mod = importlib.import_module("dazzle_filekit")
    assert hasattr(mod, symbol), (
        f"dazzle_filekit.{symbol} is in docs/api-stability.md as locked but "
        f"is not exported from the top-level package. This breaks at "
        f"least one external caller -- see docs/api-stability.md."
    )


# ---------------------------------------------------------------------------
# Submodule imports -- `from dazzle_filekit.paths import X`
# ---------------------------------------------------------------------------

SUBMODULE_LOCKED = {
    "dazzle_filekit.paths": [
        "normalize_path",
        "normalize_path_no_resolve",
        # v0.2.4 canonical entry point
        "normalize_cross_platform_path",
        # v0.3.0 (#15 Phase A -- V12, distinct from get_relative_path)
        "compute_relative_path",
    ],
    "dazzle_filekit.utils.disk": [
        "get_disk_usage",
        "check_disk_space",
        "calculate_total_size",
    ],
    "dazzle_filekit.utils.compat": [
        "is_windows",
        "is_wsl",
        "normalize_cross_platform_path",
        "resolve_cross_platform_path",
        "path_exists_cross_platform",
        # v0.3.0 (R6)
        "fix_path_case",
        "path_exists_case_sensitive",
        "get_case_sensitive_path",
    ],
    # v0.2.4 additions
    "dazzle_filekit.metadata": [
        "collect_file_metadata",
        "apply_file_metadata",
        "restore_windows_creation_time",
        "is_win32_available",
        "compare_metadata",
        "metadata_to_json",
    ],
    "dazzle_filekit.operations": [
        "atomic_write_text",
        "atomic_write_json",
        "copy_tree_preserving_links",
        # v0.3.0 (R1/R3)
        "open_file",
        "process_files",
    ],
    # v0.3.0 content module (R4)
    "dazzle_filekit.content": [
        "replace_in_file",
        "batch_replace_in_files",
    ],
    # v0.3.0 link primitives (#15 Phase A)
    "dazzle_filekit.links": [
        "LinkInfo",
        "analyze_link",
        "detect_link_type",
        "read_link_target",
        "create_junction",
        "create_hardlink",
    ],
    "dazzle_filekit.utils.validation": [
        "is_junction",
        "read_junction_target",
    ],
}


@pytest.mark.parametrize(
    "module_name,symbol",
    [
        (mod, sym)
        for mod, syms in SUBMODULE_LOCKED.items()
        for sym in syms
    ],
)
def test_submodule_symbol_importable(module_name, symbol):
    """Every locked submodule symbol must be reachable under its documented path."""
    mod = importlib.import_module(module_name)
    assert hasattr(mod, symbol), (
        f"{module_name}.{symbol} is in docs/api-stability.md as locked but "
        f"is not exported. This breaks at least one external caller -- "
        f"see docs/api-stability.md."
    )


# ---------------------------------------------------------------------------
# Module-shape assertions -- preservelib does `from dazzle_filekit import paths, operations, verification`
# ---------------------------------------------------------------------------

PRESERVELIB_MODULES = ["paths", "operations", "verification"]


@pytest.mark.parametrize("submodule", PRESERVELIB_MODULES)
def test_preservelib_module_shapes(submodule):
    """`from dazzle_filekit import paths, operations, verification` must work.

    preservelib (three copies across preserve/, safedel/_lib/, ghtraf/) uses
    this pattern as its import-fallback path. The modules themselves must be
    importable as attributes of the top-level package.
    """
    mod = importlib.import_module("dazzle_filekit")
    assert hasattr(mod, submodule), (
        f"dazzle_filekit.{submodule} is not exposed as a package attribute. "
        f"This breaks preservelib's `from dazzle_filekit import paths, "
        f"operations, verification` pattern."
    )


def test_session_logger_import_pattern():
    """Exact import statements used by claude-session-logger hooks.

    Mirrors the real import lines from log-command.py and rename_session.py.
    If these ever fail, the hooks break on every tool call.
    """
    from dazzle_filekit import normalize_cross_platform_path, create_symlink  # noqa: F401
    from dazzle_filekit import copy_file, normalize_cross_platform_path  # noqa: F401,F811


def test_safedel_classifier_import_pattern():
    """Exact import statement used by dazzlecmd safedel/_classifier.py:90."""
    from dazzle_filekit.paths import normalize_path_no_resolve  # noqa: F401


def test_fixpath_import_pattern():
    """Exact import statement used by dazzlecmd fixpath/fixpath.py:197."""
    from dazzle_filekit import resolve_cross_platform_path  # noqa: F401


def test_links_import_pattern():
    """Exact import statement used by dazzlecmd links/links.py:70."""
    from dazzle_filekit.paths import normalize_path as fk_normalize  # noqa: F401


def test_ghtraf_import_pattern():
    """Exact import statement used by github-traffic-tracker plan_lib/file_ops.py:26."""
    from dazzle_filekit import calculate_file_hash, collect_file_metadata  # noqa: F401
