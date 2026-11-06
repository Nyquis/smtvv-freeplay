"""Central table of patch verification sites and feature data paks.

The patcher uses this after writing the executable: every entry here is
re-read and must differ from its original bytes. Feature keys match the
installer's catalogue and the feature record.
"""

from __future__ import annotations

import os
import subprocess

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

# (feature key, data pak) written by the patcher when the feature is enabled.
FEATURE_PAKS = (
    ("miracles", MIRACLE_PAK),
    ("stockpile", stockpile.STOCK_PAK),
    ("shop", shop_pak.SHOP_PAK),
    ("intro", boot_pak.BOOT_PAK),
    ("masakado", quest_pak.QUEST_PAK),
    ("newborn", newborn.NEWBORN_PAK),
    ("estoma", estoma.ESTOMA_PAK),
    ("reveal", reveal.REVEAL_PAK),
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


STATIC_FEATURES = (
    "essences",
    "heal",
    "mimans",
    "leylines",
    "miracles",
    "compendium",
    "refill",
    "stockpile",
    "jump",
    "magatsuhi",
    "intro",
    "newborn",
    "autosave",
)


def static_sites(data: bytes | bytearray) -> dict[str, list[tuple[int, int, bytes]]]:
    """(offset, length, original) for every site except the dynamic slots."""
    import patch_smtvv_freeplay as patcher

    sites: dict[str, list[tuple[int, int, bytes]]] = {}

    def add(feature: str, offset: int, length: int) -> None:
        sites.setdefault(feature, []).append(
            (offset, length, bytes(data[offset : offset + length]))
        )

    add("essences", patcher.TRAMP_OFFSET, len(patcher.TRAMP_ORIG))
    add("heal", patcher.RYUKETSU_TRAMP_OFFSET, len(patcher.RYUKETSU_TRAMP_ORIG))
    mimans = signatures.resolve(
        data, patcher.MIMAN_POS_CHECK_OFFSET, patcher.MIMAN_POS_CHECK_ORIG
    )
    add(
        "mimans",
        mimans if mimans is not None else patcher.MIMAN_POS_CHECK_OFFSET,
        len(patcher.MIMAN_POS_CHECK_ORIG),
    )
    leyline_offset = signatures.resolve(
        data, gp.off(leylines.POI_VISIBLE_SITE), leylines.POI_VISIBLE_ORIG
    )
    add(
        "leylines",
        leyline_offset
        if leyline_offset is not None
        else gp.off(leylines.POI_VISIBLE_SITE),
        len(leylines.POI_VISIBLE_ORIG),
    )
    add("miracles", patcher.MIRACLE_ADDED_TRAMP, len(patcher.MIRACLE_ADDED_ORIG))
    add("miracles", patcher.MIRACLE_STATE_TRAMP, len(patcher.MIRACLE_STATE_ORIG))
    add("miracles", patcher.MIRACLE_666_NOP_ADDR, 6)
    compendium = signatures.resolve(
        data, patcher.DEVIL_COST_OFFSET, patcher.DEVIL_COST_ORIG
    )
    add(
        "compendium",
        compendium if compendium is not None else patcher.DEVIL_COST_OFFSET,
        len(patcher.DEVIL_COST_ORIG),
    )

    for thunk in gp.SETNEXTSTEP_THUNKS:
        offset = gp.off(thunk)
        for feature in ("refill", "stockpile", "magatsuhi", "autosave"):
            add(feature, offset, 5)
    for function, original in (
        (gp.ITEM_GET, gp.ITEM_GET_ORIG),
        (gp.ITEM_GET_MAX, gp.ITEM_GET_MAX_ORIG),
        (gp.ITEM_GET_NUM, gp.ITEM_GET_NUM_ORIG),
        (gp.ITEM_IS_GOTTEN, gp.ITEM_IS_GOTTEN_ORIG),
    ):
        add("refill", gp.off(function), len(original))
    for function, original in (
        (gp.ITEM_GET_MAX, gp.ITEM_GET_MAX_ORIG),
        (gp.ITEM_GET_NUM, gp.ITEM_GET_NUM_ORIG),
    ):
        add("stockpile", gp.off(function), len(original))
    for thunk in stockpile.MAX_THUNKS:
        add("stockpile", gp.off(thunk), len(stockpile.MAX_THUNK_ORIG))

    for site, original in gp.JUMP_SITES:
        resolved = signatures.resolve(data, gp.off(site), original)
        add(
            "jump",
            resolved if resolved is not None else gp.off(site),
            len(original),
        )

    intro_offset = signatures.resolve(
        data, gp.off(gp.TITLE_TICK_IMPL), gp.TITLE_TICK_ORIG
    )
    add(
        "intro",
        intro_offset if intro_offset is not None else gp.off(gp.TITLE_TICK_IMPL),
        len(gp.TITLE_TICK_ORIG),
    )
    add("newborn", gp.off(newborn.RENEWAL_JMP), 5)
    add("autosave", gp.off(autosave.FIELD_TICK_SITE), 5)
    add("autosave", gp.off(autosave.SAVE_BUILD_SITE), 5)
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
