"""End-to-end install test on a synthetic executable.

Runs the real patcher in a subprocess, then activates its output through the
installer, and checks the live executable and feature record. The fixture is a
tiny PE with only the sections and sites needed by two in-place patches, so it
needs no game data, no network and no data paks.
"""

from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path

import installer_platform
import installer_state as state
import patch_smtvv_freeplay as patcher

ROOT = Path(__file__).resolve().parents[1]

RDATA_RAW = 0x600
RDATA_RVA = 0x1000
RDATA_VSIZE = 0x1800
DATA_RAW = 0x2000
DATA_RVA = 0x00300000
DATA_VSIZE = 0x16000000
CAVE_OFFSET = 0x700
CAVE_LENGTH = 0x100
MIMAN_OFFSET = 0x800
COMPENDIUM_OFFSET = 0x900


def _section_header(data: bytearray, index: int) -> int:
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    return pe + 24 + optional_size + 40 * index


def _synthetic_exe() -> bytes:
    data = bytearray(0x3000)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x84, 0x8664)  # machine
    struct.pack_into("<H", data, 0x86, 2)  # sections
    struct.pack_into("<H", data, 0x94, 0xE0)  # optional-header size

    rdata = _section_header(data, 0)
    data[rdata : rdata + 8] = b".rdata\0\0"
    struct.pack_into(
        "<IIII", data, rdata + 8, RDATA_VSIZE, RDATA_RVA, RDATA_VSIZE, RDATA_RAW
    )
    struct.pack_into("<I", data, rdata + 36, 0x60000020)  # read + execute

    # One writable section header whose virtual range covers the stockpile and
    # autosave scratch VAs checked by the patcher. It needs no real data.
    writable = _section_header(data, 1)
    data[writable : writable + 8] = b".data\0\0\0"
    struct.pack_into(
        "<IIII", data, writable + 8, DATA_VSIZE, DATA_RVA, 0x1000, DATA_RAW
    )
    struct.pack_into("<I", data, writable + 36, 0xC0000040)  # read + write

    # A safe CC cave: preceded by a return, long enough for min_size=128.
    data[CAVE_OFFSET - 1] = 0xC3
    data[CAVE_OFFSET : CAVE_OFFSET + CAVE_LENGTH] = b"\xcc" * CAVE_LENGTH

    data[MIMAN_OFFSET : MIMAN_OFFSET + len(patcher.MIMAN_POS_CHECK_ORIG)] = (
        patcher.MIMAN_POS_CHECK_ORIG
    )
    data[COMPENDIUM_OFFSET : COMPENDIUM_OFFSET + len(patcher.DEVIL_COST_ORIG)] = (
        patcher.DEVIL_COST_ORIG
    )
    return bytes(data)


def _flags(game_dir: Path) -> list[str]:
    return [
        "--game-dir",
        str(game_dir),
        "--no-essences",
        "--no-heal",
        "--no-miracles",
        "--no-jump",
        "--no-magatsuhi",
        "--no-intro",
        "--no-masakado",
        "--no-newborn",
        "--no-estoma",
        "--no-refill",
        "--no-shop",
    ]


def test_patch_verify_and_activate_end_to_end(tmp_path):
    game = tmp_path / "SMT5V"
    bindir = game.joinpath(*state.BIN_PARTS)
    bindir.mkdir(parents=True)
    original = _synthetic_exe()
    (bindir / state.EXE).write_bytes(original)

    result = subprocess.run(
        [sys.executable, "patch_smtvv_freeplay.py", *_flags(game)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Verified patched executable." in result.stdout
    assert "[1/2] Miman Reveal" in result.stdout
    assert "[2/2] Free Compendium" in result.stdout

    log: list[str] = []
    assert installer_platform.install_patched(bindir, log.append) is True
    installer_platform.move_features(bindir)

    live = (bindir / state.EXE).read_bytes()
    assert live[MIMAN_OFFSET : MIMAN_OFFSET + 3] == b"\xb0\x01\xc3"
    assert live[COMPENDIUM_OFFSET : COMPENDIUM_OFFSET + 3] == b"\x33\xc0\xc3"
    assert (bindir / f"{state.EXE}.original").read_bytes() == original

    features = (bindir / state.FEATURES).read_text(encoding="utf-8")
    assert "mimans=1" in features
    assert "compendium=1" in features
    assert "essences=0" in features
