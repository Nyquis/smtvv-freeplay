# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Tests for the central verification/pak manifest."""

from __future__ import annotations

import pytest

import patch_manifest


@pytest.fixture
def synthetic_layout(monkeypatch):
    """Treat VA and file offset as the same value, and restore relocated globals."""
    import autosave
    import gameplay_patches as gp
    import newborn
    import patch_smtvv_freeplay as patcher
    import stockpile

    monkeypatch.setattr(gp, "off", lambda value: value)
    monkeypatch.setattr(gp, "va", lambda value: value)
    for module, names in (
        (
            patcher,
            (
                "TRAMP_OFFSET",
                "RYUKETSU_TRAMP_OFFSET",
                "PARTY_ALL_CURE_VA",
                "MIRACLE_ADDED_TRAMP",
                "MIRACLE_STATE_TRAMP",
                "MIRACLE_666_NOP_ADDR",
            ),
        ),
        (gp, ("ITEM_GET", "ITEM_GET_MAX", "ITEM_GET_NUM", "ITEM_IS_GOTTEN")),
        (
            autosave,
            (
                "SAVE_BUILD_SITE",
                "SAVE_BUILD_FN",
                "SAVE_SLOT_NATIVE",
                "FIELD_TICK_SITE",
                "FIELD_TICK_FN",
                "GAME_INSTANCE",
                "CURRENT_LANGUAGE",
            ),
        ),
        (newborn, ("RENEWAL_JMP", "RENEWAL_IMPL", "BOOK_RESET")),
        (stockpile, ("ITEM_GET_MAX", "ITEM_GET_NUM")),
    ):
        for name in names:
            monkeypatch.setattr(module, name, getattr(module, name))

    thunks = list(gp.SETNEXTSTEP_THUNKS)
    max_thunks = list(stockpile.MAX_THUNKS)
    yield
    gp.SETNEXTSTEP_THUNKS[:] = thunks
    stockpile.MAX_THUNKS[:] = max_thunks


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


def test_relocate_rewrites_sites_and_aliases(synthetic_layout):
    import autosave
    import gameplay_patches as gp
    import newborn
    import patch_smtvv_freeplay as patcher
    import stockpile

    data = bytearray(0x1000)
    placed = {
        0x100: patcher.TRAMP_ORIG,
        0x200: gp.ITEM_GET_MAX_ORIG,
        0x300: gp.SETNEXTSTEP_ORIG,
        0x380: gp.ITEM_GET_NUM_ORIG,
        0x400: newborn.RENEWAL_JMP_ORIG,
        0x480: autosave.SAVE_BUILD_ORIG,
    }
    for offset, original in placed.items():
        data[offset : offset + len(original)] = original

    notes = patch_manifest.relocate(data)

    assert patcher.TRAMP_OFFSET == 0x100
    assert gp.ITEM_GET_MAX == 0x200
    assert gp.SETNEXTSTEP_THUNKS == [0x300]
    assert stockpile.SETNEXTSTEP_THUNKS is gp.SETNEXTSTEP_THUNKS
    assert stockpile.ITEM_GET_MAX == 0x200
    assert stockpile.ITEM_GET_NUM == 0x380
    assert autosave.SAVE_BUILD_SITE == 0x480
    dispatch = int.from_bytes(newborn.RENEWAL_JMP_ORIG[1:5], "little", signed=True)
    assert newborn.RENEWAL_IMPL == 0x400 + 5 + dispatch
    assert not any("essences" in note for note in notes)


def test_relocate_rewrites_party_all_cure(synthetic_layout):
    import patch_smtvv_freeplay as patcher

    data = bytearray(0x1000)
    data[0x500 : 0x500 + len(patcher.PARTY_ALL_CURE_ORIG)] = patcher.PARTY_ALL_CURE_ORIG
    notes = patch_manifest.relocate(data)

    assert patcher.PARTY_ALL_CURE_VA == 0x500
    assert not any("party_all_cure" in note for note in notes)


def test_relocate_rewrites_autosave_helpers(synthetic_layout):
    import autosave

    data = bytearray(0x1000)
    data[0x600 : 0x600 + len(autosave.GAME_INSTANCE_ORIG)] = autosave.GAME_INSTANCE_ORIG
    data[0x700 : 0x700 + len(autosave.CURRENT_LANGUAGE_ORIG)] = (
        autosave.CURRENT_LANGUAGE_ORIG
    )
    notes = patch_manifest.relocate(data)

    assert autosave.GAME_INSTANCE == 0x600
    assert autosave.CURRENT_LANGUAGE == 0x700
    assert not any("autosave.game_instance" in note for note in notes)
    assert not any("autosave.current_language" in note for note in notes)


def test_relocate_reports_an_ambiguous_site(synthetic_layout):
    import autosave

    known = autosave.FIELD_TICK_SITE
    data = bytearray(0x1000)
    data[0x100 : 0x100 + len(autosave.FIELD_TICK_ORIG)] = autosave.FIELD_TICK_ORIG
    data[0x200 : 0x200 + len(autosave.FIELD_TICK_ORIG)] = autosave.FIELD_TICK_ORIG

    notes = patch_manifest.relocate(data)

    assert any("autosave.field_tick" in note for note in notes)
    assert autosave.FIELD_TICK_SITE == known


def test_verification_groups_match_the_sites_each_feature_patches():
    import gameplay_patches as gp

    sites = patch_manifest.static_sites(bytearray(0x1800))

    assert {offset for offset, _len, _orig in sites["refill"]} == {
        gp.off(thunk) for thunk in gp.SETNEXTSTEP_THUNKS
    }
    stockpile_offsets = {offset for offset, _len, _orig in sites["stockpile"]}
    assert gp.off(gp.ITEM_GET_MAX) in stockpile_offsets
    assert gp.off(gp.ITEM_GET_NUM) in stockpile_offsets
    assert gp.off(gp.ITEM_GET) not in stockpile_offsets


def test_every_setnextstep_patcher_verifies_the_thunk():
    import gameplay_patches as gp

    sites = patch_manifest.static_sites(bytearray(0x1800))
    expected = {gp.off(thunk) for thunk in gp.SETNEXTSTEP_THUNKS}
    for feature in ("refill", "stockpile", "magatsuhi", "autosave"):
        offsets = {offset for offset, _len, _orig in sites[feature]}
        assert expected <= offsets, feature


def test_feature_registry_keys_are_unique_and_ordered():
    assert len(patch_manifest.FEATURE_KEYS) == len(set(patch_manifest.FEATURE_KEYS))
    assert patch_manifest.FEATURE_KEYS == tuple(
        feature.key for feature in patch_manifest.FEATURES
    )
    assert set(patch_manifest.STATIC_FEATURES) <= set(patch_manifest.FEATURE_KEYS)


def test_registry_declares_known_safety_requirements():
    safety = {feature.key: feature.safety for feature in patch_manifest.FEATURES}
    assert "PartyAllCure signature" in safety["heal"]
    assert "PartyAllCure signature" in safety["refresh"]
    assert "IAT imports" in safety["jump"]
    assert "IAT imports" in safety["intro"]
    assert "GAME_INSTANCE" in safety["autosave"]
    assert "ITEM_MENU_ROWS" in safety["stockpile"]


def test_feature_apply_paths_resolve():
    import importlib

    for feature in patch_manifest.FEATURES:
        if feature.apply.startswith("patcher:"):
            assert feature.apply.split(":", 1)[1]
            continue
        module_name, _, function_name = feature.apply.partition(".")
        assert module_name and function_name, feature.apply
        module = importlib.import_module(module_name)
        assert callable(getattr(module, function_name)), feature.apply


def test_feature_paks_are_unique_and_owned_by_a_feature():
    paks = [pak for _key, pak in patch_manifest.FEATURE_PAKS]
    assert len(paks) == len(set(paks))
    for feature in patch_manifest.FEATURES:
        if feature.pak is not None:
            assert (feature.key, feature.pak) in patch_manifest.FEATURE_PAKS


def test_every_feature_pak_has_a_validation_entry():
    paks = {
        feature.key for feature in patch_manifest.FEATURES if feature.pak is not None
    }
    assert paks == set(patch_manifest.PAK_ENTRIES)
