# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Change-scoped tests for reveal.py (synthetic tags, no game data)."""

from __future__ import annotations

import struct

import pytest

import reveal


class FakePackage:
    def __init__(self, names, data):
        self.names = names
        self.e = bytearray(data)

    def name_of(self, data, pos):
        index, _ = struct.unpack_from("<ii", data, pos)
        return self.names[index]


def test_normalize_mode():
    assert reveal.normalize_mode(None) == "none"
    assert reveal.normalize_mode("both") == "both"
    with pytest.raises(RuntimeError, match="unknown map reveal mode"):
        reveal.normalize_mode("everything")


def test_reveal_tags_flips_matching_poi():
    names = [
        "None",
        "POIType",
        "ShowFar",
        "E_MINIMAP_POI_TYPE::E_MINIMAP_POI_TYPE_TREASURE",
    ]
    data = bytearray(32)
    struct.pack_into("<ii", data, 8, 3, 0)  # POIType value points at the treasure name
    data[16] = 0  # ShowFar
    tags = [
        ("POIType", "EnumProperty", 8, 8, None),
        ("ShowFar", "BoolProperty", 24, 0, 16),
    ]
    pkg = FakePackage(names, data)
    assert reveal.reveal_tags(tags, pkg.e, pkg.name_of, reveal.TARGETS["treasures"])
    assert pkg.e[16] == 1


def test_reveal_tags_ignores_other_poi():
    names = [
        "None",
        "POIType",
        "ShowFar",
        "E_MINIMAP_POI_TYPE::E_MINIMAP_POI_TYPE_CHANGE_AREA",
    ]
    data = bytearray(32)
    struct.pack_into("<ii", data, 8, 3, 0)
    tags = [
        ("POIType", "EnumProperty", 8, 8, None),
        ("ShowFar", "BoolProperty", 24, 0, 16),
    ]
    pkg = FakePackage(names, data)
    assert not reveal.reveal_tags(tags, pkg.e, pkg.name_of, reveal.TARGETS["both"])
    assert pkg.e[16] == 0


def test_reveal_tags_is_idempotent():
    names = [
        "None",
        "POIType",
        "ShowFar",
        "E_MINIMAP_POI_TYPE::E_MINIMAP_POI_TYPE_RYUKETSU",
    ]
    data = bytearray(32)
    struct.pack_into("<ii", data, 8, 3, 0)
    data[16] = 1
    tags = [
        ("POIType", "EnumProperty", 8, 8, None),
        ("ShowFar", "BoolProperty", 24, 0, 16),
    ]
    pkg = FakePackage(names, data)
    assert not reveal.reveal_tags(tags, pkg.e, pkg.name_of, reveal.TARGETS["leylines"])


def test_walk_records_bool_positions():
    names = ["None", "POIType", "EnumProperty", "ShowFar", "BoolProperty", "POI_VALUE"]

    def fname(i):
        return struct.pack("<ii", i, 0)

    data = (
        fname(1)
        + fname(2)
        + struct.pack("<ii", 8, 0)
        + fname(5)
        + b"\x00"
        + fname(5)
        + fname(3)
        + fname(4)
        + struct.pack("<ii", 0, 0)
        + b"\x00"
        + b"\x00"
        + fname(0)
    )
    pkg = FakePackage(names, data)
    tags = []
    reveal._walk(pkg, 0, len(data), tags)
    fields = {
        name: (typ, start, bool_pos) for name, typ, start, _size, bool_pos in tags
    }
    assert fields["POIType"][0] == "EnumProperty"
    assert fields["ShowFar"][0] == "BoolProperty"
    assert pkg.e[fields["ShowFar"][2]] == 0
    assert pkg.name_of(pkg.e, fields["POIType"][1]) == "POI_VALUE"
