# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Change-scoped tests for package.py."""

from __future__ import annotations

import zipfile

import package


def _names(path):
    with zipfile.ZipFile(path) as archive:
        return set(archive.namelist())


def test_release_zip_contains_shipping_files_only(tmp_path):
    out = tmp_path / "release.zip"
    count, path, size = package.build_zip(out)

    assert count > 0 and size > 0
    names = _names(path)
    for required in (
        "SMTVV Freeplay/install.bat",
        "SMTVV Freeplay/install.sh",
        "SMTVV Freeplay/patch_smtvv_freeplay.py",
        "SMTVV Freeplay/pe_imports.py",
        "SMTVV Freeplay/feature_patches.py",
        "SMTVV Freeplay/code_caves.py",
        "SMTVV Freeplay/leylines.py",
        "SMTVV Freeplay/reveal.py",
        "SMTVV Freeplay/README.md",
        "SMTVV Freeplay/LICENSE",
        "SMTVV Freeplay/NOTICE",
        "SMTVV Freeplay/LICENSING.md",
        "SMTVV Freeplay/LICENSES/MIT.txt",
        "SMTVV Freeplay/python/LICENSE.txt",
        "SMTVV Freeplay/repak/LICENSE-MIT",
        "SMTVV Freeplay/repak/LICENSE-APACHE",
        "SMTVV Freeplay/haptics/DualSenseHaptics/licenses/THIRD-PARTY-NOTICES.md",
        "SMTVV Freeplay/python/python.exe",
        "SMTVV Freeplay/repak/win64/repak.exe",
        "SMTVV Freeplay/haptics/DualSenseHaptics/SMTVHaptics.exe",
    ):
        assert required in names

    for excluded in (
        "SMTVV Freeplay/AGENTS.md",
        "SMTVV Freeplay/pixi.toml",
        "SMTVV Freeplay/package.py",
    ):
        assert excluded not in names
    assert not any(name.startswith("SMTVV Freeplay/tests/") for name in names)
    assert not any(name.startswith("SMTVV Freeplay/.github/") for name in names)


def test_shell_scripts_keep_the_executable_bit(tmp_path):
    _, path, _ = package.build_zip(tmp_path / "release.zip")
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("SMTVV Freeplay/install.sh")
        repak = archive.getinfo("SMTVV Freeplay/repak/linux64/repak")
    assert info.external_attr >> 16 == 0o755
    assert repak.external_attr >> 16 == 0o755


def test_local_runtime_files_are_excluded(tmp_path):
    _, path, _ = package.build_zip(tmp_path / "release.zip")
    names = _names(path)
    assert not any("oo2core_" in name for name in names)
    assert not any(name.endswith(".pdb") for name in names)
