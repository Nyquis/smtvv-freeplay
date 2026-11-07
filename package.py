# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""
Build the release zip for end users.

Only shipping files are included: the installers, patcher modules, docs, and
the bundled runtime/repak/haptics folders. Development files (tests, CI,
pixi/ruff config, AGENTS.md) are excluded.

Usage:
    python package.py [--out dist/smtvv-freeplay-<version>.zip]
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARCHIVE_ROOT = "SMTVV Freeplay"

INCLUDE_FILES = (
    "install.bat",
    "install.sh",
    "uninstall.bat",
    "uninstall.sh",
    "installer.py",
    "installer_platform.py",
    "installer_state.py",
    "installer_ui.py",
    "patch_manifest.py",
    "patch_smtvv_freeplay.py",
    "pe_imports.py",
    "signatures.py",
    "patch_essences.py",
    "gameplay_patches.py",
    "ue_asset.py",
    "autosave.py",
    "boot_pak.py",
    "quest_pak.py",
    "newborn.py",
    "shop_pak.py",
    "stockpile.py",
    "estoma.py",
    "leylines.py",
    "reveal.py",
    "README.md",
    "INSTALL.md",
    "LICENSE",
    "NOTICE",
    "LICENSING.md",
)
INCLUDE_DIRS = ("LICENSES", "python", "repak", "haptics")
EXECUTABLES = {"install.sh", "uninstall.sh", "repak/linux64/repak"}
FIXED_TIME = (2020, 1, 1, 0, 0, 0)
# Local runtime files that must never ship: the Oodle DLL is downloaded by
# repak on first use and is not redistributable.
EXCLUDE_PATTERNS = ("oo2core_*.dll", "*.pdb", "*.exp", "*.lib", "*.obj")


def _excluded(path: Path) -> bool:
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDE_PATTERNS)


def version() -> str:
    text = (ROOT / "patch_smtvv_freeplay.py").read_text(encoding="utf-8")
    match = re.search(r'MOD_VERSION = "([^"]+)"', text)
    if not match:
        raise RuntimeError("MOD_VERSION not found")
    return match.group(1)


def iter_files():
    for name in INCLUDE_FILES:
        path = ROOT / name
        if not path.is_file():
            raise RuntimeError(f"missing release file: {name}")
        yield path, f"{ARCHIVE_ROOT}/{name}"
    for name in INCLUDE_DIRS:
        base = ROOT / name
        if not base.is_dir():
            raise RuntimeError(f"missing release directory: {name}")
        for path in sorted(base.rglob("*")):
            if path.is_file() and not _excluded(path):
                rel = path.relative_to(ROOT).as_posix()
                yield path, f"{ARCHIVE_ROOT}/{rel}"


def build_zip(out_path: str | Path) -> tuple[int, Path, int]:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    files = list(iter_files())
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for src, arcname in files:
            rel = arcname[len(ARCHIVE_ROOT) + 1 :]
            mode = 0o755 if rel in EXECUTABLES or src.suffix == ".sh" else 0o644
            info = zipfile.ZipInfo(arcname, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = mode << 16
            archive.writestr(info, src.read_bytes())
    return len(files), out, out.stat().st_size


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Freeplay release zip")
    parser.add_argument(
        "--out",
        default=str(ROOT / "dist" / f"smtvv-freeplay-{version()}.zip"),
        help="output zip path",
    )
    args = parser.parse_args()
    count, path, size = build_zip(args.out)
    print(f"{path}  ({count} files, {size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
