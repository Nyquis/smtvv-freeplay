# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Change-scoped tests for ue_asset's tagged-property round trip.

The fixture is a hand-built package object: the parser's header handling is
covered by the real game files, while these tests exercise walk(), replace()
and build() without redistributing any game data.
"""

from __future__ import annotations

import struct

import ue_asset


def _fname(index: int) -> bytes:
    return struct.pack("<ii", index, 0)


def _package() -> ue_asset.Package:
    p = object.__new__(ue_asset.Package)
    p.names = ["None", "Text", "StrProperty"]
    p.name_ix = {name: i for i, name in enumerate(p.names)}
    p.new_names = []
    p.header_size = 0
    p.export_count = 1
    p.export_offset = 0
    p.a = bytearray(256)

    value = ue_asset.fstring("hello")
    p.e = bytearray(
        _fname(1)  # property name
        + _fname(2)  # StrProperty
        + struct.pack("<ii", len(value), 0)  # size, array index
        + b"\x00"  # no property guid
        + value
        + _fname(0)  # None
    )
    struct.pack_into("<qq", p.a, 28, len(p.e), 0)  # export size, offset

    p.at = {
        "header": 100,
        "gatherable": 104,
        "import_offset": 108,
        "depends": 112,
        "soft_refs": 116,
        "searchable": 120,
        "thumbnails": 124,
        "asset_registry": 128,
        "bulk": 136,
        "world_tile": 144,
        "preload": 152,
        "name_count": 160,
        "gen_names": None,
        "export_offset": 168,
    }
    p.name_offset = 200
    p.name_end = 240
    return p


def test_walk_finds_tagged_property():
    p = _package()
    tags = []
    p.walk(0, len(p.e), tags)
    assert [(t[3], t[4]) for t in tags] == [("Text", "StrProperty")]
    _size_at, start, end, _name, _type = tags[0]
    assert p.e[start:end] == ue_asset.fstring("hello")


def test_replace_grows_the_value_and_its_tag():
    p = _package()
    tags = []
    p.walk(0, len(p.e), tags)
    _size_at, start, _end, _name, _type = tags[0]
    old = ue_asset.fstring("hello")
    new = ue_asset.fstring("hello there")

    p.replace(start, old, new)

    assert p.e[start : start + len(new)] == new
    assert struct.unpack_from("<i", p.e, 16)[0] == len(new)
    assert p.export_range(0)[1] - p.export_range(0)[0] == len(p.e)


def test_build_appends_new_names_and_keeps_offsets():
    p = _package()
    p.name("Extra")
    original_len = len(p.a)
    uasset, uexp = p.build()

    assert len(uasset) == original_len + len(ue_asset.fstring("Extra")) + 4
    assert uexp == bytes(p.e)
    assert bytes(uasset[p.name_end : p.name_end + len(ue_asset.fstring("Extra"))]) == (
        ue_asset.fstring("Extra")
    )


def test_fstring_round_trip_ascii_and_unicode():
    reader = ue_asset._Reader(ue_asset.fstring("plain"))
    assert reader.fstr() == "plain"
    reader = ue_asset._Reader(ue_asset.fstring("女神転生"))
    assert reader.fstr() == "女神転生"
