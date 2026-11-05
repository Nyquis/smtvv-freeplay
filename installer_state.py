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
    "This lets you fly over triggers the game needs to advance, and they are "
    "not always marked. If events stop triggering after flying, walk back; "
    "you probably missed an earlier one."
)
INTRO_WARNING = (
    "Controller input sometimes stalls on launch with this enabled. Tab out "
    "and in, or open and close the Steam overlay, to restore control."
)
HAPTICS_WARNING = (
    "Haptics need a wired DualSense, or DSX with a wireless one. The panel is "
    "DualSenseHaptics\\SMTVHaptics.exe in the game's Win64 folder."
)


@dataclass(frozen=True)
class Mod:
    key: str
    label: str
    detail: str
    on_flag: str = ""
    off_flag: str = ""
    warning: str = ""
    windows_only: bool = False
    patched: bool = True


MODS = (
    Mod(
        "essences",
        "Reusable Essences",
        "Essences are not consumed.",
        "",
        "--no-essences",
    ),
    Mod("heal", "Leyline Auto-Heal", "Full HP/MP on leyline use.", "", "--no-heal"),
    Mod(
        "mimans", "Miman Reveal", "Miman positions shown on the map.", "", "--no-mimans"
    ),
    Mod(
        "leylines",
        "Leyline Founts on Map",
        "Founts visible through fog.",
        "--leylines",
        "",
    ),
    Mod("miracles", "NG+ Miracles", "Unlock NG+ miracles early.", "", "--no-miracles"),
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
        "Hold jump to rise; faster air control.",
        "",
        "--no-jump",
        warning=JUMP_WARNING,
    ),
    Mod(
        "estoma", "Free Estoma", "Estoma Barrier costs no Magatsuhi.", "", "--no-estoma"
    ),
    Mod(
        "intro",
        "Skip Intro",
        "No logos or opening movie; boot to title.",
        "",
        "--no-intro",
        warning=INTRO_WARNING,
    ),
    Mod(
        "masakado",
        "Masakado Unlock",
        "Powered-up Masakado without the Kiou Sword.",
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
        "Haptic effects for battles, skills and menus.",
        warning=HAPTICS_WARNING,
        windows_only=True,
        patched=False,
    ),
)

PATCH_MODS = tuple(mod for mod in MODS if mod.patched)

MAGATSUHI_MODES = ("none", "battle", "chain")
ITEM_HACKS = ("none", "refill", "stockpile")


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
            if mod.key == "magatsuhi":
                continue
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
        return (
            sum(
                1
                for mod in PATCH_MODS
                if mod.key != "magatsuhi" and self.mods.get(mod.key)
            )
            + (1 if self.magatsuhi != "none" else 0)
            + (1 if self.item_hacks != "none" else 0)
            + (1 if self.autosave is not None else 0)
            + (1 if any(mode != "default" for mode in self.shop.values()) else 0)
            + (1 if self.haptics else 0)
        )


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
