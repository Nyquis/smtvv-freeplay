"""Guard the thin launchers and the installer's flag contract."""

from __future__ import annotations

from pathlib import Path

import installer_platform
import installer_state as state
import patch_manifest

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


def test_registry_covers_every_installer_mod():
    features = {feature.key: feature for feature in patch_manifest.FEATURES}
    for mod in state.PATCH_MODS:
        assert mod.key in features, mod.key
        flags = set(features[mod.key].flags)
        for flag in (mod.on_flag, mod.off_flag):
            if flag:
                assert flag in flags, (mod.key, flag)


def test_every_registry_flag_is_accepted_by_the_patcher():
    text = (ROOT / "patch_smtvv_freeplay.py").read_text(encoding="utf-8")
    for feature in patch_manifest.FEATURES:
        for flag in feature.flags:
            if flag.startswith("--shop-"):
                # The category flags are generated in a loop.
                assert '"--shop-' in text, flag
                continue
            assert f'"{flag}"' in text, (feature.key, flag)


def test_registry_paks_are_installed_by_the_installer():
    installed = set(installer_platform.INSTALLED_PAKS)
    for feature in patch_manifest.FEATURES:
        if feature.pak is not None:
            assert feature.pak in installed, feature.pak
