"""Adversarial edge cases for dazzle_filekit.pathenv.

Promoted from the v0.3.3 additivity audit's probe suite (see
tests/checklists/results/2026-07-19__tester-unbounded__pathenv-additivity.md).
Complements tests/test_pathenv.py with degenerate inputs, env-var
corners (including the documented ntpath $VAR inheritance), unicode,
length extremes, mixed separators, and quote pathology. Every test
documents ACTUAL pinned behavior -- none of these are aspirational.
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
        # entries that are pure whitespace should be dropped (p.strip() check)
        assert split_path_value("  ;C:\\a;   ;", platform=PLATFORM_WINDOWS) == ["C:\\a"]

    def test_normalize_entry_only_quotes(self):
        # an entry that is ONLY quote characters -- what survives?
        result = normalize_path_entry('""', platform=PLATFORM_WINDOWS)
        assert result == "", f"expected empty string after stripping quotes, got {result!r}"

    def test_normalize_entry_empty_string(self):
        assert normalize_path_entry("", platform=PLATFORM_WINDOWS) == ""
        assert normalize_path_entry("", platform=PLATFORM_POSIX) == ""

    def test_value_that_is_only_separators_contains_nothing(self):
        assert not path_value_contains(";;;", "C:\\x", platform=PLATFORM_WINDOWS)

    def test_append_to_only_separators_value(self):
        # value=";;;" is truthy (non-empty str) so append should NOT hit the
        # empty-value branch; verify it produces a sane (if odd) result and
        # does not raise.
        result = append_path_value(";;;", "C:\\new", platform=PLATFORM_WINDOWS)
        assert result.endswith("C:\\new")


class TestUndefinedAndEnvVars:
    def test_undefined_percent_var_stays_literal_windows(self, monkeypatch):
        monkeypatch.delenv("PATHENV_TOTALLY_UNDEFINED_XYZ", raising=False)
        result = normalize_path_entry(
            r"%PATHENV_TOTALLY_UNDEFINED_XYZ%\bin", platform=PLATFORM_WINDOWS
        )
        # ntpath.expandvars leaves unresolvable %VAR% references untouched
        # (matches cmd.exe behavior) -- confirm no KeyError/exception and
        # that the literal is preserved (modulo casefold + separator canon).
        assert "pathenv_totally_undefined_xyz" in result.lower()

    def test_percent_var_on_posix_platform_not_expanded(self, monkeypatch):
        # POSIX dialect should NOT run ntpath.expandvars -- %VAR% syntax is
        # not POSIX's expansion syntax ($VAR / ${VAR}), so it must survive
        # completely literally.
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
        assert result == entry  # case (and everything else) preserved on posix

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
        expected = PLATFORM_WINDOWS if os.name == "nt" else PLATFORM_POSIX
        assert host_path_platform() == expected

    def test_split_platform_none_uses_host_dialect(self):
        # platform=None means the RUNNING host's dialect: ';' on a
        # Windows host, ':' on POSIX.
        if os.name == "nt":
            assert split_path_value("C:\\a;C:\\b") == ["C:\\a", "C:\\b"]
        else:
            assert split_path_value("/a:/b") == ["/a", "/b"]

    def test_append_platform_none_uses_host_dialect(self):
        if os.name == "nt":
            assert append_path_value("C:\\one", "C:\\two") == \
                "C:\\one;C:\\two"
        else:
            assert append_path_value("/one", "/two") == "/one:/two"


class TestMixedSeparatorsWithinOneEntry:
    def test_mixed_separators_single_entry_windows(self):
        # A single entry with BOTH slash types mixed together should still
        # canonicalize fully to backslash under the windows dialect.
        entry = r"C:\foo/bar\baz/qux"
        result = normalize_path_entry(entry, platform=PLATFORM_WINDOWS)
        assert result == r"c:\foo\bar\baz\qux"

    def test_mixed_separators_single_entry_posix(self):
        entry = r"/foo\bar/baz\qux"
        result = normalize_path_entry(entry, platform=PLATFORM_POSIX)
        assert result == "/foo/bar/baz/qux"

    def test_mixed_separator_split_uses_declared_separator_only(self):
        # split must use ONLY the declared separator; a stray posix ':'
        # embedded in a windows value (e.g. a drive letter colon) must NOT
        # be treated as a splitting separator.
        value = r"C:\a;D:\b"
        assert split_path_value(value, platform=PLATFORM_WINDOWS) == [r"C:\a", r"D:\b"]


class TestQuoteEdgeCases:
    def test_single_quote_character_only(self):
        # entry.strip('"') only strips DOUBLE quotes -- a lone single quote
        # should survive untouched (documents actual behavior, not a should).
        result = normalize_path_entry("'", platform=PLATFORM_WINDOWS)
        assert result == "'"

    def test_unbalanced_double_quote(self):
        # strip('"') strips from both ends regardless of balance -- a
        # leading-only quote is stripped from the left.
        result = normalize_path_entry('"C:\\x', platform=PLATFORM_WINDOWS)
        assert result == r"c:\x"

    def test_nested_quotes(self):
        result = normalize_path_entry('""C:\\x""', platform=PLATFORM_WINDOWS)
        # str.strip('"') strips ALL leading/trailing quote chars, not just one pair
        assert result == r"c:\x"


class TestInvalidPlatformValue:
    def test_case_sensitive_platform_string(self):
        # "Windows" (capitalized) is NOT a valid platform token -- only the
        # exact PLATFORM_WINDOWS/"windows" spelling is accepted.
        with pytest.raises(ValueError):
            split_path_value("a;b", platform="Windows")

    def test_empty_string_platform_invalid(self):
        with pytest.raises(ValueError):
            normalize_path_entry("x", platform="")
