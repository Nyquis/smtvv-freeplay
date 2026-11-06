"""Tests for the central verification/pak manifest."""

from __future__ import annotations

import patch_manifest


def test_feature_paks_are_unique_and_named():
    keys = [key for key, _pak in patch_manifest.FEATURE_PAKS]
    names = [pak for _key, pak in patch_manifest.FEATURE_PAKS]
    assert len(keys) == len(set(keys))
    assert all(name.endswith(".pak") for name in names)


def test_static_sites_cover_every_feature():
    sites = patch_manifest.static_sites(bytearray(0x1800))
    for feature in patch_manifest.STATIC_FEATURES:
        assert feature in sites
        assert sites[feature]
        assert all(length > 0 for _offset, length, _original in sites[feature])


def test_static_sites_relocate_simple_features():
    import patch_smtvv_freeplay as patcher

    data = bytearray(0x2000)
    data[0x800 : 0x800 + len(patcher.MIMAN_POS_CHECK_ORIG)] = (
        patcher.MIMAN_POS_CHECK_ORIG
    )
    data[0x900 : 0x900 + len(patcher.DEVIL_COST_ORIG)] = patcher.DEVIL_COST_ORIG
    sites = patch_manifest.static_sites(data)
    assert sites["mimans"][0][0] == 0x800
    assert sites["compendium"][0][0] == 0x900


def test_validate_pak_accepts_the_expected_entry(tmp_path, monkeypatch):
    import types

    pak = tmp_path / "pakchunk93_FreeplayStockpile_P.pak"
    pak.write_bytes(b"x")
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return types.SimpleNamespace(returncode=0, stdout="WB_CampItemList.uasset")

    monkeypatch.setattr(patch_manifest.subprocess, "run", fake_run)
    assert patch_manifest.validate_pak("repak", str(pak), "stockpile") == []
    assert calls[0][:2] == ["repak", "list"]


def test_validate_pak_reports_a_missing_entry(tmp_path, monkeypatch):
    import types

    pak = tmp_path / "pak.pak"
    pak.write_bytes(b"x")
    monkeypatch.setattr(
        patch_manifest.subprocess,
        "run",
        lambda *_a, **_k: types.SimpleNamespace(returncode=0, stdout="other"),
    )
    failures = patch_manifest.validate_pak("repak", str(pak), "stockpile")
    assert failures and "lacks" in failures[0]


def test_validate_pak_reports_an_unreadable_pak(tmp_path, monkeypatch):
    import types

    pak = tmp_path / "pak.pak"
    pak.write_bytes(b"x")
    monkeypatch.setattr(
        patch_manifest.subprocess,
        "run",
        lambda *_a, **_k: types.SimpleNamespace(returncode=1, stdout=""),
    )
    failures = patch_manifest.validate_pak("repak", str(pak), "stockpile")
    assert failures and "cannot list" in failures[0]


def test_static_sites_relocate_leylines():
    import leylines

    data = bytearray(0x2000)
    data[0xA00 : 0xA00 + len(leylines.POI_VISIBLE_ORIG)] = leylines.POI_VISIBLE_ORIG
    sites = patch_manifest.static_sites(data)
    assert sites["leylines"][0][0] == 0xA00


def test_static_sites_relocate_jump():
    import gameplay_patches as gp

    data = bytearray(0x2000)
    data[0xB00 : 0xB00 + len(gp.AIRSPEED_ORIG)] = gp.AIRSPEED_ORIG
    sites = patch_manifest.static_sites(data)
    assert any(offset == 0xB00 for offset, _length, _original in sites["jump"])


def test_static_sites_relocate_intro():
    import gameplay_patches as gp

    data = bytearray(0x2000)
    data[0xC00 : 0xC00 + len(gp.TITLE_TICK_ORIG)] = gp.TITLE_TICK_ORIG
    sites = patch_manifest.static_sites(data)
    assert sites["intro"][0][0] == 0xC00
