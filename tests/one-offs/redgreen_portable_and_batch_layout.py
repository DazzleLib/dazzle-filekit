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
         "test_copy_tree_links.py")

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
        if failed:
            print("RED    %-58s %d test(s): %s" % (name, len(failed), sorted(set(failed))[0][:70]))
        else:
            print("GREEN  %-58s <-- NOT PINNED" % name)
            unpinned.append(name)
    failed, tail = run(root)
    print("GREEN again:", tail)
    print("unpinned: %d" % len(unpinned))
    for u in unpinned:
        print("  -", u)
    return 1 if unpinned or failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
