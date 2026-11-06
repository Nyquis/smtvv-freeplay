"""Small stdlib terminal UI for the Freeplay installer."""

from __future__ import annotations

import os
import re
import shutil
import sys
import textwrap

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
        # A runtime without _ctypes can still run in a terminal that parses
        # ANSI; a classic console falls back to clear-and-redraw.
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
    """Colour, size and redraw decisions for one terminal."""

    def __init__(self) -> None:
        self.tty = sys.stdin.isatty() and sys.stdout.isatty()
        self.ansi = self.tty and _enable_windows_vt()
        self.color = self.ansi and not os.environ.get("NO_COLOR")
        self.unicode = self.ansi and _unicode_ok()

    def width(self) -> int:
        return max(40, min(100, shutil.get_terminal_size((80, 24)).columns))

    def height(self) -> int:
        return max(16, shutil.get_terminal_size((80, 24)).lines)

    def size(self) -> tuple[int, int]:
        return self.width(), self.height()

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

    def check(self) -> str:
        return "✓" if self.unicode else "+"

    def cross(self) -> str:
        return "✗" if self.unicode else "x"

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


def _pad(text: str, width: int) -> str:
    gap = max(0, width - _visible(text))
    return text + " " * gap


def _fit(text: str, width: int) -> str:
    if _visible(text) <= width:
        return text
    plain = _ANSI.sub("", text)
    return plain[: width - 3] + "..."


def spinner(console: Console, tick: int) -> str:
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏" if console.unicode else "|/-\\"
    return frames[tick % len(frames)]


def bar(console: Console, fraction: float, width: int = 28) -> str:
    fraction = max(0.0, min(1.0, fraction))
    filled = round(width * fraction)
    full = "█" if console.unicode else "#"
    empty = "░" if console.unicode else "-"
    return full * filled + empty * (width - filled)


def wrap_text(text: str, width: int) -> list[str]:
    return textwrap.wrap(text, max(10, width)) or [""]


def framed(
    console: Console,
    title: str,
    body: list[str],
    footer: list[str],
    right: str = "",
) -> list[str]:
    """Draw a box around body lines, padded to a common visible width."""
    width = min(console.width(), 100)
    inner = width - 4
    if console.unicode:
        tl, tr, bl, br = "╭", "╮", "╰", "╯"
        hor, ver, ml, mr = "─", "│", "├", "┤"
    else:
        tl = tr = bl = br = ml = mr = "+"
        hor, ver = "-", "|"

    head = f"{hor} {title} "
    tail = f" {right} " if right else hor
    dashes = max(0, width - 2 - _visible(head) - _visible(tail))
    lines = [tl + head + hor * dashes + tail + tr]
    for line in body:
        lines.append(f"{ver} {_pad(_fit(line, inner), inner)} {ver}")
    if footer:
        lines.append(ml + hor * (width - 2) + mr)
        for line in footer:
            lines.append(f"{ver} {_pad(_fit(line, inner), inner)} {ver}")
    lines.append(bl + hor * (width - 2) + br)
    return lines


class Screen:
    """Redraws a block of lines in place."""

    def __init__(self, console: Console) -> None:
        self.console = console
        self.lines = 0

    def begin(self) -> None:
        self.lines = 0
        if self.console.ansi:
            self.console.clear()
            sys.stdout.write("\x1b[?25l")
            sys.stdout.flush()

    def draw(self, lines: list[str]) -> None:
        width = self.console.width()
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


def read_key(console: Console, timeout: float | None = None) -> str | None:
    if not console.tty:
        return "enter"
    if os.name == "nt":
        import msvcrt
        import time

        if timeout is not None:
            deadline = time.monotonic() + timeout
            while not msvcrt.kbhit():
                if time.monotonic() >= deadline:
                    return None
                time.sleep(0.03)
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
        if timeout is not None and not select.select([descriptor], [], [], timeout)[0]:
            return None
        data = os.read(descriptor, 1)
        if data == b"\x1b":
            while len(data) < 3 and select.select([descriptor], [], [], 0.02)[0]:
                data += os.read(descriptor, 1)
        return decode_key(data)
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, old)


def wait_key_or_resize(
    console: Console, size: tuple[int, int], timeout: float = 0.25
) -> str | None:
    """Return the next key, or None when the terminal was resized."""
    while True:
        key = read_key(console, timeout)
        if key is not None:
            return key
        if console.size() != size:
            return None


def plain_toggle(console: Console, mods, selected: dict[str, bool]) -> None:
    """Line-mode checklist for terminals without a TUI."""
    console.write("  Mods (numbers toggle; blank line continues):")
    for index, mod in enumerate(mods, 1):
        console.write(
            f"   {index:2d}. [{'x' if selected.get(mod.key) else ' '}] {mod.label}"
        )
        console.write(f"       {mod.description}")
        if mod.warning:
            console.write(f"       [!] {mod.warning}")
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
