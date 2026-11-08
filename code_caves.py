# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""PE image mapping, x64 emission and code-cave allocation.

This module is a leaf: it has no feature imports, so every patcher module can
depend on it without creating an import cycle.
"""

from __future__ import annotations

import bisect
import struct

RDATA_RAW = 0x600
RDATA_VA = 0x140001000

# Absolute VAs that already have a branch or pointer into the image. Layout
# code must not overwrite them; the patcher fills this from its reference scan.
CAVE_REFS: list[int] = []


def set_cave_references(refs: list[int]) -> None:
    global CAVE_REFS
    CAVE_REFS = sorted(refs)


def _range_has_reference(base_va: int, length: int) -> bool:
    if not CAVE_REFS:
        return False
    i = bisect.bisect_left(CAVE_REFS, base_va)
    return i < len(CAVE_REFS) and CAVE_REFS[i] < base_va + length


# (raw offset, raw size, RVA, virtual size) for every PE section; filled from
# the loaded executable so sites outside .rdata map correctly. Empty means the
# legacy .rdata-only mapping used by synthetic tests.
IMAGE_SECTIONS: list[tuple[int, int, int, int]] = []


def set_image_layout(data) -> None:
    """Record the section table of the executable being patched."""
    global IMAGE_SECTIONS
    IMAGE_SECTIONS = []
    if len(data) < 0x40:
        return
    try:
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        count = struct.unpack_from("<H", data, pe + 6)[0]
        opt = struct.unpack_from("<H", data, pe + 20)[0]
        base = pe + 24 + opt
        sections = []
        for index in range(count):
            header = base + 40 * index
            vsize, rva, rsize, raw = struct.unpack_from("<IIII", data, header + 8)
            sections.append((raw, rsize, rva, vsize))
    except (struct.error, IndexError):
        return
    IMAGE_SECTIONS = sections


def va(foff: int) -> int:
    for raw, rsize, rva, _vsize in IMAGE_SECTIONS:
        if raw <= foff < raw + rsize:
            return IMAGE_BASE + rva + (foff - raw)
    return RDATA_VA + (foff - RDATA_RAW)


def off(v: int) -> int:
    rva = v - IMAGE_BASE
    for raw, rsize, srva, vsize in IMAGE_SECTIONS:
        if srva <= rva < srva + max(vsize, rsize):
            return raw + (rva - srva)
    return v - RDATA_VA + RDATA_RAW


class Asm:
    """Tiny x64 emitter: raw bytes plus rel32 (and rel8) fixups to labels or VAs."""

    def __init__(self, base_va: int):
        self.base = base_va
        self.b = bytearray()
        self.labels: dict[str, int] = {}
        self.fix: list[tuple[int, str | int]] = []
        self.fix8: list[tuple[int, str]] = []

    def raw(self, hexstr: str) -> Asm:
        self.b += bytes.fromhex(hexstr.replace(" ", ""))
        return self

    def label(self, name: str) -> Asm:
        self.labels[name] = len(self.b)
        return self

    def _rel(self, opcode: str, target: str | int) -> Asm:
        self.raw(opcode)
        self.fix.append((len(self.b), target))
        self.b += b"\0\0\0\0"
        return self

    def call(self, t):
        return self._rel("E8", t)

    def jmp(self, t):
        return self._rel("E9", t)

    def je(self, t):
        return self._rel("0F84", t)

    def jne(self, t):
        return self._rel("0F85", t)

    def jle(self, t):
        return self._rel("0F8E", t)

    def ja(self, t):
        return self._rel("0F87", t)

    def jae(self, t):
        return self._rel("0F83", t)

    def j8(self, opcode: str, label: str) -> Asm:
        """Short jump (one opcode byte, rel8) to a label."""
        self.raw(opcode)
        self.fix8.append((len(self.b), label))
        self.b += b"\0"
        return self

    def rip(self, opcode: str, label: str) -> Asm:
        """Instruction ending in a RIP-relative disp32 to a data label."""
        return self._rel(opcode, label)

    def f32(self, name: str, value: float) -> Asm:
        while len(self.b) % 4:
            self.b += b"\xcc"
        self.label(name)
        self.b += struct.pack("<f", value)
        return self

    def build(self) -> bytes:
        for pos, t in self.fix:
            tgt = self.base + self.labels[t] if isinstance(t, str) else t
            struct.pack_into("<i", self.b, pos, tgt - (self.base + pos + 4))
        for pos, t in self.fix8:
            struct.pack_into("<b", self.b, pos, self.labels[t] - (pos + 1))
        return bytes(self.b)


def _place(
    data: bytearray,
    cave_off: int,
    cave_end: int,
    code: bytes,
    *,
    base_va: int | None = None,
    check_refs: bool = False,
) -> int:
    if cave_off + len(code) > cave_end:
        raise RuntimeError("code cave too small")
    for i in range(len(code)):
        assert data[cave_off + i] == 0xCC
    if check_refs:
        if base_va is None:
            raise RuntimeError("base_va required for reference-checked placement")
        if _range_has_reference(base_va, len(code)):
            raise RuntimeError(
                f"code cave range 0x{base_va:X}..0x{base_va + len(code):X} "
                "contains a reference"
            )
    data[cave_off : cave_off + len(code)] = code
    return cave_off + ((len(code) + 15) & ~15)


def _jmp_site(
    data: bytearray, site_va: int, dest_va: int, length: int, opcode: int = 0xE9
) -> None:
    o = off(site_va)
    data[o] = opcode
    struct.pack_into("<i", data, o + 1, dest_va - (site_va + 5))
    for i in range(5, length):
        data[o + i] = 0x90


# Small executable sections whose raw data is mostly unused zero padding;
# the loader maps their whole raw size, so the padding can hold code.
SLACK_SECTIONS = (b".rodata", b".xtext", b".ecode", b".xpdata")
IMAGE_BASE = 0x140000000


def slack_caves(data: bytearray) -> list[list[int]]:
    """Raw alignment slack in SLACK_SECTIONS as [file start, file end,
    va - file], filled with CC so _place accepts them.

    The range starts after the section's virtual size, so it is section
    padding, not a zero-initialised static object."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    sec = pe + 24 + struct.unpack_from("<H", data, pe + 20)[0]
    caves = []
    for i in range(nsec):
        h = sec + 40 * i
        name = bytes(data[h : h + 8]).rstrip(b"\0")
        vsize, rva, rsize, raw = struct.unpack_from("<IIII", data, h + 8)
        flags = struct.unpack_from("<I", data, h + 36)[0]
        if name not in SLACK_SECTIONS or not flags & 0x20000000:
            continue
        virtual_end = raw + ((vsize + 15) & ~15)
        start = virtual_end + 16
        assert start >= virtual_end
        end = start
        while end < raw + rsize and data[end] in (0, 0xCC):
            end += 1
        end = (end - 16) & ~15
        if end - start >= 64:
            data[start:end] = b"\xcc" * (end - start)
            caves.append([start, end, IMAGE_BASE + rva - raw])
    return caves


def put_code(data: bytearray, caves: list[list[int]], build) -> int:
    """Place the code from build(Asm) in the tightest cave that fits.

    Each entry is [file start, file end, va_delta], where va_delta is
    (VA - file offset) for that section, not a displacement into the cave.
    The first reference-free slot in each cave is considered, and the cave
    with the least remaining space wins. This keeps large caves available
    without breaking the first-slot placement inside a cave.
    """
    best: tuple[int, list[int], int, int, bytes] | None = None
    for c in caves:
        va_delta = c[2]
        pos = c[0]
        slots = max(1, (c[1] - c[0]) // 16 + 1)
        for _ in range(slots):
            dest = pos + va_delta
            code = build(Asm(dest)).build()
            if pos + len(code) > c[1]:
                break
            if not _range_has_reference(dest, len(code)):
                remaining = c[1] - (pos + len(code))
                if best is None or remaining < best[0]:
                    best = (remaining, c, pos, dest, code)
                break
            pos = (pos + 16) & ~15
    if best is None:
        raise RuntimeError("code cave too small")
    _remaining, c, pos, dest, code = best
    c[0] = _place(data, pos, c[1], code, base_va=dest)
    return dest
