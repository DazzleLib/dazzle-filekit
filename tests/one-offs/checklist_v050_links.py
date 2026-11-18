"""Hand-run companion to the v0.5.0 checklist: copy a tree with a link three ways.

Builds, under a NEW folder you name, a small tree holding one junction
(Windows) or one symlink (elsewhere) that points at a folder beside it, then
copies the tree with links="keep", "follow" and "skip" and prints what each
copy holds. Nothing is deleted: the folder is left for you to look at and
remove yourself. It refuses a folder that already exists, so it cannot write
into real data.

Usage: python tests/one-offs/checklist_v050_links.py <new scratch folder>
"""
import os
import sys

from dazzle_filekit.operations import copy_tree_preserving_links
from dazzle_filekit.utils.validation import is_junction


def describe(path):
    if is_junction(path):
        return "junction -> " + os.readlink(path)
    if os.path.islink(path):
        return "symlink -> " + os.readlink(path)
    if os.path.isdir(path):
        return "folder holding " + repr(sorted(os.listdir(path)))
    if os.path.lexists(path):
        return "file"
    return "absent"


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    root = os.path.abspath(argv[1])
    if os.path.lexists(root):
        print("refusing: %s already exists; name a folder that does not" % root)
        return 2
    outside = os.path.join(root, "outside")
    src = os.path.join(root, "src")
    os.makedirs(outside)
    os.makedirs(os.path.join(src, "sub"))
    with open(os.path.join(outside, "behind-the-link.txt"), "w") as fh:
        fh.write("this file lives outside the tree\n")
    with open(os.path.join(src, "sub", "inside.txt"), "w") as fh:
        fh.write("this file lives inside the tree\n")
    link = os.path.join(src, "sub", "link")
    if sys.platform == "win32":
        from dazzle_filekit.links import create_junction_raw
        if not create_junction_raw(outside, link):
            print("could not create the junction; stopping")
            return 1
    else:
        os.symlink(outside, link)
    print("source link:        ", describe(link))
    for choice in ("keep", "follow", "skip"):
        dst = os.path.join(root, "copy-" + choice)
        copy_tree_preserving_links(src, dst, links=choice)
        print("links=%-7s copy:  " % repr(choice), describe(os.path.join(dst, "sub", "link")))
    print("outside still holds:", sorted(os.listdir(outside)))
    print("left in place:      ", root)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
