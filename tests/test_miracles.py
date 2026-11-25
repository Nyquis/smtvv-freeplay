# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Tests for the normal-miracle unlock and its data-table edits."""

from __future__ import annotations

import struct

import pytest

import feature_patches
import patch_smtvv_freeplay as patcher

ROWS = [
    (0, 0, 0, 0),  # placeholder
    (1, 1, 0, 150),  # normal
    (4, 0, 0, 0),  # placeholder carrying data
    (22, 25, 666, 10),  # NG+
    (30, 46, 0, 10),  # NG+
    (137, 43, 738, 10),  # save-state sentinel
    (145, 85, 740, 999),  # save-state sentinel
    (138, 36, 0, 30),  # normal, Estoma Field I
]


def _table(rows) -> bytearray:
    """A synthetic TBCR/TBL1 GodParameterDataTable payload."""
    body = bytearray(len(rows) * patcher.GP_ROW_SIZE)
    for index, (row_id, section, condition, cost) in enumerate(rows):
        offset = index * patcher.GP_ROW_SIZE
        struct.pack_into("<HH", body, offset, row_id, section)
        struct.pack_into("<I", body, offset + patcher.GP_ROW_CONDITION_OFF, condition)
        struct.pack_into("<H", body, offset + patcher.GP_ROW_COST_OFF, cost)
    header = b"TBCR" + struct.pack("<III", 16, 1, 0)
    return bytearray(
        b"\0\0\0\0"
        + header
        + b"TBL1"
        + struct.pack("<III", len(body), patcher.GP_ROW_SIZE, 16)
        + body
    )


def _costs(data: bytearray) -> dict[int, int]:
    count, row_size, first = patcher._miracle_table_rows(data)
    costs = {}
    for index in range(count):
        offset = first + index * row_size
        row_id = struct.unpack_from("<H", data, offset)[0]
        costs[row_id] = struct.unpack_from(
            "<H", data, offset + patcher.GP_ROW_COST_OFF
        )[0]
    return costs


def test_only_normal_rows_are_made_free():
    table = _table(ROWS)
    assert patcher.zero_normal_miracle_costs(table) == 2
    costs = _costs(table)
    assert costs[1] == 0
    assert costs[138] == 0
    assert costs[22] == 10
    assert costs[30] == 10
    assert costs[137] == 10
    assert costs[145] == 999


def test_no_normal_rows_is_an_error():
    with pytest.raises(RuntimeError, match="no normal miracle rows"):
        patcher.zero_normal_miracle_costs(_table([(22, 25, 666, 10)]))


def test_patch_writes_a_true_return(monkeypatch):
    monkeypatch.setattr(patcher, "MIRACLE_OPEN_TRAMP", 0x100)
    data = bytearray(0x200)
    data[0x100 : 0x100 + len(patcher.MIRACLE_OPEN_ORIG)] = patcher.MIRACLE_OPEN_ORIG
    assert feature_patches.patch_normal_miracles(data) == 0x100
    assert bytes(data[0x100 : 0x100 + len(patcher.MIRACLE_OPEN_PATCH)]) == (
        patcher.MIRACLE_OPEN_PATCH
    )


def test_patch_refuses_a_moved_site(monkeypatch):
    monkeypatch.setattr(patcher, "MIRACLE_OPEN_TRAMP", 0x100)
    with pytest.raises(RuntimeError, match="Miracle open AOB mismatch"):
        feature_patches.patch_normal_miracles(bytearray(0x200))
