# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Change-scoped tests for the executable source/backup guard."""

from __future__ import annotations

import pytest

import patch_smtvv_freeplay as patcher


def test_uses_original_when_live_matches_backup():
    assert patcher._choose_source("same", "same", None, False) == ("original", False)


def test_uses_original_when_live_is_the_patched_build():
    assert patcher._choose_source("patched", "original", "patched", False) == (
        "original",
        False,
    )


def test_refreshes_backup_for_a_new_build():
    assert patcher._choose_source("new", "original", "patched", False) == (
        "live",
        True,
    )


def test_first_install_uses_live_and_creates_backup():
    assert patcher._choose_source("new", None, None, False) == ("live", True)


def test_refuses_patched_build_without_original():
    with pytest.raises(RuntimeError, match="patched build"):
        patcher._choose_source("patched", None, "patched", True)


def test_refuses_partial_install_markers():
    with pytest.raises(RuntimeError, match="patched markers"):
        patcher._choose_source("unknown", "original", "patched", True)


def test_detects_miman_patch_marker(tmp_path):
    path = tmp_path / "exe"
    with open(path, "wb") as fh:
        fh.truncate(patcher.MIMAN_POS_CHECK_OFFSET + 3)
    with open(path, "r+b") as fh:
        fh.seek(patcher.MIMAN_POS_CHECK_OFFSET)
        fh.write(b"\xb0\x01\xc3")
    assert patcher._has_patched_markers(str(path)) is True


def test_blank_executable_has_no_markers(tmp_path):
    path = tmp_path / "exe"
    path.write_bytes(b"\0" * 16)
    assert patcher._has_patched_markers(str(path)) is False
