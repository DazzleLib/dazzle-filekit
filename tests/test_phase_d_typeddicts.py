"""v0.3.0 (#15 Phase D): consume dazzle-lib TypedDict payload schemas.

filekit produces the cross-layer payload shapes (STACK-MAP D10); consuming the
bedrock TypedDicts as our signatures makes the contract explicit and
machine-checkable. Type hints are resolved with ``typing.get_type_hints`` so
the assertions hold whether or not a module uses ``from __future__ import
annotations`` (links.py does; metadata.py doesn't).
"""
import typing

import dazzle_lib
from dazzle_filekit.links import LinkInfo, analyze_link
from dazzle_filekit.metadata import (
    apply_file_metadata,
    collect_file_metadata,
    collect_timestamp_info,
)


def _hint(func, name):
    return typing.get_type_hints(func).get(name)


# ---------------------------------------------------------------------------
# Signatures consume the shared schemas
# ---------------------------------------------------------------------------


def test_collect_file_metadata_returns_filemetadatadict():
    assert _hint(collect_file_metadata, "return") is dazzle_lib.FileMetadataDict


def test_apply_file_metadata_accepts_filemetadatadict():
    assert _hint(apply_file_metadata, "metadata") is dazzle_lib.FileMetadataDict


def test_collect_timestamp_info_returns_timestampsdict():
    assert _hint(collect_timestamp_info, "return") is dazzle_lib.TimestampsDict


def test_linkinfo_to_dict_returns_linktargetdict():
    assert _hint(LinkInfo.to_dict, "return") is dazzle_lib.LinkTargetDict


# ---------------------------------------------------------------------------
# The produced dicts actually conform to the schemas (AC-COVERAGE for D10)
# ---------------------------------------------------------------------------


def test_collect_file_metadata_satisfies_required_keys(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    md = collect_file_metadata(f)
    # _FileMetadataRequired: mode, size, timestamps
    for key in ("mode", "size", "timestamps"):
        assert key in md, f"FileMetadataDict requires '{key}'"
    assert isinstance(md["timestamps"], dict)


def test_collect_timestamp_info_shape(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    ts = collect_timestamp_info(f)
    assert any(k in ts for k in ("created", "modified", "accessed"))


def test_linkinfo_to_dict_conforms_to_linktargetdict(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    d = analyze_link(f).to_dict()
    # Every key we emit is a declared LinkTargetDict field.
    declared = set(dazzle_lib.LinkTargetDict.__annotations__)
    assert set(d).issubset(declared), f"emitted keys not in LinkTargetDict: {set(d) - declared}"
    for key in ("kind", "raw_target", "resolved_target", "is_broken", "is_circular"):
        assert key in d
