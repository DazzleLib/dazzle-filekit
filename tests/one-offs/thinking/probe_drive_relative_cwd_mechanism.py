"""Does os.chdir() to a tmp_path location make a drive-relative path like
"C:name.txt" actually resolve against it (Windows' per-drive hidden cwd)?
Needed to know whether a full create_shim() end-to-end reproduction of the
bare-drive-letter (Path("C:") vs Path("C:\\")) _same_dir collapse is
constructible, or whether it stays a relative_to()-reachability argument only.

SANDBOXED under tempfile.mkdtemp(); os.chdir restored in finally.
"""
import os
import shutil
import tempfile
from pathlib import Path

original_cwd = os.getcwd()
sandbox = Path(tempfile.mkdtemp(prefix="drcwd_"))
print("sandbox:", sandbox, " drive:", sandbox.drive)

try:
    os.chdir(sandbox)
    print("chdir'd to:", os.getcwd())

    (sandbox / "marker.txt").write_text("hello from sandbox")

    drive_relative = sandbox.drive + "marker.txt"   # e.g. "C:marker.txt"
    print("drive-relative spec:", repr(drive_relative))
    print("Path(drive_relative).is_absolute():", Path(drive_relative).is_absolute())

    try:
        content = Path(drive_relative).read_text()
        print("READ via drive-relative path ->", repr(content))
        print("MECHANISM CONFIRMED: drive-relative paths resolve against the "
              "per-drive hidden cwd set by os.chdir()")
    except OSError as e:
        print("read failed:", e)
        print("MECHANISM NOT CONFIRMED on this host/Python version")
finally:
    os.chdir(original_cwd)
    shutil.rmtree(sandbox, ignore_errors=True)
    print("\nrestored cwd:", os.getcwd())
    print("sandbox removed:", not sandbox.exists())
