# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Guard the repository's license files and per-file SPDX declarations."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

NEW_FILES = (
    "installer.py",
    "installer_platform.py",
    "installer_state.py",
    "installer_ui.py",
    "patch_manifest.py",
    "signatures.py",
    "leylines.py",
    "estoma.py",
    "reveal.py",
    "package.py",
)

MIXED_FILES = (
    "patch_smtvv_freeplay.py",
    "gameplay_patches.py",
    "stockpile.py",
    "newborn.py",
    "shop_pak.py",
    "ue_asset.py",
    "install.bat",
    "install.sh",
    "uninstall.bat",
    "uninstall.sh",
)

PURE_UPSTREAM_FILES = (
    "autosave.py",
    "boot_pak.py",
    "quest_pak.py",
    "patch_essences.py",
)


def test_root_license_is_apache_2_0():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.lstrip().startswith("Apache License")
    assert "Version 2.0, January 2004" in text


def test_upstream_mit_notice_is_preserved():
    text = (ROOT / "LICENSES" / "MIT.txt").read_text(encoding="utf-8")
    assert text.startswith("MIT License")
    assert "Permission is hereby granted, free of charge" in text
    assert "THE SOFTWARE IS PROVIDED" in text


def test_notice_attributes_upstream_and_third_party():
    text = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "countlessbats/smtvv-freeplay" in text
    assert "MIT License" in text
    assert "Apache License" in text
    assert "Python 3.12 runtime" in text
    assert "repak" in text
    assert "DualSense Haptics" in text


def test_licensing_scope_and_history_are_documented():
    text = (ROOT / "LICENSING.md").read_text(encoding="utf-8")
    assert "v5.21.0" in text
    assert "v5.22.0" in text
    assert "Apache-2.0" in text
    assert "LICENSES/MIT.txt" in text


def test_readme_and_haptics_notice_point_to_the_new_terms():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "licensed under the **MIT License**" not in readme
    assert "Apache License" in readme
    assert "LICENSING.md" in readme

    notice = (
        ROOT / "haptics" / "DualSenseHaptics" / "licenses" / "THIRD-PARTY-NOTICES.md"
    ).read_text(encoding="utf-8")
    assert "LICENSES/MIT.txt" in notice
    assert "root `LICENSE`" not in notice


def test_new_source_files_carry_an_apache_header():
    for name in NEW_FILES:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "SPDX-License-Identifier: Apache-2.0" in text, name


def test_mixed_source_files_carry_both_licenses_and_a_change_notice():
    for name in MIXED_FILES:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "SPDX-License-Identifier: MIT AND Apache-2.0" in text, name
        assert "Modified by Nyquis" in text, name


def test_tests_carry_an_apache_header():
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        assert "SPDX-License-Identifier: Apache-2.0" in text, path.name


def test_pure_upstream_files_stay_under_mit_only():
    for name in PURE_UPSTREAM_FILES:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "SPDX-License-Identifier" not in text, name
