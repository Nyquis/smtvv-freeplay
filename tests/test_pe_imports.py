# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Tests for the PE import-table lookup used by the hooks."""

from __future__ import annotations

import struct

import gameplay_patches as gp
import pe_imports


def _synthetic_import_pe() -> bytes:
    data = bytearray(0x400)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x84, 0x8664)
    struct.pack_into("<H", data, 0x86, 1)
    struct.pack_into("<H", data, 0x94, 0xE0)

    optional = 0x80 + 24
    struct.pack_into("<H", data, optional, 0x20B)
    struct.pack_into("<Q", data, optional + 24, 0x140000000)
    struct.pack_into("<II", data, optional + 112 + 8, 0x1000, 0x28)

    header = optional + 0xE0
    data[header : header + 8] = b".idata\0\0"
    struct.pack_into("<IIII", data, header + 8, 0x200, 0x1000, 0x200, 0x200)
    struct.pack_into("<I", data, header + 36, 0x40000040)

    struct.pack_into("<IIIII", data, 0x200, 0x1040, 0, 0, 0x1080, 0x10A0)
    struct.pack_into("<Q", data, 0x240, 0x10C0)
    struct.pack_into("<Q", data, 0x248, 0)
    data[0x280 : 0x280 + 13] = b"kernel32.dll\0"
    struct.pack_into("<Q", data, 0x2A0, 0x10C0)
    struct.pack_into("<Q", data, 0x2A8, 0)
    data[0x2C0 : 0x2C0 + 14] = b"\0\0CreateThread\0"
    return bytes(data)


def test_import_slots_returns_the_iat_slot_va():
    slots = pe_imports.import_slots(_synthetic_import_pe())
    assert slots["CreateThread"] == 0x1400010A0


def test_import_slots_ignores_invalid_images():
    assert pe_imports.import_slots(b"") == {}
    assert pe_imports.import_slots(bytearray(0x100)) == {}


def test_set_iat_slots_updates_globals_and_reports_missing(monkeypatch):
    for name in gp.IAT_SLOTS.values():
        monkeypatch.setattr(gp, name, getattr(gp, name))

    gp.set_iat_slots({"CreateThread": 0x1234})

    assert gp.IAT_CREATE_THREAD == 0x1234
    assert gp.IAT_SLEEP == 0
    assert gp.iat_missing("CreateThread") == []
    assert gp.iat_missing("Sleep") == ["Sleep"]
