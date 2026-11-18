"""What does unctools.get_unc_path_elements return for each path shape the
portable key must handle? (B: filekit 0.5.0 portable key.) Read-only."""
from unctools import get_unc_path_elements, is_unc_path

SHAPES = [
    r"\\server\share\dir\a.txt",
    r"\\server\share",
    r"\\server",
    r"//server/share/dir/a.txt",
    r"\\?\UNC\server\share\dir\a.txt",
    r"\\?\C:\Users\x\a.txt",
    r"\\.\C:\x",
    r"C:\x",
    r"/mnt/c/x",
]
for s in SHAPES:
    try:
        print(f"{s!r:40} unc={is_unc_path(s)!s:5} elements={get_unc_path_elements(s)!r}")
    except Exception as e:
        print(f"{s!r:40} raised {type(e).__name__}: {e}")
