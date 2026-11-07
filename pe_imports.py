# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""PE import-table lookup for the IAT slots used by the executable patches."""

from __future__ import annotations

import struct


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def _cstr(data: bytes, offset: int) -> str:
    end = data.find(b"\0", offset)
    if end < 0:
        return ""
    return data[offset:end].decode("latin-1", errors="replace")


def import_slots(data: bytes | bytearray) -> dict[str, int]:
    """Map imported function names to their IAT slot VA.

    Returns an empty dict if the import table cannot be parsed.
    """
    try:
        pe = _u32(data, 0x3C)
        if data[pe : pe + 4] != b"PE\0\0":
            return {}
        section_count = _u16(data, pe + 6)
        optional_size = _u16(data, pe + 20)
        optional = pe + 24
        magic = _u16(data, optional)
        if magic == 0x10B:
            image_base = _u32(data, optional + 28)
            directories = optional + 96
        elif magic == 0x20B:
            image_base = _u64(data, optional + 24)
            directories = optional + 112
        else:
            return {}

        import_rva = _u32(data, directories + 8)
        import_size = _u32(data, directories + 12)
        if not import_rva or not import_size:
            return {}

        section_table = optional + optional_size
        sections = []
        for index in range(section_count):
            header = section_table + 40 * index
            vsize, rva, rsize, raw = struct.unpack_from("<IIII", data, header + 8)
            sections.append((rva, vsize, rsize, raw))

        def file_offset(rva: int) -> int | None:
            for srva, vsize, rsize, raw in sections:
                if srva <= rva < srva + max(vsize, rsize):
                    return raw + (rva - srva)
            return None

        slots: dict[str, int] = {}
        descriptor = file_offset(import_rva)
        if descriptor is None:
            return {}
        while descriptor + 20 <= len(data):
            original_first, _stamp, _forward, name_rva, first_thunk = (
                struct.unpack_from("<IIIII", data, descriptor)
            )
            if not original_first and not name_rva and not first_thunk:
                break
            module = ""
            module_offset = file_offset(name_rva) if name_rva else None
            if module_offset is not None:
                module = _cstr(data, module_offset)
            thunk_rva = original_first or first_thunk
            thunk_offset = file_offset(thunk_rva)
            index = 0
            while thunk_offset is not None and thunk_offset + 8 <= len(data):
                entry = _u64(data, thunk_offset + 8 * index)
                if entry == 0:
                    break
                slot_va = image_base + first_thunk + 8 * index
                if entry >> 63:
                    ordinal = entry & 0xFFFF
                    if "xinput" in module.lower() and ordinal == 2:
                        slots.setdefault("XInputGetState", slot_va)
                else:
                    name_offset = file_offset(entry & 0x7FFFFFFF)
                    if name_offset is not None:
                        name = _cstr(data, name_offset + 2)
                        if name:
                            slots.setdefault(name, slot_va)
                index += 1
            descriptor += 20
        return slots
    except (IndexError, struct.error, ValueError):
        return {}
