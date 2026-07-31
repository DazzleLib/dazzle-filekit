# Contributing to dazzle-filekit

Thanks for considering it. This page is short and specific — it covers the
things about *this* project that are easy to get wrong, rather than restating
how pull requests work in general.

## Code of Conduct

This project is released with a Contributor Code of Conduct. By participating
you agree to abide by its terms.

## Getting set up

```bash
git clone https://github.com/DazzleLib/dazzle-filekit.git
cd dazzle-filekit
pip install -e ".[dev]"
python -m pytest tests/ -q
```

The suite should be green before you change anything. If it is not, that is a
bug worth reporting on its own.

## The one thing most likely to trip you up

**Running the tests on one platform is not enough.**

CI is a 3 × 5 matrix — `[ubuntu-latest, windows-latest, macos-latest]` ×
Python 3.9 through 3.13 — and this repo has shipped a platform-specific
failure **twice**, both times invisible to a green local run:

- **v0.3.3** — a probe suite that only worked on a Windows host; ubuntu CI
  caught it on push.
- **v0.4.0** — twelve tests asserting Windows path semantics without
  `@win_only`. They ran on the POSIX legs and failed there. `_same_dir` is
  built on `os.path.normcase` / `normpath` / `splitdrive`, every one of which
  is a no-op or behaves differently off Windows: `posixpath.splitdrive("C:")`
  returns `("", "C:")`, `normcase` does not case-fold, and backslash is an
  ordinary character. So `_same_dir("C:", "C:\\")` is `False` on Windows and
  `True` under posixpath.

A third case bit only *older* Pythons: an embedded NUL raises `ValueError` via
`os.path.isjunction` on 3.12+, but `ctypes.ArgumentError` from the
DeviceIoControl fallback on 3.9–3.11 — and that does **not** inherit from
`ValueError`. A 3.13 dev box cannot see it.

**So:**

- Mark Windows-semantics tests `@win_only`. If a test asserts something about
  backslashes, drive letters, case-insensitivity, or reparse points, it needs
  the gate — even if it happens to pass on Linux today. Passing by coincidence
  is not coverage.
- Reproduce the Linux leg before pushing if you touched anything
  platform-sensitive:

  ```bash
  bash tests/one-offs/run_suite_under_wsl.sh          # needs: sudo apt install python3-venv
  ```

- Where a defect is version-dependent, write the regression test so it
  **forces** the condition (monkeypatch the exception type, for instance)
  rather than relying on an old interpreter to produce it.

## Changing a public symbol

[`docs/api-stability.md`](https://github.com/DazzleLib/dazzle-filekit/blob/main/docs/api-stability.md) lists every locked symbol
**and the external tools that import it** — claude-session-logger, dazzlecmd,
github-traffic-tracker, preservelib. Renaming or removing one is a breaking
change and needs a migration commit in each named consumer, in the same cycle.

`tests/test_import_stability.py` is the automated canary. If you rename a
locked symbol, it fails.

## Docstrings

Every public callable has one — please keep it that way. Two conventions
matter because [autodoc](https://dazzle-filekit.readthedocs.io/) renders them:

- Use **napoleon** section names: `Args:`, `Attributes:`, `Returns:`,
  `Raises:`, `Yields:`, `Example:`. Anything else (`Fields:`, `Params:`) is not
  recognized, parses as a malformed block quote, and fails the docs build.
- Docstrings are parsed as reStructuredText. Indented blocks need a preceding
  blank line.

## Documentation

Docs live in `docs/` as Markdown, read through MyST, so one source serves both
GitHub and the rendered site. Build them the way CI does:

```bash
pip install -r docs/requirements.txt
python -m sphinx -b html docs docs/_build/html -W    # -W: warnings are errors
```

The `docs` job in CI runs exactly this, so a dead cross-reference fails your
pull request rather than surfacing later as a red Read the Docs build.

Each reference page carries a **`Documents vX.Y.Z — last reviewed <date>`**
marker at the top. Bump it when you add to the public surface. This is not
ceremony: that line sat reading `0.3.0` across four releases, and in the
meantime two entire modules (`content` and `pathenv`) went undocumented without
anyone noticing.

## Claims in documentation should be executable

Where a doc asserts something checkable, prefer a probe under
`tests/one-offs/` over prose, and cite it. Existing examples:

| Probe | Pins |
|---|---|
| `probe_docs_claims_unctools.py` | 19 claims made by the UNCtools guide |
| `probe_is_unc_path_two_definitions.py` | that filekit's two `is_unc_path` exports agree (20 cases) |
| `probe_junction_recursive_delete_safety.py` | that `shutil.rmtree` refuses a reparse point |

This is not perfectionism. An earlier draft of the UNCtools guide recommended
`classify_path_origin` for telling a network path from a local one; writing the
probe showed it returns `'unc'` for `\\?\C:\Users\foo` too, and the advice was
wrong before it shipped.

## Scripts and experiments

- `tests/one-offs/` — diagnostics and probes worth keeping.
- `tests/one-offs/thinking/` — scripts written to assess an idea. Keeping the
  reasoning is the point; they do not need to be tidy.
- `tests/` — anything that has earned a place in the regression suite.

## Pull requests

1. Fork and branch.
2. Make the change, with tests.
3. Run `python -m pytest tests/ -q` and the docs build.
4. Add a `CHANGELOG.md` entry under the appropriate heading.
5. Open the PR. CI runs tests on 15 platform/version combinations plus the docs
   build; all must pass.

Explaining **why** in the PR body is more useful than explaining what — the
diff already shows what.

## Reporting a bug

Include the platform, the Python version, and the smallest path or input that
reproduces it. For anything path-related, paste the **exact** string including
its slashes and any prefix: `\\?\C:\x`, `C:/x`, `/c/x` and `/mnt/c/x` are four
different inputs to this library and the difference is frequently the bug.
