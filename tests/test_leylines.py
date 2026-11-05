"""Change-scoped tests for the leyline fog-bypass patch."""

from __future__ import annotations

import struct

import leylines


def _buffer() -> bytearray:
    site = leylines.off(leylines.POI_VISIBLE_SITE)
    data = bytearray(site + len(leylines.POI_VISIBLE_ORIG))
    data[site : site + len(leylines.POI_VISIBLE_ORIG)] = leylines.POI_VISIBLE_ORIG
    data[0x1000:0x2000] = b"\xcc" * 0x1000
    return data


def test_patch_installs_site_jump_and_nops():
    data = _buffer()
    nxt = leylines.patch_leylines(data, 0x1000, 0x2000)
    assert nxt is not None

    site = leylines.off(leylines.POI_VISIBLE_SITE)
    assert data[site] == 0xE9
    assert leylines.site_jump_target(data) == leylines.va(0x1000)
    assert data[site + 5 : site + len(leylines.POI_VISIBLE_ORIG)] == b"\x90" * 6


def test_patch_cave_adds_ryuketsu_and_keeps_original_types():
    data = _buffer()
    leylines.patch_leylines(data, 0x1000, 0x2000)
    code = data[0x1000 : 0x1000 + 40]
    base = 0x140001A00

    assert code[:6] == bytes.fromhex("0fb60b80f905")

    # First conditional jump: RYUKETSU -> visible
    assert code[6:8] == b"\x0f\x84"
    first = base + 6 + 6 + struct.unpack_from("<i", code, 8)[0]
    assert first == leylines.POI_VISIBLE

    # Original MAGATSUKA / MIMAN test
    assert code[12:18] == bytes.fromhex("80e904f6c1f7")

    # Second conditional jump: MAGATSUKA / MIMAN -> visible
    assert code[18:20] == b"\x0f\x84"
    second = base + 18 + 6 + struct.unpack_from("<i", code, 20)[0]
    assert second == leylines.POI_VISIBLE

    # Fall through back to the original renderer
    assert code[24] == 0xE9
    cont = base + 24 + 5 + struct.unpack_from("<i", code, 25)[0]
    assert cont == leylines.POI_CONTINUE


def test_patch_refuses_unknown_site():
    data = bytearray(0xC00000)
    assert leylines.patch_leylines(data, 0x1000, 0x2000) is None
