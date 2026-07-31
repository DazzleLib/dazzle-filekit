"""Sphinx configuration for the dazzle-filekit documentation.

The pages themselves are Markdown, read through MyST, so a single source
serves both GitHub (where most people meet this project) and the rendered
site. Nothing here requires the docs to be written twice.

Build locally:

    pip install -r docs/requirements.txt
    sphinx-build -b html docs docs/_build/html -W

`-W` turns warnings into errors, which is what the Read the Docs build does
too -- a broken cross-reference should fail the build rather than ship as a
dead link.
"""
from __future__ import annotations

import os
import sys
from datetime import date

# Import the package so autodoc can read the real docstrings, and so the
# version below is the actual installed one rather than a copy that drifts.
sys.path.insert(0, os.path.abspath(".."))

# -- Project ---------------------------------------------------------------

project = "dazzle-filekit"
author = "Dustin Darcy"
copyright = f"{date.today().year}, {author}"

try:
    from dazzle_filekit import __version__ as release
except Exception:  # pragma: no cover - docs must build even if import fails
    release = "0.0.0"
version = ".".join(release.split(".")[:2])

# -- General ---------------------------------------------------------------

extensions = [
    # Markdown source, so docs/*.md render as-is
    "myst_parser",
    # API pages generated from the package's own docstrings
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",        # Google/NumPy-style docstring sections
    "sphinx.ext.viewcode",        # "[source]" links next to each symbol
    "sphinx.ext.intersphinx",     # link `pathlib.Path` etc. to the stdlib docs
    "sphinx.ext.autosectionlabel",
    # Presentation
    "sphinx_copybutton",          # copy button on every code block
    "sphinx_design",              # cards and grids on the landing page
    "sphinxcontrib.mermaid",      # diagrams as text, versioned with the docs
]

source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
master_doc = "index"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "README.md"]

# Section labels are prefixed with the document name so two pages may both
# have an "Overview" heading without colliding.
autosectionlabel_prefix_document = True
# Only label H1/H2. Deeper than that and the CHANGELOG's repeated
# '### Fixed' / '### Added' headings collide with one another, which is
# correct Keep-a-Changelog structure, not a defect to work around.
autosectionlabel_maxdepth = 2

# -- MyST ------------------------------------------------------------------

myst_enable_extensions = [
    "colon_fence",      # ::: fences, needed by sphinx-design directives
    "deflist",          # definition lists
    "linkify",          # bare URLs become links
    "substitution",
    "tasklist",
    "attrs_inline",
]
# Existing pages link to each other as `api-reference.md`; resolve those to
# the built pages instead of 404ing.
myst_url_schemes = ("http", "https", "mailto")
myst_heading_anchors = 3
# Treat a plain ```mermaid fence as the mermaid directive. This is what
# lets one source serve both surfaces: GitHub renders ```mermaid natively,
# and it would show ```{mermaid} as a raw code block.
myst_fence_as_directive = ["mermaid"]

# -- autodoc ---------------------------------------------------------------

autodoc_default_options = {
    "members": True,
    "undoc-members": False,      # 100% of the public surface is documented
    "show-inheritance": True,
    "member-order": "bysource",  # source order carries meaning; alphabetical does not
}
autodoc_typehints = "description"   # types in the body, not crammed into the signature
autodoc_member_order = "bysource"
autodoc_preserve_defaults = True

# Importing the package must not require Windows-only extras.
autodoc_mock_imports = ["win32security", "win32file", "win32api", "pywintypes"]

napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
# Render an `Attributes:` section as :ivar: fields rather than separate
# object descriptions. Without this a dataclass is documented twice --
# once from the docstring section, once from autodoc's member scan -- and
# every field warns as a duplicate.
napoleon_use_ivar = True

# -- intersphinx -----------------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# -- HTML ------------------------------------------------------------------

html_theme = "furo"
html_title = f"dazzle-filekit {release}"
html_static_path = ["_static"]
html_css_files = ["custom.css"]

html_theme_options = {
    "source_repository": "https://github.com/DazzleLib/dazzle-filekit/",
    "source_branch": "main",
    "source_directory": "docs/",
    "navigation_with_keys": True,
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/DazzleLib/dazzle-filekit",
            "html": (
                '<svg stroke="currentColor" fill="currentColor" viewBox="0 0 16 16">'
                '<path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38'
                "0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13"
                "-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66"
                ".07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15"
                "-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27"
                "c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15"
                "0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2"
                '0 .21.15.46.55.38A8.012 8.012 0 0 0 16 8c0-4.42-3.58-8-8-8z"></path></svg>'
            ),
            "class": "",
        },
    ],
}

# Mermaid renders client-side; no local binary needed on the RTD builder.
mermaid_version = "10.9.1"

# -- linkcheck -------------------------------------------------------------
# Run in CI as an informational step (continue-on-error): a third-party site
# being down should not fail a build, but a permanently dead link should be
# visible in the log.

linkcheck_ignore = [
    # (empty) The docs site went live on 2026-07-31, so its URL is checked
    # like any other. Do not re-add it -- an entry here would hide a real
    # outage rather than a not-yet-created project.
]

# GitHub renders heading anchors in a form linkcheck cannot match (it emits
# both `id="x"` and `id="user-content-x"` and injects them client-side), so
# every #anchor into a GitHub blob reports broken even when it resolves in a
# browser. Verified by hand for the STACK-MAP anchors this project links to.
# The URLs themselves are still checked; only their anchors are skipped.
linkcheck_anchors_ignore_for_url = [
    r"https://github\.com/.*",
]

linkcheck_timeout = 20
linkcheck_retries = 2
