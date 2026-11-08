# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Leyline Auto-Heal cave hook."""

from __future__ import annotations

import struct

import patch_smtvv_freeplay as patcher


def test_heal_code_reserves_shadow_space_and_is_wired_correctly():
    dest = 0x140522031
    cure = patcher.PARTY_ALL_CURE_VA
    original = 0x140B12345

    code = patcher._heal_code(cure, original, dest)

    assert len(code) == 32
    # rcx, rdx, r8, r9, rbx, then the x64 shadow space.
    assert code[:11] == bytes.fromhex("515241504151534883ec20")
    assert code[11] == 0xE8
    call_disp = struct.unpack_from("<i", code, 12)[0]
    assert dest + 16 + call_disp == cure
    assert code[16:20] == bytes.fromhex("4883c420")
    # rbx, r9, r8, rdx, rcx
    assert code[20:27] == bytes.fromhex("5b415941585a59")
    assert code[27] == 0xE9
    jump_disp = struct.unpack_from("<i", code, 28)[0]
    assert dest + 32 + jump_disp == original


def test_heal_code_does_not_put_saved_registers_in_shadow_space():
    code = patcher._heal_code(0x140AB94B0, 0x140B12345, 0x140522031)
    # The sub/add rsp pair must exist; without it the pushed registers become
    # the callee's shadow space and PartyAllCure overwrites them.
    assert b"\x48\x83\xec\x20" in code
    assert b"\x48\x83\xc4\x20" in code


def test_heal_cure_target_resolves_and_reports_missing(monkeypatch):
    import code_caves

    monkeypatch.setattr(code_caves, "off", lambda value: value)
    monkeypatch.setattr(code_caves, "va", lambda value: value)

    data = bytearray(0x1000)
    data[0x300 : 0x300 + len(patcher.PARTY_ALL_CURE_ORIG)] = patcher.PARTY_ALL_CURE_ORIG
    assert patcher._heal_cure_target(data) == 0x300

    data[0x300] ^= 0xFF
    assert patcher._heal_cure_target(data) is None
