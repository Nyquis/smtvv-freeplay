# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Change-scoped tests for Stockpile's side-cave allocation."""

from __future__ import annotations

import struct

import pytest

import gameplay_patches as gp
import stockpile


def _call_targets(code: bytes, base: int) -> set[int]:
    targets = set()
    for i in range(len(code) - 4):
        if code[i] == 0xE8:
            targets.add(base + i + 5 + struct.unpack_from("<i", code, i + 1)[0])
    return targets


def test_step_hook_sets_aside_and_restores():
    base = 0x140100000
    code = stockpile._step_code(
        base,
        0x140200000,  # original SetNextStep
        0x140300000,  # limits table
        0x140400000,  # hidden table
        0x140500000,  # active flag
        0x140600000,  # ItemGet
        0x140700000,  # ItemGetNum
        0x140800000,  # ItemErase
    )
    calls = _call_targets(code, base)
    assert 0x140200000 in calls
    assert 0x140600000 in calls
    assert 0x140700000 in calls
    assert 0x140800000 in calls
    # One restore loop at PRE and one at the end steps.
    assert code.count(bytes.fromhex("0f b6 14 31")) == 2


def test_cave_va_for_two_element_entry():
    assert stockpile._cave_va([0x503308, 0x5033C4]) == 0x140503D08


def test_cave_va_for_slack_entry():
    entry = [0x1400FC20, 0x1400FDC0, 0x140997400]
    assert stockpile._cave_va(entry) == 0x1549A7020


def test_failed_trial_restores_side_offsets(monkeypatch):
    side = [[0x100, 0x200], [0x300, 0x400, 0x140000000]]

    def fail(data, cave_off, cave_end, orig, side):
        side[0][0] += 16
        side[1][0] += 16
        raise RuntimeError("boom")

    monkeypatch.setattr(stockpile, "_patch_stockpile", fail)
    with pytest.raises(RuntimeError, match="boom"):
        stockpile.patch_stockpile(bytearray(), 0, 0, {}, side)
    assert side[0][0] == 0x100
    assert side[1][0] == 0x300


def test_none_trial_restores_side_offsets(monkeypatch):
    side = [[0x100, 0x200]]

    def none(data, cave_off, cave_end, orig, side):
        side[0][0] += 16

    monkeypatch.setattr(stockpile, "_patch_stockpile", none)
    assert stockpile.patch_stockpile(bytearray(), 0, 0, {}, side) is None
    assert side[0][0] == 0x100


def test_successful_trial_keeps_advanced_offsets(monkeypatch):
    side = [[0x100, 0x200]]

    def ok(data, cave_off, cave_end, orig, side):
        side[0][0] += 16
        return 16

    monkeypatch.setattr(stockpile, "_patch_stockpile", ok)
    assert stockpile.patch_stockpile(bytearray(), 0, 0, {}, side) == 16
    assert side[0][0] == 0x110


def test_put_code_uses_va_delta():
    data = bytearray(b"\xcc" * 0x100)
    caves = [[0, 0x100, 0x140001000]]
    gp.set_cave_references([])
    try:
        dest = gp.put_code(data, caves, lambda a: a.raw("C3"))
    finally:
        gp.set_cave_references([])
    assert dest == 0x140001000
    assert caves[0][0] == 16
    assert data[0] == 0xC3
