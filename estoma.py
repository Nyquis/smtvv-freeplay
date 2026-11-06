# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""
Free Estoma: make the Estoma Barrier cost no Magatsuhi.

Vengeance implements Estoma as a Miracle (Estoma Field I/II) backed by the
Blueprint data asset BP_EstomaData. Its class default object carries four
int32 properties:

    m_Magatsuhi_WhenUsed            summoned
    m_Magatsuhi_WhenChangeMoon      drain each moon phase
    m_LightMagatsuhi_WhenUsed       the same two once Estoma Field II is learned
    m_LightMagatsuhi_WhenChangeMoon

Zeroing all four makes the barrier free to summon and free to keep. The
values are plain int32s, so the edit keeps every package size and offset
intact; the asset is extracted from the user's own pakchunk0, patched, and
repacked as a small override pak.
"""

from __future__ import annotations

import os
import shutil
import struct
import tempfile

import ue_asset

ESTOMA_PAK = "pakchunk92_FreeEstoma_P.pak"
ESTOMA_ASSET = "Project/Content/Blueprints/Map/Encount/Estoma/BP_EstomaData"

# The "Light" pair is used after Estoma Field II is learned, so all four have
# to be zeroed for the barrier to be free at either rank.
COST_PROPERTIES = (
    "m_Magatsuhi_WhenUsed",
    "m_Magatsuhi_WhenChangeMoon",
    "m_LightMagatsuhi_WhenUsed",
    "m_LightMagatsuhi_WhenChangeMoon",
)

# The gauge is 0..100, so a larger stock cost means the asset layout changed.
COST_MAX = 100


def read_package(
    game_dir: str, paks_subpath: str, source_pak: str, repak: str, run_repak
) -> ue_asset.Package:
    """Extract BP_EstomaData from the game's own pak and parse it."""
    src = os.path.join(game_dir, paks_subpath, source_pak)
    if not os.path.isfile(src):
        raise RuntimeError(f"{source_pak} not found in {paks_subpath}")
    return ue_asset.Package(
        run_repak(repak, "get", src, ESTOMA_ASSET + ".uasset"),
        run_repak(repak, "get", src, ESTOMA_ASSET + ".uexp"),
    )


def find_cost_offsets(pkg) -> dict[str, int]:
    """Map each Estoma cost property to its value offset in the package."""
    found: dict[str, int] = {}
    for k in range(pkg.export_count):
        start, end = pkg.export_range(k)
        tags: list = []
        try:
            pkg.walk(start, end, tags)
        except (struct.error, ValueError):
            continue  # not a tagged-property blob (e.g. the class)
        for _size_at, value_at, _value_end, name, typ in tags:
            if typ != "IntProperty" or name not in COST_PROPERTIES:
                continue
            if name in found:
                raise RuntimeError(f"duplicate Estoma property: {name}")
            found[name] = value_at
    missing = [n for n in COST_PROPERTIES if n not in found]
    if missing:
        raise RuntimeError("Estoma cost properties not found: " + ", ".join(missing))
    return found


def zero_costs(pkg) -> dict[str, int]:
    """Zero the four costs in place and return the previous values."""
    old: dict[str, int] = {}
    for name, at in find_cost_offsets(pkg).items():
        value = struct.unpack_from("<i", pkg.e, at)[0]
        if not 0 <= value <= COST_MAX:
            raise RuntimeError(f"unexpected cost for {name}: {value}")
        old[name] = value
        struct.pack_into("<i", pkg.e, at, 0)
    return old


def build_estoma_pak(
    game_dir: str,
    paks_subpath: str,
    source_pak: str,
    repak: str,
    run_repak,
    out_dir: str | None = None,
) -> dict[str, int]:
    """Build the Free Estoma override pak; returns the old cost values.

    `out_dir` defaults to the game's Paks folder. Development and tests pass a
    temp directory so nothing is written into a game install.
    """
    pkg = read_package(game_dir, paks_subpath, source_pak, repak, run_repak)
    old = zero_costs(pkg)

    staging = tempfile.mkdtemp(prefix="smtvv_estoma_")
    try:
        asset_dir = os.path.join(staging, *ESTOMA_ASSET.split("/")[:-1])
        os.makedirs(asset_dir, exist_ok=True)
        for ext, payload in ((".uexp", pkg.e), (".uasset", pkg.a)):
            path = os.path.join(asset_dir, "BP_EstomaData" + ext)
            with open(path, "wb") as fh:
                fh.write(payload)

        target_dir = out_dir or os.path.join(game_dir, paks_subpath)
        pak_out = os.path.join(target_dir, ESTOMA_PAK)
        pak_tmp = pak_out + ".tmp"
        try:
            run_repak(repak, "pack", "--version", "V11", staging, pak_tmp)
            os.replace(pak_tmp, pak_out)
        finally:
            if os.path.isfile(pak_tmp):
                os.remove(pak_tmp)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return old
