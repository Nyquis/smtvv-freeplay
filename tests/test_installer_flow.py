"""Drive the wizard screens and the router with scripted keys."""

from __future__ import annotations

import io
import queue
import sys

import installer as entry
import installer_state as state
import installer_ui as ui


def _keys(monkeypatch, *keys):
    scripted = iter(keys)
    monkeypatch.setattr(ui, "read_key", lambda _console, *_args: next(scripted))


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


def test_review_offers_restore_original(monkeypatch, tmp_path):
    baseline = state.Selection(mods={"heal": True})
    wizard = _wizard(monkeypatch, tmp_path, baseline=baseline)
    _keys(monkeypatch, "r")
    assert entry.screen_review(wizard) == "restore"


def test_done_card_falls_back_to_ascii_checks(monkeypatch, tmp_path):
    wizard = _wizard(monkeypatch, tmp_path)
    body = entry._done_body(
        wizard,
        {
            "patches": 1,
            "total": 1,
            "paks": 0,
            "backup": "existing",
            "haptics": "not selected",
        },
    )
    assert not any("✓" in line for line in body)
    assert any(line.lstrip().startswith("+") for line in body)


def test_status_screen_picks_restore(monkeypatch, tmp_path):
    baseline = state.Selection(mods={"heal": True})
    wizard = _wizard(monkeypatch, tmp_path, baseline=baseline)
    _keys(monkeypatch, "down", "enter")
    assert entry.status_screen(wizard) == "restore"


def test_confirm_restore_enter_and_escape(monkeypatch, tmp_path):
    wizard = _wizard(monkeypatch, tmp_path)
    _keys(monkeypatch, "enter")
    assert entry.confirm_restore(wizard) is True
    _keys(monkeypatch, "esc")
    assert entry.confirm_restore(wizard) is False


def test_restore_flow_puts_the_original_back(monkeypatch, tmp_path):
    wizard = _wizard(monkeypatch, tmp_path)
    binary = wizard.game.joinpath(*state.BIN_PARTS)
    (binary / state.EXE).write_bytes(b"patched")
    (binary / f"{state.EXE}.original").write_bytes(b"original")
    (binary / state.FEATURES).write_text("heal=1\n", encoding="utf-8")
    paks = wizard.game.joinpath(*state.PAKS_PARTS)
    paks.mkdir(parents=True)
    (paks / "pakchunk99_NGPlusMiracles_P.pak").write_bytes(b"pak")
    _keys(monkeypatch, "enter")
    assert entry.restore_flow(wizard) == 0
    assert (binary / state.EXE).read_bytes() == b"original"
    assert not (binary / state.FEATURES).exists()
    assert not (paks / "pakchunk99_NGPlusMiracles_P.pak").exists()


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


def _last_frame(text):
    marker = " SMT5V: Vengeance - Freeplay Mod Installer"
    blocks = text.split(marker)
    block = marker + blocks[-1] if len(blocks) > 1 else text
    return [line for line in block.splitlines() if line.strip()]


class _FakeProcess:
    def __init__(self, code):
        self.code = code

    def wait(self, timeout=None):
        return self.code


class _FakeStream:
    def __init__(self, lines, code=0):
        self.queue = queue.Queue()
        for line in lines:
            self.queue.put(line)
        self.queue.put(None)
        self.process = _FakeProcess(code)


def test_preflight_advances_without_waiting_for_a_key(monkeypatch, tmp_path):
    wizard = _wizard(monkeypatch, tmp_path)
    lines = [
        "  Patches selected: Heal",
        "  [1/1] Leyline Auto-Heal",
        "  Check complete - nothing was written.",
    ]
    monkeypatch.setattr(
        entry.platform, "start_patcher", lambda *_args, **_kwargs: _FakeStream(lines)
    )

    def refuse(*_args, **_kwargs):
        raise AssertionError("the preflight should not wait for a key")

    monkeypatch.setattr(entry.ui, "read_key", refuse)
    ok, run = entry._run_preflight(wizard, ["--no-heal"])
    assert ok is True
    assert run.done == 1


def test_preflight_waits_for_a_key_when_it_fails(monkeypatch, tmp_path):
    wizard = _wizard(monkeypatch, tmp_path)
    lines = ["  Patches selected: Heal", "  Check summary: failed: heal"]
    monkeypatch.setattr(
        entry.platform,
        "start_patcher",
        lambda *_args, **_kwargs: _FakeStream(lines, code=1),
    )
    _keys(monkeypatch, "enter")
    ok, run = entry._run_preflight(wizard, ["--no-heal"])
    assert ok is False
    assert run.failed is True


def test_screens_fit_an_80x24_terminal(monkeypatch, tmp_path):
    root = _fake_game(tmp_path)
    everything = state.Selection(
        mods={mod.key: True for mod in state.PATCH_MODS},
        magatsuhi="battle",
        item_hacks="stockpile",
        autosave=3,
        shop={category: "free" for category in state.SHOP_CATEGORIES},
    )
    cases = (
        (entry.screen_mods, ["down"] * 6 + ["esc"], state.Selection()),
        (entry.screen_gameplay, ["esc"], state.Selection()),
        (entry.screen_shop, ["esc"], state.Selection()),
        (entry.screen_review, ["esc"], everything),
    )
    for screen, keys, selection in cases:
        console = _console(monkeypatch)
        console.width = lambda: 80
        console.height = lambda: 24
        out = sys.stdout
        wizard = entry.Wizard(
            console=console,
            screen=ui.Screen(console),
            game=root,
            version="test",
            selection=selection,
            baseline=state.Selection(),
            installed=0,
        )
        _keys(monkeypatch, *keys)
        screen(wizard)
        lines = _last_frame(out.getvalue())
        assert len(lines) <= 24, (screen.__name__, len(lines))


def test_stage_mark_uses_a_check_for_done(monkeypatch, tmp_path):
    wizard = _wizard(monkeypatch, tmp_path)
    assert entry._stage_mark(wizard.console, "done") == "[+]"
    assert entry._stage_mark(wizard.console, "active") == "[>]"
    assert entry._stage_mark(wizard.console, "pending") == "[ ]"
    wizard.console.unicode = True
    assert entry._stage_mark(wizard.console, "done") == "[✓]"


def test_install_frame_fits_80x24(monkeypatch, tmp_path):
    console = _console(monkeypatch)
    console.width = lambda: 80
    console.height = lambda: 24
    wizard = entry.Wizard(
        console=console,
        screen=ui.Screen(console),
        game=_fake_game(tmp_path),
        version="test",
        selection=state.Selection(),
        baseline=state.Selection(),
        installed=0,
    )
    wizard.preflight = state.PatchRun(
        source_choice="Using original backup.",
        tables_total=4,
        tables_ok=4,
        cave="0x00522031 len=1487",
    )
    stages = [
        ("Preflight verified", "done"),
        ("Applying patches", "done"),
        ("Installing executable", "done"),
        ("Write feature record", "done"),
        ("Finishing touches", "done"),
    ]
    entry._draw_install(
        wizard, stages, state.PatchRun(total=15, done=15), 3, "Done.", False
    )
    lines = _last_frame(sys.stdout.getvalue())
    assert len(lines) <= 24
