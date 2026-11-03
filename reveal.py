"""
Map Reveal: show treasure and leyline icons across the map.

Each area has a DataTable (``MinimapIcon_*``) whose rows describe a map icon:
``POIType`` (treasure, leyline, ...) and a ``ShowFar`` BoolProperty. Setting
``ShowFar`` makes the icon visible at a distance.

Fog-of-war is deliberately left alone: only ``ShowFar`` is changed, so icons in
unexplored areas stay hidden.

The tables are extracted from the player's own pakchunk0, edited, and repacked
as a small override pak.
"""

from __future__ import annotations

import os
import shutil
import struct
import tempfile

import ue_asset

REVEAL_PAK = "pakchunk91_FreeplayReveal_P.pak"
MINIMAP_PREFIX = "Project/Content/Blueprints/Gamedata/BinTable/Minimap/MinimapIcon_"
POI_TREASURE = "E_MINIMAP_POI_TYPE_TREASURE"
POI_RYUKETSU = "E_MINIMAP_POI_TYPE_RYUKETSU"
MODES = ("none", "treasures", "leylines", "both")
TARGETS = {
    "treasures": {POI_TREASURE},
    "leylines": {POI_RYUKETSU},
    "both": {POI_TREASURE, POI_RYUKETSU},
}


def normalize_mode(mode: str | None) -> str:
    mode = mode or "none"
    if mode not in MODES:
        raise RuntimeError(f"unknown map reveal mode: {mode}")
    return mode


def _walk(pkg, pos: int, end: int, out: list) -> int:
    """Collect tags, including the byte position of BoolProperty values."""
    data = pkg.e
    while True:
        name = pkg.name_of(data, pos)
        pos += 8
        if name == "None":
            return pos
        typ = pkg.name_of(data, pos)
        size_at = pos + 8
        size = struct.unpack_from("<i", data, size_at)[0]
        pos += 16
        bool_pos = None
        if typ == "StructProperty":
            pos += 24
        elif typ == "BoolProperty":
            bool_pos = pos
            pos += 1
        elif typ in ("ByteProperty", "EnumProperty", "ArrayProperty", "SetProperty"):
            pos += 8
        elif typ == "MapProperty":
            pos += 16
        if data[pos]:
            pos += 16
        pos += 1
        start = pos
        out.append((name, typ, start, size, bool_pos))
        pos = start + size


def reveal_tags(tags, data, name_of, targets: set[str]) -> bool:
    """Flip ShowFar for one row if it matches; returns whether it changed."""
    fields = {}
    for name, _typ, start, _size, bool_pos in tags:
        if name in ("POIType", "ShowFar"):
            fields[name] = (start, bool_pos)
    if "POIType" not in fields or "ShowFar" not in fields:
        return False
    poi_at, _ = fields["POIType"]
    _show_at, bool_pos = fields["ShowFar"]
    if bool_pos is None or data[bool_pos]:
        return False
    poi = name_of(data, poi_at).rsplit("::", 1)[-1]
    if poi not in targets:
        return False
    data[bool_pos] = 1
    return True


def reveal_table(pkg, mode: str) -> int:
    """Set ShowFar on matching rows; returns how many rows changed."""
    targets = TARGETS[normalize_mode(mode)]
    _, rows = pkg.table_rows()
    changed = 0
    for _name, start, end in rows:
        tags: list = []
        _walk(pkg, start + 8, end, tags)
        if reveal_tags(tags, pkg.e, pkg.name_of, targets):
            changed += 1
    return changed


def build_reveal_pak(
    game_dir: str,
    paks_subpath: str,
    source_pak: str,
    repak: str,
    run_repak,
    mode: str | None = None,
    out_dir: str | None = None,
) -> int:
    """Build REVEAL_PAK; returns the number of icons changed."""
    mode = normalize_mode(mode)
    if mode == "none":
        return 0

    paks_dir = os.path.join(game_dir, paks_subpath)
    src = os.path.join(paks_dir, source_pak)
    if not os.path.isfile(src):
        raise RuntimeError(f"{source_pak} not found in {paks_dir}")

    listing = run_repak(repak, "list", src).decode(errors="replace")
    entries = [
        line.strip()
        for line in listing.splitlines()
        if line.strip().startswith(MINIMAP_PREFIX) and line.strip().endswith(".uasset")
    ]
    if not entries:
        raise RuntimeError("no minimap icon tables found in pakchunk0")

    staging = tempfile.mkdtemp(prefix="smtvv_reveal_")
    modified = 0
    changed = 0
    try:
        for asset_entry in entries:
            base = asset_entry[: -len(".uasset")]
            uasset = run_repak(repak, "get", src, asset_entry)
            uexp = run_repak(repak, "get", src, base + ".uexp")
            pkg = ue_asset.Package(uasset, uexp)
            rows = reveal_table(pkg, mode)
            if not rows:
                continue
            modified += 1
            changed += rows
            for suffix, blob in ((".uasset", pkg.a), (".uexp", pkg.e)):
                path = os.path.join(staging, *(base + suffix).split("/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as fh:
                    fh.write(blob)

        if not modified:
            raise RuntimeError("no matching treasure/leyline icons found")

        out = os.path.join(out_dir or paks_dir, REVEAL_PAK)
        tmp = out + ".tmp"
        try:
            run_repak(repak, "pack", "--version", "V11", staging, tmp)
            os.replace(tmp, out)
        finally:
            if os.path.isfile(tmp):
                os.remove(tmp)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return changed
