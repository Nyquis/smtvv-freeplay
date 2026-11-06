# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Change-scoped tests for estoma.py. Synthetic packages only: no game data."""

from __future__ import annotations

import struct

import pytest

import estoma


class FakePackage:
    """Minimal stand-in for ue_asset.Package."""

    def __init__(self, tags, payload=b"", exports=1):
        self.e = bytearray(payload)
        self.export_count = exports
        self._tags = tags

    def export_range(self, k):
        return (0, len(self.e))

    def walk(self, start, end, out):
        out.extend(self._tags)


def _tag(name, at, typ="IntProperty"):
    return (0, at, at + 4, name, typ)


def _package(values, extra_tags=()):
    payload = bytearray(max(64, 4 * len(values)))
    tags = list(extra_tags)
    for i, (name, value) in enumerate(values.items()):
        at = i * 4
        struct.pack_into("<i", payload, at, value)
        tags.append(_tag(name, at))
    return FakePackage(tags, payload)


def _all_costs(**overrides):
    values = dict.fromkeys(estoma.COST_PROPERTIES, 20)
    values.update(overrides)
    return values


def test_find_cost_offsets_selects_all_four():
    pkg = _package(_all_costs())
    offsets = estoma.find_cost_offsets(pkg)
    assert set(offsets) == set(estoma.COST_PROPERTIES)
    assert sorted(offsets.values()) == [0, 4, 8, 12]


def test_missing_property_raises():
    values = _all_costs()
    values.pop("m_LightMagatsuhi_WhenChangeMoon")
    with pytest.raises(RuntimeError, match="not found"):
        estoma.find_cost_offsets(_package(values))


def test_duplicate_property_raises():
    values = _all_costs()
    pkg = _package(values)
    pkg._tags.append(_tag("m_Magatsuhi_WhenUsed", 0))
    with pytest.raises(RuntimeError, match="duplicate"):
        estoma.find_cost_offsets(pkg)


def test_non_int_properties_are_ignored():
    values = _all_costs()
    pkg = _package(
        values, extra_tags=[_tag("m_Magatsuhi_WhenUsed", 60, "BoolProperty")]
    )
    assert set(estoma.find_cost_offsets(pkg)) == set(estoma.COST_PROPERTIES)


def test_zero_costs_zeroes_every_value_and_reports_the_old_ones():
    values = {
        "m_Magatsuhi_WhenUsed": 30,
        "m_Magatsuhi_WhenChangeMoon": 20,
        "m_LightMagatsuhi_WhenUsed": 24,
        "m_LightMagatsuhi_WhenChangeMoon": 16,
    }
    pkg = _package(values)
    old = estoma.zero_costs(pkg)
    assert old == values
    for at in range(0, 16, 4):
        assert struct.unpack_from("<i", pkg.e, at)[0] == 0


def test_out_of_range_cost_raises_and_writes_nothing():
    values = _all_costs(m_Magatsuhi_WhenUsed=estoma.COST_MAX + 1)
    pkg = _package(values)
    with pytest.raises(RuntimeError, match="unexpected cost"):
        estoma.zero_costs(pkg)
    assert struct.unpack_from("<i", pkg.e, 0)[0] == estoma.COST_MAX + 1
