# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Tests for the compact Leyline Auto-Heal cave hook."""

from __future__ import annotations

import struct

import patch_smtvv_freeplay as patcher


def test_heal_code_is_compact_and_correctly_wired():
    dest = 0x140522031
    cure = patcher.PARTY_ALL_CURE_VA
    original = 0x140B12345

    code = patcher._heal_code(cure, original, dest)

    assert len(code) == 28
    # rcx, rdx, r8, r9, rdi, rsi, rbx
    assert code[:9] == bytes.fromhex("515241504151575653")
    assert code[9] == 0xE8
    call_disp = struct.unpack_from("<i", code, 10)[0]
    assert dest + 14 + call_disp == cure
    # rbx, rsi, rdi, r9, r8, rdx, rcx
    assert code[14:23] == bytes.fromhex("5b5e5f415941585a59")
    assert code[23] == 0xE9
    jump_disp = struct.unpack_from("<i", code, 24)[0]
    assert dest + 28 + jump_disp == original
    assert b"\x48\x83\xec" not in code


def test_heal_code_is_smaller_than_the_old_stack_frame():
    # The old hook used push/sub rsp,20h/call/add rsp,20h/pop/jmp = 32 bytes.
    assert len(patcher._heal_code(0x140AB94B0, 0x140B12345, 0x140522031)) < 32
