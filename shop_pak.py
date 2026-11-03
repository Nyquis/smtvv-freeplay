"""
Shop stock editor for the Freeplay patcher.

Both tables are MMI binary blobs ("TBL1" sections) extracted from the player's
own pakchunk0 and repacked as a small override pak:

  ItemTable  section 0: 100-byte rows, row N-1 = item N
             (+16 item ID, +92 buying price, +96 selling price)
  ItemTable  section 2: 24-byte rows, IDs 311-615 (essences)
             (+0 item ID, +16 buying price; essences cannot be sold)
  ShopTable  section 0: 16-byte rows (u16 item, u16 sort, u32 unlock A,
             u32 unlock B, u32); rows with A = B = 0 are always for sale

Each category has one of three modes:

  default    leave it alone
  free       zero prices, keep the game's unlock timing and stock list
  immediate  zero prices, clear unlock flags, and add missing rows for the
             categories where completeness matters (growth, misc)
"""

from __future__ import annotations

import os
import struct

SHOP_PAK = "pakchunk98_FreeplayShop_P.pak"
TABLE_ROOT = "Project/Content/Blueprints/Gamedata/BinTable/"
ITEM_TABLE = TABLE_ROOT + "Item/ItemTable"
SHOP_TABLE = TABLE_ROOT + "Facility/Table/ShopTable"

# Item ranges, matching the ItemName table.
CATEGORY_IDS = {
    "consumables": frozenset(range(1, 82)),
    "growth": frozenset(range(82, 109)),
    "essences": frozenset(range(311, 616)),
    "misc": frozenset(range(109, 114)),
}
CATEGORIES = tuple(CATEGORY_IDS)
APPEND_CATEGORIES = ("growth", "misc")
MODES = ("default", "free", "immediate")

ITEM_ROW = 100
ITEM_ID_OFF = 16
ITEM_BUY_OFF = 92
ITEM_SELL_OFF = 96
SHOP_ROW = 16
ESSENCE_SECTION = 2
ESSENCE_ROW = 24
ESSENCE_ID_OFF = 0
ESSENCE_PRICE_OFF = 16

# Offsets in the .uasset that track the .uexp length.
UASSET_SERIAL_SIZE = 590  # int64: len(uexp) - 4
UASSET_BULK_START = 169  # int32: len(uasset) + len(uexp) - 4


def normalize_modes(modes: dict[str, str] | None = None) -> dict[str, str]:
    out = {category: "default" for category in CATEGORY_IDS}
    for category, mode in (modes or {}).items():
        if category not in CATEGORY_IDS:
            raise RuntimeError(f"unknown shop category: {category}")
        if mode not in MODES:
            raise RuntimeError(f"unknown shop mode for {category}: {mode}")
        out[category] = mode
    return out


def has_changes(modes: dict[str, str] | None = None) -> bool:
    return any(mode != "default" for mode in normalize_modes(modes).values())


def _section(data: bytes | bytearray, index: int) -> tuple[int, int, int]:
    """(header offset, data offset, size) of the index-th TBL1 section."""
    pos = -1
    for _ in range(index + 1):
        pos = data.find(b"TBL1", pos + 1)
        if pos < 0:
            raise RuntimeError("table layout not recognised")
    size = struct.unpack_from("<I", data, pos + 4)[0]
    return pos, pos + 16, size


def edit_item_table(uexp: bytes, modes: dict[str, str] | None = None) -> bytes:
    modes = normalize_modes(modes)
    data = bytearray(uexp)

    # Section 0: consumables, growth items and misc items.
    _, base, size = _section(data, 0)
    for category in ("consumables", "growth", "misc"):
        if modes[category] == "default":
            continue
        for item in CATEGORY_IDS[category]:
            row = base + (item - 1) * ITEM_ROW
            if (
                row + ITEM_ROW > base + size
                or struct.unpack_from("<i", data, row + ITEM_ID_OFF)[0] != item
            ):
                raise RuntimeError(
                    f"ItemTable row for item {item} not found - game update?"
                )
            struct.pack_into("<i", data, row + ITEM_BUY_OFF, 0)
            struct.pack_into("<i", data, row + ITEM_SELL_OFF, 0)

    # Section 2: essences. They cannot be sold, so only the buy price exists.
    if modes["essences"] != "default":
        _, base, size = _section(data, ESSENCE_SECTION)
        for i in range(size // ESSENCE_ROW):
            row = base + i * ESSENCE_ROW
            item = struct.unpack_from("<i", data, row + ESSENCE_ID_OFF)[0]
            if item in CATEGORY_IDS["essences"]:
                struct.pack_into("<i", data, row + ESSENCE_PRICE_OFF, 0)

    return bytes(data)


def missing_rows(modes: dict[str, str] | None, present) -> list[int]:
    """Items to append to the shop for 'immediate' append-capable categories."""
    modes = normalize_modes(modes)
    missing: list[int] = []
    for category in APPEND_CATEGORIES:
        if modes[category] == "immediate":
            missing.extend(sorted(CATEGORY_IDS[category] - set(present)))
    return missing


def edit_shop_table(
    uasset: bytes, uexp: bytes, modes: dict[str, str] | None = None
) -> tuple[bytes, bytes]:
    modes = normalize_modes(modes)
    data = bytearray(uexp)
    head, base, size = _section(data, 0)
    if size % SHOP_ROW:
        raise RuntimeError("ShopTable layout not recognised - game update?")
    rows = size // SHOP_ROW

    immediate = [c for c in CATEGORIES if modes[c] == "immediate"]
    immediate_ids = (
        set().union(*(CATEGORY_IDS[c] for c in immediate)) if immediate else set()
    )

    present = set()
    max_sort = 0
    for i in range(rows):
        o = base + i * SHOP_ROW
        item, sort = struct.unpack_from("<HH", data, o)
        present.add(item)
        max_sort = max(max_sort, sort)
        if item in immediate_ids:
            struct.pack_into("<II", data, o + 4, 0, 0)

    missing = missing_rows(modes, present)
    if not missing:
        return uasset, bytes(data)

    # Append rows for items the shop never stocks.
    extra = b"".join(
        struct.pack("<HHIII", item, max_sort + 1 + n, 0, 0, 0)
        for n, item in enumerate(missing)
    )
    grow = len(extra)
    end = base + size
    data[end:end] = extra
    struct.pack_into("<I", data, head + 4, size + grow)

    # TBCR directory: section offsets after the first move with it.
    tbcr = data.find(b"TBCR")
    if tbcr < 0 or tbcr > head:
        raise RuntimeError("ShopTable directory not found - game update?")
    _hdr_len, count = struct.unpack_from("<II", data, tbcr + 4)
    for k in range(1, count):
        p = tbcr + 12 + 4 * k
        struct.pack_into("<I", data, p, struct.unpack_from("<I", data, p)[0] + grow)

    # Byte-array property tag: int64 property size (= count + 4) and the
    # int32 element count right before the blob.
    count_at = tbcr - 4
    n_elems = struct.unpack_from("<i", data, count_at)[0]
    prop_size_at = data.rfind(struct.pack("<q", n_elems + 4), 0, count_at)
    if prop_size_at < 0:
        raise RuntimeError("ShopTable property header not found - game update?")
    struct.pack_into("<i", data, count_at, n_elems + grow)
    struct.pack_into("<q", data, prop_size_at, n_elems + 4 + grow)

    asset = bytearray(uasset)
    if (
        struct.unpack_from("<q", asset, UASSET_SERIAL_SIZE)[0] != len(uexp) - 4
        or struct.unpack_from("<i", asset, UASSET_BULK_START)[0]
        != len(uasset) + len(uexp) - 4
    ):
        raise RuntimeError("ShopTable header not recognised - game update?")
    struct.pack_into("<q", asset, UASSET_SERIAL_SIZE, len(uexp) - 4 + grow)
    struct.pack_into("<i", asset, UASSET_BULK_START, len(uasset) + len(uexp) - 4 + grow)
    return bytes(asset), bytes(data)


def build_shop_pak(
    game_dir: str,
    paks_subpath: str,
    source_pak: str,
    repak: str,
    run_repak,
    modes: dict[str, str] | None = None,
    out_dir: str | None = None,
) -> None:
    """Build SHOP_PAK in the game's Paks folder (or `out_dir`). Raises RuntimeError."""
    import shutil
    import tempfile

    modes = normalize_modes(modes)
    if not has_changes(modes):
        return

    paks_dir = os.path.join(game_dir, paks_subpath)
    src = os.path.join(paks_dir, source_pak)
    if not os.path.isfile(src):
        raise RuntimeError(f"{source_pak} not found in {paks_dir}")

    def get(entry: str) -> bytes:
        return run_repak(repak, "get", src, entry)

    item_asset, item_exp = get(ITEM_TABLE + ".uasset"), get(ITEM_TABLE + ".uexp")
    shop_asset, shop_exp = get(SHOP_TABLE + ".uasset"), get(SHOP_TABLE + ".uexp")
    item_exp = edit_item_table(item_exp, modes)
    files = {
        ITEM_TABLE + ".uasset": item_asset,
        ITEM_TABLE + ".uexp": item_exp,
    }
    files[SHOP_TABLE + ".uasset"], files[SHOP_TABLE + ".uexp"] = edit_shop_table(
        shop_asset, shop_exp, modes
    )

    staging = tempfile.mkdtemp(prefix="smtvv_shop_")
    try:
        for entry, blob in files.items():
            path = os.path.join(staging, *entry.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(blob)
        out = os.path.join(out_dir or paks_dir, SHOP_PAK)
        tmp = out + ".tmp"
        try:
            run_repak(repak, "pack", "--version", "V11", staging, tmp)
            os.replace(tmp, out)
        finally:
            if os.path.isfile(tmp):
                os.remove(tmp)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
