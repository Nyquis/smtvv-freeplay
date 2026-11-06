"""Small stdlib terminal UI for the Freeplay installer."""

from __future__ import annotations

import os
import re
import shutil
import sys

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
CYAN = "\x1b[36m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
RED = "\x1b[31m"
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _windows_terminal_hint() -> bool:
    """Terminals that parse ANSI themselves, without a console-mode flag."""
    return bool(
        os.environ.get("WT_SESSION")
        or os.environ.get("ANSICON")
        or os.environ.get("ConEmuANSI") == "ON"
        or os.environ.get("TERM_PROGRAM") in ("vscode", "WezTerm")
    )


def _enable_windows_vt() -> bool:
    if os.name != "nt":
        return True
    try:
        import ctypes
    except ImportError:
        # The bundled embeddable runtime ships without _ctypes. Windows
        # Terminal and friends still render ANSI; a classic console falls
        # back to a clear-and-redraw interface without escape codes.
        return _windows_terminal_hint()
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except (OSError, AttributeError, ValueError):
        return False


def _unicode_ok() -> bool:
    encoding = (sys.stdout.encoding or "").lower()
    return "utf" in encoding


class Console:
    """Colour and width decisions for one terminal."""

    def __init__(self) -> None:
        self.tty = sys.stdin.isatty() and sys.stdout.isatty()
        self.ansi = self.tty and _enable_windows_vt()
        self.color = self.ansi and not os.environ.get("NO_COLOR")
        self.unicode = self.ansi and _unicode_ok()

    def width(self) -> int:
        return max(40, min(100, shutil.get_terminal_size((80, 24)).columns))

    def style(self, text: str, *codes: str) -> str:
        if not self.color or not codes:
            return text
        return "".join(codes) + text + RESET

    def bold(self, text: str) -> str:
        return self.style(text, BOLD)

    def dim(self, text: str) -> str:
        return self.style(text, DIM)

    def cyan(self, text: str) -> str:
        return self.style(text, BOLD, CYAN)

    def green(self, text: str) -> str:
        return self.style(text, GREEN)

    def yellow(self, text: str) -> str:
        return self.style(text, YELLOW)

    def red(self, text: str) -> str:
        return self.style(text, RED)

    def hint(self, text: str) -> str:
        return self.dim(text)

    def marker(self) -> str:
        return "▸" if self.unicode else ">"

    def bullet(self) -> str:
        return "•" if self.unicode else "*"

    def write(self, text: str = "") -> None:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()

    def clear(self) -> None:
        if self.ansi:
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.flush()
        elif self.tty:
            os.system("cls" if os.name == "nt" else "clear")
        else:
            self.write()


def _visible(text: str) -> int:
    return len(_ANSI.sub("", text))


def _fit(text: str, width: int) -> str:
    if _visible(text) <= width:
        return text
    plain = _ANSI.sub("", text)
    return plain[: width - 3] + "..."


class Screen:
    """Redraws a block of lines in place."""

    def __init__(self, console: Console) -> None:
        self.console = console
        self.lines = 0
        self.chrome: list[str] = []

    def begin(self) -> None:
        self.lines = 0
        if self.console.ansi:
            self.console.clear()
            sys.stdout.write("\x1b[?25l")
            sys.stdout.flush()

    def draw(self, lines: list[str]) -> None:
        width = self.console.width()
        if self.console.tty and self.chrome:
            lines = [*self.chrome, ""] + lines
        lines = [_fit(line, width) for line in lines]
        if not self.console.tty:
            for line in lines:
                self.console.write(line)
            return
        if not self.console.ansi:
            self.console.clear()
            for line in lines:
                self.console.write(line)
            return
        parts = []
        if self.lines:
            parts.append(f"\x1b[{self.lines}A")
        height = max(self.lines, len(lines))
        for line in lines:
            parts.append("\x1b[2K" + line + "\n")
        for _ in range(height - len(lines)):
            parts.append("\x1b[2K\n")
        self.lines = height
        sys.stdout.write("".join(parts))
        sys.stdout.flush()

    def end(self) -> None:
        if self.console.ansi:
            sys.stdout.write("\x1b[?25h")
            sys.stdout.flush()
        self.lines = 0


def decode_key(data: bytes) -> str:
    """Map a raw key sequence to an action or a printable character."""
    arrows = {
        b"\x1b[A": "up",
        b"\x1b[B": "down",
        b"\x1b[C": "right",
        b"\x1b[D": "left",
        b"\x1bOA": "up",
        b"\x1bOB": "down",
        b"\x1bOC": "right",
        b"\x1bOD": "left",
    }
    if data in arrows:
        return arrows[data]
    if data in (b"\r", b"\n"):
        return "enter"
    if data == b"\x1b":
        return "esc"
    if data == b" ":
        return "space"
    if data in (b"\x7f", b"\x08"):
        return "backspace"
    if data == b"\t":
        return "tab"
    return data.decode("utf-8", "ignore").lower()


def read_key(console: Console) -> str:
    if not console.tty:
        return "enter"
    if os.name == "nt":
        import msvcrt

        char = msvcrt.getwch()
        if char in ("\x00", "\xe0"):
            code = msvcrt.getwch()
            return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(code, "")
        if char == "\x03":
            raise KeyboardInterrupt
        return decode_key(char.encode("latin-1", "ignore"))
    import select
    import termios
    import tty

    descriptor = sys.stdin.fileno()
    old = termios.tcgetattr(descriptor)
    try:
        tty.setcbreak(descriptor)
        data = os.read(descriptor, 1)
        if data == b"\x1b":
            while len(data) < 3 and select.select([descriptor], [], [], 0.02)[0]:
                data += os.read(descriptor, 1)
        return decode_key(data)
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, old)


def _plain_toggle(console: Console, mods, selected: dict[str, bool]) -> None:
    console.write("  Toggle by number, one per line. Blank line to continue.")
    console.write("  " + "  ".join(f"{i + 1}={mod.key}" for i, mod in enumerate(mods)))
    while True:
        try:
            answer = input("  toggle> ").strip()
        except EOFError:
            return
        if not answer:
            return
        for token in answer.split():
            if token.isdigit() and 1 <= int(token) <= len(mods):
                key = mods[int(token) - 1].key
                selected[key] = not selected.get(key, False)


def checklist(
    console: Console,
    screen: Screen,
    title: str,
    subtitle: str,
    mods,
    selected: dict[str, bool],
    cursor: int = 0,
) -> None:
    if not console.tty:
        _plain_toggle(console, mods, selected)
        return
    screen.begin()
    try:
        while True:
            lines = [console.cyan(title), console.dim(subtitle), ""]
            for index, mod in enumerate(mods):
                pointer = console.marker() if index == cursor else " "
                box = "x" if selected.get(mod.key) else " "
                line = f" {pointer} [{box}] {mod.label}"
                if mod.detail:
                    gap = max(2, 34 - _visible(line))
                    line += " " * gap + console.dim(mod.detail)
                lines.append(line)
            lines.append("")
            lines.append(
                console.hint(
                    "  up/down move   space toggle   a all   n none   enter continue   esc cancel"
                )
            )
            screen.draw(lines)
            key = read_key(console)
            if key == "up":
                cursor = (cursor - 1) % len(mods)
            elif key == "down":
                cursor = (cursor + 1) % len(mods)
            elif key == "space":
                key_name = mods[cursor].key
                selected[key_name] = not selected.get(key_name, False)
            elif key == "a":
                for mod in mods:
                    selected[mod.key] = True
            elif key == "n":
                for mod in mods:
                    selected[mod.key] = False
            elif key == "enter":
                return
            elif key in ("esc", "q"):
                raise KeyboardInterrupt
    finally:
        screen.end()


def radio(
    console: Console,
    screen: Screen,
    title: str,
    subtitle: str,
    options: list[tuple[str, str]],
    index: int,
) -> int:
    """Pick one (value, label) option; returns the chosen index."""
    if not console.tty:
        console.write(console.cyan(title))
        for number, (value, label) in enumerate(options, 1):
            marker = "*" if number - 1 == index else " "
            console.write(f"  {marker} {number}. {label}")
        while True:
            try:
                answer = input(f"  choice [1-{len(options)}] (Enter keeps): ").strip()
            except EOFError:
                return index
            if not answer:
                return index
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                return int(answer) - 1
    screen.begin()
    try:
        while True:
            lines = [console.cyan(title), console.dim(subtitle), ""]
            for position, (_value, label) in enumerate(options):
                pointer = console.marker() if position == index else " "
                dot = "o" if position == index else " "
                lines.append(f" {pointer} ({dot}) {label}")
            lines.append("")
            lines.append(console.hint("  up/down choose   enter confirm   esc cancel"))
            screen.draw(lines)
            key = read_key(console)
            if key == "up":
                index = (index - 1) % len(options)
            elif key == "down":
                index = (index + 1) % len(options)
            elif key == "enter":
                return index
            elif key in ("esc", "q"):
                raise KeyboardInterrupt
    finally:
        screen.end()


def notice(console: Console, screen: Screen, title: str, text: str) -> bool:
    """Show a note; Enter continues, Esc goes back."""
    import textwrap

    width = console.width() - 4
    paragraphs = textwrap.wrap(text, width)
    if not console.tty:
        console.write(console.yellow(title))
        for line in paragraphs:
            console.write("  " + line)
        return True
    screen.begin()
    try:
        while True:
            lines = [console.yellow(title), ""]
            lines.extend("  " + line for line in paragraphs)
            lines.append("")
            lines.append(console.hint("  enter continue   esc back"))
            screen.draw(lines)
            key = read_key(console)
            if key == "enter":
                return True
            if key in ("esc", "q"):
                return False
    finally:
        screen.end()


def ask_text(console: Console, prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        return input(f"  {prompt}{suffix}: ").strip()
    except EOFError:
        return ""


def wait_for_enter(console: Console, message: str = "Press Enter to close") -> None:
    if not console.tty:
        return
    try:
        input(f"  {message}...")
    except EOFError:
        pass
