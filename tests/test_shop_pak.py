"""Change-scoped tests for shop_pak (synthetic TBL1 tables, no game data)."""

from __future__ import annotations

import struct

import pytest

import shop_pak


def _section_blob(body: bytes, rowsize: int) -> bytes:
    return b"TBL1" + struct.pack("<III", len(body), rowsize, 16) + body


def _item_table() -> bytes:
    # Section 0: 220 item rows.
    rows = bytearray(220 * shop_pak.ITEM_ROW)
    for n in range(1, 221):
        o = (n - 1) * shop_pak.ITEM_ROW
        struct.pack_into("<i", rows, o + shop_pak.ITEM_ID_OFF, n)
        struct.pack_into("<i", rows, o + shop_pak.ITEM_BUY_OFF, 1000 + n)
        struct.pack_into("<i", rows, o + shop_pak.ITEM_SELL_OFF, 250 + n)
    # Section 1 is a placeholder so that section 2 has the same index as in
    # the real table.
    essences = bytearray(305 * shop_pak.ESSENCE_ROW)
    for i in range(305):
        o = i * shop_pak.ESSENCE_ROW
        struct.pack_into("<i", essences, o + shop_pak.ESSENCE_ID_OFF, 311 + i)
        struct.pack_into("<i", essences, o + shop_pak.ESSENCE_PRICE_OFF, 70000)
    return (
        _section_blob(bytes(rows), shop_pak.ITEM_ROW)
        + _section_blob(b"", shop_pak.ESSENCE_ROW)
        + _section_blob(bytes(essences), shop_pak.ESSENCE_ROW)
    )


def _shop_table(rows) -> bytes:
    body = bytearray(len(rows) * shop_pak.SHOP_ROW)
    for i, (item, sort, a, b) in enumerate(rows):
        struct.pack_into("<HHIII", body, i * shop_pak.SHOP_ROW, item, sort, a, b, 0)
    return b"TBL1" + struct.pack("<III", len(body), shop_pak.SHOP_ROW, 16) + bytes(body)


def _item_row(blob: bytes, item: int) -> int:
    return 16 + (item - 1) * shop_pak.ITEM_ROW


def _essence_row(blob: bytes, index: int) -> int:
    # section 0 header+data, section 1 header (empty), section 2 header
    sec0 = 16 + 220 * shop_pak.ITEM_ROW
    sec1 = sec0 + 16
    return sec1 + 16 + index * shop_pak.ESSENCE_ROW


def test_default_mode_changes_nothing():
    original = _item_table()
    assert shop_pak.edit_item_table(original) == original


def test_growth_immediate_zeroes_growth_only():
    blob = shop_pak.edit_item_table(_item_table(), {"growth": "immediate"})
    for item in range(82, 109):
        o = _item_row(blob, item)
        assert struct.unpack_from("<i", blob, o + shop_pak.ITEM_BUY_OFF)[0] == 0
        assert struct.unpack_from("<i", blob, o + shop_pak.ITEM_SELL_OFF)[0] == 0
    for item in (1, 81, 109, 220):
        o = _item_row(blob, item)
        assert struct.unpack_from("<i", blob, o + shop_pak.ITEM_BUY_OFF)[0] != 0


def test_consumables_free_zeroes_consumables_only():
    blob = shop_pak.edit_item_table(_item_table(), {"consumables": "free"})
    for item in range(1, 82):
        o = _item_row(blob, item)
        assert struct.unpack_from("<i", blob, o + shop_pak.ITEM_BUY_OFF)[0] == 0
        assert struct.unpack_from("<i", blob, o + shop_pak.ITEM_SELL_OFF)[0] == 0
    o = _item_row(blob, 82)
    assert struct.unpack_from("<i", blob, o + shop_pak.ITEM_BUY_OFF)[0] != 0


def test_misc_immediate_zeroes_misc_only():
    blob = shop_pak.edit_item_table(_item_table(), {"misc": "immediate"})
    for item in range(109, 114):
        o = _item_row(blob, item)
        assert struct.unpack_from("<i", blob, o + shop_pak.ITEM_BUY_OFF)[0] == 0
    o = _item_row(blob, 108)
    assert struct.unpack_from("<i", blob, o + shop_pak.ITEM_BUY_OFF)[0] != 0


def test_essences_free_zeroes_section2_prices_only():
    original = _item_table()
    blob = shop_pak.edit_item_table(original, {"essences": "free"})
    for i in (0, 100, 304):
        o = _essence_row(blob, i)
        assert struct.unpack_from("<i", blob, o + shop_pak.ESSENCE_PRICE_OFF)[0] == 0
    # Section 0 must be untouched.
    o = _item_row(blob, 1)
    assert blob[o : o + shop_pak.ITEM_ROW] == original[o : o + shop_pak.ITEM_ROW]


def test_missing_rows_for_growth_and_misc():
    assert shop_pak.missing_rows({"growth": "immediate"}, {83}) == sorted(
        set(range(82, 109)) - {83}
    )
    assert shop_pak.missing_rows({"misc": "immediate"}, set()) == list(range(109, 114))
    assert shop_pak.missing_rows({"growth": "free"}, set()) == []


def test_shop_flags_cleared_for_immediate_categories():
    asset = bytes(600)  # no append path is taken, so no uasset edits needed
    table = _shop_table([(11, 0, 44, 318), (83, 1, 801, 0), (311, 2, 14, 245)])
    _, out = shop_pak.edit_shop_table(asset, table, {"consumables": "immediate"})
    assert struct.unpack_from("<II", out, 16 + 4) == (0, 0)
    assert struct.unpack_from("<II", out, 16 + shop_pak.SHOP_ROW + 4) == (801, 0)
    assert struct.unpack_from("<II", out, 16 + 2 * shop_pak.SHOP_ROW + 4) == (14, 245)


def test_shop_free_mode_leaves_flags_alone():
    table = _shop_table([(11, 0, 44, 318)])
    _, out = shop_pak.edit_shop_table(bytes(600), table, {"consumables": "free"})
    assert out == table


def test_unknown_category_or_mode_is_rejected():
    with pytest.raises(RuntimeError, match="unknown shop category"):
        shop_pak.normalize_modes({"weapons": "free"})
    with pytest.raises(RuntimeError, match="unknown shop mode"):
        shop_pak.normalize_modes({"growth": "cheap"})
