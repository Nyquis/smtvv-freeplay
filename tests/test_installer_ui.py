"""Tests for the small terminal UI helpers."""

from __future__ import annotations

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


def test_fit_ignores_colour_codes_when_measuring():
    line = "\x1b[36mhello\x1b[0m"
    assert ui._fit(line, 5) == line


def test_fit_truncates_long_lines():
    assert ui._fit("abcdefghij", 6) == "abc..."
