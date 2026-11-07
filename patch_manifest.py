# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Central table of patch verification sites and feature data paks.

The patcher uses this after writing the executable: every entry here is
re-read and must differ from its original bytes. Feature keys match the
installer's catalogue and the feature record.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

import autosave
import boot_pak
import estoma
import gameplay_patches as gp
import leylines
import newborn
import quest_pak
import reveal
import shop_pak
import signatures
import stockpile

MIRACLE_PAK = "pakchunk99_NGPlusMiracles_P.pak"
LEGACY_MAP_PAK = "pakchunk95_FreeplayMap_P.pak"  # removed Timed Quest Markers


def _patcher():
    import patch_smtvv_freeplay as patcher

    return patcher


def _off_sites(offset: int, original: bytes) -> list[tuple[int, int]]:
    return [(offset, len(original))]


def _resolved_off(data, offset: int, original: bytes) -> list[tuple[int, int]]:
    resolved = signatures.resolve(data, offset, original)
    return [(resolved if resolved is not None else offset, len(original))]


def _resolved_va(data, address: int, original: bytes) -> list[tuple[int, int]]:
    offset = gp.off(address)
    resolved = signatures.resolve(data, offset, original)
    return [(resolved if resolved is not None else offset, len(original))]


def _nextstep_sites() -> list[tuple[int, int]]:
    return [(gp.off(thunk), 5) for thunk in gp.SETNEXTSTEP_THUNKS]


def _essences_sites(data) -> list[tuple[int, int]]:
    p = _patcher()
    return _off_sites(p.TRAMP_OFFSET, p.TRAMP_ORIG)


def _heal_sites(data) -> list[tuple[int, int]]:
    p = _patcher()
    return _off_sites(p.RYUKETSU_TRAMP_OFFSET, p.RYUKETSU_TRAMP_ORIG)


def _miman_sites(data) -> list[tuple[int, int]]:
    p = _patcher()
    return _resolved_off(data, p.MIMAN_POS_CHECK_OFFSET, p.MIMAN_POS_CHECK_ORIG)


def _leyline_sites(data) -> list[tuple[int, int]]:
    return _resolved_va(data, leylines.POI_VISIBLE_SITE, leylines.POI_VISIBLE_ORIG)


def _miracle_sites(data) -> list[tuple[int, int]]:
    p = _patcher()
    return (
        _off_sites(p.MIRACLE_ADDED_TRAMP, p.MIRACLE_ADDED_ORIG)
        + _off_sites(p.MIRACLE_STATE_TRAMP, p.MIRACLE_STATE_ORIG)
        + _off_sites(p.MIRACLE_666_NOP_ADDR, p.MIRACLE_666_ORIG)
    )


def _compendium_sites(data) -> list[tuple[int, int]]:
    p = _patcher()
    return _resolved_off(data, p.DEVIL_COST_OFFSET, p.DEVIL_COST_ORIG)


def _refill_sites(data) -> list[tuple[int, int]]:
    return _nextstep_sites()


def _stockpile_sites(data) -> list[tuple[int, int]]:
    return (
        _nextstep_sites()
        + _resolved_va(data, gp.ITEM_GET_MAX, gp.ITEM_GET_MAX_ORIG)
        + _resolved_va(data, gp.ITEM_GET_NUM, gp.ITEM_GET_NUM_ORIG)
        + [
            (gp.off(thunk), len(stockpile.MAX_THUNK_ORIG))
            for thunk in stockpile.MAX_THUNKS
        ]
    )


def _stockpile_dynamic(data) -> list[tuple[int, int]]:
    return [
        (stockpile._file_off(data, slot), 8) for slot, _thunk in stockpile.MAX_SLOTS
    ]


def _jump_sites(data) -> list[tuple[int, int]]:
    return [
        site
        for address, original in gp.JUMP_SITES
        for site in _resolved_va(data, address, original)
    ]


def _magatsuhi_sites(data) -> list[tuple[int, int]]:
    return _nextstep_sites()


def _refresh_sites(data) -> list[tuple[int, int]]:
    return _nextstep_sites()


def _intro_sites(data) -> list[tuple[int, int]]:
    return _resolved_va(data, gp.TITLE_TICK_IMPL, gp.TITLE_TICK_ORIG)


def _newborn_sites(data) -> list[tuple[int, int]]:
    return [(gp.off(newborn.RENEWAL_JMP), 5)]


def _autosave_sites(data) -> list[tuple[int, int]]:
    return _nextstep_sites() + [
        (gp.off(autosave.FIELD_TICK_SITE), 5),
        (gp.off(autosave.SAVE_BUILD_SITE), 5),
    ]


@dataclass(frozen=True)
class Feature:
    """One patch feature: its flag, patch entry point, sites and data pak."""

    key: str
    label: str
    flags: tuple[str, ...]
    apply: str
    sites: Callable[[bytes | bytearray], list[tuple[int, int]]] | None = None
    dynamic: Callable[[bytes | bytearray], list[tuple[int, int]]] | None = None
    pak: str | None = None


FEATURES = (
    Feature(
        "essences",
        "Reusable Essences",
        ("--no-essences",),
        "patcher:essences",
        _essences_sites,
    ),
    Feature("heal", "Leyline Auto-Heal", ("--no-heal",), "patcher:heal", _heal_sites),
    Feature("mimans", "Miman Reveal", ("--no-mimans",), "patcher:mimans", _miman_sites),
    Feature(
        "leylines",
        "Leyline Founts on Map",
        ("--leylines", "--reveal"),
        "leylines.patch_leylines",
        _leyline_sites,
    ),
    Feature(
        "miracles",
        "NG+ Miracles",
        ("--no-miracles",),
        "patcher:miracles",
        _miracle_sites,
        pak=MIRACLE_PAK,
    ),
    Feature(
        "compendium",
        "Free Compendium",
        ("--no-compendium",),
        "patcher:compendium",
        _compendium_sites,
    ),
    Feature(
        "refill",
        "Battle Refill",
        ("--no-refill",),
        "gameplay_patches.patch_refill",
        _refill_sites,
    ),
    Feature(
        "stockpile",
        "Stockpile",
        ("--stockpile",),
        "stockpile.patch_stockpile",
        _stockpile_sites,
        _stockpile_dynamic,
        stockpile.STOCK_PAK,
    ),
    Feature(
        "jump",
        "Superjump",
        ("--no-jump",),
        "gameplay_patches.patch_jump",
        _jump_sites,
    ),
    Feature(
        "magatsuhi",
        "Full Magatsuhi",
        ("--no-magatsuhi", "--magatsuhi-chain"),
        "gameplay_patches.patch_magatsuhi",
        _magatsuhi_sites,
    ),
    Feature(
        "refresh",
        "Party Refresh",
        ("--refresh",),
        "gameplay_patches.patch_party_refresh",
        _refresh_sites,
    ),
    Feature(
        "shop",
        "Shop stock",
        (
            "--no-shop",
            "--shop-consumables",
            "--shop-growth",
            "--shop-essences",
            "--shop-misc",
        ),
        "shop_pak.build_shop_pak",
        pak=shop_pak.SHOP_PAK,
    ),
    Feature(
        "intro",
        "Skip Intro",
        ("--no-intro",),
        "gameplay_patches.patch_refocus",
        _intro_sites,
        pak=boot_pak.BOOT_PAK,
    ),
    Feature(
        "masakado",
        "Masakado Unlock",
        ("--no-masakado",),
        "quest_pak.build_quest_pak",
        pak=quest_pak.QUEST_PAK,
    ),
    Feature(
        "newborn",
        "Newborn Clears Compendium",
        ("--no-newborn",),
        "newborn.patch_newborn",
        _newborn_sites,
        pak=newborn.NEWBORN_PAK,
    ),
    Feature(
        "estoma",
        "Free Estoma",
        ("--no-estoma",),
        "estoma.build_estoma_pak",
        pak=estoma.ESTOMA_PAK,
    ),
    Feature(
        "reveal",
        "Map Reveal",
        ("--reveal",),
        "reveal.build_reveal_pak",
        pak=reveal.REVEAL_PAK,
    ),
    Feature(
        "autosave",
        "Autosave after battle",
        ("--autosave-slot",),
        "autosave.patch_autosave",
        _autosave_sites,
    ),
)

FEATURE_KEYS = tuple(feature.key for feature in FEATURES)

# (feature key, data pak) written by the patcher when the feature is enabled.
FEATURE_PAKS = tuple(
    (feature.key, feature.pak) for feature in FEATURES if feature.pak is not None
)

# Substrings that must appear in `repak list` for each generated pak.
PAK_ENTRIES = {
    "miracles": ("GodParameterDataTable",),
    "stockpile": ("WB_CampItemList",),
    "shop": ("ShopTable",),
    "intro": ("Logo",),
    "masakado": ("MM_M063_EM2170",),
    "newborn": ("InheritMessage",),
    "estoma": ("BP_EstomaData",),
    "reveal": ("Minimap",),
}


def validate_pak(repak: str, pak_path: str, feature: str) -> list[str]:
    """Check that a built pak opens and contains the expected asset."""
    expected = PAK_ENTRIES.get(feature, ())
    if not expected:
        return []
    name = os.path.basename(pak_path)
    result = subprocess.run(
        [repak, "list", pak_path], check=False, capture_output=True, text=True
    )
    if result.returncode != 0:
        return [f"{feature}: repak cannot list {name}"]
    listing = result.stdout
    return [
        f"{feature}: {name} lacks '{entry}'"
        for entry in expected
        if entry not in listing
    ]


STATIC_FEATURES = tuple(
    feature.key for feature in FEATURES if feature.sites is not None
)


def static_sites(data: bytes | bytearray) -> dict[str, list[tuple[int, int, bytes]]]:
    """(offset, length, original) for every signature site in the registry."""
    sites: dict[str, list[tuple[int, int, bytes]]] = {}
    for feature in FEATURES:
        if feature.sites is None:
            continue
        entries = feature.sites(data)
        if entries:
            sites[feature.key] = [
                (offset, length, bytes(data[offset : offset + length]))
                for offset, length in entries
            ]
    return sites


def verification_sites(
    data: bytes | bytearray,
) -> dict[str, list[tuple[int, int, bytes]]]:
    """Every site a feature changes, including the dynamic table slots."""
    sites = static_sites(data)
    for feature in FEATURES:
        if feature.dynamic is None:
            continue
        for offset, length in feature.dynamic(data):
            sites.setdefault(feature.key, []).append(
                (offset, length, bytes(data[offset : offset + length]))
            )
    return sites


def _relocate_off(data, module, name: str, original: bytes, label: str, notes):
    """Resolve a file-offset site and write it back to the module."""
    known = getattr(module, name)
    resolved = signatures.resolve(data, known, original)
    if resolved is None:
        notes.append(f"{label}: signature not unique or missing")
        return False
    setattr(module, name, resolved)
    return True


def _relocate_va(data, module, name: str, original: bytes, label: str, notes):
    """Resolve a VA site and write the new VA back to the module."""
    known = getattr(module, name)
    resolved = signatures.resolve(data, gp.off(known), original)
    if resolved is None:
        notes.append(f"{label}: signature not unique or missing")
        return False
    setattr(module, name, gp.va(resolved))
    return True


def _relocate_va_list(data, module, name: str, original: bytes, label: str, notes):
    """Resolve every VA in a list, updating the list in place so aliases see it."""
    entries = getattr(module, name)
    moved = []
    ok = True
    for known in entries:
        resolved = signatures.resolve(data, gp.off(known), original)
        if resolved is None:
            notes.append(f"{label}: signature not unique or missing")
            moved.append(known)
            ok = False
        else:
            moved.append(gp.va(resolved))
    entries[:] = moved
    return ok


def _derive_target(data, module, site_name: str, target_name: str) -> None:
    """Point a call/jump target at the address the resolved site now reaches."""
    site = getattr(module, site_name)
    disp = int.from_bytes(
        bytes(data[gp.off(site) + 1 : gp.off(site) + 5]), "little", signed=True
    )
    setattr(module, target_name, site + 5 + disp)


def relocate(data: bytes | bytearray) -> list[str]:
    """Resolve every remaining patch site by its unique signature.

    Sites that still match their known offset keep it. When a site has moved,
    its module constant (and every imported alias that caches the value) is
    rewritten before verification and patching run. Ambiguous or missing
    signatures are left at their known address so the feature's own guard can
    fail safely. Returns human-readable notes for unresolved sites.
    """
    import patch_smtvv_freeplay as patcher

    notes: list[str] = []

    # File-offset sites in the main patcher.
    _relocate_off(data, patcher, "TRAMP_OFFSET", patcher.TRAMP_ORIG, "essences", notes)
    _relocate_off(
        data,
        patcher,
        "RYUKETSU_TRAMP_OFFSET",
        patcher.RYUKETSU_TRAMP_ORIG,
        "heal",
        notes,
    )
    _relocate_va(
        data,
        patcher,
        "PARTY_ALL_CURE_VA",
        patcher.PARTY_ALL_CURE_ORIG,
        "heal.party_all_cure",
        notes,
    )
    _relocate_off(
        data,
        patcher,
        "MIRACLE_ADDED_TRAMP",
        patcher.MIRACLE_ADDED_ORIG,
        "miracles.added",
        notes,
    )
    _relocate_off(
        data,
        patcher,
        "MIRACLE_STATE_TRAMP",
        patcher.MIRACLE_STATE_ORIG,
        "miracles.state",
        notes,
    )
    _relocate_off(
        data,
        patcher,
        "MIRACLE_666_NOP_ADDR",
        patcher.MIRACLE_666_ORIG,
        "miracles.nop666",
        notes,
    )

    # Shared item helpers and the SetNextStep thunk (also used by stockpile and
    # autosave through the same list object).
    _relocate_va_list(
        data, gp, "SETNEXTSTEP_THUNKS", gp.SETNEXTSTEP_ORIG, "setnextstep", notes
    )
    for name, original in (
        ("ITEM_GET", gp.ITEM_GET_ORIG),
        ("ITEM_GET_MAX", gp.ITEM_GET_MAX_ORIG),
        ("ITEM_GET_NUM", gp.ITEM_GET_NUM_ORIG),
        ("ITEM_IS_GOTTEN", gp.ITEM_IS_GOTTEN_ORIG),
    ):
        _relocate_va(data, gp, name, original, name.lower(), notes)

    # stockpile imports the item helpers by name; keep its aliases in sync.
    stockpile.ITEM_GET_MAX = gp.ITEM_GET_MAX
    stockpile.ITEM_GET_NUM = gp.ITEM_GET_NUM
    _relocate_va_list(
        data,
        stockpile,
        "MAX_THUNKS",
        stockpile.MAX_THUNK_ORIG,
        "stockpile.max_thunks",
        notes,
    )

    # Autosave sites and the functions its hooks call.
    if _relocate_va(
        data,
        autosave,
        "SAVE_BUILD_SITE",
        autosave.SAVE_BUILD_ORIG,
        "autosave.save_build",
        notes,
    ):
        _derive_target(data, autosave, "SAVE_BUILD_SITE", "SAVE_BUILD_FN")
    _relocate_va(
        data,
        autosave,
        "GAME_INSTANCE",
        autosave.GAME_INSTANCE_ORIG,
        "autosave.game_instance",
        notes,
    )
    _relocate_va(
        data,
        autosave,
        "CURRENT_LANGUAGE",
        autosave.CURRENT_LANGUAGE_ORIG,
        "autosave.current_language",
        notes,
    )
    _relocate_va(
        data,
        autosave,
        "SAVE_SLOT_NATIVE",
        autosave.SAVE_SLOT_ORIG,
        "autosave.save_slot",
        notes,
    )
    # FIELD_TICK_ORIG is not unique (the same call shape recurs), so this stays
    # a guard-only site that fails safely if a game update moves it.
    if _relocate_va(
        data,
        autosave,
        "FIELD_TICK_SITE",
        autosave.FIELD_TICK_ORIG,
        "autosave.field_tick",
        notes,
    ):
        _derive_target(data, autosave, "FIELD_TICK_SITE", "FIELD_TICK_FN")

    # Newborn: the entry thunk and the compendium reset it calls.
    if _relocate_va(
        data,
        newborn,
        "RENEWAL_JMP",
        newborn.RENEWAL_JMP_ORIG,
        "newborn.renewal_jmp",
        notes,
    ):
        _derive_target(data, newborn, "RENEWAL_JMP", "RENEWAL_IMPL")
    _relocate_va(
        data,
        newborn,
        "BOOK_RESET",
        newborn.BOOK_RESET_ORIG,
        "newborn.book_reset",
        notes,
    )
    return notes
