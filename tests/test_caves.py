"""Change-scoped tests for the hardened code-cave finder."""

from __future__ import annotations

import struct

import pytest

import gameplay_patches as gp
import patch_smtvv_freeplay as patcher


def _pe_with_code(*, before: int = 0xC3) -> bytearray:
    """Minimal PE with one executable .rdata section at raw 0x600."""
    data = bytearray(0x1800)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x80 + 4, 0x8664)  # machine
    struct.pack_into("<H", data, 0x80 + 6, 1)  # sections
    struct.pack_into("<H", data, 0x80 + 20, 0xE0)  # optional-header size
    header = 0x80 + 24 + 0xE0
    data[header : header + 8] = b".rdata\0\0"
    struct.pack_into("<IIII", data, header + 8, 0x1000, 0x1000, 0x1000, 0x600)
    struct.pack_into("<I", data, header + 36, 0x60000020)  # read + execute

    data[0x6FF] = before
    data[0x700:0x800] = b"\xcc" * 0x100
    data[0x800] = 0x48
    return data


def test_finds_cc_padding_in_executable_section():
    data = _pe_with_code()
    cave = patcher.find_cc_cave(data, min_size=64)
    assert cave == (0x700, 0x100)

    info = patcher.LAST_CAVE_INFO
    assert info is not None
    assert info["section"] == ".rdata"
    assert info["exec"] is True
    assert info["writable"] is False
    assert info["before"] == 0xC3
    assert info["prefix_refs"] == 0
    assert info["total_refs"] == 0
    assert info["safe"] is True


def test_rejects_a_run_referenced_in_its_prefix():
    data = _pe_with_code()
    # Direct call at 0x650 -> 0x710, inside the first 64 bytes of the run.
    data[0x650] = 0xE8
    struct.pack_into("<i", data, 0x651, 0x140001110 - (0x140001055))
    # A second, unreferenced run later in the section.
    data[0xBFF] = 0xC3
    data[0xC00:0xC80] = b"\xcc" * 0x80
    data[0xC80] = 0x48

    cave = patcher.find_cc_cave(data, min_size=64)
    assert cave == (0xC00, 0x80)
    assert patcher.LAST_CAVE_INFO["prefix_refs"] == 0


def test_side_cave_spans_split_around_a_reference():
    data = _pe_with_code()
    # Direct call at 0x650 -> 0x780, in the middle of the run.
    data[0x650] = 0xE8
    struct.pack_into("<i", data, 0x651, 0x140001180 - 0x140001055)

    spans = patcher.find_cc_caves(data, min_size=64, count=4)
    assert spans
    for start, length in spans:
        assert not (start <= 0x780 < start + length)
    assert (0x700, 0x80) in spans
    assert (0x790, 0x70) in spans


def test_place_rejects_reference_in_exact_range():
    data = bytearray(b"\xcc" * 0x100)
    gp.set_cave_references([0x1000])
    try:
        with pytest.raises(RuntimeError, match="contains a reference"):
            gp._place(data, 0, 0x100, b"\x90" * 4, base_va=0xFFE, check_refs=True)
        gp.set_cave_references([])
    finally:
        gp.set_cave_references([])


def test_place_allows_clean_range():
    data = bytearray(b"\xcc" * 0x100)
    gp.set_cave_references([0x3000])
    try:
        assert (
            gp._place(data, 0, 0x100, b"\x90" * 4, base_va=0x2000, check_refs=True)
            == 16
        )
    finally:
        gp.set_cave_references([])


def test_slack_caves_start_beyond_virtual_size():
    data = bytearray(0x1000)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x80 + 4, 0x8664)
    struct.pack_into("<H", data, 0x80 + 6, 1)
    struct.pack_into("<H", data, 0x80 + 20, 0xE0)
    header = 0x80 + 24 + 0xE0
    data[header : header + 8] = b".rodata\0"
    struct.pack_into("<IIII", data, header + 8, 9, 0x1000, 0x200, 0x600)
    struct.pack_into("<I", data, header + 36, 0x60000020)

    caves = gp.slack_caves(data)
    assert caves
    start, _end, _delta = caves[0]
    assert start >= 0x600 + ((9 + 15) & ~15)


def test_rejects_a_run_that_does_not_follow_a_return():
    data = _pe_with_code(before=0x90)
    assert patcher.find_cc_cave(data, min_size=64) is None


def test_rejects_a_non_executable_section():
    data = _pe_with_code()
    header = 0x80 + 24 + 0xE0
    struct.pack_into("<I", data, header + 36, 0x40000040)  # read only
    assert patcher.find_cc_cave(data, min_size=64) is None
