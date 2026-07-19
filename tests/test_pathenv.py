"""Tests for dazzle_filekit.pathenv -- declared-platform PATH-value helpers.

Migrated from dazzlecmd-lib's self-setup comparator tests (dazzlecmd#103)
at the v0.3.3 homing, re-spelled for the platform-string API. The point
of the declared-platform contract: every assertion here must pass
IDENTICALLY on a Windows or POSIX host -- a Windows registry value's
semantics travel with the value, not the parser's host.
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


class TestSplit:
    def test_windows_semicolon_even_on_posix_host(self):
        entries = split_path_value(r"C:\a;C:\b;;C:\c",
                                   platform=PLATFORM_WINDOWS)
        assert entries == [r"C:\a", r"C:\b", r"C:\c"]

    def test_posix_colon_even_on_windows_host(self):
        entries = split_path_value("/usr/bin:/home/u/.local/bin",
                                   platform=PLATFORM_POSIX)
        assert entries == ["/usr/bin", "/home/u/.local/bin"]

    def test_host_default_matches_host(self):
        assert host_path_platform() == (
            PLATFORM_WINDOWS if os.name == "nt" else PLATFORM_POSIX)
        sep_value = "a;b" if os.name == "nt" else "a:b"
        assert split_path_value(sep_value) == ["a", "b"]

    def test_invalid_platform_raises(self):
        with pytest.raises(ValueError):
            split_path_value("x", platform="vms")


class TestNormalizeEntry:
    def test_windows_casefold(self):
        assert normalize_path_entry(r"C:\Foo\Scripts",
                                    platform=PLATFORM_WINDOWS) == \
            normalize_path_entry(r"c:\foo\scripts",
                                 platform=PLATFORM_WINDOWS)

    def test_windows_separator_canonicalized(self):
        assert normalize_path_entry("C:/foo/bar",
                                    platform=PLATFORM_WINDOWS) == \
            normalize_path_entry(r"C:\foo\bar", platform=PLATFORM_WINDOWS)

    def test_windows_percent_var_expansion_any_host(self, monkeypatch):
        monkeypatch.setenv("PATHENV_TEST_ROOT", r"C:\Users\someone")
        assert normalize_path_entry(r"%PATHENV_TEST_ROOT%\bin",
                                    platform=PLATFORM_WINDOWS) == \
            normalize_path_entry(r"C:\Users\someone\bin",
                                 platform=PLATFORM_WINDOWS)

    def test_quotes_stripped(self):
        assert normalize_path_entry('"C:\\spaced dir\\bin"',
                                    platform=PLATFORM_WINDOWS) == \
            normalize_path_entry(r"C:\spaced dir\bin",
                                 platform=PLATFORM_WINDOWS)

    def test_trailing_separators_dropped(self):
        assert normalize_path_entry("C:\\x\\", platform=PLATFORM_WINDOWS) \
            == normalize_path_entry(r"C:\x", platform=PLATFORM_WINDOWS)
        assert normalize_path_entry("/usr/bin/", platform=PLATFORM_POSIX) \
            == "/usr/bin"

    def test_posix_case_preserved(self):
        assert normalize_path_entry("/Home/U/bin",
                                    platform=PLATFORM_POSIX) == "/Home/U/bin"

    def test_deterministic_output_per_platform(self):
        # The windows dialect always yields backslash form, on ANY host.
        assert normalize_path_entry("C:/one/two",
                                    platform=PLATFORM_WINDOWS) == r"c:\one\two"


class TestContains:
    def test_exact(self):
        assert path_value_contains(r"C:\one;C:\two", r"C:\two",
                                   platform=PLATFORM_WINDOWS)

    def test_case_insensitive_windows(self):
        assert path_value_contains(r"C:\Foo\Scripts", r"c:\foo\scripts",
                                   platform=PLATFORM_WINDOWS)

    def test_trailing_slash_both_sides(self):
        assert path_value_contains(r"C:\foo\Scripts\;C:\bar",
                                   r"C:\foo\Scripts",
                                   platform=PLATFORM_WINDOWS)
        assert path_value_contains(r"C:\foo\Scripts;C:\bar",
                                   "C:\\foo\\Scripts\\",
                                   platform=PLATFORM_WINDOWS)

    def test_expandable_spelling_counts_as_present(self, monkeypatch):
        monkeypatch.setenv("APPDATA", r"C:\Users\u\AppData\Roaming")
        assert path_value_contains(
            r"C:\one;%APPDATA%\Python\Python313\Scripts",
            r"C:\Users\u\AppData\Roaming\Python\Python313\Scripts",
            platform=PLATFORM_WINDOWS)

    def test_absent(self):
        assert not path_value_contains(r"C:\one;C:\two", r"C:\three",
                                       platform=PLATFORM_WINDOWS)

    def test_posix_case_sensitive(self):
        assert not path_value_contains("/Home/U/bin", "/home/u/bin",
                                       platform=PLATFORM_POSIX)
        assert path_value_contains("/home/u/bin:/usr/bin", "/home/u/bin",
                                   platform=PLATFORM_POSIX)


class TestAppend:
    def test_appends_when_absent(self):
        assert append_path_value(r"C:\one", r"C:\two",
                                 platform=PLATFORM_WINDOWS) == r"C:\one;C:\two"

    def test_noop_when_present_even_differently_spelled(self, monkeypatch):
        monkeypatch.setenv("APPDATA", r"C:\Users\u\AppData\Roaming")
        value = r"C:\one;%APPDATA%\Py\Scripts"
        assert append_path_value(value,
                                 r"C:\Users\u\AppData\Roaming\Py\Scripts",
                                 platform=PLATFORM_WINDOWS) == value

    def test_empty_value(self):
        assert append_path_value("", r"C:\only",
                                 platform=PLATFORM_WINDOWS) == r"C:\only"

    def test_trailing_separator_not_doubled(self):
        assert append_path_value(r"C:\one;", r"C:\two",
                                 platform=PLATFORM_WINDOWS) == r"C:\one;C:\two"

    def test_posix(self):
        assert append_path_value("/usr/bin", "/home/u/.local/bin",
                                 platform=PLATFORM_POSIX) == \
            "/usr/bin:/home/u/.local/bin"

    def test_pure_no_io(self):
        # Nonexistent directories are fine -- pure string logic.
        assert append_path_value("Z:\\no\\such", "Q:\\also\\none",
                                 platform=PLATFORM_WINDOWS) == \
            "Z:\\no\\such;Q:\\also\\none"
