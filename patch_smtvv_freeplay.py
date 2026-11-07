# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-FileCopyrightText: 2026 the countlessbats/smtvv-freeplay authors
# SPDX-License-Identifier: MIT AND Apache-2.0
# Modified by Nyquis from the upstream MIT project; see LICENSING.md.

"""
SMT5V: Vengeance - Freeplay Patcher
===================================
Applies quality-of-life patches to the game executable and optional data paks:

  1. Reusable Essences  -- essences are not consumed when used.
     Redirects the ItemErase trampoline (0x00ACDD40) through a code cave
     that skips erasure for item IDs 311-615 (the essence range).

  2. Leyline Auto-Heal  -- full party HP/MP restored on leyline access.
     Hooks SetRyuketsuSaveAccess (0x00CD57D0) to call PartyAllCure
     (VA 0x140AB94B0) before the original leyline logic runs.

  3. Miman Reveal  -- every Miman position is shown on the map.

  3b. Leyline Founts -- leyline fount icons are drawn through fog on the
      main map; the minimap keeps its normal local range.

  4. NG+ Miracles  -- selected NG+ miracles are visible and purchasable
     before clearing the game.

  5. Free Compendium  -- summoning demons from the compendium costs nothing.
     The shared demon-cost formula (used by every compendium price path)
     returns 0.

  6. Item Hacks  -- one of:
     Battle Refill: at the start of every battle, each battle-usable item
     the player has ever obtained is topped up to its carry limit.
     Stockpile: battle items stack to 99, but each battle allows only the
     normal carry limit of each (data pak built from the player's game
     files).

  7. Superjump  -- hold jump to keep rising; faster air movement and
     near-instant turning while airborne.

  8. Shop Stock  -- per-category shop pricing and availability for
     consumables, growth items, essences and misc items (data pak built from
     the player's game files).

  9. Full Magatsuhi  -- the Magatsuhi gauge is filled at the start of every
     battle.

 10. Skip Intro  -- no logo or warning screens, opening movie or "press any
     button" screen; the game boots straight to the title menu (data pak
     built from the player's game files).

 11. Masakado Unlock  -- Masakado offers his powered-up fight without the
     Kiou Sword (data pak built from the player's game files).

 12. Newborn Clears Compendium  -- a New Game+ started with Newborn also
     empties the Demon Compendium; the carry-over lists say so (data pak
     built from the player's game files).

 13. Autosave after battle  -- (optional, --autosave-slot N) the game is
     saved to slot N (1-20) after every battle, once back on the field.

 14. Free Estoma  -- the Estoma Barrier costs no Magatsuhi to summon or to
     keep through moon phases (data pak built from the player's game files).

Executable patches share the same large CC cave in .rdata.

Usage
-----
    python patch_smtvv_freeplay.py [--game-dir <path>]

If --game-dir is not supplied the script tries to auto-detect the game
from common Steam library locations.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import os
import platform
import re
import shutil
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autosave
import boot_pak
import estoma
import gameplay_patches
import leylines
import newborn
import patch_manifest
import pe_imports
import quest_pak
import reveal
import shop_pak
import signatures
import stockpile
from patch_manifest import LEGACY_MAP_PAK, MIRACLE_PAK

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MOD_VERSION = "5.27.0"
FEATURES_FILE = "Freeplay.features"  # installed features, kept next to the executable

EXE_NAME = "SMT5V-Win64-Shipping.exe"
EXE_SUBPATH = os.path.join("Project", "Binaries", "Win64", EXE_NAME)

# NG+ miracle data pak: built at install time from the user's own game data.
# GodParameterDataTable is extracted from pakchunk0 with the bundled repak
# tool, edited, and repacked as a small override pak.
PAKS_SUBPATH = os.path.join("Project", "Content", "Paks")
SOURCE_PAK = "pakchunk0-WindowsNoEditor.pak"
GP_TABLE_ENTRY = (
    "Project/Content/Blueprints/Gamedata/BinTable/"
    "GodParameter/Table/GodParameterDataTable"
)

# Essence item-ID range (inclusive)
ESSENCE_ID_MIN = 311  # 0x137
ESSENCE_ID_MAX = 615  # 0x267

# PE section layout (for VA <-> file-offset conversion in .rdata)
IMAGE_BASE = 0x140000000
RDATA_RAW = 0x600
RDATA_VA = 0x140001000

# ItemErase implementation trampoline
# This 5-byte JMP (E9 xx xx xx xx) is the single bottleneck through which
# every item-erase call passes.  Seven call-sites total.
TRAMP_OFFSET = 0x00ACDD40
TRAMP_ORIG = bytes([0xE9, 0xEB, 0x6F, 0x8C, 0x06])

# SetRyuketsuSaveAccess exec trampoline  (leyline fount access entry point)
# NOTE: 0x00CD5700 is the FName-init trampoline (called at startup — do NOT
# touch it).  0x00CDB6C0 is the *exec-body* trampoline, invoked only when
# the player actually accesses a leyline fount.
RYUKETSU_TRAMP_OFFSET = 0x00CDB6C0
RYUKETSU_TRAMP_ORIG = bytes([0xE9, 0x8B, 0xD5, 0x65, 0x0A])

# PartyAllCure C++ implementation  (full party HP/MP restore)
# Self-contained: fetches NkmDataManager singleton internally,
# so it can be called with any register state.
PARTY_ALL_CURE_VA = 0x140AB94B0
# 29-byte prologue; unique. It stops before the relative call displacement,
# so it stays valid if the function called from the prologue moves.
PARTY_ALL_CURE_ORIG = bytes.fromhex(
    "48895c240848896c241048897424185741544155415641574883ec40e8"
)

# CheckMimanPositionFlag C++ implementation  (is a miman shown on the map?)
# Signature: bool CheckMimanPositionFlag(int index).  The map asks this when
# it builds its markers; patched to "mov al, 1; ret" so every position shows.
MIMAN_POS_CHECK_OFFSET = 0x00ADB180  # VA 0x140ADBB80
MIMAN_POS_CHECK_ORIG = bytes.fromhex("48895c240848896c2410488974241857")

# NG+ Miracle unlock patches
# IsAddedSelectableGodParameterSkill trampoline — controls shop visibility
MIRACLE_ADDED_TRAMP = 0x00ACBD90
MIRACLE_ADDED_ORIG = bytes([0xE9, 0xEB, 0x37, 0x89, 0x06])

# GetGodParameterSkillState trampoline — controls miracle purchasability
MIRACLE_STATE_TRAMP = 0x00ACB780
MIRACLE_STATE_ORIG = bytes([0xE9, 0x5B, 0xEB, 0x88, 0x06])

# Hardcoded "cmp ecx, 666; je BLOCK" that hides Divine Persuasion
MIRACLE_666_NOP_ADDR = 0x00551AEE  # 6-byte JE instruction to NOP
MIRACLE_666_ORIG = bytes.fromhex("0f84d9010000")

# Miracle IDs/enums to force-unlock (both 0-based and 1-based to cover
# all code paths: some functions use enum=ID-1, others use raw ID)
MIRACLE_UNLOCK_IDS = [22, 23, 24, 30, 31, 32]

# Demon cost formula (compendium summon price). Called by
# CalcDevilCost_ByBibleData / _ByDevilData / _ByPartyData; returns the
# Macca cost in EAX. Patched to "xor eax, eax; ret".
DEVIL_COST_OFFSET = 0x00BFB480
DEVIL_COST_ORIG = bytes.fromhex("4c8bdc49894b0841574881ecc0000000")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def file_to_va(foff: int) -> int:
    return gameplay_patches.va(foff)


def _heal_code(party_cure_va: int, orig_tgt: int, dest_va: int) -> bytes:
    """Call PartyAllCure, then tail-jump to the original fount function.

    The 32-byte frame reserves the Windows x64 shadow space below the saved
    registers; the callee's prologue spills live there.
    """
    code = bytearray()
    code += b"\x51"  # push rcx
    code += b"\x52"  # push rdx
    code += b"\x41\x50"  # push r8
    code += b"\x41\x51"  # push r9
    code += b"\x53"  # push rbx
    code += b"\x48\x83\xec\x20"  # sub rsp, 20h (shadow space)
    code += b"\xe8"  # call PartyAllCure
    code += struct.pack("<i", party_cure_va - (dest_va + len(code) + 4))
    code += b"\x48\x83\xc4\x20"  # add rsp, 20h
    code += b"\x5b"  # pop rbx
    code += b"\x41\x59"  # pop r9
    code += b"\x41\x58"  # pop r8
    code += b"\x5a"  # pop rdx
    code += b"\x59"  # pop rcx
    code += b"\xe9"  # jmp original
    code += struct.pack("<i", orig_tgt - (dest_va + len(code) + 4))
    return bytes(code)


def _heal_cure_target(data: bytearray) -> int | None:
    """VA of PartyAllCure for this build, or None when its prologue is missing."""
    site = signatures.resolve(
        data, gameplay_patches.off(PARTY_ALL_CURE_VA), PARTY_ALL_CURE_ORIG
    )
    return None if site is None else file_to_va(site)


IMAGE_SCN_MEM_EXECUTE = 0x20000000
CAVE_PREFIX = 64  # bytes of a candidate checked for live references
CAVE_REF_MARGIN = 16  # bytes after a reference that must stay untouched
LAST_CAVE_INFO: dict | None = None
LAST_REFERENCES: list[int] = []
_REF_CACHE: tuple[tuple, list[int], list[int]] | None = None


def _pe_sections(
    data: bytes | bytearray,
) -> list[tuple[str, int, int, int, int]]:
    """(name, raw offset, raw size, virtual address, characteristics)."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    base = pe + 24 + opt
    sections = []
    for i in range(count):
        h = base + 40 * i
        name = bytes(data[h : h + 8]).rstrip(b"\0").decode("latin-1")
        _vsize, rva, rsize, raw = struct.unpack_from("<IIII", data, h + 8)
        flags = struct.unpack_from("<I", data, h + 36)[0]
        sections.append((name, raw, rsize, rva, flags))
    return sections


def _code_section(
    data: bytes | bytearray,
) -> tuple[list[tuple[str, int, int, int, int]], int, int, int]:
    """The executable .rdata section, plus its raw offset, size and RVA."""
    sections = _pe_sections(data)
    for name, raw, rsize, rva, flags in sections:
        if name == ".rdata" and flags & IMAGE_SCN_MEM_EXECUTE:
            return sections, raw, rsize, rva
    for name, raw, rsize, rva, flags in sections:
        if raw <= RDATA_RAW < raw + rsize:
            return sections, raw, rsize, rva
    raise RuntimeError("no executable .rdata section")


def _section_for(
    sections: list[tuple[str, int, int, int, int]], foff: int
) -> tuple[str, int]:
    for name, raw, rsize, _rva, flags in sections:
        if raw <= foff < raw + rsize:
            return name, flags
    return "?", 0


def _section_for_va(data: bytes | bytearray, va: int) -> tuple[str, int]:
    """Section name and characteristics for an absolute VA."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    base = pe + 24 + opt
    rva = va - IMAGE_BASE
    page_match = None
    for i in range(count):
        h = base + 40 * i
        name = bytes(data[h : h + 8]).rstrip(b"\0").decode("latin-1")
        vsize, srva, rsize, _raw = struct.unpack_from("<IIII", data, h + 8)
        flags = struct.unpack_from("<I", data, h + 36)[0]
        end = srva + max(vsize, rsize)
        if srva <= rva < end:
            return name, flags
        page_start = srva & ~0xFFF
        page_end = (end + 0xFFF) & ~0xFFF
        if page_start <= rva < page_end:
            if flags & 0x80000000:
                return name, flags
            page_match = (name, flags)
    return page_match or ("?", 0)


def _assert_writable(data: bytes | bytearray, va: int, label: str) -> None:
    name, flags = _section_for_va(data, va)
    if not flags & 0x80000000:
        print(f"\n  ERROR: {label} (0x{va:X}) is in non-writable section {name}")
        sys.exit(1)


def _assert_mapped(data: bytes | bytearray, va: int, label: str) -> None:
    name, _flags = _section_for_va(data, va)
    if name == "?":
        print(f"\n  ERROR: {label} (0x{va:X}) is outside every mapped section")
        sys.exit(1)


def _scratch_regions() -> list[tuple[str, int, int]]:
    """Writable scratch used by the patches: (label, VA, size)."""
    return [
        ("STOCK_ACTIVE", stockpile.STOCK_ACTIVE, 1),
        ("STOCK_LAST_ID", stockpile.STOCK_LAST_ID, 4),
        ("STOCK_HIDDEN", stockpile.STOCK_HIDDEN, stockpile.ID_MAX + 1),
        ("AUTOSAVE_PENDING", autosave.AUTOSAVE_PENDING, 4),
        ("AUTOSAVE_COUNT", autosave.AUTOSAVE_COUNT, 4),
        ("AUTOSAVE_RESULT", autosave.AUTOSAVE_RESULT, 1),
        ("AUTOSAVE_BUSY", autosave.AUTOSAVE_BUSY, 1),
        ("AUTOSAVE_LOCATION", autosave.AUTOSAVE_LOCATION, 4),
        ("AUTOSAVE_LOCATION_VALID", autosave.AUTOSAVE_LOCATION_VALID, 1),
        ("AUTOSAVE_RETRY", autosave.AUTOSAVE_RETRY, 1),
        ("MAGATSUHI_ACTOR", gameplay_patches.MAGATSUHI_ACTOR, 8),
        ("MAGATSUHI_ARRAY", gameplay_patches.MAGATSUHI_ARRAY, 8),
        ("REFOCUS_DONE", gameplay_patches.REFOCUS_DONE, 1),
    ]


def _reference_sets(
    data: bytes | bytearray, code_raw: int, code_rsize: int, code_rva: int
) -> tuple[list[int], list[int]]:
    """Sorted VAs of direct rel32 branches in the code section and of
    8-byte image pointers anywhere in the file."""
    global _REF_CACHE
    key = (
        len(data),
        code_raw,
        code_rsize,
        code_rva,
        zlib.crc32(memoryview(data)[code_raw : code_raw + code_rsize]),
    )
    if _REF_CACHE is not None and _REF_CACHE[0] == key:
        return _REF_CACHE[1], _REF_CACHE[2]

    code = data[code_raw : code_raw + code_rsize]
    targets: list[int] = []
    for m in re.finditer(rb"[\xe8\xe9]", code):
        i = m.start()
        if i + 5 > len(code):
            continue
        site = IMAGE_BASE + code_rva + i
        targets.append(site + 5 + struct.unpack_from("<i", code, i + 1)[0])
    for m in re.finditer(rb"\x0f[\x80-\x8f]", code):
        i = m.start()
        if i + 6 > len(code):
            continue
        site = IMAGE_BASE + code_rva + i
        targets.append(site + 6 + struct.unpack_from("<i", code, i + 2)[0])

    pointers = set()
    for m in re.finditer(rb"\x01\x00\x00\x00", data):
        i = m.start()
        if i < 4:
            continue
        low = struct.unpack_from("<I", data, i - 4)[0]
        value = 0x100000000 + low
        if IMAGE_BASE <= value < 0x14D000000:
            pointers.add(value)

    targets.sort()
    ptrs = sorted(pointers)
    _REF_CACHE = (key, targets, ptrs)
    return targets, ptrs


def _count_between(values: list[int], lo: int, hi: int) -> int:
    return bisect.bisect_left(values, hi) - bisect.bisect_left(values, lo)


def _values_between(values: list[int], lo: int, hi: int) -> list[int]:
    return values[bisect.bisect_left(values, lo) : bisect.bisect_left(values, hi)]


def _cave_candidates(data: bytes | bytearray, min_size: int) -> list[dict]:
    global LAST_REFERENCES
    sections, code_raw, code_rsize, code_rva = _code_section(data)
    targets, ptrs = _reference_sets(data, code_raw, code_rsize, code_rva)
    LAST_REFERENCES = sorted(set(targets) | set(ptrs))
    candidates = []
    for m in re.finditer(
        b"\xcc{%d,}" % min_size, data[code_raw : code_raw + code_rsize]
    ):
        start = code_raw + m.start()
        stop = code_raw + m.end()
        length = stop - start
        section, flags = _section_for(sections, start)
        executable = bool(flags & IMAGE_SCN_MEM_EXECUTE)
        before = data[start - 1] if start else 0
        after = data[stop] if stop < len(data) else 0
        va = IMAGE_BASE + code_rva + (start - code_raw)
        prefix = min(CAVE_PREFIX, length)
        prefix_refs = _count_between(targets, va, va + prefix) + _count_between(
            ptrs, va, va + prefix
        )
        total_refs = _count_between(targets, va, va + length) + _count_between(
            ptrs, va, va + length
        )
        refs = sorted(
            set(_values_between(targets, va, va + length))
            | set(_values_between(ptrs, va, va + length))
        )
        boundary_ok = before in (0xC3, 0xC2)
        candidates.append(
            {
                "start": start,
                "length": length,
                "va": va,
                "section": section,
                "exec": executable,
                "writable": bool(flags & 0x80000000),
                "before": before,
                "after": after,
                "refs": refs,
                "prefix_refs": prefix_refs,
                "total_refs": total_refs,
                "boundary": boundary_ok,
                "safe": executable and boundary_ok and prefix_refs == 0,
            }
        )
    return candidates


def _pick_caves(
    data: bytes | bytearray,
    min_size: int,
    count: int,
    exclude: tuple[int, int] | None,
) -> list[dict]:
    runs = _cave_candidates(data, min_size)
    if exclude is not None:
        runs = [
            r
            for r in runs
            if r["start"] + r["length"] <= exclude[0] or r["start"] >= exclude[1]
        ]
    safe = [r for r in runs if r["safe"]]
    safe.sort(key=lambda r: r["length"], reverse=True)
    return safe[:count]


def find_cc_cave(
    data: bytes | bytearray, min_size: int = 32, exclude: tuple[int, int] | None = None
) -> tuple[int, int] | None:
    """Return (offset, length) of the largest safe CC-padded region in .rdata."""
    global LAST_CAVE_INFO
    picked = _pick_caves(data, min_size, 1, exclude)
    if not picked:
        return None
    LAST_CAVE_INFO = picked[0]
    return picked[0]["start"], picked[0]["length"]


def _free_spans(candidate: dict, min_size: int) -> list[tuple[int, int]]:
    """Split one CC run around its references, leaving the referenced byte
    and a small margin untouched."""
    start = candidate["start"]
    end = start + candidate["length"]
    spans = []
    cursor = start
    for ref_va in candidate["refs"]:
        ref_off = start + (ref_va - candidate["va"])
        if ref_off > cursor:
            spans.append((cursor, ref_off - cursor))
        cursor = max(cursor, ref_off + CAVE_REF_MARGIN)
    if end > cursor:
        spans.append((cursor, end - cursor))
    return [(o, n) for o, n in spans if n >= min_size]


def find_cc_caves(
    data: bytes | bytearray,
    min_size: int,
    count: int,
    exclude: tuple[int, int] | None = None,
) -> list[tuple[int, int]]:
    """Up to count reference-free CC-padded spans in .rdata, largest first.

    Side thunks must not land on a branch target or pointer, so each run is
    split at its detected references before sizing.
    """
    runs = _cave_candidates(data, min_size)
    if exclude is not None:
        runs = [
            r
            for r in runs
            if r["start"] + r["length"] <= exclude[0] or r["start"] >= exclude[1]
        ]
    spans = []
    for r in runs:
        if r["exec"]:
            spans.extend(_free_spans(r, min_size))
    spans.sort(key=lambda s: s[1], reverse=True)
    return spans[:count]


def locate_game_dir(hint: str | None = None) -> str | None:
    """Try to find the SMT5V install folder."""
    candidates: list[str] = []

    if hint:
        candidates.append(hint)

    # Common Steam library roots (Windows)
    if platform.system() == "Windows":
        for drive in "CDEFGH":
            candidates.append(
                os.path.join(
                    f"{drive}:\\", "SteamLibrary", "steamapps", "common", "SMT5V"
                )
            )
            candidates.append(
                os.path.join(
                    f"{drive}:\\",
                    "Program Files (x86)",
                    "Steam",
                    "steamapps",
                    "common",
                    "SMT5V",
                )
            )
            candidates.append(
                os.path.join(
                    f"{drive}:\\",
                    "Program Files",
                    "Steam",
                    "steamapps",
                    "common",
                    "SMT5V",
                )
            )

    # Check if we're already inside the game tree
    here = os.path.abspath(os.path.dirname(__file__))
    parts = here.replace("\\", "/").split("/")
    for i, p in enumerate(parts):
        if p.upper() == "SMT5V":
            candidates.insert(0, os.sep.join(parts[: i + 1]))

    for c in candidates:
        exe = os.path.join(c, EXE_SUBPATH)
        if os.path.isfile(exe):
            return c

    return None


def find_repak() -> str | None:
    """Locate the bundled repak binary (fall back to one on PATH)."""
    here = os.path.abspath(os.path.dirname(__file__))
    if platform.system() == "Windows":
        bundled = os.path.join(here, "repak", "win64", "repak.exe")
    else:
        bundled = os.path.join(here, "repak", "linux64", "repak")
    if os.path.isfile(bundled):
        return bundled
    return shutil.which("repak")


def _repak_error_message(err: str) -> str:
    """Turn repak's stderr into a user-facing reason."""
    if "oodle" in err.lower():
        return (
            "repak needs the Oodle runtime (oo2core_9_win64.dll), which it "
            "downloads on first use. Allow repak.exe through the firewall and "
            "run the installer again; later runs work offline."
        )
    return err or "unknown error"


def run_repak(repak: str, *args: str) -> bytes:
    """Run repak, returning stdout bytes. Raises RuntimeError on failure."""
    import subprocess

    try:
        proc = subprocess.run([repak, *args], capture_output=True, check=False)
    except OSError as exc:
        raise RuntimeError(f"could not run repak: {exc}") from exc
    if proc.returncode != 0:
        err = proc.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"repak {args[0]} failed: {_repak_error_message(err)}")
    return proc.stdout


def build_miracle_pak(game_dir: str) -> None:
    """Extract GodParameterDataTable from the user's pakchunk0, apply the
    NG+ edits (F5=1, F6=0 for the unlocked miracle rows), and pack it as
    an override pak. Raises RuntimeError with a user-facing reason."""
    import tempfile

    paks_dir = os.path.join(game_dir, PAKS_SUBPATH)
    src_pak = os.path.join(paks_dir, SOURCE_PAK)
    if not os.path.isfile(src_pak):
        raise RuntimeError(f"{SOURCE_PAK} not found in {paks_dir}")

    repak = find_repak()
    if repak is None:
        raise RuntimeError(
            "bundled repak tool not found (repak/ folder missing from the mod bundle)"
        )

    def get_entry(suffix: str) -> bytes:
        entry = GP_TABLE_ENTRY + suffix
        try:
            return run_repak(repak, "get", src_pak, entry)
        except RuntimeError:
            # Fall back to searching the raw pak listing (no prefix
            # stripping) in case the entry path layout differs from the
            # expected mount point.
            listing = run_repak(repak, "list", "--strip-prefix", "", src_pak)
            base = ("GodParameterDataTable" + suffix).encode()
            for line in listing.splitlines():
                if line.strip().endswith(base):
                    return run_repak(
                        repak,
                        "get",
                        "--strip-prefix",
                        "",
                        src_pak,
                        line.strip().decode(),
                    )
            raise

    gp_data = bytearray(get_entry(".uexp"))
    gp_uasset = get_entry(".uasset")

    needed = 89 + max(22, 23, 30, 31) * 20 + 12
    if len(gp_data) < needed:
        raise RuntimeError(
            f"GodParameterDataTable.uexp is smaller than "
            f"expected ({len(gp_data)} bytes) — game update?"
        )

    for idx in [22, 23, 30, 31]:
        goff = 89 + idx * 20
        gp_data[goff + 7] = 1
        struct.pack_into("<I", gp_data, goff + 8, 0)

    staging = tempfile.mkdtemp(prefix="smtvv_gp_")
    try:
        table_dir = os.path.join(staging, *GP_TABLE_ENTRY.split("/")[:-1])
        os.makedirs(table_dir, exist_ok=True)
        with open(os.path.join(table_dir, "GodParameterDataTable.uexp"), "wb") as fh:
            fh.write(gp_data)
        with open(os.path.join(table_dir, "GodParameterDataTable.uasset"), "wb") as fh:
            fh.write(gp_uasset)

        pak_out = os.path.join(paks_dir, MIRACLE_PAK)
        pak_tmp = pak_out + ".tmp"
        try:
            run_repak(repak, "pack", "--version", "V11", staging, pak_tmp)
            os.replace(pak_tmp, pak_out)
        finally:
            if os.path.isfile(pak_tmp):
                os.remove(pak_tmp)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def check_tables(game_dir: str, repak: str | None) -> None:
    """Report the data tables the overrides depend on, without writing."""
    src = os.path.join(game_dir, PAKS_SUBPATH, SOURCE_PAK)
    if not os.path.isfile(src):
        print(f"  [missing] {SOURCE_PAK}")
        return
    if repak is None:
        print("  [skip] bundled repak tool not found")
        return
    for label, entry, minimum in (
        ("GodParameterDataTable", GP_TABLE_ENTRY + ".uexp", 1000),
        ("ItemTable", shop_pak.ITEM_TABLE + ".uexp", 22000),
        ("BP_EstomaData", estoma.ESTOMA_ASSET + ".uexp", 208),
    ):
        try:
            blob = run_repak(repak, "get", src, entry)
        except RuntimeError as exc:
            print(f"  [missing] {label}: {exc}")
            continue
        state = "ok" if len(blob) >= minimum else "size"
        print(f"  [{state}] {label}: {len(blob):,} bytes")
    try:
        listing = run_repak(repak, "list", src).decode(errors="replace")
        count = sum(
            1
            for line in listing.splitlines()
            if reveal.MINIMAP_PREFIX in line and line.endswith(".uasset")
        )
    except RuntimeError as exc:
        print(f"  [missing] minimap tables: {exc}")
    else:
        print(f"  [{'ok' if count else 'missing'}] MinimapIcon tables: {count}")


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _patched_markers() -> tuple[tuple[int, bytes], ...]:
    """Sites whose bytes prove the executable has already been patched."""
    return (
        (MIMAN_POS_CHECK_OFFSET, b"\xb0\x01\xc3"),
        (DEVIL_COST_OFFSET, b"\x33\xc0\xc3"),
        (gameplay_patches.off(leylines.POI_VISIBLE_SITE), b"\xe9"),
    )


def _has_patched_markers(path: str) -> bool:
    with open(path, "rb") as fh:
        for offset, marker in _patched_markers():
            fh.seek(offset)
            if fh.read(len(marker)) == marker:
                return True
    return False


def _choose_source(
    live_hash: str,
    original_hash: str | None,
    patched_hash: str | None,
    patched_markers: bool,
) -> tuple[str, bool]:
    """Return ("live" | "original", refresh_backup).

    "live" means the live executable is a new unpatched build and must become
    the new .original backup. "original" means the existing backup is safe.
    """
    if patched_hash is not None and live_hash == patched_hash:
        if original_hash is None:
            raise RuntimeError(
                "the live executable is the patched build but the .original "
                "backup is missing; verify the game files or restore it"
            )
        return "original", False
    if original_hash is None:
        if patched_markers:
            raise RuntimeError(
                "the live executable looks patched but the .original backup is "
                "missing; verify the game files or restore it"
            )
        return "live", True
    if live_hash == original_hash:
        return "original", False
    if patched_markers:
        raise RuntimeError(
            "the live executable differs from both backups and still contains "
            "patched markers; refusing to patch a partial install"
        )
    return "live", True


def _verification_sites(
    data: bytes | bytearray,
) -> dict[str, list[tuple[int, int, bytes]]]:
    """Every site a feature is expected to change, from the feature registry."""
    return patch_manifest.verification_sites(data)


def _verify_patched(
    path: str,
    sites: dict[str, list[tuple[int, int, bytes]]],
    results: dict[str, bool],
    game_dir: str,
) -> list[str]:
    """Re-read the patched executable and check every applied site/pak."""
    with open(path, "rb") as fh:
        patched = fh.read()
    failures = []
    for feature, entries in sites.items():
        if not results.get(feature):
            continue
        for offset, length, original in entries:
            if patched[offset : offset + length] == original:
                failures.append(f"{feature}: site 0x{offset:08X} was not changed")
    repak = find_repak()
    for feature, pak in patch_manifest.FEATURE_PAKS:
        if results.get(feature):
            pak_path = os.path.join(game_dir, PAKS_SUBPATH, pak)
            if not os.path.isfile(pak_path):
                failures.append(f"{feature}: missing data pak {pak}")
            elif repak is not None:
                failures.extend(patch_manifest.validate_pak(repak, pak_path, feature))
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="SMT5V: Vengeance - Freeplay Patcher")
    parser.add_argument(
        "--game-dir", default=None, help="Path to the SMT5V install folder"
    )
    parser.add_argument(
        "--no-essences", action="store_true", help="Skip the Reusable Essences patch"
    )
    parser.add_argument(
        "--no-heal", action="store_true", help="Skip the Leyline Auto-Heal patch"
    )
    parser.add_argument(
        "--no-mimans", action="store_true", help="Skip the Miman Position Reveal patch"
    )
    parser.add_argument(
        "--no-miracles", action="store_true", help="Skip the NG+ Miracles Unlock patch"
    )
    parser.add_argument(
        "--no-compendium", action="store_true", help="Skip the Free Compendium patch"
    )
    parser.add_argument(
        "--no-refill", action="store_true", help="Skip the Battle Refill patch"
    )
    parser.add_argument(
        "--stockpile",
        action="store_true",
        help="Install Stockpile instead of Battle Refill",
    )
    parser.add_argument(
        "--no-masakado", action="store_true", help="Skip the Masakado Unlock patch"
    )
    parser.add_argument(
        "--no-intro", action="store_true", help="Skip the Skip Intro patch"
    )
    parser.add_argument(
        "--no-magatsuhi", action="store_true", help="Skip the Full Magatsuhi patch"
    )
    parser.add_argument(
        "--magatsuhi-chain",
        action="store_true",
        help="Refill Magatsuhi once per chain instead of at every battle",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Experimental: restore party HP/MP every battle step",
    )
    parser.add_argument(
        "--no-shop",
        action="store_true",
        help="Leave the shop stock and prices untouched",
    )
    for _category in shop_pak.CATEGORIES:
        parser.add_argument(
            f"--shop-{_category}",
            choices=shop_pak.MODES,
            default="immediate" if _category == "growth" else "default",
            help=f"Shop {_category}: default, free or immediate",
        )
    parser.add_argument(
        "--no-jump", action="store_true", help="Skip the Superjump patch"
    )
    parser.add_argument(
        "--no-markers", action="store_true", help=argparse.SUPPRESS
    )  # removed feature; accepted for old scripts
    parser.add_argument(
        "--no-newborn",
        action="store_true",
        help="Skip the Newborn Clears Compendium patch",
    )
    parser.add_argument(
        "--no-estoma", action="store_true", help="Skip the Free Estoma patch"
    )
    parser.add_argument(
        "--leylines",
        action="store_true",
        help="Show leyline founts through fog on the main map",
    )
    parser.add_argument(
        "--reveal",
        choices=reveal.MODES,
        default="none",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the patches against the game without writing anything",
    )
    parser.add_argument(
        "--autosave-slot",
        type=int,
        metavar="N",
        choices=range(autosave.SLOT_MIN, autosave.SLOT_MAX + 1),
        help="Save to slot N (1-20) after every battle",
    )
    args = parser.parse_args()
    check = args.check

    do_essences = not args.no_essences
    do_heal = not args.no_heal
    do_mimans = not args.no_mimans
    do_miracles = not args.no_miracles
    do_compendium = not args.no_compendium
    do_stockpile = args.stockpile
    do_refill = not args.no_refill and not do_stockpile
    do_jump = not args.no_jump
    do_magatsuhi = not args.no_magatsuhi
    do_refresh = args.refresh
    do_intro = not args.no_intro
    do_masakado = not args.no_masakado
    shop_modes = {
        category: getattr(args, f"shop_{category}") for category in shop_pak.CATEGORIES
    }
    if args.no_shop:
        shop_modes = {category: "default" for category in shop_pak.CATEGORIES}
    do_shop = shop_pak.has_changes(shop_modes)
    do_newborn = not args.no_newborn
    do_estoma = not args.no_estoma
    do_leylines = args.leylines
    do_reveal = args.reveal != "none" and not do_leylines
    if args.leylines and args.reveal != "none":
        print("  NOTE: --leylines replaces the legacy --reveal pak; ignoring --reveal")
    autosave_slot = args.autosave_slot
    results: dict[str, bool] = {}
    failed: list[str] = []
    selected = {
        "essences": do_essences,
        "heal": do_heal,
        "mimans": do_mimans,
        "leylines": do_leylines,
        "miracles": do_miracles,
        "compendium": do_compendium,
        "refill": do_refill,
        "stockpile": do_stockpile,
        "jump": do_jump,
        "magatsuhi": do_magatsuhi,
        "refresh": do_refresh,
        "shop": do_shop,
        "intro": do_intro,
        "masakado": do_masakado,
        "newborn": do_newborn,
        "estoma": do_estoma,
        "autosave": autosave_slot is not None,
        "reveal": do_reveal,
    }

    cave_budget: dict[str, int] = {}
    cave_mark = 0

    def ok(key: str) -> None:
        nonlocal cave_mark
        results[key] = True
        cave_budget[key] = next_cave_off - cave_mark
        cave_mark = next_cave_off

    def fail(key: str) -> None:
        if key not in failed:
            failed.append(key)

    game_dir = locate_game_dir(args.game_dir)
    if game_dir is None:
        print("ERROR: Could not find the SMT5V install folder.")
        print("       Use --game-dir <path> to specify it manually.")
        sys.exit(1)

    exe_path = os.path.join(game_dir, EXE_SUBPATH)
    bak_path = exe_path + ".original"
    out_path = exe_path + ".patched"

    print("=" * 62)
    print(f"  SMT5V: Vengeance - Freeplay Patcher v{MOD_VERSION}")
    print("=" * 62)
    print(f"  Game folder : {game_dir}")
    print(f"  Executable  : {exe_path}")
    print()

    # ------------------------------------------------------------------
    # Tidy up state left by earlier installs. The executable is always
    # rebuilt from the original backup, so the override pak must match
    # the patches selected *this* run: remove it here and rebuild it
    # below only if the miracles patch is enabled and succeeds.
    # ------------------------------------------------------------------
    if not check:
        for pak in (
            MIRACLE_PAK,
            shop_pak.SHOP_PAK,
            boot_pak.BOOT_PAK,
            quest_pak.QUEST_PAK,
            LEGACY_MAP_PAK,
            newborn.NEWBORN_PAK,
            stockpile.STOCK_PAK,
            estoma.ESTOMA_PAK,
            reveal.REVEAL_PAK,
        ):
            stale_pak = os.path.join(game_dir, PAKS_SUBPATH, pak)
            if os.path.isfile(stale_pak):
                print(f"  Removing previous {pak} (rebuilt if selected)")
                os.remove(stale_pak)

    legacy_extract = os.path.join(game_dir, PAKS_SUBPATH, "pakchunk0-WindowsNoEditor")
    if os.path.isdir(legacy_extract):
        print(
            f"  NOTE: extracted game data at "
            f"Paks{os.sep}pakchunk0-WindowsNoEditor{os.sep} is no longer"
        )
        print("        needed by this mod and can be deleted to free space.")

    if not os.path.isfile(exe_path):
        print(f"\n  ERROR: executable not found: {exe_path}")
        sys.exit(1)

    live_hash = _sha256_file(exe_path)
    original_hash = _sha256_file(bak_path) if os.path.isfile(bak_path) else None
    patched_hash = _sha256_file(out_path) if os.path.isfile(out_path) else None
    patched_markers = _has_patched_markers(exe_path)

    def _short(value: str | None) -> str:
        return value[:12] if value else "missing"

    print("  Source check :")
    print(f"    live        {_short(live_hash)}")
    print(f"    original    {_short(original_hash)}")
    print(f"    patched     {_short(patched_hash)}")
    try:
        source_kind, refresh_backup = _choose_source(
            live_hash, original_hash, patched_hash, patched_markers
        )
    except RuntimeError as exc:
        print(f"\n  ERROR: {exc}")
        sys.exit(1)

    source = exe_path if source_kind == "live" else bak_path
    if source_kind == "live":
        print("  Using live executable; the .original backup will be refreshed.")
        if check:
            print("  Check only: a real run would replace .original with this build.")
    else:
        print("  Using original backup.")
    if not check and os.path.isfile(out_path):
        os.remove(out_path)
    print(f"  Reading {os.path.basename(source)} ...")
    with open(source, "rb") as fh:
        data = bytearray(fh.read())
    gameplay_patches.set_image_layout(data)
    gameplay_patches.set_iat_slots(pe_imports.import_slots(data))
    relocation_notes = patch_manifest.relocate(data)
    if relocation_notes:
        print("  Relocation   : some sites could not be resolved")
        for note in relocation_notes:
            print(f"    {note}")
    print(f"  File size: {len(data):,} bytes")
    verify_sites = _verification_sites(data)

    if check:
        print("\n  Data tables:")
        check_tables(game_dir, find_repak())

    # ------------------------------------------------------------------
    # Find code cave (shared by all patches)
    # ------------------------------------------------------------------
    try:
        cave = find_cc_cave(data, min_size=128)
    except RuntimeError as exc:
        print(f"\n  ERROR: {exc}")
        sys.exit(1)
    if cave is None:
        print("\n  ERROR: no suitable CC cave found in .rdata.")
        sys.exit(1)
    cave_off, cave_len = cave
    gameplay_patches.set_cave_references(LAST_REFERENCES)
    info = LAST_CAVE_INFO
    if info is not None:
        print(
            f"  Cave check  : 0x{cave_off:08X}  len={cave_len}  "
            f"section={info['section']}  exec={'yes' if info['exec'] else 'no'}  "
            f"write={'no' if not info['writable'] else 'yes'}  "
            f"boundary={info['before']:02X}  "
            f"refs(first {CAVE_PREFIX})={info['prefix_refs']}  "
            f"refs(run)={info['total_refs']}  "
            f"refs(scan)={len(LAST_REFERENCES)}"
        )
        if not info["safe"]:
            print("  WARNING: cave safety checks did not all pass")
    for label, addr, size in _scratch_regions():
        _assert_writable(data, addr, label)
        offset = gameplay_patches.off(addr)
        data[offset : offset + size] = b"\0" * size
    if autosave_slot is not None:
        for label, addr in (
            ("SAVE_HEADERS", autosave.SAVE_HEADERS),
            ("SAVE_HEADER_COUNT", autosave.SAVE_HEADER_COUNT),
            ("FNAME_BLOCKS", autosave.FNAME_BLOCKS),
        ):
            _assert_mapped(data, addr, label)
    next_cave_off = cave_off
    cave_mark = cave_off
    patch_num = 0
    enabled = [
        n
        for n, on in [
            ("Essences", do_essences),
            ("Heal", do_heal),
            ("Mimans", do_mimans),
            ("Leylines", do_leylines),
            ("Reveal", do_reveal),
            ("Miracles", do_miracles),
            ("Compendium", do_compendium),
            ("Refill", do_refill),
            ("Stockpile", do_stockpile),
            ("Jump", do_jump),
            ("Magatsuhi", do_magatsuhi),
            ("Party Refresh", do_refresh),
            ("Shop", do_shop),
            ("Intro", do_intro),
            ("Masakado", do_masakado),
            ("Newborn", do_newborn),
            ("Estoma", do_estoma),
            ("Autosave", autosave_slot is not None),
        ]
        if on
    ]
    total = len(enabled)

    if total == 0:
        print("\n  All patches disabled — nothing to do.")
        sys.exit(0)

    print(f"\n  Patches selected: {', '.join(enabled)}")

    if check:
        report = signatures.audit(data, _verification_sites(data))
        unique, total = signatures.summarise(report)
        print(f"  Signature audit : {unique}/{total} sites unique")
        for feature, entries in report.items():
            bad = [entry for entry in entries if not entry.unique]
            if bad:
                print(f"    {feature:<10} {len(bad)} non-unique")

    # ==================================================================
    # PATCH: Reusable Essences
    # ==================================================================
    if do_essences:
        actual = bytes(data[TRAMP_OFFSET : TRAMP_OFFSET + 5])
        if actual != TRAMP_ORIG:
            print(f"\n  ERROR: Essence AOB mismatch at 0x{TRAMP_OFFSET:08X}")
            sys.exit(1)

        orig_disp = struct.unpack_from("<i", data, TRAMP_OFFSET + 1)[0]
        tramp_va = file_to_va(TRAMP_OFFSET)
        orig_target = tramp_va + 5 + orig_disp
        p_off = next_cave_off
        p_va = file_to_va(p_off)

        sc = bytearray()
        sc += b"\x81\xf9"
        sc += struct.pack("<I", ESSENCE_ID_MIN)  # cmp ecx, 311
        sc += b"\x72"
        jb_pos = len(sc)
        sc += b"\x00"  # jb .pass
        sc += b"\x81\xf9"
        sc += struct.pack("<I", ESSENCE_ID_MAX)  # cmp ecx, 615
        sc += b"\x77"
        ja_pos = len(sc)
        sc += b"\x00"  # ja .pass
        sc += b"\xc3"  # ret (skip)
        not_ess = len(sc)
        sc[jb_pos] = not_ess - (jb_pos + 1)
        sc[ja_pos] = not_ess - (ja_pos + 1)
        sc += b"\xe9"  # jmp original
        sc += struct.pack("<i", orig_target - (p_va + len(sc) + 4))

        for i in range(len(sc)):
            assert data[p_off + i] == 0xCC
        next_cave_off = gameplay_patches._place(
            data,
            p_off,
            cave_off + cave_len,
            bytes(sc),
            base_va=p_va,
            check_refs=True,
        )
        struct.pack_into("<i", data, TRAMP_OFFSET + 1, p_va - (tramp_va + 5))

        patch_num += 1
        print(f"\n  [{patch_num}/{total}] Reusable Essences")
        print(f"    Code cave     : 0x{p_off:08X}  ({len(sc)} bytes)")
        print(f"    Trampoline    : 0x{TRAMP_OFFSET:08X}  -> cave")
        ok("essences")

    # ==================================================================
    # PATCH: Leyline Auto-Heal
    # ==================================================================
    if do_heal:
        ry_actual = bytes(data[RYUKETSU_TRAMP_OFFSET : RYUKETSU_TRAMP_OFFSET + 5])
        cure_va = (
            _heal_cure_target(data)
            if ry_actual == RYUKETSU_TRAMP_ORIG
            else None
        )
        if ry_actual != RYUKETSU_TRAMP_ORIG:
            print("\n  WARNING: Leyline AOB mismatch - skipping heal patch")
            fail("heal")
        elif cure_va is None:
            print("\n  WARNING: PartyAllCure AOB mismatch - skipping heal patch")
            fail("heal")
        else:
            ry_disp = struct.unpack_from("<i", data, RYUKETSU_TRAMP_OFFSET + 1)[0]
            ry_tramp_va = file_to_va(RYUKETSU_TRAMP_OFFSET)
            ry_orig_tgt = ry_tramp_va + 5 + ry_disp

            h_off = next_cave_off
            h_va = file_to_va(h_off)
            hsc = _heal_code(cure_va, ry_orig_tgt, h_va)
            next_cave_off = gameplay_patches._place(
                data,
                h_off,
                cave_off + cave_len,
                hsc,
                base_va=h_va,
                check_refs=True,
            )
            struct.pack_into(
                "<i", data, RYUKETSU_TRAMP_OFFSET + 1, h_va - (ry_tramp_va + 5)
            )

            patch_num += 1
            print(f"\n  [{patch_num}/{total}] Leyline Auto-Heal")
            print(f"    Code cave     : 0x{h_off:08X}  ({len(hsc)} bytes)")
            print(f"    Trampoline    : 0x{RYUKETSU_TRAMP_OFFSET:08X}  -> cave")
            ok("heal")

    # ==================================================================
    # PATCH: Miman Reveal
    # ==================================================================
    if do_mimans:
        miman_offset = signatures.resolve(
            data, MIMAN_POS_CHECK_OFFSET, MIMAN_POS_CHECK_ORIG
        )
        if miman_offset is None:
            print(
                f"\n  WARNING: Miman AOB mismatch at "
                f"0x{MIMAN_POS_CHECK_OFFSET:08X} - skipping"
            )
            fail("mimans")
        else:
            data[miman_offset : miman_offset + 3] = b"\xb0\x01\xc3"
            patch_num += 1
            print(f"\n  [{patch_num}/{total}] Miman Reveal")
            print(f"    Position check: 0x{miman_offset:08X}  -> true")
            ok("mimans")

    # ==================================================================
    # PATCH: Leyline Founts on the Main Map
    # ==================================================================
    if do_leylines:
        start = next_cave_off
        try:
            result = leylines.patch_leylines(data, next_cave_off, cave_off + cave_len)
        except RuntimeError as exc:
            print(f"\n  WARNING: Leyline Founts skipped - {exc}")
            result = None
        if result is None:
            print("\n  WARNING: Leyline icon AOB mismatch - skipping")
            fail("leylines")
        else:
            next_cave_off = result
            patch_num += 1
            print(f"\n  [{patch_num}/{total}] Leyline Founts")
            print(f"    Code cave     : 0x{start:08X}  ({next_cave_off - start} bytes)")
            print("    Fog bypass    : E_MINIMAP_POI_TYPE_RYUKETSU")
            ok("leylines")

    # ==================================================================
    # PATCH: NG+ Miracles Unlock
    # ==================================================================
    if do_miracles:
        miracles_ok = True

        # 1. NOP the hardcoded "cmp ecx, 666; je BLOCK"
        expected_je = bytes([0x0F, 0x84])
        if data[MIRACLE_666_NOP_ADDR : MIRACLE_666_NOP_ADDR + 2] == expected_je:
            for i in range(6):
                data[MIRACLE_666_NOP_ADDR + i] = 0x90
        else:
            print("\n  WARNING: 666-block AOB mismatch — skipping NOP")
            miracles_ok = False

        # 2. Hook IsAddedSelectableGodParameterSkill -> true for NG+ IDs
        ma_actual = bytes(data[MIRACLE_ADDED_TRAMP : MIRACLE_ADDED_TRAMP + 5])
        ms_actual = bytes(data[MIRACLE_STATE_TRAMP : MIRACLE_STATE_TRAMP + 5])

        if ma_actual != MIRACLE_ADDED_ORIG:
            print("\n  WARNING: IsAdded AOB mismatch")
            miracles_ok = False
        if ms_actual != MIRACLE_STATE_ORIG:
            print("\n  WARNING: GetState AOB mismatch")
            miracles_ok = False

        if miracles_ok:
            # Hook IsAddedSelectable
            ma_disp = struct.unpack_from("<i", data, MIRACLE_ADDED_TRAMP + 1)[0]
            ma_va = file_to_va(MIRACLE_ADDED_TRAMP)
            ma_tgt = ma_va + 5 + ma_disp

            mc1 = next_cave_off
            mc1_va = file_to_va(mc1)
            sc_a = bytearray()
            je_a = []
            for mid in MIRACLE_UNLOCK_IDS:
                sc_a += b"\x83\xf9" + bytes([mid]) + b"\x74"
                je_a.append(len(sc_a))
                sc_a += b"\x00"
            sc_a += b"\xe9"
            sc_a += struct.pack("<i", ma_tgt - (mc1_va + len(sc_a) + 4))
            yes_a = len(sc_a)
            for jp in je_a:
                sc_a[jp] = yes_a - (jp + 1)
            sc_a += b"\xb0\x01\xc3"

            next_cave_off = gameplay_patches._place(
                data,
                mc1,
                cave_off + cave_len,
                bytes(sc_a),
                base_va=mc1_va,
                check_refs=True,
            )
            data[MIRACLE_ADDED_TRAMP] = 0xE9
            struct.pack_into(
                "<i", data, MIRACLE_ADDED_TRAMP + 1, mc1_va - (ma_va + 5)
            )

            # Hook GetGodParameterSkillState -> return 4 (purchasable)
            ms_disp = struct.unpack_from("<i", data, MIRACLE_STATE_TRAMP + 1)[0]
            ms_va = file_to_va(MIRACLE_STATE_TRAMP)
            ms_tgt = ms_va + 5 + ms_disp

            mc2 = next_cave_off
            mc2_va = file_to_va(mc2)
            sc_s = bytearray()
            je_s = []
            for mid in MIRACLE_UNLOCK_IDS:
                sc_s += b"\x83\xf9" + bytes([mid]) + b"\x74"
                je_s.append(len(sc_s))
                sc_s += b"\x00"
            sc_s += b"\xe9"
            sc_s += struct.pack("<i", ms_tgt - (mc2_va + len(sc_s) + 4))
            yes_s = len(sc_s)
            for jp in je_s:
                sc_s[jp] = yes_s - (jp + 1)
            sc_s += b"\xb0\x04\xc3"

            next_cave_off = gameplay_patches._place(
                data,
                mc2,
                cave_off + cave_len,
                bytes(sc_s),
                base_va=mc2_va,
                check_refs=True,
            )
            data[MIRACLE_STATE_TRAMP] = 0xE9
            struct.pack_into(
                "<i", data, MIRACLE_STATE_TRAMP + 1, mc2_va - (ms_va + 5)
            )

            patch_num += 1
            print(f"\n  [{patch_num}/{total}] NG+ Miracles Unlock")
            print(
                f"    Code caves    : 0x{mc1:08X} ({len(sc_a)}B)"
                f" + 0x{mc2:08X} ({len(sc_s)}B)"
            )
            print(f"    NOP 666-block : 0x{MIRACLE_666_NOP_ADDR:08X}")

        # 3. Build data pak from the user's own game data
        #    (F5=1, F6=0, keep original Glory costs)
        if miracles_ok:
            try:
                if check:
                    print("    Data pak      : check only")
                    ok("miracles")
                else:
                    build_miracle_pak(game_dir)
                    print(f"    Data pak      : {MIRACLE_PAK}")
                    ok("miracles")
            except RuntimeError as exc:
                print(f"    WARNING: NG+ miracle data pak not built — {exc}")
                print(
                    "             The miracle shop hooks are still "
                    "installed, but some NG+ miracles may stay locked."
                )
                fail("miracles")
        else:
            fail("miracles")

    # ==================================================================
    # PATCH: Free Compendium
    # ==================================================================
    if do_compendium:
        compendium_offset = signatures.resolve(data, DEVIL_COST_OFFSET, DEVIL_COST_ORIG)
        if compendium_offset is None:
            print(
                f"\n  WARNING: Compendium AOB mismatch at "
                f"0x{DEVIL_COST_OFFSET:08X} - skipping"
            )
            fail("compendium")
        else:
            data[compendium_offset : compendium_offset + 3] = b"\x33\xc0\xc3"
            patch_num += 1
            print(f"\n  [{patch_num}/{total}] Free Compendium")
            print(f"    Cost formula  : 0x{compendium_offset:08X}  -> 0")
            ok("compendium")

    # ==================================================================
    # PATCH: Battle Refill / Superjump / Full Magatsuhi
    # ==================================================================
    cave_end = cave_off + cave_len
    slack = None
    if do_stockpile or do_magatsuhi or do_refresh or autosave_slot is not None:
        trial = bytearray(data)
        slack = gameplay_patches.slack_caves(trial)
        data[:] = trial  # padding refilled with CC only
        del trial

    gameplay_patches.DEFER_SETNEXTSTEP = True
    gameplay_patches.DEFERRED_STEPS.clear()

    if do_refresh:
        cure_va = _heal_cure_target(data)
        if cure_va is None:
            print("\n  WARNING: PartyAllCure AOB mismatch - skipping Party Refresh")
            fail("refresh")
        else:
            try:
                step_va = gameplay_patches.patch_party_refresh(
                    data, slack, cure_va
                )
            except RuntimeError as exc:
                print(f"\n  WARNING: Party Refresh skipped - {exc}")
                fail("refresh")
            else:
                gameplay_patches.DEFERRED_STEPS["refresh"] = step_va
                patch_num += 1
                print(f"\n  [{patch_num}/{total}] Party Refresh")
                print("    HP/MP         : restored every battle step")
                ok("refresh")

    # ==================================================================
    # PATCH: Stockpile (exe + item list pak; reads the ItemTable carry limits)
    # ==================================================================
    stockpile_ok = False
    if do_stockpile:
        repak = find_repak()
        try:
            if repak is None:
                raise RuntimeError("bundled repak tool not found")
            _item_asset, item_exp = stockpile.read_item_table(
                game_dir, PAKS_SUBPATH, SOURCE_PAK, repak, run_repak
            )
            limits = stockpile.battle_item_limits(item_exp)
            start = next_cave_off
            side = [
                [o, o + n]
                for o, n in find_cc_caves(
                    data, min_size=96, count=3, exclude=(cave_off, cave_end)
                )
            ]
            if slack:
                side += slack
            if not side:
                raise RuntimeError("no second code cave")
            trial = bytearray(data)  # applied only if the whole patch fits
            result = stockpile.patch_stockpile(
                trial, next_cave_off, cave_end, limits, side
            )
            if result is None:
                raise RuntimeError("AOB mismatch")
            data[:] = trial
            del trial
            next_cave_off = result
            stockpile_ok = True
            patch_num += 1
            print(f"\n  [{patch_num}/{total}] Stockpile")
            print(f"    Code cave     : 0x{start:08X}  ({next_cave_off - start} bytes)")
            print(
                f"    Battle items  : {len(limits)} can be stocked to {stockpile.STOCK_MAX}"
            )
        except RuntimeError as exc:
            print(f"\n  WARNING: Stockpile skipped - {exc}")
            fail("stockpile")
        if stockpile_ok:
            try:
                if check:
                    print("    Data pak      : check only")
                    ok("stockpile")
                else:
                    stockpile.build_stock_pak(
                        game_dir, PAKS_SUBPATH, SOURCE_PAK, repak, run_repak
                    )
                    print(f"    Data pak      : {stockpile.STOCK_PAK}")
                    ok("stockpile")
            except RuntimeError as exc:
                print(f"    WARNING: Stockpile data pak not built - {exc}")
                fail("stockpile")

    for on, label, builder in (
        (do_refill, "Battle Refill", gameplay_patches.patch_refill),
        (do_jump, "Superjump", gameplay_patches.patch_jump),
    ):
        if not on:
            continue
        start = next_cave_off
        result = builder(data, next_cave_off, cave_end)
        key = "refill" if label == "Battle Refill" else "jump"
        if result is None:
            print(f"\n  WARNING: {label} AOB mismatch - skipping")
            fail(key)
            continue
        next_cave_off = result
        patch_num += 1
        print(f"\n  [{patch_num}/{total}] {label}")
        print(f"    Code cave     : 0x{start:08X}  ({next_cave_off - start} bytes)")
        ok(key)

    # ==================================================================
    # PATCH: Full Magatsuhi / Autosave after battle (section padding caves)
    # ==================================================================
    if do_magatsuhi:
        try:
            trial = bytearray(data)  # applied only if the whole patch fits
            if not gameplay_patches.patch_magatsuhi(
                trial, slack, chain=args.magatsuhi_chain
            ):
                raise RuntimeError("AOB mismatch")
            data[:] = trial
            del trial
            patch_num += 1
            print(f"\n  [{patch_num}/{total}] Full Magatsuhi")
            ok("magatsuhi")
        except RuntimeError as exc:
            print(f"\n  WARNING: Full Magatsuhi skipped - {exc}")
            fail("magatsuhi")
    if autosave_slot is not None:
        area_labels = None
        try:
            repak = find_repak()
            if repak is None:
                raise RuntimeError("bundled repak tool not found")
            area_labels = autosave.read_area_labels(
                game_dir, PAKS_SUBPATH, SOURCE_PAK, repak, run_repak
            )
        except Exception as exc:  # noqa: BLE001 - optional labels, never fatal
            print(f"\n  NOTE: Autosave location names unavailable - {exc}")
        try:
            trial = bytearray(data)
            if not autosave.patch_autosave(trial, slack, autosave_slot, area_labels):
                raise RuntimeError("AOB mismatch")
            data[:] = trial
            del trial
            patch_num += 1
            print(f"\n  [{patch_num}/{total}] Autosave after battle")
            print(f"    Save slot     : {autosave_slot}")
            if area_labels:
                print(f"    Location names: {len(area_labels)}")
            ok("autosave")
        except RuntimeError as exc:
            print(f"\n  WARNING: Autosave skipped - {exc}")
            fail("autosave")

    if gameplay_patches.DEFERRED_STEPS:
        main_cave = [
            next_cave_off,
            cave_end,
            gameplay_patches.RDATA_VA - gameplay_patches.RDATA_RAW,
        ]
        try:
            gameplay_patches.patch_setnextstep(
                data, list(slack or []) + [main_cave]
            )
            next_cave_off = main_cave[0]
            print("\n  Shared battle-step dispatcher")
            print(
                f"    Hooks         : {', '.join(gameplay_patches.DEFERRED_STEPS)}"
            )
        except RuntimeError as exc:
            print(f"\n  WARNING: battle-step dispatcher did not fit - {exc}")
            for key in gameplay_patches.DEFERRED_STEPS:
                results[key] = False
                fail(key)
    gameplay_patches.DEFER_SETNEXTSTEP = False
    gameplay_patches.DEFERRED_STEPS.clear()

    # ==================================================================
    # PATCH: Shop stock and prices (data pak only)
    # ==================================================================
    if do_shop:
        patch_num += 1
        print(f"\n  [{patch_num}/{total}] Shop stock")
        repak = find_repak()
        try:
            if repak is None:
                raise RuntimeError("bundled repak tool not found")
            if check:
                print("    Data pak      : check only")
                ok("shop")
            else:
                shop_pak.build_shop_pak(
                    game_dir, PAKS_SUBPATH, SOURCE_PAK, repak, run_repak, shop_modes
                )
                print(f"    Data pak      : {shop_pak.SHOP_PAK}")
                ok("shop")
            print(
                "    Categories    : "
                + ", ".join(
                    f"{category}={mode}"
                    for category, mode in shop_modes.items()
                    if mode != "default"
                )
            )
        except RuntimeError as exc:
            print(f"    WARNING: shop data pak not built - {exc}")
            fail("shop")

    # ==================================================================
    # PATCH: Skip Intro (data pak + title refocus)
    # ==================================================================
    if do_intro:
        patch_num += 1
        print(f"\n  [{patch_num}/{total}] Skip Intro")
        intro_pak_ok = False
        repak = find_repak()
        try:
            if repak is None:
                raise RuntimeError("bundled repak tool not found")
            if check:
                print("    Data pak      : check only")
                intro_pak_ok = True
            else:
                boot_pak.build_boot_pak(
                    game_dir, PAKS_SUBPATH, SOURCE_PAK, repak, run_repak
                )
                print(f"    Data pak      : {boot_pak.BOOT_PAK}")
                intro_pak_ok = True
        except RuntimeError as exc:
            print(f"    WARNING: intro data pak not built - {exc}")
            fail("intro")
        main_cave = [
            next_cave_off,
            cave_end,
            gameplay_patches.RDATA_VA - gameplay_patches.RDATA_RAW,
        ]
        dest = gameplay_patches.patch_refocus(data, list(slack or []) + [main_cave])
        if dest is None:
            print("    WARNING: title refocus AOB mismatch - skipping")
            fail("intro")
        else:
            next_cave_off = main_cave[0]
            print(
                f"    Code cave     : 0x{dest:08X}  "
                f"(main cave free {cave_end - next_cave_off} bytes)"
            )
            if intro_pak_ok:
                ok("intro")
            else:
                fail("intro")

    # ==================================================================
    # PATCH: Masakado Unlock (data pak only)
    # ==================================================================
    if do_masakado:
        patch_num += 1
        print(f"\n  [{patch_num}/{total}] Masakado Unlock")
        repak = find_repak()
        try:
            if repak is None:
                raise RuntimeError("bundled repak tool not found")
            if check:
                print("    Data pak      : check only")
                ok("masakado")
            else:
                quest_pak.build_quest_pak(game_dir, PAKS_SUBPATH, repak, run_repak)
                print(f"    Data pak      : {quest_pak.QUEST_PAK}")
                ok("masakado")
        except RuntimeError as exc:
            print(f"    WARNING: quest data pak not built - {exc}")
            fail("masakado")

    # ==================================================================
    # PATCH: Newborn Clears Compendium (exe + text pak)
    # ==================================================================
    if do_newborn:
        start = next_cave_off
        result = newborn.patch_newborn(data, next_cave_off, cave_end)
        if result is None:
            print("\n  WARNING: Newborn Clears Compendium AOB mismatch - skipping")
            fail("newborn")
        else:
            next_cave_off = result
            patch_num += 1
            print(f"\n  [{patch_num}/{total}] Newborn Clears Compendium")
            print(f"    Code cave     : 0x{start:08X}  ({next_cave_off - start} bytes)")
            repak = find_repak()
            try:
                if repak is None:
                    raise RuntimeError("bundled repak tool not found")
                if check:
                    print("    Data pak      : check only")
                    ok("newborn")
                else:
                    newborn.build_newborn_pak(game_dir, PAKS_SUBPATH, repak, run_repak)
                    print(f"    Data pak      : {newborn.NEWBORN_PAK}")
                    ok("newborn")
            except RuntimeError as exc:
                print(f"    WARNING: carry-over text pak not built - {exc}")
                fail("newborn")

    # ==================================================================
    # PATCH: Free Estoma (data pak only)
    # ==================================================================
    if do_estoma:
        repak_tool = find_repak()
        try:
            if repak_tool is None:
                raise RuntimeError("bundled repak tool not found")
            patch_num += 1
            print(f"\n  [{patch_num}/{total}] Free Estoma")
            if check:
                print("    Data pak      : check only")
                ok("estoma")
            else:
                old_costs = estoma.build_estoma_pak(
                    game_dir, PAKS_SUBPATH, SOURCE_PAK, repak_tool, run_repak
                )
                print(f"    Data pak      : {estoma.ESTOMA_PAK}")
                print(
                    "    Costs zeroed  : "
                    + ", ".join(f"{name}={value}" for name, value in old_costs.items())
                )
                ok("estoma")
        except RuntimeError as exc:
            print(f"\n  WARNING: Free Estoma skipped - {exc}")
            fail("estoma")

    # ==================================================================
    # PATCH: Map Reveal (data pak only)
    # ==================================================================
    if do_reveal:
        patch_num += 1
        print(f"\n  [{patch_num}/{total}] Map Reveal")
        repak = find_repak()
        try:
            if repak is None:
                raise RuntimeError("bundled repak tool not found")
            if check:
                print("    Data pak      : check only")
                ok("reveal")
            else:
                changed = reveal.build_reveal_pak(
                    game_dir, PAKS_SUBPATH, SOURCE_PAK, repak, run_repak, args.reveal
                )
                print(f"    Data pak      : {reveal.REVEAL_PAK}")
                print(f"    Icons revealed: {changed}")
                ok("reveal")
        except RuntimeError as exc:
            print(f"    WARNING: map reveal pak not built - {exc}")
            fail("reveal")

    if cave_budget:
        print()
        print("  Cave budget (main code cave):")
        for key in sorted(
            cave_budget, key=lambda name: cave_budget[name], reverse=True
        ):
            print(f"    {key:<14} {cave_budget[key]:>5} bytes")
        free = max(0, cave_off + cave_len - next_cave_off)
        print(f"    {'free':<14} {free:>5} bytes of {cave_len}")
        if free < 32:
            print("    WARNING: main code cave is nearly full; new hooks may not fit")

    failed_selected = [key for key in failed if selected.get(key)]
    if check:
        if failed_selected:
            print(f"\n  Check summary: failed: {', '.join(failed_selected)}")
            print("\n  Check failed - nothing was written.")
            sys.exit(1)
        print("\n  Check complete - nothing was written.")
        return
    if failed_selected:
        print(
            "\n  WARNING: partial install; not fully applied: "
            + ", ".join(failed_selected)
        )

    # ------------------------------------------------------------------
    # Backup & save
    # ------------------------------------------------------------------
    if refresh_backup:
        print(f"\n  Refreshing original backup -> {os.path.basename(bak_path)}")
        shutil.copy2(exe_path, bak_path)
    elif not os.path.isfile(bak_path):
        print(f"\n  Backing up original -> {os.path.basename(bak_path)}")
        shutil.copy2(exe_path, bak_path)

    print(f"  Writing patched -> {os.path.basename(out_path)}")
    with open(out_path, "wb") as fh:
        fh.write(data)

    failures = _verify_patched(out_path, verify_sites, results, game_dir)
    if failures:
        os.remove(out_path)
        print("\n  ERROR: post-write verification failed:")
        for failure in failures:
            print(f"    - {failure}")
        sys.exit(1)
    print("  Verified patched executable.")

    # Feature record for the installer; it becomes FEATURES_FILE once the
    # patched executable is in place.
    features = {
        "essences": results.get("essences", False),
        "heal": results.get("heal", False),
        "mimans": results.get("mimans", False),
        "leylines": results.get("leylines", False),
        "miracles": results.get("miracles", False),
        "compendium": results.get("compendium", False),
        "jump": results.get("jump", False),
        "magatsuhi": results.get("magatsuhi", False),
        "refresh": results.get("refresh", False),
        "intro": results.get("intro", False),
        "masakado": results.get("masakado", False),
        "newborn": results.get("newborn", False),
        "estoma": results.get("estoma", False),
    }
    lines = [f"{k}={int(v)}" for k, v in features.items()]
    chain_fill = bool(results.get("magatsuhi")) and args.magatsuhi_chain
    lines.append(f"magatsuhi_chain={int(chain_fill)}")
    lines.append(
        "itemhacks="
        + (
            "stockpile"
            if results.get("stockpile")
            else "refill"
            if results.get("refill")
            else "none"
        )
    )
    lines.append(f"autosave={autosave_slot if results.get('autosave') else 0}")
    for category, mode in shop_modes.items():
        lines.append(f"shop_{category}={mode if results.get('shop') else 'default'}")
    lines.append(f"reveal={args.reveal if results.get('reveal') else 'none'}")
    lines.append(f"game_hash={live_hash}")
    with open(
        os.path.join(os.path.dirname(out_path), FEATURES_FILE + ".new"),
        "w",
        newline="\r\n",
    ) as fh:
        fh.write("\n".join(lines) + "\n")

    print()
    print("  " + "-" * 58)
    print("  Next steps:")
    print("    * install.bat / install.sh activates the patched EXE")
    print("    * uninstall.bat / uninstall.sh restores the original")
    print("  " + "-" * 58)


if __name__ == "__main__":
    main()
