"""Red-green audit for the portable path key and the batch planner, on a COPY.

Tests written beside the code were born green. This reverts one behaviour at
a time and records which tests go red; a reversion that turns nothing red
names a behaviour no test pins.

Safety: the real source is never modified. The package and the test files are
copied to a fresh temp folder, each mutation is applied to the copy, and
pytest runs against the copy only. The path key, the planner and the
normalizer are pure (no disk access). The tree-copy tests COPY, inside
pytest's tmp_path, a scratch tree whose one junction points at a scratch
folder beside it; no mutation makes the copy delete, so the worst a mutant
does is copy that scratch folder's one file. Nothing is deleted; the temp
folder is left in place and printed.

Usage: python tests/one-offs/redgreen_portable_and_batch_layout.py [substring]
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
B = "dazzle_filekit/batch_layout.py"
P = "dazzle_filekit/portable.py"
O = "dazzle_filekit/operations.py"
TESTS = ("test_portable.py", "test_batch_layout.py", "test_paths_expand.py",
         "test_copy_tree_links.py", "test_v051_import_and_unc_prefix.py",
         "test_create_dest_path_absolute_unc.py")
PA = "dazzle_filekit/paths.py"

MUTATIONS = [
    ("planner: duplicates are not merged",
     [(B, "        if ident in seen:\n", "        if False:\n")]),
    ("planner: case is not folded on a case-insensitive root",
     [(B, "    return tuple(p.casefold() for p in parts) if insensitive else tuple(parts)",
          "    return tuple(parts)")]),
    ("planner: a root is accepted as an item",
     [(B, "        if not split.parts:\n", "        if False:\n")]),
    ("planner: an item inside another is kept",
     [(B, "        if ancestor is None:\n            kept.append((original, split, root_key, folded))\n            continue",
          "        if True:\n            kept.append((original, split, root_key, folded))\n            continue")]),
    ("planner: an item under a link is dropped, not refused",
     [(B, "        if is_link is not None and is_link(ancestor[0]):\n", "        if False:\n")]),
    ("planner: drop_nested=False still drops",
     [(B, "        elif drop_nested:\n", "        elif True:\n")]),
    ("planner: the multi-root prefix is missing",
     [(B, "            if multi_root:\n", "            if False:\n")]),
    ("planner: relative paths use the native separator",
     [(B, '            relpath = "/".join(rel_parts)', '            relpath = split.sep.join(rel_parts)')]),
    ("planner: a leftover collision is not refused",
     [(B, "            if clash_key in used:\n", "            if False:\n")]),
    ("planner: names are not validated for the target",
     [(B, "                key_to_relpath(rel_parts, target_flavor=target)\n", "                pass\n")]),
    ("planner: an unencodable path becomes an item",
     [(B, "        except PortablePathError as exc:\n            plan.errors.append(str(exc))\n            continue",
          "        except PortablePathError as exc:\n            plan.errors.append(str(exc))\n            split = _split('/x', 'posix')")]),
    ("planner: the base is one level too shallow",
     [(B, "        base_parts = first_split.parts[:common]", "        base_parts = first_split.parts[:max(common - 1, 0)]")]),
    ("paths: expand=False still expands and strips",
     [("dazzle_filekit/paths.py", "    if expand:\n        # expand=False takes the path LITERALLY",
       "    if True:\n        # expand=False takes the path LITERALLY")]),
    ("paths: the default no longer expands",
     [("dazzle_filekit/paths.py", "    if expand:\n        # expand=False takes the path LITERALLY",
       "    if False:\n        # expand=False takes the path LITERALLY")]),
    ("copy: keep enters the junction (the 0.4.3 behaviour)",
     [(O, "            if is_junction(full):\n", "            if False:\n")]),
    ("copy: keep drops the junction instead of recreating it",
     [(O, "                if links == \"keep\":\n                    junctions.append(", "                if False:\n                    junctions.append(")]),
    ("copy: follow keeps links",
     [(O, "        if links == \"follow\":\n            return skipped", "        if False:\n            return skipped")]),
    ("copy: follow keeps symlinks as links",
     [(O, "        symlinks=(links != \"follow\"),", "        symlinks=True,")]),
    ("copy: skip keeps symlinks",
     [(O, "            elif links == \"skip\" and os.path.islink(full):", "            elif False:")]),
    ("copy: an unknown choice is accepted",
     [(O, "    if links not in (\"keep\", \"follow\", \"skip\"):", "    if False:")]),
    ("copy: a junction that could not be made is not an error",
     [(O, "        if failed:\n            raise shutil.Error(failed)", "        if False:\n            raise shutil.Error(failed)")]),
    ("copy: the caller's ignore is dropped",
     [(O, "        skipped: Set[str] = set(ignore(directory, names)) if ignore else set()", "        skipped: Set[str] = set()")]),
    ("import: unctools is imported at module top again",
     [(P, "from dataclasses import dataclass\n", "from dataclasses import dataclass\nfrom unctools import get_unc_path_elements\n")]),
    # -- decode, the relative-path join, and the flavor check: added
    #    2026-11-18 after the reversion-to-test matrix showed that eleven
    #    tests of these functions had never been turned red.
    ("decode: a UNC key decodes on POSIX",
     [(P, '        if runtime != "windows":\n            return None\n        return "\\\\\\\\" + "\\\\".join(rest)',
          '        if False:\n            return None\n        return "\\\\\\\\" + "\\\\".join(rest)')]),
    ("decode: a ROOT key decodes on Windows",
     [(P, '    if head == "ROOT":\n        if runtime == "windows":\n            return None',
          '    if head == "ROOT":\n        if False:\n            return None')]),
    ("decode: a drive key decodes on plain POSIX",
     [(P, '        if runtime == "wsl":\n            return f"/mnt/{head.lower()}"',
          '        if True:\n            return f"/mnt/{head.lower()}"')]),
    ("decode: the WSL mount keeps the upper-case letter",
     [(P, 'return f"/mnt/{head.lower()}" + "".join("/" + p for p in rest)',
          'return f"/mnt/{head}" + "".join("/" + p for p in rest)')]),
    ("decode: an unknown key root is accepted",
     [(P, '    raise PortablePathError(f"unknown key root {head!r} in {key!r}")', "    return None")]),
    ("relpath: '..' and empty parts are accepted",
     [(P, '    if part in ("", ".", ".."):\n        raise PortablePathError(f"invalid part {part!r} in {where}")',
          '    if False:\n        raise PortablePathError(f"invalid part {part!r} in {where}")')]),
    ("relpath: characters Windows cannot store are accepted",
     [(P, "        if bad:\n            raise PortablePathError(\n                f\"part {part!r} has characters Windows cannot store \"",
          "        if False:\n            raise PortablePathError(\n                f\"part {part!r} has characters Windows cannot store \"")]),
    ("relpath: a trailing dot or space is accepted",
     [(P, '        if part.endswith((".", " ")):', "        if False:")]),
    ("relpath: a reserved Windows name is accepted",
     [(P, '        if part.split(".")[0].upper() in _RESERVED:', "        if False:")]),
    ("relpath: Windows rules are applied to a POSIX target too",
     [(P, '    if target_flavor == "windows":\n        bad = sorted(', '    if True:\n        bad = sorted(')]),
    ("relpath: joined with '/' for a Windows target",
     [(P, '    sep = "\\\\" if target_flavor == "windows" else "/"\n    return sep.join(parts)', '    return "/".join(parts)')]),
    ("decode: a malformed key ('..', empty part) is accepted",
     [(P, '        if p in ("", ".", "..") or "\\x00" in p:\n            raise PortablePathError(f"invalid part {p!r} in key {key!r}")',
          '        if False:\n            raise PortablePathError(f"invalid part {p!r} in key {key!r}")')]),
    ("decode: a UNC key without a share is accepted",
     [(P, "        if len(parts) < 3:\n            raise PortablePathError(f\"UNC key needs a server and a share: {key!r}\")",
          "        if False:\n            raise PortablePathError(f\"UNC key needs a server and a share: {key!r}\")")]),
    ("key: /mnt/<x> is not a drive under WSL either",
     [(P, '    if flavor == "wsl" and len(parts) >= 2 and parts[0] == "mnt"', '    if False and len(parts) >= 2 and parts[0] == "mnt"')]),
    ("flavor: an unknown flavor is accepted",
     [(P, "    if flavor not in FLAVORS:\n", "    if False:\n")]),
    ("key: the error is only a ValueError again",
     [(P, "class PortablePathError(FileOperationError, ValueError):", "class PortablePathError(ValueError):")]),
    ("paths: the extended UNC prefix is not unwrapped",
     [("dazzle_filekit/paths.py", '        if path_str.upper().startswith("\\\\\\\\?\\\\UNC\\\\"):', "        if False:")]),
    ("paths: the extended UNC marker is case-sensitive",
     [("dazzle_filekit/paths.py", '        if path_str.upper().startswith("\\\\\\\\?\\\\UNC\\\\"):', '        if path_str.startswith("\\\\\\\\?\\\\UNC\\\\"):')]),
    ("key: /mnt/<x> is a drive on plain POSIX too",
     [(P, '    if flavor == "wsl" and len(parts) >= 2 and parts[0] == "mnt"', '    if len(parts) >= 2 and parts[0] == "mnt"')]),
    ("key: a device path is accepted",
     [(P, '    elif s.startswith("\\\\\\\\.\\\\"):\n        raise PortablePathError(f"device path is not portable: {original!r}")',
          '    elif False:\n        raise PortablePathError(f"device path is not portable: {original!r}")')]),
    ("key: a drive-relative path is accepted",
     [(P, '    if not rest.startswith("\\\\"):\n        raise PortablePathError(f"drive-relative path is not absolute: {original!r}")',
          '    if False:\n        raise PortablePathError(f"drive-relative path is not absolute: {original!r}")')]),
    ("key: the drive letter is not upper-cased",
     [(P, "        token=(letter.upper(),),", "        token=(letter,),")]),
    ("key: a component that needs the prefix is accepted",
     [(P, "    if split.needs_prefix:\n        bad = next(p for p in split.parts if _needs_prefix(p))\n        raise PortablePathError(",
          "    if False:\n        bad = next(p for p in split.parts if _needs_prefix(p))\n        raise PortablePathError(")]),
    ("dest path: a UNC source is joined onto dest_base again (escapes)",
     [(PA, "            if text.startswith('\\\\\\\\'):\n", "            if False:\n")]),
    # Considered and dropped as equivalent (2026-11-19): routing EVERY Windows
    # source through the key ("if True:") leaves all tests green because, for
    # the normalised drive paths create_dest_path produces, the key's layout
    # is byte-identical to the old drive layout. Not a gap in the tests.
]


def run(root):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([root] + [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header",
         "--no-cov", "--tb=no", "-rfE"] + ["tests/" + t for t in TESTS],
        cwd=root, env=env, capture_output=True, text=True, timeout=600)
    failed = [ln.split(" - ")[0].split("::", 1)[-1] for ln in p.stdout.splitlines()
              if ln.startswith(("FAILED ", "ERROR "))]
    lines = [ln for ln in p.stdout.splitlines() if ln.strip()]
    return failed, (lines[-1] if lines else "(no output) " + p.stderr[-200:])


def main(argv):
    only = argv[1] if len(argv) > 1 else None
    root = tempfile.mkdtemp(prefix="dz-redgreen-filekit-")
    shutil.copytree(os.path.join(REPO, "dazzle_filekit"), os.path.join(root, "dazzle_filekit"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    os.makedirs(os.path.join(root, "tests"))
    for name in TESTS:
        shutil.copy2(os.path.join(REPO, "tests", name), os.path.join(root, "tests", name))
    print("copy:", root, "(the real source is not modified)")
    failed, tail = run(root)
    print("GREEN baseline:", tail)
    if failed:
        print("baseline not green:", failed)
        return 2
    unpinned = []
    results = {}        # reversion -> the tests it turned red
    for name, edits in MUTATIONS:
        if only and only not in name:
            continue
        originals, texts, problem = {}, {}, None
        for rel, old, new in edits:
            path = os.path.join(root, rel.replace("/", os.sep))
            if path not in originals:
                with open(path, "r", encoding="utf-8", newline="") as fh:
                    originals[path] = texts[path] = fh.read().replace("\r\n", "\n")
            if texts[path].count(old) != 1:
                problem = "anchor found %d times: %r" % (texts[path].count(old), old[:50])
                break
            texts[path] = texts[path].replace(old, new)
        if problem:
            print("BROKEN %-58s %s" % (name, problem))
            unpinned.append(name + " [anchor]")
            continue
        for path, text in texts.items():
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        try:
            failed, tail = run(root)
        finally:
            for path, text in originals.items():
                with open(path, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(text)
        results[name] = sorted(set(failed))
        if failed:
            print("RED    %-58s %d test(s): %s" % (name, len(failed), sorted(set(failed))[0][:70]))
        else:
            print("GREEN  %-58s <-- NOT PINNED" % name)
            unpinned.append(name)
    failed, tail = run(root)
    print("GREEN again:", tail)
    out = os.environ.get("REDGREEN_JSON")
    if out:
        # A test in `collected` that no reversion turned red has never shown
        # here that it can fail.
        import json
        env = dict(os.environ, PYTHONPATH=root, PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
             "-o", "addopts="] + ["tests/" + t for t in TESTS],
            cwd=root, env=env, capture_output=True, text=True)
        collected = [ln.strip().split("::", 1)[-1] for ln in p.stdout.splitlines() if "::" in ln]
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"reversions": results, "collected": collected}, fh, indent=1)
        print("wrote", out)
    print("unpinned: %d" % len(unpinned))
    for u in unpinned:
        print("  -", u)
    return 1 if unpinned or failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
