"""Change-scoped tests for gameplay_patches' emitter and AOB guards."""

from __future__ import annotations

import struct

import pytest

import gameplay_patches as gp


def test_asm_jmp_to_next_label_is_zero_displacement():
    a = gp.Asm(0x1000)
    a.raw("90").jmp("end").label("end").raw("C3")
    assert a.build() == b"\x90\xe9\x00\x00\x00\x00\xc3"


def test_asm_call_uses_absolute_va():
    a = gp.Asm(0x1000)
    a.call(0x2000)
    code = a.build()
    assert code[0] == 0xE8
    rel = struct.unpack_from("<i", code, 1)[0]
    assert 0x1000 + 5 + rel == 0x2000


def test_place_writes_code_and_aligns_to_16():
    data = bytearray(b"\xcc" * 32)
    nxt = gp._place(data, 0, 32, b"\x01\x02\x03")
    assert data[:3] == b"\x01\x02\x03"
    assert data[3] == 0xCC
    assert nxt == 16


def test_place_rejects_a_small_cave():
    with pytest.raises(RuntimeError, match="cave too small"):
        gp._place(bytearray(b"\xcc" * 4), 0, 4, b"\x01" * 8)


def test_place_requires_cc_padding():
    with pytest.raises(AssertionError):
        gp._place(bytearray(8), 0, 8, b"\x01")


def test_jmp_site_writes_relative_jump_and_nops():
    data = bytearray(32)
    site = gp.RDATA_VA - gp.RDATA_RAW  # off(site) == 0
    gp._jmp_site(data, site, 0x140002000, 8)
    assert data[0] == 0xE9
    rel = struct.unpack_from("<i", data, 1)[0]
    assert site + 5 + rel == 0x140002000
    assert data[5:8] == b"\x90\x90\x90"


def test_magatsuhi_guard_refuses_unknown_layout():
    data = bytearray(0xC30000)
    assert gp.patch_magatsuhi(data, [[0, 0]]) is False


def _magatsuhi_blob():
    data = bytearray(0xC30000)
    thunk = gp.off(gp.SETNEXTSTEP_THUNKS[0])
    data[thunk : thunk + 5] = gp.SETNEXTSTEP_ORIG
    data[:0x800] = b"\xcc" * 0x800
    caves = [[0, 0x800, gp.RDATA_VA - gp.RDATA_RAW]]
    return data, caves, gp.va(0)


def test_magatsuhi_chain_mode_stores_the_actor_and_gauge_array():
    data, caves, base = _magatsuhi_blob()
    assert gp.patch_magatsuhi(data, caves, chain=True) is True
    code = bytes(data[:0x800])
    targets = set()
    for pos in range(len(code) - 7):
        for lead in (
            b"\x48\x39\x1d",
            b"\x48\x39\x15",
            b"\x48\x89\x1d",
            b"\x48\x89\x15",
        ):
            if code.startswith(lead, pos):
                disp = struct.unpack_from("<i", code, pos + 3)[0]
                targets.add(base + pos + 7 + disp)
    assert targets == {gp.MAGATSUHI_ACTOR, gp.MAGATSUHI_ARRAY}


def test_magatsuhi_battle_mode_has_no_chain_check():
    data, caves, _base = _magatsuhi_blob()
    assert gp.patch_magatsuhi(data, caves) is True
    code = bytes(data[:0x800])
    assert not any(lead in code for lead in (b"\x48\x39\x1d", b"\x48\x89\x1d"))


def test_refill_guard_refuses_unknown_layout():
    data = bytearray(0xC30000)
    assert gp.patch_refill(data, 0, 0) is None


def test_jump_guard_refuses_unknown_layout():
    data = bytearray(0xB00000)
    assert gp.patch_jump(data, 0, 0) is None
