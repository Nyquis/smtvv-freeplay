# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Tests for the shared SetNextStep dispatcher."""

from __future__ import annotations

import struct

import code_caves
import gameplay_patches as gp

SITE = 0x100
ORIG_TARGET = 0x150
CAVE_START = 0x200
CAVE_END = 0x300
STEP_VAS = (0x400, 0x410, 0x420)


def _call_targets(code: bytes, base: int) -> list[int]:
    targets = []
    for index in range(len(code) - 4):
        if code[index] == 0xE8:
            disp = struct.unpack_from("<i", code, index + 1)[0]
            targets.append(base + index + 5 + disp)
    return targets


def test_dispatcher_calls_original_then_each_step(monkeypatch):
    thunk = bytes.fromhex("e94b000000")  # jmp ORIG_TARGET from SITE
    monkeypatch.setattr(gp, "SETNEXTSTEP_THUNKS", [SITE])
    monkeypatch.setattr(gp, "SETNEXTSTEP_ORIG", thunk)
    monkeypatch.setattr(code_caves, "CAVE_REFS", [])
    # gameplay_patches imports off/va by value; _jmp_site lives in code_caves.
    monkeypatch.setattr(gp, "off", lambda value: value)
    monkeypatch.setattr(gp, "va", lambda value: value)
    monkeypatch.setattr(code_caves, "off", lambda value: value)
    monkeypatch.setattr(code_caves, "va", lambda value: value)
    monkeypatch.setattr(
        gp,
        "DEFERRED_STEPS",
        {"refill": STEP_VAS[0], "magatsuhi": STEP_VAS[1], "autosave": STEP_VAS[2]},
    )

    data = bytearray(b"\xcc" * 0x500)
    data[SITE : SITE + 5] = thunk
    data[ORIG_TARGET] = 0xC3

    assert gp.patch_setnextstep(data, [[CAVE_START, CAVE_END, 0]]) is True

    assert data[SITE] == 0xE9
    dest = SITE + 5 + struct.unpack_from("<i", data, SITE + 1)[0]
    code = bytes(data[dest:CAVE_END])
    assert code.startswith(bytes.fromhex("534883ec204889cb"))

    targets = _call_targets(code, dest)
    assert ORIG_TARGET in targets
    for step in STEP_VAS:
        assert step in targets
