# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Tests for the best-fit cave allocator."""

from __future__ import annotations

import gameplay_patches as gp


def test_put_code_uses_the_tightest_cave(monkeypatch):
    monkeypatch.setattr(gp, "_range_has_reference", lambda *_args: False)
    data = bytearray(b"\xcc" * 0x200)
    caves = [
        [0x00, 0x80, 0],  # large: 112 bytes remain after a 16-byte hook
        [0x80, 0x90, 0],  # small: exactly 16 bytes remain
    ]

    dest = gp.put_code(data, caves, lambda a: a.raw("90" * 16))

    assert dest == 0x80
    assert caves[0][0] == 0x00
    assert caves[1][0] == 0x90
    assert data[0x80:0x90] == b"\x90" * 16


def test_put_code_skips_referenced_slots(monkeypatch):
    monkeypatch.setattr(
        gp,
        "_range_has_reference",
        lambda va, length: va in (0x00, 0x10),
    )
    data = bytearray(b"\xcc" * 0x80)
    caves = [[0x00, 0x30, 0]]

    dest = gp.put_code(data, caves, lambda a: a.raw("90" * 16))

    assert dest == 0x20
    assert caves[0][0] == 0x30
