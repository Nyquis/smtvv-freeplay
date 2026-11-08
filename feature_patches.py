# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Executable feature patches that used to be inline in the main patcher."""

from __future__ import annotations

import struct

import gameplay_patches
import signatures


def _patcher():
    import patch_smtvv_freeplay as patcher

    return patcher


def patch_essences(
    data: bytearray, next_cave_off: int, cave_off: int, cave_len: int
) -> int:
    """Reusable Essences: skip ItemErase for essence IDs."""
    p = _patcher()
    if bytes(data[p.TRAMP_OFFSET : p.TRAMP_OFFSET + 5]) != p.TRAMP_ORIG:
        raise RuntimeError(f"Essence AOB mismatch at 0x{p.TRAMP_OFFSET:08X}")

    orig_disp = struct.unpack_from("<i", data, p.TRAMP_OFFSET + 1)[0]
    tramp_va = p.file_to_va(p.TRAMP_OFFSET)
    orig_target = tramp_va + 5 + orig_disp
    p_off = next_cave_off
    p_va = p.file_to_va(p_off)

    sc = bytearray()
    sc += b"\x81\xf9"
    sc += struct.pack("<I", p.ESSENCE_ID_MIN)
    sc += b"\x72"
    jb_pos = len(sc)
    sc += b"\x00"
    sc += b"\x81\xf9"
    sc += struct.pack("<I", p.ESSENCE_ID_MAX)
    sc += b"\x77"
    ja_pos = len(sc)
    sc += b"\x00"
    sc += b"\xc3"
    not_ess = len(sc)
    sc[jb_pos] = not_ess - (jb_pos + 1)
    sc[ja_pos] = not_ess - (ja_pos + 1)
    sc += b"\xe9"
    sc += struct.pack("<i", orig_target - (p_va + len(sc) + 4))

    next_cave_off = gameplay_patches._place(
        data,
        p_off,
        cave_off + cave_len,
        bytes(sc),
        base_va=p_va,
        check_refs=True,
    )
    struct.pack_into("<i", data, p.TRAMP_OFFSET + 1, p_va - (tramp_va + 5))
    return next_cave_off


def patch_heal(
    data: bytearray, next_cave_off: int, cave_off: int, cave_len: int
) -> int | None:
    """Leyline Auto-Heal: call PartyAllCure before the fount function."""
    p = _patcher()
    if bytes(data[p.RYUKETSU_TRAMP_OFFSET : p.RYUKETSU_TRAMP_OFFSET + 5]) != (
        p.RYUKETSU_TRAMP_ORIG
    ):
        raise RuntimeError("Leyline AOB mismatch")
    cure_va = p._heal_cure_target(data)
    if cure_va is None:
        raise RuntimeError("PartyAllCure AOB mismatch")

    ry_disp = struct.unpack_from("<i", data, p.RYUKETSU_TRAMP_OFFSET + 1)[0]
    ry_tramp_va = p.file_to_va(p.RYUKETSU_TRAMP_OFFSET)
    ry_orig_tgt = ry_tramp_va + 5 + ry_disp

    h_off = next_cave_off
    h_va = p.file_to_va(h_off)
    hsc = p._heal_code(cure_va, ry_orig_tgt, h_va)
    next_cave_off = gameplay_patches._place(
        data,
        h_off,
        cave_off + cave_len,
        hsc,
        base_va=h_va,
        check_refs=True,
    )
    struct.pack_into("<i", data, p.RYUKETSU_TRAMP_OFFSET + 1, h_va - (ry_tramp_va + 5))
    return next_cave_off


def patch_miman(data: bytearray) -> int | None:
    """Miman Reveal: make CheckMimanPositionFlag always return true."""
    p = _patcher()
    offset = signatures.resolve(data, p.MIMAN_POS_CHECK_OFFSET, p.MIMAN_POS_CHECK_ORIG)
    if offset is None:
        return None
    data[offset : offset + 3] = b"\xb0\x01\xc3"
    return offset


def patch_miracles(
    data: bytearray, next_cave_off: int, cave_off: int, cave_len: int
) -> tuple[int, int, int, int, int]:
    """NG+ Miracles: unlock IDs and hide the hardcoded 666 block."""
    p = _patcher()

    if data[p.MIRACLE_666_NOP_ADDR : p.MIRACLE_666_NOP_ADDR + 2] != b"\x0f\x84":
        raise RuntimeError("666-block AOB mismatch")
    for index in range(6):
        data[p.MIRACLE_666_NOP_ADDR + index] = 0x90

    if bytes(data[p.MIRACLE_ADDED_TRAMP : p.MIRACLE_ADDED_TRAMP + 5]) != (
        p.MIRACLE_ADDED_ORIG
    ):
        raise RuntimeError("IsAdded AOB mismatch")
    if bytes(data[p.MIRACLE_STATE_TRAMP : p.MIRACLE_STATE_TRAMP + 5]) != (
        p.MIRACLE_STATE_ORIG
    ):
        raise RuntimeError("GetState AOB mismatch")

    ma_disp = struct.unpack_from("<i", data, p.MIRACLE_ADDED_TRAMP + 1)[0]
    ma_va = p.file_to_va(p.MIRACLE_ADDED_TRAMP)
    ma_tgt = ma_va + 5 + ma_disp

    mc1 = next_cave_off
    mc1_va = p.file_to_va(mc1)
    sc_a = bytearray()
    je_a = []
    for mid in p.MIRACLE_UNLOCK_IDS:
        sc_a += b"\x83\xf9" + bytes([mid]) + b"\x74"
        je_a.append(len(sc_a))
        sc_a += b"\x00"
    sc_a += b"\xe9"
    sc_a += struct.pack("<i", ma_tgt - (mc1_va + len(sc_a) + 4))
    yes_a = len(sc_a)
    for jp in je_a:
        sc_a[jp] = yes_a - (jp + 1)
    sc_a += b"\xb0\x01\xc3"

    next_cave_off = gameplay_patches._place(
        data,
        mc1,
        cave_off + cave_len,
        bytes(sc_a),
        base_va=mc1_va,
        check_refs=True,
    )
    data[p.MIRACLE_ADDED_TRAMP] = 0xE9
    struct.pack_into("<i", data, p.MIRACLE_ADDED_TRAMP + 1, mc1_va - (ma_va + 5))

    ms_disp = struct.unpack_from("<i", data, p.MIRACLE_STATE_TRAMP + 1)[0]
    ms_va = p.file_to_va(p.MIRACLE_STATE_TRAMP)
    ms_tgt = ms_va + 5 + ms_disp

    mc2 = next_cave_off
    mc2_va = p.file_to_va(mc2)
    sc_s = bytearray()
    je_s = []
    for mid in p.MIRACLE_UNLOCK_IDS:
        sc_s += b"\x83\xf9" + bytes([mid]) + b"\x74"
        je_s.append(len(sc_s))
        sc_s += b"\x00"
    sc_s += b"\xe9"
    sc_s += struct.pack("<i", ms_tgt - (mc2_va + len(sc_s) + 4))
    yes_s = len(sc_s)
    for jp in je_s:
        sc_s[jp] = yes_s - (jp + 1)
    sc_s += b"\xb0\x04\xc3"

    next_cave_off = gameplay_patches._place(
        data,
        mc2,
        cave_off + cave_len,
        bytes(sc_s),
        base_va=mc2_va,
        check_refs=True,
    )
    data[p.MIRACLE_STATE_TRAMP] = 0xE9
    struct.pack_into("<i", data, p.MIRACLE_STATE_TRAMP + 1, mc2_va - (ms_va + 5))
    return next_cave_off, mc1, len(sc_a), mc2, len(sc_s)


def patch_compendium(data: bytearray) -> int | None:
    """Free Compendium: make the summon cost formula return zero."""
    p = _patcher()
    offset = signatures.resolve(data, p.DEVIL_COST_OFFSET, p.DEVIL_COST_ORIG)
    if offset is None:
        return None
    data[offset : offset + 3] = b"\x33\xc0\xc3"
    return offset
