"""Guard the thin launchers and the installer's flag contract."""

from __future__ import annotations

from pathlib import Path

import installer_state as state

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "install.bat"
SH = ROOT / "install.sh"


def test_launchers_hand_over_to_python():
    for path in (BAT, SH):
        assert "installer.py" in path.read_text(encoding="utf-8")


def test_launchers_keep_no_questions():
    bat = BAT.read_text(encoding="utf-8").lower()
    sh = SH.read_text(encoding="utf-8").lower()
    assert "set /p" not in bat
    assert "read -r -p" not in sh


def test_launchers_pass_arguments_through():
    assert "%*" in BAT.read_text(encoding="utf-8")
    assert '"$@"' in SH.read_text(encoding="utf-8")


def test_every_catalogue_flag_exists_in_the_patcher():
    text = (ROOT / "patch_smtvv_freeplay.py").read_text(encoding="utf-8")
    for mod in state.PATCH_MODS:
        for flag in (mod.on_flag, mod.off_flag):
            if flag:
                assert f'"{flag}"' in text, flag


def test_package_ships_the_installer_modules():
    text = (ROOT / "package.py").read_text(encoding="utf-8")
    for name in (
        "installer.py",
        "installer_ui.py",
        "installer_state.py",
        "installer_platform.py",
    ):
        assert f'"{name}"' in text
