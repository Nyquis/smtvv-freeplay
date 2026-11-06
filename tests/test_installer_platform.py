"""Tests for installer_platform's pure discovery helpers."""

from __future__ import annotations

import installer_platform as platform
import installer_state as state


def _fake_game(tmp_path):
    root = tmp_path / "SMT5V"
    binary = root.joinpath(*state.BIN_PARTS)
    binary.mkdir(parents=True)
    (binary / state.EXE).write_bytes(b"MZ")
    return root


def test_normalize_accepts_root_bin_and_exe(tmp_path):
    root = _fake_game(tmp_path)
    binary = root.joinpath(*state.BIN_PARTS)
    assert platform.normalize_game_dir(root) == root
    assert platform.normalize_game_dir(binary) == root
    assert platform.normalize_game_dir(binary / state.EXE) == root


def test_normalize_strips_quotes_and_rejects_other_folders(tmp_path):
    root = _fake_game(tmp_path)
    assert platform.normalize_game_dir(f'"{root}"') == root
    assert platform.normalize_game_dir(tmp_path) is None


def test_find_game_uses_the_explicit_path(tmp_path):
    root = _fake_game(tmp_path)
    assert platform.find_game(str(root)) == root


def test_bin_and_paks_paths_follow_the_game_root(tmp_path):
    root = _fake_game(tmp_path)
    assert platform.bin_dir(root) == root.joinpath(*state.BIN_PARTS)
    assert platform.paks_dir(root) == root.joinpath(*state.PAKS_PARTS)


def test_parse_library_paths_reads_vdf_entries():
    text = '"libraryfolders"\n{\n"0"\n{\n"path"\t"D:\\\\Steam"\n}\n}\n'
    assert platform.parse_library_paths(text) == [platform.Path("D:\\Steam")]


def test_installed_paks_are_unique_and_nonempty():
    assert len(platform.INSTALLED_PAKS) == len(set(platform.INSTALLED_PAKS))
    assert all(name.endswith(".pak") for name in platform.INSTALLED_PAKS)


def test_start_patcher_streams_lines(tmp_path):
    script = tmp_path / "fake.py"
    script.write_text(
        "print('[1/2] One')\nprint('  detail')\nprint('[2/2] Two')\n",
        encoding="utf-8",
    )
    stream = platform.start_patcher(script, tmp_path, [], check=True)
    lines = []
    while True:
        line = stream.queue.get(timeout=10)
        if line is None:
            break
        lines.append(line)
    assert lines == ["[1/2] One", "  detail", "[2/2] Two"]
    assert stream.process.wait(timeout=10) == 0
