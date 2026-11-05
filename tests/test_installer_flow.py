"""Drive the terminal widgets with scripted keys, without a real terminal."""

from __future__ import annotations

import io
import sys

import installer as entry
import installer_state as state
import installer_ui as ui


def _console(monkeypatch):
    console = ui.Console()
    console.tty = True
    console.color = False
    console.unicode = False
    return console


def _keys(monkeypatch, *keys):
    scripted = iter(keys)
    monkeypatch.setattr(ui, "read_key", lambda _console: next(scripted))


def test_checklist_moves_toggles_and_confirms(monkeypatch):
    console = _console(monkeypatch)
    screen = ui.Screen(console)
    mods = state.MODS[:2]
    selected = {mod.key: False for mod in mods}
    _keys(monkeypatch, "down", "space", "enter")
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    ui.checklist(console, screen, "Mods", "sub", mods, selected)
    assert selected[mods[1].key] is True
    assert selected[mods[0].key] is False
    assert "Mods" in out.getvalue()


def test_checklist_select_all_and_none(monkeypatch):
    console = _console(monkeypatch)
    screen = ui.Screen(console)
    mods = state.MODS[:3]
    selected = {mod.key: False for mod in mods}
    _keys(monkeypatch, "a", "n", "a", "enter")
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    ui.checklist(console, screen, "Mods", "sub", mods, selected)
    assert all(selected[mod.key] for mod in mods)


def test_radio_moves_and_confirms(monkeypatch):
    console = _console(monkeypatch)
    screen = ui.Screen(console)
    options = [("a", "A"), ("b", "B"), ("c", "C")]
    _keys(monkeypatch, "down", "down", "enter")
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert ui.radio(console, screen, "Pick", "sub", options, 0) == 2


def test_notice_returns_false_on_escape(monkeypatch):
    console = _console(monkeypatch)
    screen = ui.Screen(console)
    _keys(monkeypatch, "esc")
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert ui.notice(console, screen, "Warning", "text") is False


def test_split_args_reads_game_dir_and_flags():
    game, flags, scripted = entry.split_args(["--game-dir", "C:\\game", "--no-heal"])
    assert game == "C:\\game"
    assert flags == ["--no-heal"]
    assert scripted is True


def test_split_args_accepts_a_positional_game_dir():
    game, flags, scripted = entry.split_args(["C:\\game", "--shop-growth", "free"])
    assert game == "C:\\game"
    assert flags == ["--shop-growth", "free"]
    assert scripted is True


def test_split_args_without_flags_is_interactive():
    game, flags, scripted = entry.split_args(["--game-dir", "C:\\game"])
    assert game == "C:\\game"
    assert flags == []
    assert scripted is False


def test_split_args_uninstall():
    game, flags, scripted = entry.split_args(["--game-dir", "C:\\game", "--uninstall"])
    assert game == "C:\\game"
    assert flags == ["--uninstall"]
    assert scripted is True
