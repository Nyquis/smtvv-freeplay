"""Tests for the small terminal UI helpers."""

from __future__ import annotations

import io
import sys

import installer_ui as ui


def test_decode_arrow_sequences():
    assert ui.decode_key(b"\x1b[A") == "up"
    assert ui.decode_key(b"\x1b[B") == "down"
    assert ui.decode_key(b"\x1b[C") == "right"
    assert ui.decode_key(b"\x1b[D") == "left"
    assert ui.decode_key(b"\x1bOA") == "up"
    assert ui.decode_key(b"\x1bOD") == "left"


def test_decode_control_keys():
    assert ui.decode_key(b"\r") == "enter"
    assert ui.decode_key(b"\n") == "enter"
    assert ui.decode_key(b"\x1b") == "esc"
    assert ui.decode_key(b" ") == "space"
    assert ui.decode_key(b"\x7f") == "backspace"
    assert ui.decode_key(b"\t") == "tab"


def test_decode_printable_is_lowercase():
    assert ui.decode_key(b"A") == "a"
    assert ui.decode_key("é".encode()) == "é"


def test_fit_keeps_short_lines_untouched():
    assert ui._fit("hello", 20) == "hello"


def test_wait_key_or_resize_returns_the_key(monkeypatch):
    console = _plain_console()
    console.size = lambda: (80, 24)
    monkeypatch.setattr(ui, "read_key", lambda _c, timeout=None: "enter")
    assert ui.wait_key_or_resize(console, (80, 24)) == "enter"


def test_wait_key_or_resize_detects_a_resize(monkeypatch):
    console = _plain_console()
    sizes = iter([(80, 24), (100, 30)])
    console.size = lambda: next(sizes)
    monkeypatch.setattr(ui, "read_key", lambda _c, timeout=None: None)
    assert ui.wait_key_or_resize(console, (80, 24)) is None


def test_fit_ignores_colour_codes_when_measuring():
    line = "\x1b[36mhello\x1b[0m"
    assert ui._fit(line, 5) == line


def test_fit_truncates_long_lines():
    assert ui._fit("abcdefghij", 6) == "abc..."


def _plain_console():
    console = ui.Console()
    console.tty = True
    console.ansi = False
    console.color = False
    console.unicode = False
    return console


def test_framed_ascii_lines_share_a_width():
    lines = ui.framed(_plain_console(), "Step 1", ["one", "two"], ["hint"])
    assert len({ui._visible(line) for line in lines}) == 1
    assert lines[0].startswith("+")
    assert lines[-1].startswith("+")


def test_bar_uses_unicode_blocks():
    console = _plain_console()
    console.unicode = True
    assert ui.bar(console, 0, 10) == "░" * 10
    assert ui.bar(console, 1, 10) == "█" * 10
    assert len(ui.bar(console, 0.5, 10)) == 10


def test_bar_has_an_ascii_fallback():
    console = _plain_console()
    assert ui.bar(console, 0, 4) == "----"
    assert ui.bar(console, 1, 4) == "####"


def test_spinner_cycles():
    console = _plain_console()
    assert ui.spinner(console, 0) == "|"
    assert ui.spinner(console, 1) == "/"


def test_framed_unicode_uses_box_drawing():
    console = _plain_console()
    console.unicode = True
    lines = ui.framed(console, "Step 1", ["one"], [])
    assert lines[0].startswith("╭")
    assert lines[-1].endswith("╯")
    assert len({ui._visible(line) for line in lines}) == 1


def test_windows_terminal_hint_detects_known_terminals(monkeypatch):
    for name in ("WT_SESSION", "ANSICON", "ConEmuANSI", "TERM_PROGRAM"):
        monkeypatch.delenv(name, raising=False)
    assert ui._windows_terminal_hint() is False
    monkeypatch.setenv("WT_SESSION", "1")
    assert ui._windows_terminal_hint() is True


def test_vt_falls_back_when_ctypes_is_missing(monkeypatch):
    monkeypatch.setattr(ui.os, "name", "nt")
    monkeypatch.setitem(sys.modules, "ctypes", None)
    monkeypatch.setattr(ui, "_windows_terminal_hint", lambda: False)
    assert ui._enable_windows_vt() is False
    monkeypatch.setattr(ui, "_windows_terminal_hint", lambda: True)
    assert ui._enable_windows_vt() is True


def test_enter_and_leave_fullscreen_emit_the_sequences(monkeypatch):
    console = _plain_console()
    console.ansi = True
    console.alt_screen = True
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    console.enter_fullscreen()
    console.leave_fullscreen()
    text = out.getvalue()
    assert "\x1b[?1049h" in text
    assert "\x1b[?1049l" in text


def test_fullscreen_is_a_noop_without_vt(monkeypatch):
    console = _plain_console()
    console.alt_screen = False
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    console.enter_fullscreen()
    console.leave_fullscreen()
    assert out.getvalue() == ""


def test_screen_clears_when_the_terminal_resizes(monkeypatch):
    console = _plain_console()
    console.ansi = True
    sizes = iter([(80, 24), (80, 24), (100, 30)])
    console.size = lambda: next(sizes)
    cleared = []
    console.clear = lambda: cleared.append("clear")
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    screen = ui.Screen(console)
    screen.begin()
    screen.draw(["a"])
    screen.draw(["b"])
    assert cleared == ["clear", "clear"]
