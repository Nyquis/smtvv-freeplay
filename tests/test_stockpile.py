# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Change-scoped tests for Stockpile's side-cave allocation."""

from __future__ import annotations

import pytest

import gameplay_patches as gp
import stockpile


def test_show_count_clamps_boss_rush_refill():
    assert stockpile._show_count(99, 0, 5) == (5, 94)
    assert stockpile._show_count(99, 94, 5) == (5, 94)
    assert stockpile._show_count(98, 94, 5) == (4, 94)
    assert stockpile._show_count(3, 94, 5) == (0, 94)
    assert stockpile._show_count(99, 0, 0) == (99, 0)


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
