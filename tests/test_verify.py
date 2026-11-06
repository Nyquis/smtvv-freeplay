# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Change-scoped tests for post-write verification."""

from __future__ import annotations

import patch_smtvv_freeplay as patcher


def test_verify_patched_accepts_changed_site(tmp_path):
    path = tmp_path / "exe"
    path.write_bytes(b"\x01\x01")
    sites = {"demo": [(0, 2, b"\x00\x00")]}
    assert (
        patcher._verify_patched(str(path), sites, {"demo": True}, str(tmp_path)) == []
    )


def test_verify_patched_rejects_unchanged_site(tmp_path):
    path = tmp_path / "exe"
    path.write_bytes(b"\x00\x00")
    sites = {"demo": [(0, 2, b"\x00\x00")]}
    failures = patcher._verify_patched(str(path), sites, {"demo": True}, str(tmp_path))
    assert failures and "was not changed" in failures[0]


def test_verify_patched_ignores_unselected_feature(tmp_path):
    path = tmp_path / "exe"
    path.write_bytes(b"\x00\x00")
    sites = {"demo": [(0, 2, b"\x00\x00")]}
    assert patcher._verify_patched(str(path), sites, {}, str(tmp_path)) == []


def test_verify_patched_checks_paks(tmp_path):
    path = tmp_path / "exe"
    path.write_bytes(b"\x00")
    failures = patcher._verify_patched(str(path), {}, {"shop": True}, str(tmp_path))
    assert failures and "missing data pak" in failures[0]
