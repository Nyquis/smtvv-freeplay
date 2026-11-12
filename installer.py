# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""SMT5V: Vengeance - Freeplay Mod Installer.

The batch and shell launchers only pick a Python interpreter and hand over
their arguments; everything below is standard library only.
"""

from __future__ import annotations

import os
import queue
import re
import sys
import tempfile
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import installer_platform as platform
import installer_state as state
import installer_ui as ui

HERE = Path(__file__).resolve().parent
PATCH_SCRIPT = HERE / "patch_smtvv_freeplay.py"
HAPTICS_SOURCE = HERE / "haptics"
LOG_DIR = HERE / "logs"
LOG_NAME = "freeplay-installer.log"
LAST_LOG: list[str] = []
LAST_ERROR: list[str] = []
LAST_CONTEXT: list[str] = []
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
FLAGS_WITH_VALUE = (
    "--shop-consumables",
    "--shop-growth",
    "--shop-essences",
    "--shop-misc",
    "--autosave-slot",
    "--reveal",
)
ACTION_TAGS = {
    "install": "[+] INSTALL",
    "change": "[~] CHANGE ",
    "remove": "[-] REMOVE ",
    "keep": "[=] KEEP   ",
}


def split_args(argv: list[str]) -> tuple[str | None, list[str], bool]:
    """(game dir, patcher flags, scripted) from the command line."""
    game: str | None = None
    flags: list[str] = []
    scripted = False
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--game-dir" and index + 1 < len(argv):
            game = argv[index + 1]
            index += 2
            continue
        if arg.startswith("--game-dir="):
            game = arg.split("=", 1)[1]
            index += 1
            continue
        if arg == "--no-color":
            os.environ["NO_COLOR"] = "1"
            index += 1
            continue
        if arg == "--uninstall":
            scripted = True
            flags.append(arg)
            index += 1
            continue
        if arg.startswith("-"):
            scripted = True
            flags.append(arg)
            if arg in FLAGS_WITH_VALUE and index + 1 < len(argv):
                flags.append(argv[index + 1])
                index += 2
                continue
            index += 1
            continue
        if game is None:
            game = arg
        index += 1
    return game, flags, scripted


def banner(console: ui.Console, version: str) -> None:
    width = console.width()
    console.write(console.cyan("=" * width))
    console.write(
        console.cyan(f" SMT5V: Vengeance - Freeplay Mod Installer   v{version}")
    )
    console.write(console.cyan("=" * width))


def status_line(console: ui.Console, game: Path, selection: state.Selection) -> None:
    count = selection.count()
    console.write("")
    console.write(f"  Game:      {game}")
    console.write(
        f"  Installed: {count} of {state.total_mods()} mods"
        if count
        else "  Installed: none"
    )
    console.write("")


def show_step(console: ui.Console, number: int, total: int, label: str) -> None:
    width = console.width()
    console.write("")
    console.write(console.cyan("=" * width))
    console.write(console.cyan(f" Step {number} of {total} - {label}"))
    console.write(console.cyan("=" * width))


def run_uninstall(game: Path, console: ui.Console) -> int:
    bindir = platform.bin_dir(game)
    log = console.write
    platform.restore_original(bindir, log)
    platform.remove_paks(game, log)
    platform.remove_haptics(bindir, HAPTICS_SOURCE, log)
    platform.remove_legacy_superjump(bindir, HAPTICS_SOURCE, log)
    for name in (state.FEATURES, state.FEATURES + ".new"):
        try:
            (bindir / name).unlink()
        except OSError:
            pass
    console.write("")
    console.write(console.green("  Done - original files restored."))
    return 0


def run_patcher_steps(game: Path, flags: list[str], console: ui.Console) -> bool:
    show_step(console, 1, 2, "Preflight check (nothing is written)")
    result = platform.run_patcher(PATCH_SCRIPT, game, flags, check=True)
    if result.returncode != 0:
        if result.stdout:
            console.write(result.stdout.rstrip())
        if result.stderr:
            console.write(result.stderr.rstrip())
        console.write("")
        console.write(console.red("  Patch verification failed. Nothing was written."))
        LAST_LOG[:] = (result.stdout or "").splitlines()
        LAST_ERROR[:] = ["Patch verification failed. Nothing was written."]
        return False
    console.write(console.green("  All selected patches verified."))

    show_step(console, 2, 2, "Applying patches (writes game files)")
    result = platform.run_patcher(PATCH_SCRIPT, game, flags, check=False)
    if result.returncode != 0:
        console.write("")
        console.write(console.red("  Patcher failed. See the messages above."))
        LAST_LOG[:] = (result.stdout or "").splitlines()
        LAST_ERROR[:] = ["Patcher failed while applying patches."]
        return False
    return True


def finish_install(
    game: Path,
    selection: state.Selection,
    has_haptics: bool,
    console: ui.Console,
) -> None:
    bindir = platform.bin_dir(game)
    log = console.write
    platform.install_patched(bindir, log)
    platform.move_features(bindir)
    platform.remove_legacy_superjump(bindir, HAPTICS_SOURCE, log)
    if os.name == "nt" and selection.haptics:
        if platform.install_haptics(bindir, HAPTICS_SOURCE, log):
            platform.record_haptics(bindir)
    elif os.name == "nt" and has_haptics:
        platform.remove_haptics(bindir, HAPTICS_SOURCE, log)


def run_scripted(game_arg: str | None, flags: list[str], console: ui.Console) -> int:
    LAST_LOG.clear()
    LAST_ERROR.clear()
    game = platform.find_game(game_arg, HERE)
    if game is None:
        console.write(console.red("Could not find SMT5V. Pass --game-dir <folder>."))
        _write_failure_log(console, 1, ["SMT5V folder not found."])
        return 1
    if flags == ["--uninstall"]:
        return run_uninstall(game, console)
    bindir = platform.bin_dir(game)
    features = state.read_features(bindir / state.FEATURES)
    banner(console, state.mod_version(PATCH_SCRIPT))
    status_line(console, game, state.selection_from(features))
    _remember_flags(flags)
    if not run_patcher_steps(game, flags, console):
        _write_failure_log(console, 1)
        return 1
    selection = state.selection_from(state.read_features(bindir / state.FEATURES))
    finish_install(
        game,
        selection,
        has_haptics=features.get("haptics") == "1",
        console=console,
    )
    console.write("")
    console.write(console.green("  Done - mods installed."))
    return 0


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------


@dataclass
class Wizard:
    console: ui.Console
    screen: ui.Screen
    game: Path
    version: str
    selection: state.Selection
    baseline: state.Selection
    installed: int
    preflight: state.PatchRun | None = None


def _stage_mark(console: ui.Console, status: str) -> str:
    return {
        "done": f"[{console.check()}]",
        "active": "[>]",
        "pending": "[ ]",
        "failed": "[!]",
    }[status]


def _window(cursor: int, count: int, rows: int) -> tuple[int, int]:
    if count <= rows:
        return 0, count
    start = min(max(0, cursor - rows // 2), count - rows)
    return start, start + rows


def _draw(
    w: Wizard, step: str, body: list[str], footer: list[str], right: str = ""
) -> None:
    header = [
        w.console.cyan(f" SMT5V: Vengeance - Freeplay Mod Installer   v{w.version}"),
        f" {w.console.dim('Game:')} {w.game}",
        "",
    ]
    w.screen.draw(header + ui.framed(w.console, step, body, footer, right=right))


def _commit_mods(w: Wizard, checks: dict[str, bool]) -> None:
    w.selection.mods = {
        mod.key: checks.get(mod.key, False)
        for mod in state.PATCH_MODS
        if mod.key != "magatsuhi"
    }
    w.selection.haptics = bool(checks.get("haptics")) and os.name == "nt"


def screen_mods(w: Wizard) -> str:
    mods = [mod for mod in state.MODS if not (mod.windows_only and os.name != "nt")]
    checks = {
        mod.key: (
            w.selection.haptics
            if mod.key == "haptics"
            else w.selection.mods.get(mod.key, False)
        )
        for mod in mods
    }
    if not w.console.tty:
        ui.plain_toggle(w.console, mods, checks)
        _commit_mods(w, checks)
        return "next"

    cursor = 0
    w.screen.begin()
    try:
        while True:
            text_width = min(w.console.width(), 100) - 8
            focused = mods[cursor]
            description = ui.wrap_text(focused.description, text_width)
            warning_lines = (
                ui.wrap_text(focused.warning, text_width) if focused.warning else []
            )
            fixed = (
                8 + len(description) + (1 + len(warning_lines) if warning_lines else 0)
            )
            rows = max(3, w.console.height() - fixed)
            start, end = _window(cursor, len(mods), rows)
            body: list[str] = []
            for index in range(start, end):
                mod = mods[index]
                pointer = w.console.marker() if index == cursor else " "
                box = "x" if checks[mod.key] else " "
                warning = "  !" if mod.warning else ""
                body.append(f" {pointer} [{box}] {mod.label}{warning}")
            body.append("")
            body.extend("   " + line for line in description)
            if warning_lines:
                body.append("")
                for line in warning_lines:
                    body.append(w.console.yellow(f"   [!] {line}"))
            footer = [
                w.console.hint(
                    "up/down move   space toggle   a all   n none   enter next   esc quit"
                )
            ]
            size = w.console.size()
            _draw(
                w,
                "Step 1 of 4: Core Mods",
                body,
                footer,
                right=f"{start + 1}-{end} of {len(mods)}",
            )
            key = ui.wait_key_or_resize(w.console, size)
            if key is None:
                continue
            if key == "up":
                cursor = (cursor - 1) % len(mods)
            elif key == "down":
                cursor = (cursor + 1) % len(mods)
            elif key == "space":
                name = mods[cursor].key
                checks[name] = not checks.get(name, False)
            elif key == "a":
                for mod in mods:
                    checks[mod.key] = True
            elif key == "n":
                for mod in mods:
                    checks[mod.key] = False
            elif key == "enter":
                break
            elif key in ("esc", "q"):
                return "quit"
    finally:
        w.screen.end()
    _commit_mods(w, checks)
    return "next"


def _plain_choice(
    console: ui.Console, title: str, options: list[tuple[str, str]], index: int
) -> int:
    console.write(f"  {title}")
    for number, (_value, label) in enumerate(options, 1):
        console.write(f"    {number}. {label}")
    while True:
        answer = ui.ask_text(console, "choose", str(index + 1))
        if not answer:
            return index
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return int(answer) - 1


def screen_gameplay(w: Wizard) -> str:
    hacks = [
        ("refill", "Battle Refill"),
        ("stockpile", "Stockpile"),
        ("none", "Neither"),
    ]
    magatsuhi = [
        ("battle", "Every battle"),
        ("chain", "Once per chain"),
        ("none", "Game default"),
    ]
    slots: list[int | None] = [None, *range(state.AUTOSAVE_MIN, state.AUTOSAVE_MAX + 1)]
    hack_index = [value for value, _ in hacks].index(w.selection.item_hacks)
    mode_index = [value for value, _ in magatsuhi].index(w.selection.magatsuhi)
    slot_index = (
        slots.index(w.selection.autosave) if w.selection.autosave in slots else 0
    )

    descriptions = {
        0: "Battle Refill tops battle items up when each battle starts. Stockpile "
        "stacks them to 99 in camp while battles keep the normal caps. Neither "
        "leaves items untouched.",
        1: "Every battle fills the gauge at the start of every encounter, including "
        "each Boss Rush round. Once per chain fills only the first battle of a chain. "
        "Game default leaves the gauge alone.",
        2: "Autosave writes one slot after every battle, overwriting that slot each "
        "time. Off disables it.",
    }

    if not w.console.tty:
        w.selection.item_hacks = hacks[
            _plain_choice(w.console, "Item Hacks", hacks, hack_index)
        ][0]
        w.selection.magatsuhi = magatsuhi[
            _plain_choice(w.console, "Full Magatsuhi", magatsuhi, mode_index)
        ][0]
        while True:
            answer = ui.ask_text(
                w.console,
                "Autosave slot (1-20, n off, blank keeps)",
                str(w.selection.autosave) if w.selection.autosave else "off",
            )
            parsed = state.autosave_choice(answer, w.selection.autosave)
            if parsed == "keep":
                break
            if parsed == "invalid":
                w.console.write(
                    w.console.red("  Enter a slot from 1 to 20, n, or blank.")
                )
                continue
            w.selection.autosave = parsed
            break
        return "next"

    focus = 0
    w.screen.begin()
    try:
        while True:

            def arrow(label: str, selected: bool) -> str:
                left = "<" if not w.console.unicode else "‹"
                right = ">" if not w.console.unicode else "›"
                value = w.console.bold(label) if selected else label
                return f"{left} {value} {right}"

            hack_label = dict(hacks)[w.selection.item_hacks]
            mode_label = dict(magatsuhi)[w.selection.magatsuhi]
            slot_label = (
                "Off"
                if w.selection.autosave is None
                else f"Slot {w.selection.autosave}"
            )
            rows = [
                ("Item Hacks", arrow(hack_label, focus == 0)),
                ("Full Magatsuhi", arrow(mode_label, focus == 1)),
                ("Autosave", arrow(slot_label, focus == 2)),
            ]
            body = []
            for index, (label, value) in enumerate(rows):
                pointer = w.console.marker() if index == focus else " "
                body.append(f" {pointer} {label:<21} {value}")
            body.append("")
            text_width = min(w.console.width(), 100) - 8
            body.extend(
                "   " + line for line in ui.wrap_text(descriptions[focus], text_width)
            )
            footer = [
                w.console.hint(
                    "up/down move   left/right change   enter next   esc back"
                )
            ]
            size = w.console.size()
            _draw(w, "Step 2 of 4: Gameplay", body, footer)
            key = ui.wait_key_or_resize(w.console, size)
            if key is None:
                continue
            if key == "up":
                focus = (focus - 1) % 3
            elif key == "down":
                focus = (focus + 1) % 3
            elif key in ("left", "right", "space"):
                if focus == 0:
                    hack_index = (hack_index + (1 if key != "left" else -1)) % len(
                        hacks
                    )
                    w.selection.item_hacks = hacks[hack_index][0]
                elif focus == 1:
                    mode_index = (mode_index + (1 if key != "left" else -1)) % len(
                        magatsuhi
                    )
                    w.selection.magatsuhi = magatsuhi[mode_index][0]
                else:
                    slot_index = (slot_index + (1 if key != "left" else -1)) % len(
                        slots
                    )
                    w.selection.autosave = slots[slot_index]
            elif key == "enter":
                break
            elif key in ("esc", "q"):
                return "back"
    finally:
        w.screen.end()
    return "next"


def screen_shop(w: Wizard) -> str:
    modes = [
        ("default", "Game default"),
        ("free", "Free, default timing"),
        ("immediate", "Free and immediate"),
    ]
    if not w.console.tty:
        w.console.write("  Shop stock and prices (per category):")
        for category in state.SHOP_CATEGORIES:
            current = [value for value, _ in modes].index(w.selection.shop[category])
            index = _plain_choice(
                w.console, state.SHOP_CATEGORY_LABELS[category], modes, current
            )
            w.selection.shop[category] = modes[index][0]
        return "next"

    focus = 0
    w.screen.begin()
    try:
        while True:
            body = []
            for index, category in enumerate(state.SHOP_CATEGORIES):
                pointer = w.console.marker() if index == focus else " "
                mode = w.selection.shop[category]
                label = dict(modes)[mode]
                left = "<" if not w.console.unicode else "‹"
                right = ">" if not w.console.unicode else "›"
                body.append(
                    f" {pointer} {state.SHOP_CATEGORY_LABELS[category]:<21} "
                    f"{left} {label} {right}"
                )
            body.append("")
            text_width = min(w.console.width(), 100) - 8
            body.extend(
                "   " + line
                for line in ui.wrap_text(
                    "Game default leaves this category alone. Free removes prices. "
                    "Free and immediate also unlocks the stock without story progress.",
                    text_width,
                )
            )
            footer = [
                w.console.hint(
                    "up/down move   left/right change   enter next   esc back"
                )
            ]
            size = w.console.size()
            _draw(w, "Step 3 of 4: Shop", body, footer)
            key = ui.wait_key_or_resize(w.console, size)
            if key is None:
                continue
            if key == "up":
                focus = (focus - 1) % len(state.SHOP_CATEGORIES)
            elif key == "down":
                focus = (focus + 1) % len(state.SHOP_CATEGORIES)
            elif key in ("left", "right", "space"):
                category = state.SHOP_CATEGORIES[focus]
                current = [value for value, _ in modes].index(
                    w.selection.shop[category]
                )
                step = 1 if key != "left" else -1
                w.selection.shop[category] = modes[(current + step) % len(modes)][0]
            elif key == "enter":
                break
            elif key in ("esc", "q"):
                return "back"
    finally:
        w.screen.end()
    return "next"


def _baseline_text(w: Wizard) -> str:
    original = platform.bin_dir(w.game) / f"{state.EXE}.original"
    if original.is_file():
        return f"{state.EXE}.original found in Project/Binaries/Win64"
    return "none yet; it will be created from the live executable"


def screen_review(w: Wizard) -> str:
    changes = state.diff_selection(w.baseline, w.selection)
    counts = state.count_actions(changes)
    empty = w.selection.count() == 0
    removable = empty and w.installed > 0
    if not w.console.tty:
        w.console.write("")
        for change in changes:
            w.console.write(f"   {ACTION_TAGS[change.action]} {change.label}")
        if empty:
            w.console.write(
                "   This removes the installed mods."
                if removable
                else "   Nothing selected."
            )
            if not removable:
                return "quit"
        answer = ui.ask_text(w.console, "Apply these changes? [Y/n]", "y")
        return "apply" if answer.lower() not in ("n", "no") else "back"

    w.screen.begin()
    try:
        while True:
            rows = max(3, w.console.height() - 14)
            body = [
                f" {w.console.dim('Game:')} {w.game}",
                f" {w.console.dim('File:')} {state.EXE}",
                f" {w.console.dim('Backup:')} {_baseline_text(w)}",
                "",
            ]
            visible = changes[:rows]
            for change in visible:
                body.append(f"   {ACTION_TAGS[change.action]}  {change.label}")
            if len(changes) > len(visible):
                body.append(f"   ... and {len(changes) - len(visible)} more")
            if not changes:
                body.append("   No changes.")
            body.append("")
            if removable:
                body.append(
                    w.console.yellow(
                        "   Nothing selected: this removes every installed mod."
                    )
                )
            elif empty:
                body.append(
                    w.console.yellow(
                        "   Nothing selected. Use esc to go back and choose a mod."
                    )
                )
            else:
                body.append(
                    f"   {counts['install']} to install, {counts['change']} to change, "
                    f"{counts['remove']} to remove, {counts['keep']} unchanged."
                )
            hints = (
                "enter apply   esc back"
                if not empty or removable
                else "esc back to the mod list"
            )
            if w.installed:
                hints += "   r restore original"
            footer = [w.console.hint(hints)]
            size = w.console.size()
            _draw(w, "Step 4 of 4: Review", body, footer)
            key = ui.wait_key_or_resize(w.console, size)
            if key is None:
                continue
            if key == "enter" and (not empty or removable):
                return "apply"
            if key == "r" and w.installed:
                return "restore"
            if key in ("esc", "q"):
                return "back"
    finally:
        w.screen.end()


def _wrap(console: ui.Console, text: str, prefix: str = "   ") -> list[str]:
    width = min(console.width(), 100) - 8
    return [prefix + line for line in ui.wrap_text(text, width)]


def _draw_preflight(
    w: Wizard, run: state.PatchRun, tick: int, final: bool, ok: bool
) -> None:
    console = w.console
    if final:
        status = (
            console.green(
                f"{console.check()} Preflight complete - nothing was written."
            )
            if ok
            else console.red(
                f"{console.cross()} Preflight failed - nothing was written."
            )
        )
    else:
        status = f"{console.cyan(ui.spinner(console, tick))} Checking patches..."
    body = [f" {status}", ""]
    if run.total:
        body.append(f" {ui.bar(console, run.fraction())}  {run.done}/{run.total}")
    elif not final:
        body.append(f" {console.dim('Reading and scanning the executable...')}")
    body.append("")
    if run.source_choice:
        body.append(f" {console.dim('Source:')} {run.source_choice}")
    if run.file_size:
        body.append(f" {console.dim('Size:')}   {run.file_size}")
    if run.cave:
        body.append(f" {console.dim('Cave:')}   {run.cave}")
    if run.tables_total:
        body.append(f" {console.dim('Tables:')} {run.tables_ok}/{run.tables_total} ok")
    if not final and run.current:
        body.append("")
        body.append(f" {console.bold(run.current)}")
        for detail in run.patches[-1][1][:2]:
            body.append("   " + console.dim(detail))
    if final and run.selected:
        body.append("")
        for line in _wrap(console, ", ".join(run.selected)):
            body.append(console.dim(line))
    for warning in run.warnings[:4]:
        body.append(" " + console.yellow("[!] " + warning))
    footer = [
        console.hint(
            "enter continue   d details"
            if final
            else "nothing is written during this step"
        )
    ]
    right = f"{run.done}/{run.total}" if run.total else ""
    _draw(w, "Step 1 of 2: Preflight check", body, footer, right=right)


def show_log(w: Wizard, title: str, log: list[str]) -> None:
    visible = max(4, w.console.height() - 9)
    offset = max(0, len(log) - visible)
    w.screen.begin()
    try:
        while True:
            visible = max(4, w.console.height() - 9)
            offset = min(offset, max(0, len(log) - visible))
            shown = log[offset : offset + visible] or [w.console.dim("(empty)")]
            end = min(len(log), offset + visible)
            body = [" " + line for line in shown]
            footer = [
                w.console.hint(
                    f"up/down scroll   enter close   ({offset + 1}-{end} of {len(log)})"
                )
            ]
            size = w.console.size()
            _draw(w, title, body, footer)
            key = ui.wait_key_or_resize(w.console, size)
            if key is None:
                continue
            if key == "up":
                offset = max(0, offset - 1)
            elif key == "down":
                offset = min(max(0, len(log) - visible), offset + 1)
            elif key in ("enter", "esc"):
                return
    finally:
        w.screen.end()


def _await_card(
    w: Wizard, title: str, body: list[str], log: list[str] | None = None
) -> None:
    w.screen.begin()
    try:
        while True:
            footer = [w.console.hint("enter close" + ("   d details" if log else ""))]
            size = w.console.size()
            _draw(w, title, body, footer)
            key = ui.wait_key_or_resize(w.console, size)
            if key is None:
                continue
            if key == "enter":
                return
            if key == "d" and log:
                w.screen.end()
                show_log(w, f"{title} - log", log)
                w.screen.begin()
    finally:
        w.screen.end()


def _run_preflight(w: Wizard, flags: list[str]) -> tuple[bool, state.PatchRun]:
    _remember_flags(flags)
    run = state.PatchRun()
    if not w.console.tty:
        result = platform.run_patcher(PATCH_SCRIPT, w.game, flags, check=True)
        for line in (result.stdout or "").splitlines():
            run.feed(line)
        if result.returncode == 0:
            w.console.write(w.console.green("  All selected patches verified."))
        else:
            for line in (result.stdout or "").splitlines():
                w.console.write("  " + line)
            w.console.write(
                w.console.red("  Patch verification failed. Nothing was written.")
            )
            LAST_LOG[:] = (result.stdout or "").splitlines()
            LAST_ERROR[:] = ["Patch verification failed. Nothing was written."]
        for warning in run.warnings:
            w.console.write(w.console.yellow("  WARNING: " + warning))
        return result.returncode == 0, run

    stream = platform.start_patcher(PATCH_SCRIPT, w.game, flags, check=True)
    tick = 0
    w.screen.begin()
    try:
        while True:
            try:
                line = stream.queue.get(timeout=0.1)
            except queue.Empty:
                _draw_preflight(w, run, tick, False, False)
                tick += 1
                continue
            if line is None:
                break
            run.feed(line)
            _draw_preflight(w, run, tick, False, False)
            tick += 1
    finally:
        w.screen.end()
    code = stream.process.wait()
    ok = code == 0 and not run.failed
    w.screen.begin()
    try:
        _draw_preflight(w, run, tick, True, ok)
        if ok:
            return True, run
        LAST_LOG[:] = run.log
        LAST_ERROR[:] = ["Patch verification failed. Nothing was written."]
        while True:
            size = w.console.size()
            _draw_preflight(w, run, tick, True, False)
            key = ui.wait_key_or_resize(w.console, size)
            if key is None:
                continue
            if key == "enter":
                return False, run
            if key == "d":
                w.screen.end()
                show_log(w, "Preflight log", run.log)
                w.screen.begin()
    finally:
        w.screen.end()


def _draw_install(
    w: Wizard,
    stages: list[tuple[str, str]],
    run: state.PatchRun,
    tick: int,
    note: str,
    applying: bool,
) -> None:
    console = w.console
    lead = (
        console.green(console.check())
        if note == "Done."
        else console.cyan(ui.spinner(console, tick))
    )
    body = [f" {lead} {note}"]
    if applying and run.total:
        body.append(f" {ui.bar(console, run.fraction())}  {run.done}/{run.total}")
    elif applying:
        body.append(f" {console.dim('Working...')}")
    body.append("")
    for label, status in stages:
        line = f" {_stage_mark(console, status)} {label}"
        body.append(console.green(line) if status == "done" else line)
    if w.preflight and (w.preflight.source_choice or w.preflight.tables_total):
        bits = []
        if w.preflight.source_choice:
            bits.append(w.preflight.source_choice.rstrip(".").removeprefix("Using "))
        if w.preflight.tables_total:
            bits.append(f"tables {w.preflight.tables_ok}/{w.preflight.tables_total}")
        if w.preflight.cave:
            bits.append("cave " + w.preflight.cave.split()[0])
        body.append("")
        body.append(" " + console.dim(" · ".join(bits)))
    if applying and run.current:
        body.append("")
        body.append(f" {console.bold(run.current)}")
        for detail in run.patches[-1][1][:2]:
            body.append("   " + console.dim(detail))
    for warning in run.warnings[-3:]:
        body.append(" " + console.yellow("[!] " + warning))
    footer = [console.hint("do not close this window" if applying else "working...")]
    right = f"{run.done}/{run.total}" if applying and run.total else ""
    _draw(w, "Step 2 of 2: Installing", body, footer, right=right)


def _failure_body(w: Wizard, run: state.PatchRun) -> list[str]:
    body = [f" {w.console.red(w.console.cross() + ' Patcher failed')}", ""]
    if run.total:
        body.append(f" {run.done}/{run.total} patches applied")
    body.append(" The executable was not replaced.")
    body.append("")
    for line in run.tail(6):
        body.append("   " + line.strip())
    return body


def _done_body(w: Wizard, summary: dict) -> list[str]:
    console = w.console
    backup = "created" if summary.get("backup") == "created" else "found"
    body = [
        f" {console.green(console.check())} Preflight verified",
        (
            f" {console.green(console.check())} {summary.get('patches', 0)}/"
            f"{summary.get('total', 0)} patches applied and verified"
        ),
        f" {console.green(console.check())} Executable installed (backup {backup})",
        f" {console.green(console.check())} {summary.get('paks', 0)} data paks rebuilt",
        f" {console.green(console.check())} Feature record written",
    ]
    haptics = summary.get("haptics", "not selected")
    if haptics != "not selected":
        body.append(f" {console.green(console.check())} DualSense Haptics {haptics}")
    body.append("")
    body += _wrap(
        console,
        "Run install.bat again to change mods, or choose 'Restore the original "
        "game files' to revert. Save data was not touched.",
    )
    return body


def _run_install(
    w: Wizard, has_haptics: bool, preflight: state.PatchRun | None = None
) -> dict:
    _remember_flags(w.selection.flags())
    w.preflight = preflight
    bindir = platform.bin_dir(w.game)
    original_existed = (bindir / f"{state.EXE}.original").is_file()
    run = state.PatchRun()
    stages: list[tuple[str, str]] = [
        ("Preflight verified", "done"),
        ("Applying patches", "active"),
        ("Installing executable", "pending"),
        ("Write feature record", "pending"),
        ("Finishing touches", "pending"),
    ]
    stream = platform.start_patcher(
        PATCH_SCRIPT, w.game, w.selection.flags(), check=False
    )
    tick = 0
    w.screen.begin()
    try:
        while True:
            try:
                line = stream.queue.get(timeout=0.1)
            except queue.Empty:
                _draw_install(w, stages, run, tick, "Applying patches...", True)
                tick += 1
                continue
            if line is None:
                break
            run.feed(line)
            _draw_install(w, stages, run, tick, "Applying patches...", True)
            tick += 1
        code = stream.process.wait()
        if code != 0 or run.failed:
            stages[1] = ("Applying patches", "failed")
            _draw_install(w, stages, run, tick, "Patcher failed", False)
            w.screen.end()
            card_log = (preflight.log if preflight else []) + run.log
            LAST_LOG[:] = card_log
            LAST_ERROR[:] = _failure_body(w, run)
            _await_card(w, "Installation failed", _failure_body(w, run), card_log)
            return {"ok": False}
        stages[1] = ("Applying patches", "done")

        stages[2] = ("Installing executable", "active")
        _draw_install(w, stages, run, tick, "Installing executable...", False)
        platform.install_patched(bindir, lambda _message: None)
        stages[2] = ("Installing executable", "done")

        stages[3] = ("Write feature record", "active")
        _draw_install(w, stages, run, tick, "Writing feature record...", False)
        platform.move_features(bindir)
        stages[3] = ("Write feature record", "done")

        stages[4] = ("Finishing touches", "active")
        _draw_install(w, stages, run, tick, "Finishing touches...", False)
        haptics = "not selected"
        if os.name == "nt" and w.selection.haptics:
            haptics = (
                "installed"
                if platform.install_haptics(
                    bindir, HAPTICS_SOURCE, lambda _message: None
                )
                else "skipped"
            )
            if haptics == "installed":
                platform.record_haptics(bindir)
        elif os.name == "nt" and has_haptics:
            platform.remove_haptics(bindir, HAPTICS_SOURCE, lambda _message: None)
            haptics = "removed"
        platform.remove_legacy_superjump(bindir, HAPTICS_SOURCE, lambda _message: None)
        stages[4] = ("Finishing touches", "done")
        _draw_install(w, stages, run, tick, "Done.", False)
    finally:
        w.screen.end()

    summary = {
        "ok": True,
        "patches": run.done,
        "total": run.total,
        "paks": run.paks,
        "verified": run.verified,
        "backup": "existing" if original_existed else "created",
        "haptics": haptics,
    }
    card_log = (preflight.log if preflight else []) + run.log
    _await_card(w, "Done", _done_body(w, summary), card_log)
    return summary


def status_screen(w: Wizard) -> str:
    options = ["change", "restore", "quit"]
    labels = [
        "Change installed mods",
        "Restore the original game files",
        "Quit",
    ]
    cursor = 0
    w.screen.begin()
    try:
        while True:
            body = [f" Installed: {w.installed} of {state.total_mods()} mods", ""]
            for index, label in enumerate(labels):
                pointer = w.console.marker() if index == cursor else " "
                body.append(f" {pointer} {label}")
            footer = [w.console.hint("up/down move   enter select   esc quit")]
            size = w.console.size()
            _draw(w, "Freeplay setup", body, footer)
            key = ui.wait_key_or_resize(w.console, size)
            if key is None:
                continue
            if key == "up":
                cursor = (cursor - 1) % len(labels)
            elif key == "down":
                cursor = (cursor + 1) % len(labels)
            elif key == "enter":
                return options[cursor]
            elif key in ("esc", "q"):
                return "quit"
    finally:
        w.screen.end()


def confirm_restore(w: Wizard) -> bool:
    original = platform.bin_dir(w.game) / f"{state.EXE}.original"
    body = _wrap(
        w.console,
        "This copies the original executable over the live one and removes the "
        "mod data paks, haptics and the feature record. Save data is not touched.",
    )
    body.append("")
    if original.is_file():
        body += _wrap(
            w.console,
            f"Backup found: {state.EXE}.original",
            prefix="   ",
        )
    else:
        for line in _wrap(
            w.console,
            "No backup found. Steam > Verify Integrity restores the executable; "
            "the mod data paks will still be removed.",
        ):
            body.append(w.console.yellow(line))
    footer = [w.console.hint("enter restore   esc cancel")]
    w.screen.begin()
    try:
        while True:
            size = w.console.size()
            _draw(w, "Restore the original game files", body, footer)
            key = ui.wait_key_or_resize(w.console, size)
            if key is None:
                continue
            if key == "enter":
                return True
            if key in ("esc", "q"):
                return False
    finally:
        w.screen.end()


def restore_flow(w: Wizard) -> int:
    run_uninstall(w.game, w.console)
    body = [
        f" {w.console.green(w.console.check())} Original executable restored",
        f" {w.console.green(w.console.check())} Mod data paks removed",
        f" {w.console.green(w.console.check())} Feature record removed",
        "",
    ]
    body += _wrap(w.console, "Restart the game from Steam when you are ready.")
    _await_card(w, "Restored", body)
    return 0


def _interactive_flow(game_arg: str | None, console: ui.Console) -> int:
    LAST_LOG.clear()
    LAST_ERROR.clear()
    version = state.mod_version(PATCH_SCRIPT)
    console.clear()
    banner(console, version)
    console.write("")
    game = platform.find_game(game_arg, HERE)
    while game is None:
        console.write(console.yellow("  Could not find SMT5V automatically."))
        console.write("  In Steam: right-click SMT5V > Manage > Browse local files,")
        console.write("  then paste that folder here.")
        answer = ui.ask_text(console, "SMT5V folder (blank to cancel)")
        if not answer:
            console.write("  Cancelled.")
            return 1
        game = platform.normalize_game_dir(answer)
        if game is None:
            console.write(console.red(f"  That folder does not contain {state.EXE}."))
    bindir = platform.bin_dir(game)
    features = state.read_features(bindir / state.FEATURES)
    baseline = state.selection_from(features)
    selection = state.selection_from(features)
    installed = baseline.count()
    status_line(console, game, baseline)

    w = Wizard(
        console=console,
        screen=ui.Screen(console),
        game=game,
        version=version,
        selection=selection,
        baseline=baseline,
        installed=installed,
    )
    if installed:
        while True:
            choice = status_screen(w)
            if choice == "quit":
                console.write("")
                console.write("  Cancelled. Nothing was written.")
                return 1
            if choice == "change":
                break
            if confirm_restore(w):
                return restore_flow(w)

    steps = [screen_mods, screen_gameplay, screen_shop, screen_review]
    index = 0
    while 0 <= index < len(steps):
        result = steps[index](w)
        if result == "apply":
            if w.selection.count() == 0:
                if confirm_restore(w):
                    return restore_flow(w)
                continue
            index = len(steps)
            break
        if result == "restore":
            if confirm_restore(w):
                return restore_flow(w)
            continue
        if result == "next":
            index += 1
        elif result == "back":
            index -= 1
            if index < 0:
                console.write("")
                console.write("  Cancelled. Nothing was written.")
                return 1
        elif result == "quit":
            console.write("")
            console.write("  Cancelled. Nothing was written.")
            return 1

    if w.selection.count() == 0:
        console.write("")
        console.write("  No mods chosen. Nothing was written.")
        return 0

    if not console.tty:
        console.clear()
        banner(console, version)
        status_line(console, game, w.selection)
        if not run_patcher_steps(game, w.selection.flags(), console):
            ui.wait_for_enter(console)
            return 1
        finish_install(
            game,
            w.selection,
            has_haptics=features.get("haptics") == "1",
            console=console,
        )
        console.write("")
        console.write(console.green("  Done - mods installed."))
        console.write("  Run this installer again to change or remove mods.")
        ui.wait_for_enter(console)
        return 0

    ok, preflight_run = _run_preflight(w, w.selection.flags())
    if not ok:
        return 1
    summary = _run_install(w, features.get("haptics") == "1", preflight_run)
    return 0 if summary.get("ok") else 1


def _remember_flags(flags: list[str]) -> None:
    text = "Selected flags: " + (" ".join(flags) if flags else "(none)")
    for index, line in enumerate(LAST_CONTEXT):
        if line.startswith("Selected flags:"):
            LAST_CONTEXT[index] = text
            return
    LAST_CONTEXT.append(text)


def _redact(text: str) -> str:
    replacements = [
        (str(Path.home()), "%USERPROFILE%" if os.name == "nt" else "~"),
        (tempfile.gettempdir(), "%TEMP%" if os.name == "nt" else "$TMPDIR"),
    ]
    for raw, replacement in replacements:
        if raw:
            text = text.replace(raw, replacement)
            text = text.replace(raw.replace("\\", "/"), replacement)
    return text


def _log_candidates() -> list[Path]:
    candidates = [LOG_DIR / LOG_NAME, Path(tempfile.gettempdir()) / LOG_NAME]
    unique: list[Path] = []
    for path in candidates:
        if path not in unique:
            unique.append(path)
    return unique


def _write_log(console: ui.Console, code: int, traceback_text: str = "") -> Path | None:
    lines = [
        "SMT5V Freeplay Installer",
        f"Version: {state.mod_version(PATCH_SCRIPT)}",
        f"Time: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"Python: {sys.version.split()[0]}",
        f"Platform: {sys.platform}",
        f"Exit code: {code}",
    ]
    if LAST_CONTEXT:
        lines += ["", "--- Context ---", *LAST_CONTEXT]
    if console.transcript:
        lines += ["", "--- Installer messages ---", *console.transcript]
    if LAST_ERROR:
        lines += ["", "--- Failure ---", *LAST_ERROR]
    if LAST_LOG:
        lines += ["", "--- Patcher output ---", *LAST_LOG]
    if traceback_text:
        lines += ["", "--- Traceback ---", *traceback_text.rstrip().splitlines()]
    text = "\n".join(_ANSI.sub("", line) for line in lines)
    text = _redact(text) + "\n"
    for path in _log_candidates():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", errors="replace")
        except OSError:
            continue
        return path
    return None


def _write_failure_log(
    console: ui.Console,
    code: int,
    error: list[str] | None = None,
    traceback_text: str = "",
) -> None:
    if error:
        LAST_ERROR[:] = error
    path = _write_log(console, code, traceback_text)
    if path:
        console.write(f"  Full log: {path}")
    else:
        console.write("  Full log: could not be written.")


def run_interactive(game_arg: str | None, console: ui.Console) -> int:
    console.enter_fullscreen()
    try:
        code = _interactive_flow(game_arg, console)
    finally:
        console.leave_fullscreen()
    if code == 0:
        console.write("  Freeplay installer finished.")
    else:
        console.write("  Freeplay installer stopped.")
        if LAST_ERROR or LAST_LOG:
            _write_failure_log(console, code)
    if console.tty:
        ui.wait_for_enter(console, "Press Enter to close")
    return code


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    LAST_LOG.clear()
    LAST_ERROR.clear()
    LAST_CONTEXT.clear()
    game_arg, flags, scripted = split_args(argv)
    LAST_CONTEXT[:] = [
        f"Mode: {'scripted' if scripted else 'interactive'}",
        f"Arguments: {' '.join(argv) if argv else '(none)'}",
    ]
    console = ui.Console()
    try:
        if scripted:
            return run_scripted(game_arg, flags, console)
        return run_interactive(game_arg, console)
    except KeyboardInterrupt:
        console.write("")
        console.write("  Cancelled.")
        return 1
    # Top-level boundary: any unexpected failure must still produce a log.
    except Exception:  # noqa: BLE001
        console.write("")
        console.write("  Installer crashed.")
        _write_failure_log(
            console, 1, ["Unexpected exception."], traceback.format_exc()
        )
        if console.tty:
            ui.wait_for_enter(console, "Press Enter to close")
        return 1


if __name__ == "__main__":
    sys.exit(main())
