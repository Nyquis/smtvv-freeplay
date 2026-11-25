# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-FileCopyrightText: 2026 the countlessbats/smtvv-freeplay authors
# SPDX-License-Identifier: MIT AND Apache-2.0
# Modified by Nyquis from the upstream MIT project; see LICENSING.md.

"""
Stockpile: battle items can be stockpiled up to 99 outside battle, while
each battle still allows only the game's normal carry limit of each item
(e.g. 5 Somas).

The ItemTable keeps its limits (section 0, 100-byte rows, row N-1 = item N;
+58 carry limit, +61 nonzero when usable in battle). For every battle item
with a limit below 99, the exe's ItemGetMaxNum reports 99, except to the
item menus' list rows, so the game's carry checks allow 99 while the menus
show the normal limit and stock above it as e.g. 11/10. STOCK_PAK carries
the camp item list widget with its "count == max" colour check turned into
"count >= max".

When a battle enters E_BTL_STEP_PRE, the stock above each item's normal limit
is taken out of the real inventory with ItemErase and recorded; until the
battle reaches E_BTL_STEP_END_EVENT, ItemGetMaxNum reports the normal limit to
the battle menus. At the end steps the set-aside stock is added back with
ItemGet. Because the real inventory is capped for the whole battle, every
consume check sees the per-battle allowance instead of only the UI counter.
Leftovers from a battle that ended without its end step are restored at the
next PRE, so they cannot be lost.
"""

from __future__ import annotations

import os
import struct

import gameplay_patches
from code_caves import Asm, _jmp_site, _place, off, va
from gameplay_patches import (
    BTL_NEXTSTEP_OFF,
    BTL_STEP_END_EVENT,
    BTL_STEP_PRE,
    ITEM_GET,
    ITEM_GET_MAX,
    ITEM_GET_MAX_ORIG,
    ITEM_GET_NUM,
    ITEM_GET_NUM_ORIG,
    ITEM_GET_ORIG,
    SETNEXTSTEP_ORIG,
    SETNEXTSTEP_THUNKS,
)
from shop_pak import ITEM_ID_OFF, ITEM_ROW, ITEM_TABLE, _section

STOCK_PAK = "pakchunk93_FreeplayStockpile_P.pak"
ITEM_LIST = "Project/Content/Blueprints/UI/Camp/Item/WB_CampItemList"
IMPORT_SIZE = 28

ITEM_MAX_OFF = 58          # u8 carry limit
ITEM_BATTLE_OFF = 61       # nonzero: usable in battle
STOCK_MAX = 99
ID_MAX = 135               # use items are 1..135

# ItemErase entry thunk (also the Essences hook site). The patcher updates this
# VA when it relocates the site.
ITEM_ERASE = 0x140ACE740

STOCK_ACTIVE = 0x1549A9900   # spare zeroed bytes in a writable section page
STOCK_LAST_ID = 0x1549A9908  # item ID of the latest ItemGetMaxNum call
STOCK_HIDDEN = 0x1549A9910   # u8 per item ID, 0..ID_MAX
# Item menu code that fills each list row from ItemGetMaxNum / ItemGetNum
# (unpacked at run time, so only its address range is used).
ITEM_MENU_ROWS = (0x147A95A40, 0x147A95C00)
# Blueprint exec thunk of ItemGetMaxNum (a 5-byte jump into the protected
# body), hooked in place.
MAX_THUNKS = [0x140CCBA60]
MAX_THUNK_ORIG = bytes.fromhex("e90bd42d0a")
# The other registered copy (0x140CCA910) must keep its code bytes (patching
# them makes the game exit during startup), so its entry in the native
# function table is pointed at the hook instead: (table slot, thunk).
MAX_SLOTS = [(0x143279EB0, 0x140CCA910)]


def _file_off(data: bytes, v: int) -> int:
    """File offset of VA v, from the section table."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    sec = pe + 24 + struct.unpack_from("<H", data, pe + 20)[0]
    rva = v - 0x140000000
    for i in range(count):
        vsize, vaddr, rsize, raw = struct.unpack_from("<4I", data, sec + i * 40 + 8)
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raw + rva - vaddr
    raise RuntimeError(f"address {v:#x} not in any section")


def battle_item_limits(uexp: bytes) -> dict[int, int]:
    """{item: carry limit} for every battle item with a limit below STOCK_MAX."""
    _, base, size = _section(bytearray(uexp), 0)
    limits = {}
    for item in range(1, ID_MAX + 1):
        row = base + (item - 1) * ITEM_ROW
        if row + ITEM_ROW > base + size or struct.unpack_from("<i", uexp, row + ITEM_ID_OFF)[0] != item:
            raise RuntimeError(f"ItemTable row for item {item} not found - game update?")
        limit = uexp[row + ITEM_MAX_OFF]
        if uexp[row + ITEM_BATTLE_OFF] and 0 < limit < STOCK_MAX:
            limits[item] = limit
    if not limits:
        raise RuntimeError("no battle items found in ItemTable - game update?")
    return limits


def u32(value: int) -> str:
    return struct.pack("<I", value).hex()


def _cave_va(c: list[int]) -> int:
    """VA of a side-cave entry.

    A two-element entry is [file start, file end]. A three-element entry adds
    c[2] = VA - file offset for its section; it is not a displacement into the
    cave.
    """
    return c[0] + c[2] if len(c) > 2 else va(c[0])


def item_erase_va() -> int:
    """ItemErase entry. The essences feature may redirect it through a cave."""
    return ITEM_ERASE


def _step_code(
    base_va: int,
    prev: int | None,
    limits_va: int,
    hidden_va: int,
    active_va: int,
    item_get: int,
    item_get_num: int,
    item_erase: int,
) -> bytes:
    """SetNextStep hook: set the excess aside at PRE, restore it at the end."""
    a = Asm(base_va)
    a.raw("53 56 57 48 83 EC 20 48 89 CB")  # push rbx/rsi/rdi; sub rsp,20h
    if prev is not None:
        a.call(prev)
    a.raw("0F B6 83" + u32(BTL_NEXTSTEP_OFF))  # movzx eax, m_NextStep
    a.raw(f"83 F8 {BTL_STEP_PRE:02x}").jne("end")

    # PRE: restore anything a previous battle left set aside.
    a.raw("31 F6")  # xor esi, esi
    a.label("restore")
    a.raw("FF C6")  # inc esi
    a.raw("81 FE" + u32(ID_MAX))
    a.ja("snapshot")
    a._rel("48 8D 0D", hidden_va)  # lea rcx, [hidden]
    a.raw("0F B6 14 31")  # movzx edx, byte [rcx+rsi]
    a.raw("85 D2").je("restore")
    a.raw("89 F1").call(item_get)  # mov ecx, esi; ItemGet(id, count)
    a._rel("48 8D 0D", hidden_va)
    a.raw("C6 04 31 00")  # mov byte [rcx+rsi], 0
    a.jmp("restore")

    # PRE: take the excess out of the real inventory.
    a.label("snapshot")
    a.raw("31 F6")  # xor esi, esi
    a.label("snap")
    a.raw("FF C6")  # inc esi
    a.raw("81 FE" + u32(ID_MAX))
    a.ja("active")
    a._rel("48 8D 05", limits_va)  # lea rax, [limits]
    a.raw("0F B6 3C 30")  # movzx edi, byte [rax+rsi]
    a.raw("85 FF").je("snap")
    a.raw("89 F1").call(item_get_num)  # eax = real count
    a.raw("29 F8")  # sub eax, edi
    a.jle("zero")
    a._rel("48 8D 0D", hidden_va)
    a.raw("88 04 31")  # mov [hidden+rsi], al
    a.raw("89 C2")  # mov edx, eax
    a.raw("89 F1").call(item_erase)  # ItemErase(id, extra)
    a.jmp("snap")
    a.label("zero")
    a._rel("48 8D 0D", hidden_va)
    a.raw("C6 04 31 00")
    a.jmp("snap")

    a.label("active")
    a.raw("B0 01")._rel("88 05", active_va)
    a.jmp("done")

    # End steps: add the set-aside stock back.
    a.label("end")
    a.raw(f"83 F8 {BTL_STEP_END_EVENT:02x}")
    a._rel("0F 82", "done")
    a.raw("31 F6")  # xor esi, esi
    a.label("restore_end")
    a.raw("FF C6")  # inc esi
    a.raw("81 FE" + u32(ID_MAX))
    a.ja("cleared")
    a._rel("48 8D 0D", hidden_va)
    a.raw("0F B6 14 31")
    a.raw("85 D2").je("restore_end")
    a.raw("89 F1").call(item_get)
    a._rel("48 8D 0D", hidden_va)
    a.raw("C6 04 31 00")
    a.jmp("restore_end")
    a.label("cleared")
    a.raw("31 C0")._rel("88 05", active_va)

    a.label("done")
    a.raw("48 83 C4 20 5F 5E 5B C3")
    return a.build()


def patch_stockpile(data: bytearray, cave_off: int, cave_end: int,
                     orig: dict[int, int], side: list[list[int]]) -> int | None:
    """Transactional wrapper: a failed trial must not consume side-cave space."""
    original = [c[0] for c in side]
    try:
        result = _patch_stockpile(data, cave_off, cave_end, orig, side)
    except BaseException:
        for c, start in zip(side, original):
            c[0] = start
        raise
    if result is None:
        for c, start in zip(side, original):
            c[0] = start
    return result


def _patch_stockpile(data: bytearray, cave_off: int, cave_end: int,
                     orig: dict[int, int], side: list[list[int]]) -> int | None:
    """Main code goes in the shared cave; the ItemGetMaxNum hooks go in the
    smaller caves listed in side ([start, end] or [start, end, va - file],
    used up in place)."""
    for t in SETNEXTSTEP_THUNKS:
        if data[off(t) : off(t) + 5] != SETNEXTSTEP_ORIG:
            return None
    for t in MAX_THUNKS:
        if data[off(t) : off(t) + 5] != MAX_THUNK_ORIG:
            return None
    for fn, expected in (
        (ITEM_GET, ITEM_GET_ORIG),
        (ITEM_GET_NUM, ITEM_GET_NUM_ORIG),
        (ITEM_GET_MAX, ITEM_GET_MAX_ORIG),
    ):
        if data[off(fn) : off(fn) + 5] != expected:
            return None
    if data[off(ITEM_ERASE)] != 0xE9:
        return None
    for slot, thunk in MAX_SLOTS:
        if struct.unpack_from("<Q", data, _file_off(data, slot))[0] != thunk:
            return None
    limits = bytes(orig.get(i, 0) for i in range(ID_MAX + 1))

    # Reserve the limits table before the hooks so both the battle and menu
    # hooks can read it. It is read-only data in the code cave.
    table_size = (len(limits) + 15) & ~15
    if cave_off + table_size > cave_end:
        return None
    limits_va = va(cave_off)
    cave_off = _place(
        data, cave_off, cave_end, limits, base_va=limits_va, check_refs=True
    )

    # SetNextStep: at PRE take the stock above each item's normal limit out of
    # the real inventory; at the end steps add it back.
    erase_va = item_erase_va()
    if gameplay_patches.DEFER_SETNEXTSTEP:
        dest = va(cave_off)
        cave_off = _place(
            data,
            cave_off,
            cave_end,
            _step_code(
                dest,
                None,
                limits_va,
                STOCK_HIDDEN,
                STOCK_ACTIVE,
                ITEM_GET,
                ITEM_GET_NUM,
                erase_va,
            ),
        )
        gameplay_patches.DEFERRED_STEPS["stockpile"] = dest
    else:
        for t in SETNEXTSTEP_THUNKS:
            prev = t + 5 + struct.unpack_from("<i", data, off(t) + 1)[0]
            dest = va(cave_off)
            cave_off = _place(
                data,
                cave_off,
                cave_end,
                _step_code(
                    dest,
                    prev,
                    limits_va,
                    STOCK_HIDDEN,
                    STOCK_ACTIVE,
                    ITEM_GET,
                    ITEM_GET_NUM,
                    erase_va,
                ),
            )
            _jmp_site(data, t, dest, 5)

    # ItemGetMaxNum body: remember which item was asked for, and let the
    # game's carry checks see the stock limit for items with a normal limit.
    max_orig = ITEM_GET_MAX + 5 + struct.unpack_from("<i", data, off(ITEM_GET_MAX) + 1)[0]
    def side_put(build) -> int:
        for c in side:
            base = _cave_va(c)
            code = build(Asm(base)).build()
            if c[0] + len(code) <= c[1]:
                c[0] = _place(data, c[0], c[1], code, base_va=base, check_refs=True)
                return base
        raise RuntimeError("code cave too small")

    def max_hook(a):
        a.raw("48 8B 04 24")                      # mov rax, [rsp] (return address)
        a._rel("89 0D", STOCK_LAST_ID)            # mov [last], ecx
        # The item menus' list rows get the table limit as is.
        a.raw("49 B8" + struct.pack("<Q", ITEM_MENU_ROWS[0]).hex())   # mov r8, imm64
        a.raw("4C 29 C0")                         # sub rax, r8
        a.raw("48 3D" + u32(ITEM_MENU_ROWS[1] - ITEM_MENU_ROWS[0]))
        a._rel("0F 82", max_orig)                 # jb: tail-call the original
        a.raw("53 48 83 EC 20 89 CB")             # push rbx; sub rsp,20h; mov ebx,ecx
        a.call(max_orig)
        a.raw("81 FB" + u32(ID_MAX)).ja("keep")
        a._rel("48 8D 15", limits_va)
        a.raw("80 3C 1A 00").je("keep")           # cmp byte [rdx+rbx], 0
        a.raw("B8" + u32(STOCK_MAX))
        a.label("keep")
        a.raw("48 83 C4 20 5B C3")
        return a

    _jmp_site(data, ITEM_GET_MAX, side_put(max_hook), 5)

    # Blueprint ItemGetMaxNum: in battle, report the item's normal limit.
    def thunk_hook(prev):
        def build(a):
            # rax is passed through untouched: the game also calls this
            # entry outside Blueprint and uses what it returns.
            a.raw("53 48 83 EC 20 4C 89 C3")      # push rbx; sub rsp,20h; mov rbx,r8 (result)
            a.raw("B9 FF FF FF FF")._rel("89 0D", STOCK_LAST_ID)
            a.call(prev)
            a._rel("8A 0D", STOCK_ACTIVE).raw("84 C9").je("done")   # battles only
            a._rel("8B 0D", STOCK_LAST_ID)        # mov ecx, [last]
            a.raw("81 F9" + u32(ID_MAX)).ja("done")
            a._rel("48 8D 15", limits_va)
            a.raw("0F B6 14 0A 85 D2").je("done")    # movzx edx,[rdx+rcx]; test edx,edx
            a.raw("48 85 DB").je("done")          # no result slot
            # The original call already wrote the full result; only its low
            # byte needs to change to the normal carry limit.
            a.raw("88 13")                        # mov [rbx], dl
            a.label("done")
            a.raw("48 83 C4 20 5B C3")
            return a
        return build

    for t in MAX_THUNKS:
        prev = t + 5 + struct.unpack_from("<i", data, off(t) + 1)[0]
        _jmp_site(data, t, side_put(thunk_hook(prev)), 5)
    for slot, _ in MAX_SLOTS:
        prev = struct.unpack_from("<Q", data, _file_off(data, slot))[0]
        struct.pack_into("<Q", data, _file_off(data, slot), side_put(thunk_hook(prev)))
    return cave_off


def read_item_table(game_dir: str, paks_subpath: str, source_pak: str,
                    repak: str, run_repak) -> tuple[bytes, bytes]:
    src = os.path.join(game_dir, paks_subpath, source_pak)
    if not os.path.isfile(src):
        raise RuntimeError(f"{source_pak} not found")
    return (run_repak(repak, "get", src, ITEM_TABLE + ".uasset"),
            run_repak(repak, "get", src, ITEM_TABLE + ".uexp"))


def edit_item_list(uasset: bytes, uexp: bytes) -> tuple[bytes, bytes]:
    """WB_CampItemList colours a row's count when it equals the maximum;
    make it count >= maximum, so stock above the limit is coloured too."""
    from ue_asset import Package

    pkg = Package(uasset, uexp)
    at = struct.unpack_from("<i", pkg.a, pkg.at["import_offset"])[0]
    count = struct.unpack_from("<i", pkg.a, pkg.at["import_offset"] - 4)[0]
    hits = []
    for k in range(count):
        o = at + k * IMPORT_SIZE
        outer, name = struct.unpack_from("<ii", pkg.a, o + 16)
        if outer >= 0:
            continue
        owner = struct.unpack_from(
            "<i", pkg.a, at + (-outer - 1) * IMPORT_SIZE + 20
        )[0]
        if (
            pkg.names[name] == "EqualEqual_IntInt"
            and pkg.names[owner] == "KismetMathLibrary"
        ):
            hits.append(o)
    if len(hits) != 1:
        raise RuntimeError("item list colour check not found - game update?")
    struct.pack_into("<ii", pkg.a, hits[0] + 20, pkg.name("GreaterEqual_IntInt"), 0)
    return pkg.build()


def build_stock_pak(game_dir: str, paks_subpath: str, source_pak: str,
                    repak: str, run_repak) -> None:
    """Build STOCK_PAK (the item list widget) in the game's Paks folder."""
    import shutil
    import tempfile

    src = os.path.join(game_dir, paks_subpath, source_pak)
    if not os.path.isfile(src):
        raise RuntimeError(f"{source_pak} not found")
    files = dict(zip((ITEM_LIST + ".uasset", ITEM_LIST + ".uexp"),
                     edit_item_list(run_repak(repak, "get", src, ITEM_LIST + ".uasset"),
                                    run_repak(repak, "get", src, ITEM_LIST + ".uexp"))))
    staging = tempfile.mkdtemp(prefix="smtvv_stock_")
    try:
        for entry, blob in files.items():
            path = os.path.join(staging, *entry.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(blob)
        out = os.path.join(game_dir, paks_subpath, STOCK_PAK)
        tmp = out + ".tmp"
        try:
            run_repak(repak, "pack", "--version", "V11", staging, tmp)
            os.replace(tmp, out)
        finally:
            if os.path.isfile(tmp):
                os.remove(tmp)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
