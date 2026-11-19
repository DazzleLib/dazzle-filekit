"""What does create_dest_path(path_style="absolute") produce for each source shape?

Pure computation: nothing is created, written or moved. Run before and after
changing the absolute branch; the drive and POSIX rows must not change
(dazzle-filekit#19: "drive and POSIX outputs are byte-identical to before").
"""
import sys

from dazzle_filekit.paths import create_dest_path
from dazzle_filekit.portable import encode_portable_path, key_to_relpath

SOURCES = [
    r"C:\x\a.txt",
    r"c:\x\sub\a.txt",
    r"E:\code\a b\c.txt",
    r"\\server\share\a.txt",
    r"\\server\share\d\e\a.txt",
    r"\\?\C:\x\a.txt",
    r"\\?\UNC\server\share\a.txt",
]


def main():
    dest = r"C:\dest"
    for s in SOURCES:
        try:
            out = str(create_dest_path(s, r"C:\x", dest, path_style="absolute"))
        except Exception as e:                      # noqa: BLE001 - a probe reports everything
            out = "ERROR %s: %s" % (type(e).__name__, e)
        try:
            key = encode_portable_path(s, flavor="windows")
            via_key = key_to_relpath(key, target_flavor="windows")
        except Exception as e:                      # noqa: BLE001
            key, via_key = "ERROR", str(e)
        escapes = not out.lower().startswith(dest.lower() + "\\")
        bad = any(ch in out[3:] for ch in '?*"<>|') or ":" in out[3:]
        print("%-32r -> %-48r key=%-28r rel=%-28r %s%s" % (
            s, out, key, via_key, " ESCAPES" if escapes else "", " ILLEGAL-CHAR" if bad else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
