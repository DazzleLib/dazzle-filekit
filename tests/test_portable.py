"""The portable path key: one literal way to name an absolute path in a store.

``encode_portable_path`` turns an absolute path into a ``/``-joined key whose
first part is the root: a drive letter (``C``), ``UNC/<server>/<share>``, or
``ROOT`` for the POSIX root. ``flavor`` says how to READ the path and is
required: the same text means different things on different systems
(``/mnt/d/x`` is drive D under WSL and an ordinary folder on plain Linux).
Nothing is expanded, resolved or looked up on disk.

Pure functions; these tests touch no files.
"""
import pytest

from dazzle_filekit.portable import (
    PortablePathError,
    decode_portable_path,
    encode_portable_path,
    key_to_relpath,
)


@pytest.mark.parametrize("path, flavor, key", [
    (r"C:\Users\x\a.txt", "windows", "C/Users/x/a.txt"),
    ("c:/users/x", "windows", "C/users/x"),            # letter upper-cased, case kept
    (r"\\?\C:\x", "windows", "C/x"),                    # extended-length prefix dropped
    (r"\\srv\share\a", "windows", "UNC/srv/share/a"),
    (r"\\?\UNC\srv\share\a", "windows", "UNC/srv/share/a"),
    ("//srv/share/a", "windows", "UNC/srv/share/a"),
    (r"C:\a\.\b", "windows", "C/a/b"),                  # "." folded lexically
    (r"C:\a\..\b", "windows", "C/b"),                   # ".." folded lexically
    ("/mnt/c/Users/x", "wsl", "C/Users/x"),             # a drive under WSL ...
    ("/mnt/c/Users/x", "posix", "ROOT/mnt/c/Users/x"),  # ... a folder on plain POSIX
    ("/mnt/d/x", "wsl", "D/x"),
    ("/mnt/d/x", "posix", "ROOT/mnt/d/x"),
    ("/home/x", "posix", "ROOT/home/x"),
    ("/home/x", "wsl", "ROOT/home/x"),
])
def test_encode(path, flavor, key):
    assert encode_portable_path(path, flavor=flavor) == key


def test_the_same_file_has_one_key_from_windows_and_from_wsl():
    assert (encode_portable_path(r"C:\Users\x\a.txt", flavor="windows")
            == encode_portable_path("/mnt/c/Users/x/a.txt", flavor="wsl"))


@pytest.mark.parametrize("path, flavor", [
    (r"relative\path", "windows"),
    ("relative/path", "posix"),
    ("C:drive-relative", "windows"),
    ("\\\\.\\C:\\x", "windows"),                 # device path
    (r"\\?\Volume{1234}\x", "windows"),
    (r"\\?\GLOBALROOT\Device\x", "windows"),
    (r"\\server", "windows"),                    # no share
    (r"C:\..\x", "windows"),                     # ".." above the root
    ("/../x", "posix"),
    (r"\\?\C:\folder\name.", "windows"),         # exists only under the prefix
])
def test_paths_with_no_portable_form_are_refused(path, flavor):
    with pytest.raises(PortablePathError):
        encode_portable_path(path, flavor=flavor)


def test_flavor_is_required_and_checked():
    with pytest.raises(TypeError):
        encode_portable_path(r"C:\x")                      # no flavor
    with pytest.raises(ValueError):
        encode_portable_path(r"C:\x", flavor="amiga")
    with pytest.raises(ValueError):
        decode_portable_path("C/x", runtime="amiga")


@pytest.mark.parametrize("key, runtime, native", [
    ("C/Users/x", "windows", r"C:\Users\x"),
    ("C/Users/x", "wsl", "/mnt/c/Users/x"),
    ("C/Users/x", "posix", None),                # plain POSIX has no drive C
    ("UNC/srv/share/a", "windows", r"\\srv\share\a"),
    ("UNC/srv/share/a", "posix", None),
    ("ROOT/home/x", "posix", "/home/x"),
    ("ROOT/home/x", "wsl", "/home/x"),
    ("ROOT/home/x", "windows", None),
])
def test_decode(key, runtime, native):
    assert decode_portable_path(key, runtime=runtime) == native


@pytest.mark.parametrize("path, flavor", [
    (r"C:\Users\x\a.txt", "windows"),
    (r"\\srv\share\dir\f.txt", "windows"),
    ("/mnt/c/Users/x", "wsl"),
    ("/home/x/y", "posix"),
])
def test_round_trip_where_a_native_form_exists(path, flavor):
    key = encode_portable_path(path, flavor=flavor)
    assert decode_portable_path(key, runtime=flavor) == path


@pytest.mark.parametrize("bad", ["", "C//x", "C/./x", "C/../x"])
def test_a_malformed_key_is_refused(bad):
    with pytest.raises(PortablePathError):
        decode_portable_path(bad, runtime="windows")


@pytest.mark.parametrize("bad", [
    "XY/a",          # not a drive letter, not UNC, not ROOT
    "c/Users/x",     # a drive letter is stored upper-case; lower-case is not a key root
    "root/home/x",   # the root words are exact
    "UNC/srv",       # a UNC key needs a server AND a share
])
@pytest.mark.parametrize("runtime", ["windows", "wsl", "posix"])
def test_a_key_with_an_unknown_root_is_refused_not_guessed(bad, runtime):
    # Added 2026-11-18: the red-green matrix showed nothing pinned this. A
    # decoder that returned None here would read as "no native form on this
    # system" -- a different, and wrong, answer for a key that is not a key.
    with pytest.raises(PortablePathError):
        decode_portable_path(bad, runtime=runtime)


def test_key_to_relpath_joins_for_the_target():
    assert key_to_relpath(["a", "b.txt"], target_flavor="posix") == "a/b.txt"
    assert key_to_relpath(["a", "b.txt"], target_flavor="windows") == "a\\b.txt"
    assert key_to_relpath("C/Users/x", target_flavor="posix") == "C/Users/x"


@pytest.mark.parametrize("parts, target", [
    (["a", "..", "b"], "posix"),        # never climbs
    (["..", "..", "x"], "windows"),
    (["a", ".", "b"], "posix"),
    (["a", "", "b"], "posix"),
    (["a:b"], "windows"),               # a drive-like or stream-like name
    (["a\\b"], "windows"),              # a separator hidden in a part
    (["CON"], "windows"),               # reserved device name
    (["name."], "windows"),             # trailing dot
    (["name "], "windows"),             # trailing space
])
def test_key_to_relpath_refuses_parts_that_escape_or_cannot_exist(parts, target):
    with pytest.raises(PortablePathError):
        key_to_relpath(parts, target_flavor=target)


def test_names_legal_on_posix_stay_legal_for_a_posix_target():
    assert key_to_relpath(["a:b", "CON", "name."], target_flavor="posix") == "a:b/CON/name."
