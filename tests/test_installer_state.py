"""Tests for the installer's catalogue, state parsing and flags."""

from __future__ import annotations

import installer_state as state


def test_catalogue_keys_are_unique():
    keys = [mod.key for mod in state.MODS]
    assert len(keys) == len(set(keys))


def test_features_round_trip_through_a_selection():
    features = {
        "essences": "1",
        "heal": "0",
        "jump": "1",
        "magatsuhi": "1",
        "magatsuhi_chain": "1",
        "itemhacks": "stockpile",
        "autosave": "7",
        "shop_consumables": "free",
        "shop_growth": "immediate",
    }
    selection = state.selection_from(features)
    assert selection.mods["essences"] is True
    assert selection.mods["heal"] is False
    assert selection.magatsuhi == "chain"
    assert selection.item_hacks == "stockpile"
    assert selection.autosave == 7
    assert selection.shop["consumables"] == "free"
    assert selection.shop["growth"] == "immediate"
    assert selection.shop["misc"] == "default"


def test_legacy_shop_flag_means_growth_immediate():
    selection = state.selection_from({"shop": "1"})
    assert selection.shop["growth"] == "immediate"


def test_battle_magatsuhi_when_chain_bit_is_absent():
    assert state.selection_from({"magatsuhi": "1"}).magatsuhi == "battle"
    assert state.selection_from({}).magatsuhi == "none"


def test_flags_for_a_full_selection():
    selection = state.Selection(
        mods={"essences": True, "heal": False},
        item_hacks="stockpile",
        magatsuhi="chain",
        autosave=3,
    )
    flags = selection.flags()
    assert "--no-heal" in flags
    assert "--no-essences" not in flags
    assert "--stockpile" in flags
    assert "--magatsuhi-chain" in flags
    assert "--no-magatsuhi" not in flags
    assert flags[flags.index("--autosave-slot") + 1] == "3"


def test_flags_for_no_item_hack_and_no_magatsuhi():
    flags = state.Selection(item_hacks="none", magatsuhi="none").flags()
    assert "--no-refill" in flags
    assert "--no-magatsuhi" in flags


def test_leylines_uses_its_own_flag():
    flags = state.Selection(mods={"leylines": True}).flags()
    assert "--leylines" in flags
    assert "--no-leylines" not in flags


def test_selection_counts_one_per_group():
    selection = state.Selection(
        mods={"essences": True, "heal": True},
        item_hacks="refill",
        magatsuhi="battle",
        autosave=1,
        shop={
            "consumables": "free",
            "growth": "default",
            "essences": "default",
            "misc": "default",
        },
    )
    # two mods, item hack, Magatsuhi, autosave, one shop group
    assert selection.count() == 6


def test_autosave_choice_accepts_slots_and_off():
    assert state.autosave_choice("", 3) == "keep"
    assert state.autosave_choice("n", 3) is None
    assert state.autosave_choice("12", None) == 12
    assert state.autosave_choice("21", None) == "invalid"
    assert state.autosave_choice("abc", None) == "invalid"


def test_total_matches_the_catalogue_groups(monkeypatch):
    expected = len(state.PATCH_MODS) + 4
    monkeypatch.setattr(state.os, "name", "posix")
    assert state.total_mods() == expected


def test_missing_features_file_is_empty(tmp_path):
    assert state.read_features(tmp_path / "Freeplay.features") == {}
