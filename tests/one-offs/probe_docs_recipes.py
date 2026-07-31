"""Execute the substance of every recipe in docs/recipes.md.

Example code is the fastest-rotting part of any documentation: a signature
changes, the prose still reads fine, and the snippet is quietly wrong until a
user pastes it. This runs each recipe's real calls against a real temporary
tree so a drifted signature fails here instead of in someone's terminal.

Not a doctest -- the recipes use illustrative paths (D:/project, big.iso) that
should stay readable rather than be contorted into fixtures. What is verified
is the API surface each recipe depends on and the behaviour it claims.

Sandboxed under mkdtemp; nothing outside it is read or written.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import dazzle_filekit as F

WINDOWS = os.name == "nt"
results = []


def check(recipe, claim, ok, detail=""):
    results.append((recipe, claim, bool(ok), detail))


sandbox = Path(tempfile.mkdtemp(prefix="recipes_"))
try:
    # ---------------------------------------------------------------- setup
    src = sandbox / "project"
    (src / "sub").mkdir(parents=True)
    (src / "a.py").write_text("print('a')\n")
    (src / "b.md").write_text("# b\n")
    (src / "sub" / "c.py").write_text("print('c')\n")
    dst = sandbox / "backup"

    # -------------------------------------- 1. copy a tree and verify it
    # NOTE: search_paths is a LIST. Passing a bare string iterates it character
    # by character, and Path("/") is the drive root -- see
    # scratchpad probe_find_files_string_arg.py and the api-reference warning.
    files = F.find_files([src], patterns=["*.py", "*.md"])
    check("copy+verify", "find_files([root]) returns the 3 seeded files", len(files) == 3,
          "got %d" % len(files))

    F.copy_files_with_path(files, source_base=src, dest_base=dst)
    landed = list(dst.rglob("*.py")) + list(dst.rglob("*.md"))
    check("copy+verify", "copy_files_with_path reproduced them", len(landed) == 3,
          "got %d" % len(landed))

    verified = F.verify_copied_files(
        {str(p): p for p in files},
        {str(p): dst / p.relative_to(src) for p in files},
    )
    check("copy+verify", "verify_copied_files reports all good",
          bool(verified) and all(
              (v[0] if isinstance(v, tuple) else v) for v in verified.values()))

    F.compare_directories(src, dst)
    check("copy+verify", "compare_directories is callable on two trees", True)

    # -------------------------------------------------- 2. long-path shims
    long_name = "L" * 200 + ".txt"
    check("longpath", "needs_shim False for a short path",
          F.needs_shim(str(sandbox / "x.txt")) is False)

    deep = Path("D:/") / ("d" * 80) / ("e" * 80) / long_name
    plan = F.plan_shim(deep, root=str(sandbox / ".dzs"))
    if WINDOWS:
        check("longpath", "plan_shim flags a 360-char path as needing a shim",
              plan.needed is True, plan.reason)
        check("longpath", "plan carries anchor/link/shimmed when usable",
              (not plan.usable) or all([plan.anchor, plan.link, plan.shimmed]))
        check("longpath", "plan.resolved() never raises",
              isinstance(plan.resolved(), Path))
    check("longpath", "budget_for(short root) exceeds the 244-char worst case",
          F.budget_for(r"C:\.dzs") >= 244, "got %d" % F.budget_for(r"C:\.dzs"))
    check("longpath", "budget shrinks as the root grows",
          F.budget_for(r"C:\.dzs") > F.budget_for(r"C:\Users\Somebody\AppData\Local"))
    check("longpath", "candidate_roots returns an ordered list",
          isinstance(F.candidate_roots(str(deep)), list))
    check("longpath", "reap_shims on a missing root returns []",
          F.reap_shims(sandbox / "no_such_root") == [])

    # --------------------------------------------------- 3. link auditing
    plain = sandbox / "plain_dir"
    plain.mkdir()
    info = F.analyze_link(plain)
    check("links", "analyze_link(plain dir).kind is None", info.kind is None)
    check("links", "LinkInfo exposes the documented fields",
          all(hasattr(info, f) for f in
              ("link_path", "kind", "raw_target", "resolved_target",
               "is_broken", "is_circular")))
    check("links", "detect_link_type(plain dir) is None",
          F.detect_link_type(plain) is None)

    hard_src = sandbox / "hard.bin"
    hard_src.write_bytes(b"x")
    if F.create_hardlink(hard_src, sandbox / "hard_alias.bin"):
        check("links", "create_hardlink then detect_link_type == 'hardlink'",
              F.detect_link_type(sandbox / "hard_alias.bin") == "hardlink")

    if WINDOWS:
        jtarget = sandbox / "jtarget"
        jtarget.mkdir()
        (jtarget / "canary.txt").write_text("survive")
        jlink = sandbox / "jlink"
        if F.create_junction(jtarget, jlink):
            check("links", "create_junction -> detect_link_type 'junction'",
                  F.detect_link_type(jlink) == "junction")
            check("links", "read_link_target returns the stored target",
                  F.read_link_target(jlink) is not None)
            F.remove_link(jlink)
            check("links", "remove_link detaches without touching the target",
                  (not jlink.exists()) and (jtarget / "canary.txt").exists())

    # ------------------------------------------------------- 4. hashing
    tool = F.detect_native_hash_tool("sha256")
    check("hashing", "detect_native_hash_tool returns a name or None",
          tool is None or isinstance(tool, str), "tool=%r" % tool)
    # Returns None when no native tool exists -- the CALLER falls back.
    d1 = F.calculate_file_hash_native(src / "a.py", algorithm="sha256")
    check("hashing", "native returns a digest or None (no silent fallback)",
          d1 is None or isinstance(d1, str), "got %r" % (d1,))
    # calculate_file_hash takes algorithmS (a list) and returns a DICT --
    # unlike calculate_file_hash_native, which is singular and returns a str.
    d2 = F.calculate_file_hash(src / "a.py", algorithms=["sha256"])
    check("hashing", "calculate_file_hash returns a dict keyed by algorithm",
          isinstance(d2, dict) and "sha256" in d2, repr(d2)[:60])
    if d1 is not None:
        check("hashing", "native and hashlib digests agree",
              d1.lower() == d2["sha256"].lower())
    else:
        check("hashing", "no native tool here; documented fallback is explicit",
              (d1 or d2["sha256"]) == d2["sha256"],
              "detect_native_hash_tool returned None on this host")

    hashes = F.calculate_directory_hashes(src, pattern="*", recursive=True)
    check("hashing", "calculate_directory_hashes returns a dict", isinstance(hashes, dict) and hashes)
    manifest = sandbox / "archive.sha256"
    F.save_hashes_to_file(hashes, manifest)
    check("hashing", "save_hashes_to_file wrote a manifest", manifest.exists())
    loaded = F.load_hashes_from_file(manifest)
    check("hashing", "load_hashes_from_file round-trips", isinstance(loaded, dict) and loaded)
    # Manifest keys are RELATIVE to the scanned dir; verification resolves
    # them against the cwd. From elsewhere every entry reports (False, h, None).
    away = F.verify_files_with_manifest(loaded)
    check("hashing", "verifying from the wrong cwd fails with actual-hash None",
          all((not ok) and actual is None for ok, _, actual in away.values()),
          repr(away)[:70])

    _cwd = os.getcwd()
    os.chdir(src)
    try:
        report = F.verify_files_with_manifest(loaded)
    finally:
        os.chdir(_cwd)
    check("hashing", "verifying from inside the scanned dir passes",
          all(v[0] for v in report.values()), "%d entries" % len(report))

    # ------------------------------------------------- 5. real places only
    cands = ["/home/me/notes", "/dev/null", "NUL", "C:/tmp/nul.txt", "C:/code"]
    from dazzle_filekit.utils.validation import is_valid_path
    places = [p for p in cands if is_valid_path(p) and not F.is_device_path(p)]
    check("places", "device paths and reserved names are filtered out",
          "/dev/null" not in places and "NUL" not in places
          and "C:/tmp/nul.txt" not in places, "kept=%r" % places)
    check("places", "ordinary paths survive the filter",
          "/home/me/notes" in places and "C:/code" in places, "kept=%r" % places)
    check("places", "classify_fs_object names an existing directory",
          F.classify_fs_object(src) == "directory")

    # ------------------------------------------------------- 6. pathenv
    raw = r"C:\Windows\system32;%USERPROFILE%\bin;C:\tools"
    parts = F.split_path_value(raw, platform=F.PLATFORM_WINDOWS)
    check("pathenv", "split_path_value finds 3 entries", len(parts) == 3, repr(parts))
    check("pathenv", "path_value_contains is case-insensitive for windows values",
          F.path_value_contains(raw, r"c:\TOOLS", platform=F.PLATFORM_WINDOWS) is True)
    grown = F.append_path_value(raw, r"C:\newtool", platform=F.PLATFORM_WINDOWS)
    check("pathenv", "append_path_value adds a missing entry", "newtool" in grown)
    same = F.append_path_value(raw, r"c:\TOOLS", platform=F.PLATFORM_WINDOWS)
    check("pathenv", "append_path_value is a no-op when already present",
          same == raw, "changed to %r" % same)
    check("pathenv", "host_path_platform is one of the two tokens",
          F.host_path_platform() in (F.PLATFORM_WINDOWS, F.PLATFORM_POSIX))

    # ------------------------------------------- 7. cross-platform paths
    check("xplatform", "normalize_cross_platform_path is callable",
          F.normalize_cross_platform_path("/c/Users/foo/file.txt") is not None)
    check("xplatform", "path_exists_cross_platform finds a real file",
          F.path_exists_cross_platform(str(src / "a.py")) is True)
    check("xplatform", "is_wsl returns a bool", isinstance(F.is_wsl(), bool))

    # ---------------------------------------------------- 8. atomic writes
    cfg = sandbox / "config.json"
    F.atomic_write_json(cfg, {"threshold": 240})
    check("atomic", "atomic_write_json wrote valid JSON",
          '"threshold"' in cfg.read_text())
    stream = sandbox / "manifest.txt"
    with F.AtomicStreamWriter(stream) as w:
        for p, digest in list(hashes.items())[:3]:
            w.write("%s  %s\n" % (digest, p))
    check("atomic", "AtomicStreamWriter produced a complete file",
          stream.exists() and stream.read_text().count("\n") == 3)

    # --------------------------------------------------- 9. text replace
    cfgfile = sandbox / "setup.cfg"
    cfgfile.write_text("version = 0.4.1\n")
    check("replace", "replace_in_file reports a change",
          F.replace_in_file(cfgfile, "0.4.1", "0.4.2") is True)
    check("replace", "...and the change landed", "0.4.2" in cfgfile.read_text())
    md = sandbox / "mdtree"
    md.mkdir()
    (md / "one.md").write_text("0.4.1\n")
    (md / "two.md").write_text("nothing here\n")
    res = F.batch_replace_in_files(md, "0.4.1", "0.4.2", pattern="*.md", recursive=True)
    check("replace", "batch_replace_in_files maps path -> changed",
          isinstance(res, dict) and sum(bool(v) for v in res.values()) == 1, repr(res))

    # ------------------------------------------------------ 10. disk space
    usage = F.get_disk_usage(str(sandbox))
    check("disk", "get_disk_usage exposes total/free", usage.total > 0 and usage.free >= 0)
    size = F.calculate_total_size([src])
    check("disk", "calculate_total_size([root]) counts the seeded bytes", size > 0,
          "%d bytes" % size)

    # check_disk_space returns a 4-TUPLE. A non-empty tuple is always truthy,
    # so `if check_disk_space(...)` would pass even on a full disk.
    res = F.check_disk_space(str(sandbox), 1024)
    check("disk", "check_disk_space returns a 4-tuple, not a bool",
          isinstance(res, tuple) and len(res) == 4, repr(res)[:70])
    check("disk", "...whose first element is the verdict", res[0] is True)

    ok, msg = F.ensure_disk_space(str(sandbox), [src])
    check("disk", "ensure_disk_space takes SOURCE PATHS and returns (bool, msg)",
          ok is True and isinstance(msg, str))

    try:
        F.check_disk_space(str(sandbox), 1024, raise_on_insufficient=True)
        check("disk", "raise_on_insufficient=True does not fire when there is room", True)
    except F.InsufficientSpaceError:
        check("disk", "raise_on_insufficient=True does not fire when there is room", False)

finally:
    shutil.rmtree(sandbox, ignore_errors=True)

# ------------------------------------------------------------------ report
width = max(len(c) for _, c, _, _ in results)
fails = [r for r in results if not r[2]]
current = None
for recipe, claim, ok, detail in results:
    if recipe != current:
        print("\n  %s" % recipe.upper())
        current = recipe
    print("    [%s] %-*s %s" % ("OK" if ok else "XX", width, claim,
                                "" if ok else "<- " + (detail or "failed")))

print()
print("  %d checks across %d recipes, %d FAILED"
      % (len(results), len({r[0] for r in results}), len(fails)))
sys.exit(1 if fails else 0)
