"""SMT5V: Vengeance - Freeplay Mod Installer.

Unity-free, stdlib-only installer: the batch and shell launchers only pick a
Python interpreter and hand over their arguments.
"""

from __future__ import annotations

import os
import sys
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


def review(console: ui.Console, screen: ui.Screen, selection: state.Selection) -> None:
    screen.begin()
    try:
        lines = [console.cyan("Review"), ""]
        chosen = [
            mod.label
            for mod in state.PATCH_MODS
            if mod.key not in ("magatsuhi",) and selection.mods.get(mod.key)
        ]
        if selection.magatsuhi != "none":
            mode = (
                "every battle" if selection.magatsuhi == "battle" else "once per chain"
            )
            chosen.append(f"Full Magatsuhi ({mode})")
        if selection.haptics:
            chosen.append("DualSense Haptics")
        if selection.item_hacks != "none":
            chosen.append(
                "Battle Refill" if selection.item_hacks == "refill" else "Stockpile"
            )
        if selection.autosave is not None:
            chosen.append(f"Autosave after battle (slot {selection.autosave})")
        custom_shop = [
            f"{category}: {mode}"
            for category, mode in selection.shop.items()
            if mode != "default"
        ]
        lines.extend(f"  {console.bullet()} {item}" for item in chosen)
        if custom_shop:
            lines.extend(f"  {console.bullet()} Shop {item}" for item in custom_shop)
        if not chosen and not custom_shop:
            lines.append(console.yellow("  Nothing selected."))
        lines.append("")
        lines.append(console.hint("  enter install   esc cancel"))
        screen.draw(lines)
        while True:
            key = ui.read_key(console)
            if key == "enter":
                return
            if key in ("esc", "q"):
                raise KeyboardInterrupt
    finally:
        screen.end()


def run_interactive(game_arg: str | None, console: ui.Console) -> int:
    version = state.mod_version(PATCH_SCRIPT)
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
    selection = state.selection_from(features)
    installed = selection.count()
    status_line(console, game, selection)
    if installed:
        answer = ui.ask_text(console, "[Enter] change mods   [u] uninstall everything")
        if answer.lower() == "u":
            return run_uninstall(game, console)

    screen = ui.Screen(console)
    screen.chrome = [
        console.cyan(f" SMT5V: Vengeance - Freeplay Mod Installer   v{version}"),
        "",
        f" Game: {game}",
        f" Installed: {installed} of {state.total_mods()} mods"
        if installed
        else " Installed: none",
    ]
    shown = [mod for mod in state.MODS if not (mod.windows_only and os.name != "nt")]
    checks = {
        mod.key: (
            selection.haptics
            if mod.key == "haptics"
            else selection.mods.get(mod.key, False)
        )
        for mod in shown
    }
    try:
        ui.checklist(
            console,
            screen,
            "Mods",
            "Space toggles a mod. Enter continues.",
            shown,
            checks,
        )
        for mod in shown:
            if (
                checks.get(mod.key)
                and mod.warning
                and not ui.notice(console, screen, mod.label, mod.warning)
            ):
                return 1
        selection.mods = {
            mod.key: checks.get(mod.key, False)
            for mod in state.PATCH_MODS
            if mod.key != "magatsuhi"
        }
        selection.haptics = bool(checks.get("haptics")) and os.name == "nt"

        hacks = [
            ("refill", "Battle Refill"),
            ("stockpile", "Stockpile"),
            ("none", "Neither"),
        ]
        hacks_index = [value for value, _ in hacks].index(selection.item_hacks)
        selection.item_hacks = hacks[
            ui.radio(
                console,
                screen,
                "Item Hacks",
                "Choose one.",
                hacks,
                hacks_index,
            )
        ][0]

        modes = [
            ("battle", "Every battle"),
            ("chain", "Once per chain"),
            ("none", "Game default"),
        ]
        mode_index = [value for value, _ in modes].index(selection.magatsuhi)
        selection.magatsuhi = modes[
            ui.radio(
                console,
                screen,
                "Full Magatsuhi",
                "When the gauge is refilled.",
                modes,
                mode_index,
            )
        ][0]

        while True:
            default = str(selection.autosave) if selection.autosave else ""
            answer = ui.ask_text(
                console,
                "Autosave slot after battle (1-20, blank keeps, n turns off)",
                default,
            )
            parsed = state.autosave_choice(answer, selection.autosave)
            if parsed == "keep":
                break
            if parsed == "invalid":
                console.write(console.red("  Enter a slot from 1 to 20, or n."))
                continue
            selection.autosave = parsed
            break

        for category in state.SHOP_CATEGORIES:
            options = [
                ("default", "Game default"),
                ("free", "Free, default timing"),
                ("immediate", "Free and available immediately"),
            ]
            current = [value for value, _ in options].index(selection.shop[category])
            selection.shop[category] = options[
                ui.radio(
                    console,
                    screen,
                    f"Shop: {category}",
                    "Stock and price for this category.",
                    options,
                    current,
                )
            ][0]

        review(console, screen, selection)
    except KeyboardInterrupt:
        console.write("")
        console.write("  Cancelled. Nothing was written.")
        return 1

    if selection.count() == 0:
        if installed:
            answer = ui.ask_text(
                console, "[u]ninstall everything, or [Enter] to cancel"
            )
            if answer.lower() == "u":
                return run_uninstall(game, console)
        console.write("")
        console.write("  No mods chosen. Nothing was written.")
        return 0

    console.clear()
    banner(console, version)
    status_line(console, game, selection)
    if not run_patcher_steps(game, selection.flags(), console):
        ui.wait_for_enter(console)
        return 1
    finish_install(
        game, selection, has_haptics=features.get("haptics") == "1", console=console
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
