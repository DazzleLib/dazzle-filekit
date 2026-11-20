"""v0.5.3: dazzle_filekit.locking and portable.current_flavor."""

import os
import subprocess
import sys
import textwrap
import time
import types

import pytest

from dazzle_filekit import locking, portable
from dazzle_filekit.locking import LockTimeoutError, exclusive_lock
from dazzle_filekit.utils import compat

HOLDER = textwrap.dedent("""
    import sys, time
    from dazzle_filekit.locking import exclusive_lock
    with exclusive_lock(sys.argv[1], timeout=5):
        print("held", flush=True)
        time.sleep(float(sys.argv[2]))
""")


def _start_holder(lock_path, seconds=20):
    proc = subprocess.Popen([sys.executable, "-c", HOLDER, str(lock_path), str(seconds)],
                            stdout=subprocess.PIPE, text=True)
    line = proc.stdout.readline().strip()
    assert line == "held", f"holder did not take the lock: {line!r}"
    return proc


def test_lock_is_taken_and_released(tmp_path):
    lock = tmp_path / "store.lock"
    with exclusive_lock(lock, timeout=1):
        assert lock.exists()
    with exclusive_lock(lock, timeout=0):   # free again: a single attempt succeeds
        pass


def test_second_holder_in_same_process_is_refused(tmp_path):
    lock = tmp_path / "store.lock"
    with exclusive_lock(lock, timeout=1):
        with pytest.raises(LockTimeoutError) as e:
            with exclusive_lock(lock, timeout=0):
                pass
    assert str(lock) in str(e.value)


def test_contention_waits_until_the_deadline_then_raises(tmp_path):
    lock = tmp_path / "store.lock"
    holder = _start_holder(lock)
    try:
        t0 = time.monotonic()
        with pytest.raises(LockTimeoutError):
            with exclusive_lock(lock, timeout=0.5):
                pass
        assert 0.4 <= time.monotonic() - t0 < 5
    finally:
        holder.kill()
        holder.wait(timeout=10)


def test_deadline_is_enforced_with_a_fake_clock(tmp_path, monkeypatch):
    """A regression in the deadline must fail fast, not hang the suite."""
    lock = tmp_path / "store.lock"
    now = [0.0]
    sleeps = []

    def clock():
        return now[0]

    def sleep(s):
        sleeps.append(s)
        if len(sleeps) > 500:
            raise AssertionError("exclusive_lock kept retrying past its deadline")
        now[0] += s

    monkeypatch.setattr(locking, "try_lock", lambda fd: False)   # always held elsewhere
    with pytest.raises(LockTimeoutError):
        with exclusive_lock(lock, timeout=1.0, poll=0.1, clock=clock, sleep=sleep):
            pass
    assert 9 <= len(sleeps) <= 11


def test_killed_holder_frees_the_lock(tmp_path):
    lock = tmp_path / "store.lock"
    holder = _start_holder(lock)
    holder.kill()
    holder.wait(timeout=10)
    with exclusive_lock(lock, timeout=3):
        pass


def test_waiter_gets_the_lock_when_the_holder_exits(tmp_path):
    lock = tmp_path / "store.lock"
    holder = _start_holder(lock, seconds=0.5)
    try:
        with exclusive_lock(lock, timeout=5):
            pass
    finally:
        holder.wait(timeout=10)


def test_error_type_sits_under_the_stack_root():
    from dazzle_lib.exceptions import FileOperationError
    assert issubclass(LockTimeoutError, FileOperationError)
    assert issubclass(LockTimeoutError, TimeoutError)


def test_posix_branch_with_a_fake_fcntl(monkeypatch, tmp_path):
    calls = []
    state = {"busy": False}

    def flock(fd, op):
        calls.append(op)
        if op & fake.LOCK_UN:
            return
        if state["busy"]:
            raise BlockingIOError(11, "busy")

    fake = types.SimpleNamespace(LOCK_EX=2, LOCK_NB=4, LOCK_UN=8, flock=flock)
    monkeypatch.setitem(sys.modules, "fcntl", fake)
    monkeypatch.setattr(locking, "_WINDOWS", False)
    fd = os.open(str(tmp_path / "x.lock"), os.O_RDWR | os.O_CREAT)
    try:
        assert locking.try_lock(fd) is True
        assert calls[-1] == fake.LOCK_EX | fake.LOCK_NB
        state["busy"] = True
        assert locking.try_lock(fd) is False
        locking.unlock(fd)
        assert calls[-1] == fake.LOCK_UN
    finally:
        os.close(fd)


def test_locking_imports_in_a_fresh_interpreter():
    r = subprocess.run([sys.executable, "-c", "import dazzle_filekit.locking as l; print(l.exclusive_lock.__name__)"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "exclusive_lock" in r.stdout


@pytest.mark.parametrize("platform,wsl_env,expected", [
    ("windows", None, "windows"),
    ("linux", "Ubuntu", "wsl"),
    ("linux", None, "posix"),
    ("darwin", None, "posix"),
])
def test_current_flavor(monkeypatch, platform, wsl_env, expected):
    monkeypatch.setattr(compat, "PLATFORM", platform)
    if wsl_env:
        monkeypatch.setenv("WSL_DISTRO_NAME", wsl_env)
    else:
        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    if expected == "posix" and platform == "linux":
        monkeypatch.setattr("builtins.open", _no_proc_version(open))
    assert portable.current_flavor() == expected


def _no_proc_version(real_open):
    def fake_open(path, *a, **kw):
        if str(path) == "/proc/version":
            raise OSError("no /proc here")
        return real_open(path, *a, **kw)
    return fake_open


def test_current_flavor_matches_this_runtime():
    expected = "windows" if sys.platform == "win32" else None
    if expected:
        assert portable.current_flavor() == expected
    else:
        assert portable.current_flavor() in ("wsl", "posix")
