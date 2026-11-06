"""SMT5V: Vengeance - Freeplay Mod Installer.

The batch and shell launchers only pick a Python interpreter and hand over
their arguments; everything below is standard library only.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import installer_platform as platform
import installer_state as state
import installer_ui as ui

HERE = Path(__file__).resolve().parent
PATCH_SCRIPT = HERE / "patch_smtvv_freeplay.py"
HAPTICS_SOURCE = HERE / "haptics"
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
        return False
    console.write(console.green("  All selected patches verified."))

    show_step(console, 2, 2, "Applying patches (writes game files)")
    result = platform.run_patcher(PATCH_SCRIPT, game, flags, check=False)
    if result.returncode != 0:
        console.write("")
        console.write(console.red("  Patcher failed. See the messages above."))
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
    game = platform.find_game(game_arg, HERE)
    if game is None:
        console.write(console.red("Could not find SMT5V. Pass --game-dir <folder>."))
        return 1
    if flags == ["--uninstall"]:
        return run_uninstall(game, console)
    bindir = platform.bin_dir(game)
    features = state.read_features(bindir / state.FEATURES)
    banner(console, state.mod_version(PATCH_SCRIPT))
    status_line(console, game, state.selection_from(features))
    if not run_patcher_steps(game, flags, console):
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
            rows = max(3, w.console.height() - 12)
            start, end = _window(cursor, len(mods), rows)
            body: list[str] = []
            for index in range(start, end):
                mod = mods[index]
                pointer = w.console.marker() if index == cursor else " "
                box = "x" if checks[mod.key] else " "
                warning = "  !" if mod.warning else ""
                body.append(f" {pointer} [{box}] {mod.label}{warning}")
            body.append("")
            focused = mods[cursor]
            text_width = min(w.console.width(), 100) - 8
            body.extend(
                "   " + line for line in ui.wrap_text(focused.description, text_width)
            )
            if focused.warning:
                body.append("")
                for line in ui.wrap_text(focused.warning, text_width):
                    body.append(w.console.yellow(f"   [!] {line}"))
            footer = [
                w.console.hint(
                    "up/down move   space toggle   a all   n none   enter next   esc quit"
                )
            ]
            _draw(
                w,
                "Step 1 of 4: Core Mods",
                body,
                footer,
                right=f"{start + 1}-{end} of {len(mods)}",
            )
            key = ui.read_key(w.console)
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
            _draw(w, "Step 2 of 4: Gameplay", body, footer)
            key = ui.read_key(w.console)
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
            _draw(w, "Step 3 of 4: Shop", body, footer)
            key = ui.read_key(w.console)
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
            rows = max(3, w.console.height() - 11)
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
            footer = [
                w.console.hint(
                    "enter apply   esc back"
                    if not empty or removable
                    else "esc back to the mod list"
                )
            ]
            _draw(w, "Step 4 of 4: Review", body, footer)
            key = ui.read_key(w.console)
            if key == "enter" and (not empty or removable):
                return "apply"
            if key in ("esc", "q"):
                return "back"
    finally:
        w.screen.end()


def run_interactive(game_arg: str | None, console: ui.Console) -> int:
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
    if installed:
        answer = ui.ask_text(console, "[Enter] change mods   [u] uninstall everything")
        if answer.lower() == "u":
            return run_uninstall(game, console)

    w = Wizard(
        console=console,
        screen=ui.Screen(console),
        game=game,
        version=version,
        selection=selection,
        baseline=baseline,
        installed=installed,
    )
    steps = [screen_mods, screen_gameplay, screen_shop, screen_review]
    index = 0
    while 0 <= index < len(steps):
        result = steps[index](w)
        if result == "apply":
            index = len(steps)
            break
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
        return run_uninstall(game, console)

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


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    game_arg, flags, scripted = split_args(argv)
    console = ui.Console()
    try:
        if scripted:
            return run_scripted(game_arg, flags, console)
        return run_interactive(game_arg, console)
    except KeyboardInterrupt:
        console.write("")
        console.write("  Cancelled.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
