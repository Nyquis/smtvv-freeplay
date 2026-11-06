"""Drive the wizard screens and the router with scripted keys."""

from __future__ import annotations

import io
import sys

import installer as entry
import installer_state as state
import installer_ui as ui


def _keys(monkeypatch, *keys):
    scripted = iter(keys)
    monkeypatch.setattr(ui, "read_key", lambda _console: next(scripted))


def _fake_game(tmp_path):
    root = tmp_path / "SMT5V"
    binary = root.joinpath(*state.BIN_PARTS)
    binary.mkdir(parents=True)
    (binary / state.EXE).write_bytes(b"MZ")
    return root


def _console(monkeypatch):
    console = ui.Console()
    console.tty = True
    console.ansi = False
    console.color = False
    console.unicode = False
    console.clear = lambda: None
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    return console


def _wizard(monkeypatch, tmp_path, selection=None, baseline=None, installed=None):
    console = _console(monkeypatch)
    selection = selection if selection is not None else state.Selection()
    baseline = baseline if baseline is not None else state.Selection()
    return entry.Wizard(
        console=console,
        screen=ui.Screen(console),
        game=_fake_game(tmp_path),
        version="test",
        selection=selection,
        baseline=baseline,
        installed=baseline.count() if installed is None else installed,
    )


def test_mods_screen_toggles_and_advances(monkeypatch, tmp_path):
    wizard = _wizard(monkeypatch, tmp_path)
    _keys(monkeypatch, "down", "space", "enter")
    assert entry.screen_mods(wizard) == "next"
    assert wizard.selection.mods["heal"] is True
    assert wizard.selection.mods["essences"] is False


def test_mods_screen_select_all_and_none(monkeypatch, tmp_path):
    wizard = _wizard(monkeypatch, tmp_path)
    _keys(monkeypatch, "a", "n", "a", "enter")
    assert entry.screen_mods(wizard) == "next"
    assert all(wizard.selection.mods.values())


def test_gameplay_screen_changes_all_three_options(monkeypatch, tmp_path):
    wizard = _wizard(monkeypatch, tmp_path)
    _keys(monkeypatch, "right", "down", "right", "down", "right", "enter")
    assert entry.screen_gameplay(wizard) == "next"
    assert wizard.selection.item_hacks == "refill"
    assert wizard.selection.magatsuhi == "battle"
    assert wizard.selection.autosave == 1


def test_gameplay_screen_back_does_not_apply(monkeypatch, tmp_path):
    wizard = _wizard(monkeypatch, tmp_path)
    _keys(monkeypatch, "left", "esc")
    assert entry.screen_gameplay(wizard) == "back"


def test_shop_screen_changes_the_focused_category(monkeypatch, tmp_path):
    wizard = _wizard(monkeypatch, tmp_path)
    _keys(monkeypatch, "right", "down", "right", "enter")
    assert entry.screen_shop(wizard) == "next"
    assert wizard.selection.shop["consumables"] == "free"
    assert wizard.selection.shop["growth"] == "free"
    assert wizard.selection.shop["misc"] == "default"


def test_review_lists_the_diff_and_applies(monkeypatch, tmp_path):
    selection = state.Selection(mods={"heal": True}, magatsuhi="chain")
    baseline = state.Selection(mods={"essences": True})
    wizard = _wizard(monkeypatch, tmp_path, selection=selection, baseline=baseline)
    _keys(monkeypatch, "enter")
    assert entry.screen_review(wizard) == "apply"


def test_review_blocks_an_empty_selection(monkeypatch, tmp_path):
    wizard = _wizard(monkeypatch, tmp_path)
    _keys(monkeypatch, "enter", "esc")
    assert entry.screen_review(wizard) == "back"


def test_review_allows_uninstall_when_something_is_installed(monkeypatch, tmp_path):
    baseline = state.Selection(mods={"heal": True})
    wizard = _wizard(
        monkeypatch, tmp_path, selection=state.Selection(), baseline=baseline
    )
    _keys(monkeypatch, "enter")
    assert entry.screen_review(wizard) == "apply"


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


def test_router_passes_the_selected_flags(monkeypatch, tmp_path):
    console = ui.Console()
    monkeypatch.setattr(entry.ui, "Console", lambda: console)
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    root = _fake_game(tmp_path)
    monkeypatch.setattr(entry.platform, "find_game", lambda *_args: root)

    def pick_mods(wizard):
        wizard.selection.mods["heal"] = True
        return "next"

    def pick_gameplay(wizard):
        wizard.selection.magatsuhi = "chain"
        return "next"

    monkeypatch.setattr(entry, "screen_mods", pick_mods)
    monkeypatch.setattr(entry, "screen_gameplay", pick_gameplay)
    monkeypatch.setattr(entry, "screen_shop", lambda _w: "next")
    monkeypatch.setattr(entry, "screen_review", lambda _w: "apply")
    monkeypatch.setattr(entry.ui, "wait_for_enter", lambda *_args: None)
    monkeypatch.setattr(entry, "finish_install", lambda *_args, **_kwargs: None)
    captured = {}

    def fake_steps(game, flags, console):
        captured["flags"] = flags
        return True

    monkeypatch.setattr(entry, "run_patcher_steps", fake_steps)
    assert entry.main(["--game-dir", str(root)]) == 0
    assert "--no-heal" not in captured["flags"]
    assert "--magatsuhi-chain" in captured["flags"]
    assert "--no-refill" in captured["flags"]
