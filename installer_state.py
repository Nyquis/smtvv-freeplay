"""Mod catalogue, install state and patcher flags for the Freeplay installer."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

EXE = "SMT5V-Win64-Shipping.exe"
BIN_PARTS = ("Project", "Binaries", "Win64")
PAKS_PARTS = ("Project", "Content", "Paks")
FEATURES = "Freeplay.features"
SHOP_CATEGORIES = ("consumables", "growth", "essences", "misc")
SHOP_MODES = ("default", "free", "immediate")
AUTOSAVE_MIN = 1
AUTOSAVE_MAX = 20

JUMP_WARNING = (
    "This can fly over triggers the game needs to advance, and they are not "
    "always marked. If events stop triggering after flying, walk back; you "
    "probably missed an earlier one."
)
INTRO_WARNING = (
    "Controller input sometimes stalls on launch. Tab out and in, or open and "
    "close the Steam overlay, to restore control."
)
HAPTICS_WARNING = (
    "Needs a wired DualSense, or DSX with a wireless one. The panel is "
    "DualSenseHaptics\\SMTVHaptics.exe in the game's Win64 folder."
)


@dataclass(frozen=True)
class Mod:
    key: str
    label: str
    description: str
    on_flag: str = ""
    off_flag: str = ""
    warning: str = ""
    windows_only: bool = False
    patched: bool = True


MODS = (
    Mod(
        "essences",
        "Reusable Essences",
        "Essences are not consumed when you use them.",
        "",
        "--no-essences",
    ),
    Mod(
        "heal",
        "Leyline Auto-Heal",
        "Using a leyline fount restores the party's full HP and MP.",
        "",
        "--no-heal",
    ),
    Mod(
        "mimans",
        "Miman Reveal",
        "All miman positions are shown on the map, including ones you have "
        "not found yet.",
        "",
        "--no-mimans",
    ),
    Mod(
        "leylines",
        "Leyline Founts on Map",
        "Leyline fount icons are drawn through unexplored fog on the main map.",
        "--leylines",
        "",
    ),
    Mod(
        "miracles",
        "NG+ Miracles",
        "NG+ miracles are unlocked from the start.",
        "",
        "--no-miracles",
    ),
    Mod(
        "compendium",
        "Free Compendium",
        "Compendium summons cost nothing.",
        "",
        "--no-compendium",
    ),
    Mod(
        "jump",
        "Superjump",
        "Hold jump to keep rising, with faster air control.",
        "",
        "--no-jump",
        warning=JUMP_WARNING,
    ),
    Mod(
        "estoma",
        "Free Estoma",
        "The Estoma Barrier costs no Magatsuhi, including its moon-phase upkeep.",
        "",
        "--no-estoma",
    ),
    Mod(
        "intro",
        "Skip Intro",
        "Skips the logos, opening movie and title prompt.",
        "",
        "--no-intro",
        warning=INTRO_WARNING,
    ),
    Mod(
        "masakado",
        "Masakado Unlock",
        "The powered-up Masakado fight is available without the Kiou Sword.",
        "",
        "--no-masakado",
    ),
    Mod(
        "newborn",
        "Newborn Clears Compendium",
        "NG+ Newborn starts with an empty compendium.",
        "",
        "--no-newborn",
    ),
    Mod(
        "haptics",
        "DualSense Haptics",
        "DualSense haptics for battles, skills, field actions and menus.",
        warning=HAPTICS_WARNING,
        windows_only=True,
        patched=False,
    ),
)

PATCH_MODS = tuple(mod for mod in MODS if mod.patched)

MAGATSUHI_MODES = ("none", "battle", "chain")
ITEM_HACKS = ("none", "refill", "stockpile")

ITEM_LABELS = {"refill": "Battle Refill", "stockpile": "Stockpile", "none": "Neither"}
MAGATSUHI_LABELS = {
    "none": "Game default",
    "battle": "Every battle",
    "chain": "Once per chain",
}
SHOP_LABELS = {
    "default": "Game default",
    "free": "Free, default timing",
    "immediate": "Free and immediate",
}
SHOP_CATEGORY_LABELS = {
    "consumables": "Consumables",
    "growth": "Growth items",
    "essences": "Essences (buy price)",
    "misc": "Misc items",
}


@dataclass
class Selection:
    mods: dict[str, bool] = field(default_factory=dict)
    item_hacks: str = "none"
    magatsuhi: str = "none"
    shop: dict[str, str] = field(
        default_factory=lambda: {category: "default" for category in SHOP_CATEGORIES}
    )
    autosave: int | None = None
    haptics: bool = False

    def flags(self) -> list[str]:
        """Patcher flags for this selection."""
        out: list[str] = []
        for mod in PATCH_MODS:
            if self.mods.get(mod.key):
                if mod.on_flag:
                    out.append(mod.on_flag)
            elif mod.off_flag:
                out.append(mod.off_flag)
        if self.magatsuhi == "none":
            out.append("--no-magatsuhi")
        elif self.magatsuhi == "chain":
            out.append("--magatsuhi-chain")
        if self.item_hacks == "stockpile":
            out.append("--stockpile")
        elif self.item_hacks == "none":
            out.append("--no-refill")
        for category in SHOP_CATEGORIES:
            out.extend((f"--shop-{category}", self.shop[category]))
        if self.autosave is not None:
            out.extend(("--autosave-slot", str(self.autosave)))
        return out

    def count(self) -> int:
        """How many mods this selection installs."""
        mods = sum(1 for mod in PATCH_MODS if self.mods.get(mod.key))
        return (
            mods
            + (1 if self.magatsuhi != "none" else 0)
            + (1 if self.item_hacks != "none" else 0)
            + (1 if self.autosave is not None else 0)
            + (1 if any(mode != "default" for mode in self.shop.values()) else 0)
            + (1 if self.haptics else 0)
        )


def _action(before, after) -> str:
    if after == before:
        return "keep" if after not in (None, "none", False) else "none"
    if after in (None, "none", False):
        return "remove"
    if before in (None, "none", False):
        return "install"
    return "change"


@dataclass(frozen=True)
class Change:
    label: str
    action: str


def diff_selection(before: Selection, after: Selection) -> list[Change]:
    """What the review screen shows, relative to the installed state."""
    rows: list[Change] = []
    for mod in PATCH_MODS:
        was = bool(before.mods.get(mod.key))
        now = bool(after.mods.get(mod.key))
        if now:
            rows.append(Change(mod.label, "keep" if was else "install"))
        elif was:
            rows.append(Change(mod.label, "remove"))

    if after.magatsuhi != "none" or before.magatsuhi != "none":
        rows.append(
            Change(
                f"Full Magatsuhi: {MAGATSUHI_LABELS[after.magatsuhi]}",
                _action(before.magatsuhi, after.magatsuhi),
            )
        )
    if after.item_hacks != "none" or before.item_hacks != "none":
        rows.append(
            Change(
                f"Item Hacks: {ITEM_LABELS[after.item_hacks]}",
                _action(before.item_hacks, after.item_hacks),
            )
        )
    if after.autosave is not None or before.autosave is not None:
        label = (
            "Autosave after battle: off"
            if after.autosave is None
            else f"Autosave after battle: slot {after.autosave}"
        )
        rows.append(Change(label, _action(before.autosave, after.autosave)))
    for category in SHOP_CATEGORIES:
        if (
            before.shop[category] != after.shop[category]
            or after.shop[category] != "default"
        ):
            rows.append(
                Change(
                    f"Shop {category}: {SHOP_LABELS[after.shop[category]]}",
                    _action(before.shop[category], after.shop[category]),
                )
            )
    if after.haptics or before.haptics:
        rows.append(Change("DualSense Haptics", _action(before.haptics, after.haptics)))
    return [row for row in rows if row.action != "none"]


def count_actions(changes: list[Change]) -> dict[str, int]:
    counts = {"install": 0, "change": 0, "remove": 0, "keep": 0}
    for change in changes:
        counts[change.action] += 1
    return counts


def read_features(path: str | os.PathLike[str]) -> dict[str, str]:
    """Parse Freeplay.features; missing files give an empty mapping."""
    values: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                key, sep, value = line.rstrip("\r\n").partition("=")
                if sep and key:
                    values[key.strip()] = value.strip()
    except OSError:
        return {}
    return values


def selection_from(features: dict[str, str]) -> Selection:
    """Rebuild the selection recorded by a previous install."""
    selection = Selection()
    for mod in PATCH_MODS:
        selection.mods[mod.key] = features.get(mod.key) == "1"
    hacks = features.get("itemhacks", "none")
    selection.item_hacks = hacks if hacks in ITEM_HACKS else "none"
    if features.get("magatsuhi") == "1":
        selection.magatsuhi = (
            "chain" if features.get("magatsuhi_chain") == "1" else "battle"
        )
    for category in SHOP_CATEGORIES:
        mode = features.get(f"shop_{category}", "default")
        selection.shop[category] = mode if mode in SHOP_MODES else "default"
    if features.get("shop") == "1":
        selection.shop["growth"] = "immediate"
    try:
        slot = int(features.get("autosave", "0"))
    except ValueError:
        slot = 0
    if AUTOSAVE_MIN <= slot <= AUTOSAVE_MAX:
        selection.autosave = slot
    selection.haptics = features.get("haptics") == "1"
    return selection


def total_mods() -> int:
    """Selectable mod entries: patch mods, Magatsuhi, item hack, autosave, shop."""
    return len(PATCH_MODS) + 4 + (1 if os.name == "nt" else 0)


def autosave_choice(text: str, current: int | None) -> int | None | str:
    """Parse an autosave answer: a slot, None for off, or 'keep' for blank."""
    text = text.strip()
    if not text:
        return "keep"
    if text.lower() in ("n", "no", "off", "0"):
        return None
    if text.isdigit() and AUTOSAVE_MIN <= int(text) <= AUTOSAVE_MAX:
        return int(text)
    return "invalid"


_VERSION_RE = re.compile(r'MOD_VERSION = "([^"]+)"')


def mod_version(path: str | os.PathLike[str]) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            match = _VERSION_RE.search(fh.read())
    except OSError:
        return "unknown"
    return match.group(1) if match else "unknown"
