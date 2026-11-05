"""Guard against drift between the Windows and Linux installers."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "install.bat"
SH = ROOT / "install.sh"

SHOP_CATEGORIES = ("consumables", "growth", "essences", "misc")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _bat_keys() -> set[str]:
    match = re.search(r'set "BOOL_KEYS=([^"]+)"', _read(BAT))
    assert match, "BOOL_KEYS not found in install.bat"
    return set(match.group(1).split())


def _sh_keys() -> set[str]:
    match = re.search(r"BOOL_KEYS=\(([^)]+)\)", _read(SH))
    assert match, "BOOL_KEYS not found in install.sh"
    return set(match.group(1).split())


def test_installers_expose_the_same_features():
    assert _bat_keys() == _sh_keys()


def test_every_batch_feature_has_a_prompt():
    text = _read(BAT)
    for key in _bat_keys():
        assert re.search(rf"call :ask(?:_warned)? {re.escape(key)}\b", text), key


def test_every_linux_feature_is_asked():
    text = _read(SH)
    for key in _sh_keys():
        assert re.search(rf"\b{re.escape(key)}\b", text)
    assert 'ask "$k"' in text


def test_installers_verify_before_applying():
    bat, sh = _read(BAT), _read(SH)
    for text in (bat, sh):
        assert "Verifying patches" in text
        assert "Patch verification failed" in text
        assert "--check" in text


def test_installers_offer_the_magatsuhi_modes():
    bat, sh = _read(BAT), _read(SH)
    for text in (bat, sh):
        assert "--magatsuhi-chain" in text
        assert "magatsuhi_chain" in text


def test_installers_offer_leylines():
    bat, sh = _read(BAT), _read(SH)
    for text in (bat, sh):
        assert "leylines" in text
        assert "--leylines" in text


def test_installers_handle_the_same_shop_categories():
    bat, sh = _read(BAT), _read(SH)
    for category in SHOP_CATEGORIES:
        assert f"shop_{category}" in bat
        assert f"shop_{category}" in sh
