"""plan_batch: where each item of a batch goes, with no two on one path.

Pure functions: nothing here touches the disk. The cases come from the
decided contract (a common base per root; duplicates merged; nested items
dropped; an item under a link, a root, and a leftover collision refused) and
from the incident that motivated it: two files with the same name in
different folders, staged into one flat folder, where the second replaced the
first.
"""
import pytest

from dazzle_filekit.batch_layout import plan_batch


def _rel(plan):
    return [i.relpath for i in plan.items]


def test_same_named_files_get_distinct_paths_under_their_common_parent():
    plan = plan_batch(
        [r"C:\Users\me\.claude\session-states\1.json",
         r"C:\Users\me\claude\context-window\1.json",
         r"C:\Users\me\claude\bookmarks\prompttext\1.json"],
        flavor="windows")

    assert plan.ok and plan.warnings == []
    assert plan.bases == [{"native": r"C:\Users\me", "key": "C/Users/me"}]
    assert _rel(plan) == [".claude/session-states/1.json",
                          "claude/context-window/1.json",
                          "claude/bookmarks/prompttext/1.json"]
    assert len(set(_rel(plan))) == 3


def test_one_item_keeps_just_its_name():
    plan = plan_batch([r"C:\work\docs"], flavor="windows")
    assert plan.ok and _rel(plan) == ["docs"]
    assert plan.bases == [{"native": r"C:\work", "key": "C/work"}]


def test_two_folders_with_one_name():
    plan = plan_batch([r"C:\work\path1\docs", r"C:\work\path2\docs"],
                      flavor="windows")
    assert plan.ok and _rel(plan) == ["path1/docs", "path2/docs"]
    assert plan.bases[0]["native"] == r"C:\work"


def test_items_on_two_drives_get_a_base_each_and_a_numbered_prefix():
    plan = plan_batch([r"C:\code\a\docs", r"E:\code\other\docs", r"C:\code\b\x.txt"],
                      flavor="windows")

    assert plan.ok
    assert [b["native"] for b in plan.bases] == [r"C:\code", r"E:\code\other"]
    assert [(i.base_index, i.relpath) for i in plan.items] == [
        (0, "0/a/docs"), (0, "0/b/x.txt"), (1, "1/docs")]


def test_a_share_is_its_own_root():
    plan = plan_batch([r"\\srv\share\a\x.txt", r"\\srv\share\b\x.txt"],
                      flavor="windows")
    assert plan.ok and _rel(plan) == ["a/x.txt", "b/x.txt"]
    assert plan.bases == [{"native": r"\\srv\share", "key": "UNC/srv/share"}]


@pytest.mark.parametrize("flavor, base_native, base_key", [
    ("wsl", "/mnt/c/Users/me", "C/Users/me"),
    ("posix", "/mnt/c/Users/me", "ROOT/mnt/c/Users/me"),
])
def test_the_same_posix_shaped_paths_read_per_flavor(flavor, base_native, base_key):
    plan = plan_batch(["/mnt/c/Users/me/a/x", "/mnt/c/Users/me/b/x"], flavor=flavor)
    assert plan.ok and _rel(plan) == ["a/x", "b/x"]
    assert plan.bases == [{"native": base_native, "key": base_key}]


def test_exact_and_case_variant_duplicates_are_merged_on_windows():
    plan = plan_batch([r"C:\a\File.txt", r"C:\a\File.txt", r"c:\A\file.TXT",
                       r"C:\a\other.txt"], flavor="windows")

    assert plan.ok and _rel(plan) == ["File.txt", "other.txt"]
    assert [d["reason"] for d in plan.dropped] == ["duplicate", "duplicate"]
    assert "given twice" in plan.warnings[0] and "same item" in plan.warnings[1]


def test_case_matters_on_a_posix_root():
    plan = plan_batch(["/data/a/File.txt", "/data/a/file.txt"], flavor="posix")
    assert not plan.ok                       # distinct items, but ...
    assert "would both be stored at" in plan.errors[0]   # ... one store path


def test_an_item_inside_another_is_dropped_with_a_warning():
    plan = plan_batch([r"C:\proj\build", r"C:\proj\build\out\a.o", r"C:\proj\notes.txt"],
                      flavor="windows")

    assert plan.ok and _rel(plan) == ["build", "notes.txt"]
    assert plan.dropped == [{"original": r"C:\proj\build\out\a.o", "reason": "nested"}]
    assert "carries it" in plan.warnings[0]


def test_an_item_inside_another_can_be_an_error_instead():
    plan = plan_batch([r"C:\proj\build", r"C:\proj\build\out"], flavor="windows",
                      drop_nested=False)
    assert not plan.ok and "also in the batch" in plan.errors[0]


def test_an_item_under_a_link_is_an_error():
    link = r"C:\wt\private"
    plan = plan_batch([link, r"C:\wt\private\notes.md"], flavor="windows",
                      is_link=lambda p: p == link)

    assert not plan.ok
    assert "which is a link" in plan.errors[0]
    assert plan.dropped == []


@pytest.mark.parametrize("flavor, root", [
    ("windows", "C:\\"), ("windows", r"\\srv\share"), ("posix", "/"), ("wsl", "/mnt/c"),
])
def test_a_root_is_refused(flavor, root):
    plan = plan_batch([root], flavor=flavor)
    assert not plan.ok and "root cannot be an item" in plan.errors[0]
    assert plan.items == []


@pytest.mark.parametrize("flavor, bad", [
    ("windows", r"relative\path"),
    ("windows", "C:drive-relative"),
    ("windows", "\\\\.\\C:\\x"),
    ("posix", "relative/path"),
])
def test_a_path_with_no_portable_form_is_an_error_not_an_item(flavor, bad):
    plan = plan_batch([bad], flavor=flavor)
    assert not plan.ok and plan.items == []


def test_names_illegal_on_the_target_are_refused():
    plan = plan_batch(["/data/a:b", "/data/ok"], flavor="posix",
                      target_flavor="windows")
    assert not plan.ok and len(plan.errors) == 1
    assert _rel(plan) == ["ok"]


def test_an_unknown_flavor_is_a_value_error():
    with pytest.raises(ValueError):
        plan_batch(["/x"], flavor="amiga")


def test_many_items_never_collide():
    """A seeded sweep: whatever the mix of depths and repeated names, an
    accepted plan gives every item its own relative path."""
    import random
    rng = random.Random(20261118)
    names = ["a", "b", "docs", "x.json", "1.json", "private"]
    for _ in range(200):
        paths = []
        for _ in range(rng.randint(1, 8)):
            depth = rng.randint(1, 4)
            parts = [rng.choice(names) for _ in range(depth)]
            paths.append("C:\\" + "\\".join(parts))
        plan = plan_batch(paths, flavor="windows")
        if plan.ok:
            rels = [r.casefold() for r in _rel(plan)]
            assert len(rels) == len(set(rels)), paths
            assert len(plan.items) + len(plan.dropped) == len(paths), paths
