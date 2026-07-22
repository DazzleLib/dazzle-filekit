# dazzle-filekit 0.3.3 pathenv additivity audit

**Date**: 2026-07-19
**Agent**: tester-unbounded (autonomous, warm-up pre-approved by user for SAFE-READ + SAFE-WRITE-SCRATCH scope)
**Repo**: `C:\code\dazzle-filekit`, branch `dazzlesum-upstreaming`
**HEAD**: `dbb1472bccda0bf8bb96226388522e3845e5cdf9`
**origin/main**: `7a059e58d2fae76bb91716142ecbdcf86dfd2d06`
**Scope verified**: the UNCOMMITTED working-tree changes (the actual "0.3.3" diff). The 3 branch commits ahead of `origin/main` (`dbb1472`, `f3df383`, `f67d01d`) are pre-existing, already-committed work (native checksum backend, `AtomicStreamWriter`, junction-detection improvements) unrelated to the pathenv/regex-consolidation work under review; they were still scanned for symbol removal per the task instructions (see Audit section).

## Environment

- Python 3.13.2, Windows 10 Pro (win32)
- `dazzle_filekit.__file__` = `C:\code\dazzle-filekit\dazzle_filekit\__init__.py` — editable install confirmed pointing at this checkout
- `dazzle_filekit.__version__` = `0.3.3` — confirmed
- Shell: PowerShell throughout (Bash tool confirmed blocked on this machine: `PreToolUse:Bash hook error: ... tester-unbounded-guard.py: No such file or directory`)
- Uncommitted files touched: `CHANGELOG.md`, `dazzle_filekit/__init__.py`, `dazzle_filekit/paths.py`, `dazzle_filekit/utils/compat.py`, `docs/api-stability.md`, `pyproject.toml`, `tests/test_import_stability.py` (modified); `dazzle_filekit/pathenv.py`, `tests/test_pathenv.py` (untracked/new)

## PASS / FAIL Table

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Full suite `pytest tests/ -q --no-cov` | **PASS** | `407 passed, 11 skipped in 13.54s` — matches claimed baseline delta exactly (376→407 = +31 new tests, 11 skipped unchanged) |
| 2 | Additivity audit — uncommitted diff (primary 0.3.3 scope) | **PASS** | No removed/renamed symbol, no changed signature, no changed default anywhere in the diff. See Audit section. |
| 3 | Additivity audit — regex single-sourcing bit-identical | **PASS** | `_WSL_MNT_RE` and `_MANGLED_MNT_RE` literals in `paths.py` are character-identical to the inline literals they replaced in `utils/compat.py`. Third pattern (windows drive-letter, used on the POSIX-host branch) deliberately left un-swapped, exactly as documented in the CHANGELOG/code comment. |
| 4 | Additivity audit — prior branch commits (secondary scope) | **PASS (unrelated)** | Only 5 removed lines across `links.py`/`operations.py`/`utils/validation.py`/`verification.py`; all are a trailing-whitespace trim, a docstring rewrite, and a junction-existence-check condition tweak — no symbol/signature removal. Not part of the 0.3.3 pathenv change set. |
| 5 | Real-FS `resolve_cross_platform_path` probe (7 formats) | **PASS** | All 7 cases resolved correctly, zero exceptions. Mangled MSYS form correctly probed and resolved via existence check. Nonexistent drive returned a sensible non-existent path rather than raising. |
| 6 | Installed `dz fixpath` consumer probe | **PASS** | `dz fixpath /c/Windows/System32/notepad.exe` → `C:\Windows\System32\notepad.exe`; `dz fixpath C:/Windows` → `C:\Windows`. No tracebacks. |
| 7 | Adversarial pathenv edge cases (25 new tests, scratch) | **PASS** (24 as originally written, 1 finding — see below) | `25 passed` after correcting one test's wrong assumption about `ntpath.expandvars` (see Findings #1) |
| 8 | Import-stability canary `test_import_stability.py` | **PASS** | `95 passed in 0.39s`, including all 7 new `pathenv`-related locked symbols and the `pathenv` submodule shape |

**Overall: 8/8 PASS.**

## Additivity Audit Verdict

**The claim "no symbol removed, renamed, or behavior-changed" holds for the uncommitted 0.3.3 diff.** Explicit list of everything that is not purely additive, however small:

1. **Nothing removed or renamed.** `dazzle_filekit/__init__.py` only *adds* imports/`__all__` entries; `pathenv` is a wholly new module; `paths.py` only adds a docstring paragraph and one new module-level regex constant (`_MANGLED_MNT_RE`); `docs/api-stability.md`/`CHANGELOG.md`/`tests/test_import_stability.py` only add rows/entries/parametrize cases.
2. **One internal behavior-preserving refactor** in `utils/compat.py::resolve_cross_platform_path`: two `re.match`/`re.search` calls that used inline pattern literals now import and use `paths._WSL_MNT_RE` / `paths._MANGLED_MNT_RE` instead. Verified **character-for-character identical**:
   - `_WSL_MNT_RE`: `r'^/mnt/([a-zA-Z])(/.*)?$'` (old inline) == `r"^/mnt/([a-zA-Z])(/.*)?$"` (new shared) — identical.
   - `_MANGLED_MNT_RE`: `r'[/\\]mnt[/\\]([a-zA-Z])[/\\](.*)'` (old inline) == `r"[/\\]mnt[/\\]([a-zA-Z])[/\\](.*)"` (new shared) — identical.
   - The third inline pattern (`r'^([a-zA-Z]):[/\\](.*)'`, used only on the POSIX-host branch to detect Windows-style paths) was **deliberately left un-swapped** against `paths._WIN_DRIVE_RE` (which anchors with a trailing `$`), exactly as the code comment and CHANGELOG both state. This is the one asymmetry in the refactor and it is intentional, documented in three places (code comment, CHANGELOG, and implicitly consistent with `paths.py`'s docstring), and does not change behavior for any normal path — confirmed no test exercises the pathological embedded-newline case where the two patterns would diverge, so this is a documented, low-risk, intentional non-unification rather than an oversight.
3. **No default-value changes** anywhere in the diff — all new `pathenv.py` function parameters (`platform: Optional[str] = None`) are additions to a brand-new module, not changes to existing signatures.
4. **No changed defaults or signatures in prior branch commits** either (`dbb1472`/`f3df383`/`f67d01d`) — the 5 removed lines there are a trailing-whitespace fix, a docstring edit, and one conditional tweak in junction detection, none of which touch a public symbol's name or signature.

**Verdict: the additive-only / zero-behavior-change claim for 0.3.3 is substantiated.**

## Real-FS Behavior Probe Results (`resolve_cross_platform_path`, Windows host)

| Input | Result | Exists |
|---|---|---|
| `C:\Windows` | `WindowsPath('C:/Windows')` | True |
| `/c/Windows` | `WindowsPath('C:/Windows')` | True |
| `/mnt/c/Windows` | `WindowsPath('C:/Windows')` | True |
| `C:/Windows` | `WindowsPath('C:/Windows')` | True |
| `%TEMP%` (expanded) | `WindowsPath('C:/Users/Extreme/AppData/Local/Temp')` | True |
| `C:\fake\mnt\c\Windows` (mangled MSYS form) | `WindowsPath('C:/Windows')` | True — correctly probed and resolved to the real path |
| `/mnt/q/nope` (nonexistent) | `WindowsPath('Q:/nope')` | False — sensible non-crashing fallback |

No exceptions in any case.

## Adversarial pathenv Edge Cases (written in scratch, promotable)

25 tests written and run against the shipped `pathenv.py`, beyond the 21 shipped in `tests/test_pathenv.py`. Location: `%TEMP%\claude\...\scratchpad\test_pathenv_adversarial.py` (per write-scope constraints, not committed to the repo). Final result: **25 passed**.

Categories covered: empty/degenerate values (empty string, separator-only values, whitespace-only entries, quote-only entries), undefined `%VAR%` handling, unicode paths (accented + CJK), very long values (5000 entries) and very long single entries (20k chars), `platform=None` host-default behavior, mixed separators within one entry, quote edge cases (single quote, unbalanced double quote, nested quotes), and invalid platform-string rejection (case sensitivity, empty string).

**One assumption in the initial test draft was wrong and had to be corrected** — see Finding #1 below; the corrected test now documents actual behavior rather than asserting a false expectation.

Test content (as run):

```python
"""Adversarial edge-case probe for dazzle_filekit.pathenv (scratch, not shipped).

Written by tester-unbounded during the 0.3.3 additivity audit to probe
beyond the shipped tests/test_pathenv.py suite. Not part of the package;
lives in %TEMP% scratch per the audit's write-scope constraints.
"""
import os

import pytest

from dazzle_filekit.pathenv import (
    PLATFORM_POSIX,
    PLATFORM_WINDOWS,
    append_path_value,
    host_path_platform,
    normalize_path_entry,
    path_value_contains,
    split_path_value,
)


class TestEmptyAndDegenerate:
    def test_split_empty_string(self):
        assert split_path_value("", platform=PLATFORM_WINDOWS) == []
        assert split_path_value("", platform=PLATFORM_POSIX) == []

    def test_split_only_separators(self):
        assert split_path_value(";;;", platform=PLATFORM_WINDOWS) == []
        assert split_path_value(":::", platform=PLATFORM_POSIX) == []

    def test_split_whitespace_only_entries_dropped(self):
        assert split_path_value("  ;C:\\a;   ;", platform=PLATFORM_WINDOWS) == ["C:\\a"]

    def test_normalize_entry_only_quotes(self):
        result = normalize_path_entry('""', platform=PLATFORM_WINDOWS)
        assert result == "", f"expected empty string after stripping quotes, got {result!r}"

    def test_normalize_entry_empty_string(self):
        assert normalize_path_entry("", platform=PLATFORM_WINDOWS) == ""
        assert normalize_path_entry("", platform=PLATFORM_POSIX) == ""

    def test_value_that_is_only_separators_contains_nothing(self):
        assert not path_value_contains(";;;", "C:\\x", platform=PLATFORM_WINDOWS)

    def test_append_to_only_separators_value(self):
        result = append_path_value(";;;", "C:\\new", platform=PLATFORM_WINDOWS)
        assert result.endswith("C:\\new")


class TestUndefinedAndEnvVars:
    def test_undefined_percent_var_stays_literal_windows(self, monkeypatch):
        monkeypatch.delenv("PATHENV_TOTALLY_UNDEFINED_XYZ", raising=False)
        result = normalize_path_entry(
            r"%PATHENV_TOTALLY_UNDEFINED_XYZ%\bin", platform=PLATFORM_WINDOWS
        )
        assert "pathenv_totally_undefined_xyz" in result.lower()

    def test_percent_var_on_posix_platform_not_expanded(self, monkeypatch):
        monkeypatch.setenv("PATHENV_TEST_ROOT", "/should/not/be/used")
        result = normalize_path_entry("%PATHENV_TEST_ROOT%/bin", platform=PLATFORM_POSIX)
        assert result == "%PATHENV_TEST_ROOT%/bin"

    def test_dollar_var_on_windows_IS_also_expanded(self, monkeypatch):
        # FINDING (informational, not a regression): CPython's ntpath.expandvars
        # supports BOTH %VAR% and POSIX-style $VAR/${VAR} syntax regardless of
        # the "windows" dialect requested here -- it is a property of the
        # underlying stdlib helper, inherited as-is, not something pathenv.py
        # adds or removes. The module docstring's "expands %VAR% references"
        # phrasing is technically true but doesn't mention $VAR also expands;
        # a caller feeding a POSIX-spelled variable reference through the
        # windows dialect gets it silently expanded too. Documented here so
        # the behavior is pinned, not implying a bug.
        monkeypatch.setenv("PATHENV_TEST_ROOT", r"C:\should\appear")
        result = normalize_path_entry("$PATHENV_TEST_ROOT\\bin", platform=PLATFORM_WINDOWS)
        assert result == r"c:\should\appear\bin"


class TestUnicodeAndLength:
    def test_unicode_path_windows(self):
        entry = r"C:\Users\\u00e9éé\Café\\u65e5本語"
        result = normalize_path_entry(entry, platform=PLATFORM_WINDOWS)
        assert result == entry.casefold().replace("/", "\\").rstrip("\\")

    def test_unicode_path_posix_case_preserved(self):
        entry = "/home/u/ééé/日本語"
        result = normalize_path_entry(entry, platform=PLATFORM_POSIX)
        assert result == entry

    def test_very_long_value_many_entries(self):
        entries = [f"C:\\dir{i}" for i in range(5000)]
        value = ";".join(entries)
        split = split_path_value(value, platform=PLATFORM_WINDOWS)
        assert len(split) == 5000
        assert split[0] == "C:\\dir0"
        assert split[-1] == "C:\\dir4999"

    def test_single_very_long_entry(self):
        long_component = "x" * 20000
        entry = f"C:\\{long_component}"
        result = normalize_path_entry(entry, platform=PLATFORM_WINDOWS)
        assert result == entry.casefold()


class TestPlatformNoneHostBehavior:
    def test_platform_none_uses_actual_host(self):
        assert host_path_platform() == PLATFORM_WINDOWS
        assert os.name == "nt"

    def test_split_platform_none_matches_os_pathsep_semantics(self):
        assert split_path_value("C:\\a;C:\\b") == ["C:\\a", "C:\\b"]

    def test_append_platform_none_windows_host(self):
        assert append_path_value("C:\\one", "C:\\two") == "C:\\one;C:\\two"


class TestMixedSeparatorsWithinOneEntry:
    def test_mixed_separators_single_entry_windows(self):
        entry = r"C:\foo/bar\baz/qux"
        result = normalize_path_entry(entry, platform=PLATFORM_WINDOWS)
        assert result == r"c:\foo\bar\baz\qux"

    def test_mixed_separators_single_entry_posix(self):
        entry = r"/foo\bar/baz\qux"
        result = normalize_path_entry(entry, platform=PLATFORM_POSIX)
        assert result == "/foo/bar/baz/qux"

    def test_mixed_separator_split_uses_declared_separator_only(self):
        value = r"C:\a;D:\b"
        assert split_path_value(value, platform=PLATFORM_WINDOWS) == [r"C:\a", r"D:\b"]


class TestQuoteEdgeCases:
    def test_single_quote_character_only(self):
        result = normalize_path_entry("'", platform=PLATFORM_WINDOWS)
        assert result == "'"

    def test_unbalanced_double_quote(self):
        result = normalize_path_entry('"C:\\x', platform=PLATFORM_WINDOWS)
        assert result == r"c:\x"

    def test_nested_quotes(self):
        result = normalize_path_entry('""C:\\x""', platform=PLATFORM_WINDOWS)
        assert result == r"c:\x"


class TestInvalidPlatformValue:
    def test_case_sensitive_platform_string(self):
        with pytest.raises(ValueError):
            split_path_value("a;b", platform="Windows")

    def test_empty_string_platform_invalid(self):
        with pytest.raises(ValueError):
            normalize_path_entry("x", platform="")
```

## Findings (severity-ranked)

1. **LOW / informational — `normalize_path_entry(..., platform=PLATFORM_WINDOWS)` also expands POSIX-style `$VAR`/`${VAR}` syntax, not just `%VAR%`.** This is a property of CPython's `ntpath.expandvars`, which the module docstring describes as expanding "`%VAR%` references the way the OS does" — true, but incomplete: `ntpath.expandvars` also handles `$VAR`/`${VAR}` syntax regardless of the requested dialect, because it's inherited stdlib behavior, not something `pathenv.py` chose. Not a regression (this is a brand-new module — there is no prior behavior to diverge from) and not a functional bug (nothing in the shipped test suite or real-world callers passes `$VAR`-style PATH entries under the windows dialect). Recommend: a one-line docstring addendum on `normalize_path_entry` noting that `ntpath.expandvars` also recognizes `$VAR`/`${VAR}` syntax, to avoid a future surprise if a caller ever encounters a mixed-syntax value. **Does not block ship** — cosmetic/documentation only.
2. **No other findings.** The regex single-sourcing is bit-identical, the deliberately-unswapped third pattern is documented in three independent places (comment, CHANGELOG, and consistent with `paths.py`'s own docstring), the real-FS probes and consumer probe (`dz fixpath`) behaved correctly with no exceptions, and 25/25 adversarial edge-case tests pass against the shipped implementation.

## New Tests Written (candidates for promotion)

`test_pathenv_adversarial.py` (full content above) is a reasonable candidate for promotion into `tests/test_pathenv.py` if the maintainer wants edge-case coverage for: empty/separator-only values, quote-only entries, unicode, very-long values/entries, `platform=None` host-default behavior, mixed-separator entries, and quote-balance edge cases. The one genuinely new-information test (`test_dollar_var_on_windows_IS_also_expanded`) is the most valuable of the 25 — it pins down an inherited stdlib behavior that isn't otherwise documented or tested anywhere in the shipped suite.

## SHIP / HOLD

**SHIP.**

- Full suite: 407 passed / 11 skipped, matches the claimed baseline delta exactly.
- Import-stability canary: 95 passed, all 7 new `pathenv` symbols locked correctly.
- Additivity claim substantiated: zero removed/renamed symbols, zero changed signatures/defaults, one internal refactor verified bit-identical with its one intentional, documented asymmetry.
- Real-FS and real consumer (`dz fixpath`) probes behave correctly with no exceptions across 9 combined cases.
- 25 adversarial edge-case tests pass against the shipped code; the only finding is a low-severity documentation-completeness note about inherited `ntpath.expandvars` `$VAR` support, not a functional defect.

No blocking issues found.
