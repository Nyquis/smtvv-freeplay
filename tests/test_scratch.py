# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Guard the writable scratch regions used by the executable patches."""

from __future__ import annotations

import itertools

import patch_smtvv_freeplay as patcher


def test_scratch_regions_are_nonempty_and_disjoint():
    regions = patcher._scratch_regions()
    assert regions
    assert all(size > 0 for _label, _va, size in regions)

    spans = sorted((va, va + size) for _label, va, size in regions)
    for (_start, end), (next_start, _end) in itertools.pairwise(spans):
        assert end <= next_start
