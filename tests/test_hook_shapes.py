# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Source-level guard for the stack/shadow-space discipline of every hook.

This is intentionally simple: each call hook must contain its known-safe
prologue/epilogue pair. The heal hook has a dedicated byte-level test.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CASES = (
    ("gameplay_patches.py", "53 56 57", "48 83 EC 20"),  # refill
    ("gameplay_patches.py", "53 48 83 EC 20 48 89 CB", "48 83 C4 20 5B C3"),
    ("gameplay_patches.py", "48 83 EC 28", "48 83 C4 28"),  # jump vcall
    ("gameplay_patches.py", "48 81 EC A8", "48 81 C4 A8"),  # jump arc
    ("gameplay_patches.py", "48 83 EC 38", "48 83 C4 38"),  # refocus
    ("gameplay_patches.py", "53 48 83 EC 30", "48 83 C4 30"),  # refocus thread
    ("stockpile.py", "53 48 83 EC 20 89 CB", "48 83 C4 20 5B C3"),
    ("stockpile.py", "53 56 57 48 83 EC 20 48 89 CB", "48 83 C4 20 5F 5E 5B C3"),
    ("stockpile.py", "53 48 83 EC 20 4C 89 C3", "48 83 C4 20 5B C3"),
    ("autosave.py", "53 48 83 EC 20 48 89 CB", "48 83 C4 20 5B C3"),
    ("autosave.py", "51 52 41 50 41 51 48 83 EC 68", "48 83 C4 68"),
    ("autosave.py", "53 48 83 EC 20", "48 83 C4 20 5B C3"),
    ("autosave.py", "56 48 83 EC 20", "48 83 C4 20 5E C3"),
    ("newborn.py", "48 83 EC 28", "48 83 C4 28 C3"),
)


def test_every_call_hook_keeps_its_safe_frame():
    for filename, prologue, epilogue in CASES:
        text = (ROOT / filename).read_text(encoding="utf-8")
        assert prologue in text, (filename, prologue)
        assert epilogue in text, (filename, epilogue)
