"""Host operations for the Freeplay installer: discovery, files and processes."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from boot_pak import BOOT_PAK
from estoma import ESTOMA_PAK
from installer_state import BIN_PARTS, EXE, FEATURES, PAKS_PARTS
from newborn import NEWBORN_PAK
from patch_smtvv_freeplay import LEGACY_MAP_PAK, MIRACLE_PAK
from quest_pak import QUEST_PAK
from reveal import REVEAL_PAK
from shop_pak import SHOP_PAK
from stockpile import STOCK_PAK

INSTALLED_PAKS = (
    MIRACLE_PAK,
    SHOP_PAK,
    ESTOMA_PAK,
    REVEAL_PAK,
    BOOT_PAK,
    QUEST_PAK,
    LEGACY_MAP_PAK,
    NEWBORN_PAK,
    STOCK_PAK,
)
LEGACY_SUPERJUMP_SHA256 = (
    "4d51dc377c15006ee4903de265ccda3514900a059d2019498b66ee9dcc56b819"
)


def bin_dir(game_dir: Path) -> Path:
    return game_dir.joinpath(*BIN_PARTS)


def paks_dir(game_dir: Path) -> Path:
    return game_dir.joinpath(*PAKS_PARTS)


def normalize_game_dir(value: str | os.PathLike[str] | None) -> Path | None:
    """Accept the game root, the Win64 folder or the executable itself."""
    if not value:
        return None
    path = Path(str(value).strip().strip('"').strip("'")).expanduser()
    if path.suffix.lower() == ".exe":
        path = path.parent
    for candidate in [path, *list(path.parents)[:4]]:
        if (candidate.joinpath(*BIN_PARTS) / EXE).is_file():
            return candidate
    return None


def _steam_roots() -> list[Path]:
    roots: list[Path] = []
    if os.name == "nt":
        try:
            import winreg
        except ImportError:
            return roots
        locations = (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        )
        for hive, subkey in locations:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    for name in ("SteamPath", "InstallPath"):
                        try:
                            value, _ = winreg.QueryValueEx(key, name)
                        except OSError:
                            continue
                        if value:
                            roots.append(Path(value))
            except OSError:
                pass
    else:
        home = Path.home()
        roots.extend(
            (
                home / ".steam" / "steam",
                home / ".steam" / "root",
                home / ".local" / "share" / "Steam",
            )
        )
    return [root for root in roots if root.is_dir()]


def parse_library_paths(text: str) -> list[Path]:
    """Steam library folders from a libraryfolders.vdf body."""
    return [
        Path(match.group(1).replace("\\\\", "\\"))
        for match in re.finditer(r'"path"\s*"([^"]+)"', text)
    ]


def _libraries(roots: list[Path]) -> list[Path]:
    libraries: list[Path] = []
    for root in roots:
        candidates = [root]
        vdf = root / "steamapps" / "libraryfolders.vdf"
        try:
            candidates.extend(
                parse_library_paths(vdf.read_text(encoding="utf-8", errors="replace"))
            )
        except OSError:
            pass
        for library in candidates:
            if library not in libraries:
                libraries.append(library)
    return libraries


def find_game(explicit: str | None = None, here: Path | None = None) -> Path | None:
    """Locate SMT5V: explicit path, Steam libraries, then relative to `here`."""
    if explicit:
        return normalize_game_dir(explicit)
    candidates: list[Path] = []
    if here is not None:
        base = here.resolve()
        candidates.extend([base, *list(base.parents)[:3]])
    if os.name == "nt":
        for drive in "CDEFGH":
            candidates.extend(
                (
                    Path(f"{drive}:\\SteamLibrary\\steamapps\\common\\SMT5V"),
                    Path(
                        f"{drive}:\\Program Files (x86)\\Steam\\steamapps\\common\\SMT5V"
                    ),
                    Path(f"{drive}:\\Program Files\\Steam\\steamapps\\common\\SMT5V"),
                )
            )
    for library in _libraries(_steam_roots()):
        candidates.append(library / "steamapps" / "common" / "SMT5V")
    for candidate in candidates:
        if (candidate.joinpath(*BIN_PARTS) / EXE).is_file():
            return candidate.resolve()
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def loader_record(bindir: Path, source_root: Path) -> str | None:
    for path in (
        bindir / "DualSenseHaptics" / "loader.sha256",
        source_root / "DualSenseHaptics" / "loader.sha256",
    ):
        try:
            value = path.read_text(encoding="utf-8", errors="replace").strip().lower()
        except OSError:
            continue
        if value:
            return value
    return None


def haptics_owned(bindir: Path, source_root: Path) -> bool:
    dll = bindir / "xinput1_3.dll"
    if not dll.is_file():
        return False
    record = loader_record(bindir, source_root)
    return record is not None and sha256_file(dll) == record


def stop_haptics(bindir: Path) -> None:
    if os.name != "nt" or not (bindir / "DualSenseHaptics").is_dir():
        return
    script = (
        "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and "
        "$_.ExecutablePath.StartsWith([IO.Path]::GetFullPath($env:HDIR), "
        "[StringComparison]::OrdinalIgnoreCase) } | ForEach-Object { "
        "Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; "
        "Wait-Process -Id $_.ProcessId -Timeout 5 -ErrorAction SilentlyContinue }"
    )
    env = dict(os.environ)
    env["HDIR"] = str(bindir / "DualSenseHaptics") + os.sep
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        env=env,
        capture_output=True,
        check=False,
    )


def install_haptics(bindir: Path, source_root: Path, log) -> bool:
    """Copy the haptics loadout; mirrors install.bat's ownership rules."""
    if os.name != "nt":
        return False
    dll = bindir / "xinput1_3.dll"
    if dll.exists() and not haptics_owned(bindir, source_root):
        log(
            "xinput1_3.dll in the game folder belongs to another mod; haptics not installed."
        )
        return False
    log("Installing DualSense Haptics...")
    stop_haptics(bindir)
    try:
        shutil.copytree(
            source_root / "DualSenseHaptics",
            bindir / "DualSenseHaptics",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("loader.sha256"),
        )
        shutil.copy2(source_root / "xinput1_3.dll", dll)
        shutil.copy2(
            source_root / "DualSenseHaptics" / "loader.sha256",
            bindir / "DualSenseHaptics" / "loader.sha256",
        )
    except OSError:
        log("DualSense Haptics could not be copied. Quit the game and try again.")
        return (bindir / "DualSenseHaptics" / "loader.sha256").is_file()
    return True


def remove_haptics(bindir: Path, source_root: Path, log) -> None:
    if haptics_owned(bindir, source_root):
        try:
            (bindir / "xinput1_3.dll").unlink()
        except OSError:
            pass
    if not (bindir / "DualSenseHaptics").is_dir():
        return
    log("Removing DualSense Haptics...")
    stop_haptics(bindir)
    shutil.rmtree(bindir / "DualSenseHaptics", ignore_errors=True)


def remove_legacy_superjump(bindir: Path, source_root: Path, log) -> None:
    dll = bindir / "xinput1_3.dll"
    if not dll.is_file():
        return
    if haptics_owned(bindir, source_root):
        return
    if sha256_file(dll) == LEGACY_SUPERJUMP_SHA256:
        log("Removing legacy Superjump module (xinput1_3.dll)...")
        try:
            dll.unlink()
        except OSError:
            pass
    else:
        log("Found xinput1_3.dll, but it is not the old Superjump module; leaving it.")


def restore_original(bindir: Path, log) -> bool:
    original = bindir / f"{EXE}.original"
    if not original.is_file():
        log("No executable backup found. Use Steam > Verify Integrity to restore.")
        return False
    log("Restoring original executable...")
    shutil.copy2(original, bindir / EXE)
    return True


def remove_paks(game_dir: Path, log) -> None:
    for name in INSTALLED_PAKS:
        path = paks_dir(game_dir) / name
        if path.is_file():
            log(f"Removing {name}...")
            try:
                path.unlink()
            except OSError:
                pass


def install_patched(bindir: Path, log) -> bool:
    patched = bindir / f"{EXE}.patched"
    if not patched.is_file():
        return False
    original = bindir / f"{EXE}.original"
    if not original.is_file():
        log("Backing up original executable...")
        shutil.copy2(bindir / EXE, original)
    log("Installing patched executable...")
    shutil.copy2(patched, bindir / EXE)
    return True


def move_features(bindir: Path) -> None:
    new = bindir / f"{FEATURES}.new"
    if new.is_file():
        os.replace(new, bindir / FEATURES)


def record_haptics(bindir: Path) -> None:
    path = bindir / FEATURES
    if not path.is_file():
        return
    lines = [
        line
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not line.startswith("haptics=")
    ]
    lines.append("haptics=1")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\r\n")


def run_patcher(script: Path, game_dir: Path, flags: list[str], check: bool = False):
    command = [sys.executable, str(script), "--game-dir", str(game_dir), *flags]
    if check:
        command.append("--check")
    return subprocess.run(command, check=False, text=True, capture_output=check)
