# Licensing

This repository contains three kinds of material:

1. **Code and modifications authored by Nyquis** — Apache License 2.0.
2. **Code derived from the upstream `countlessbats/smtvv-freeplay` project** —
   MIT License, reproduced in [LICENSES/MIT.txt](LICENSES/MIT.txt).
3. **Bundled third-party components** — their own licenses, listed below.

The root [LICENSE](LICENSE) is the Apache License 2.0. It applies to the
Nyquis-authored code and to Nyquis's modifications. The upstream MIT notice is
retained in [LICENSES/MIT.txt](LICENSES/MIT.txt) and must remain with any
distribution that includes upstream-derived material.

## File scope

### Apache-2.0

These files were added by Nyquis and are licensed under Apache-2.0:

- `installer.py`, `installer_platform.py`, `installer_state.py`,
  `installer_ui.py`
- `patch_manifest.py`, `signatures.py`, `leylines.py`, `estoma.py`,
  `reveal.py`, `package.py`
- `tests/` (all test modules)
- `pixi.toml`, `ruff.toml`, `pytest.ini`, `.kopiaignore`
- `.github/workflows/` (CI and release workflows)
- `AGENTS.md`, `DEVELOPMENT.md`, `python/RUNTIME.md`
- `haptics/DualSenseHaptics/licenses/THIRD-PARTY-NOTICES.md`

### MIT + Apache-2.0

These files started as upstream MIT code and contain modifications by Nyquis.
They carry an SPDX header of `MIT AND Apache-2.0` where they are source code:

- `patch_smtvv_freeplay.py`
- `gameplay_patches.py`
- `stockpile.py`
- `newborn.py`
- `shop_pak.py`
- `ue_asset.py`
- `install.bat`, `install.sh`
- `uninstall.bat`, `uninstall.sh`
- `README.md`, `INSTALL.md` (documentation; no SPDX header)

### MIT only

These files are upstream code and were not modified by Nyquis:

- `autosave.py`
- `boot_pak.py`
- `quest_pak.py`
- `patch_essences.py`
- `haptics/DualSenseHaptics/` (the haptics component and its assets, except
  the Nyquis-authored `licenses/THIRD-PARTY-NOTICES.md`)

### Third-party components

- **Python 3.12 runtime** in `python/`: Python Software Foundation License 2.0.
  See `python/LICENSE.txt`.
- **repak** in `repak/`: dual MIT/Apache-2.0. See `repak/LICENSE-MIT` and
  `repak/LICENSE-APACHE`.
- **DualSense Haptics dependencies**: MIT and BSD-2-Clause. See
  `haptics/DualSenseHaptics/licenses/THIRD-PARTY-NOTICES.md` and
  `haptics/DualSenseHaptics/licenses/MinHook.txt`.

The development environment in `pixi.lock` lists build-time packages under
their own licenses. Those packages are not part of the release archive.

## Release history

Releases up to and including **v5.21.0** were published under the MIT License.
Starting with **v5.22.0**, Nyquis-authored code and modifications are licensed
under Apache-2.0, with the upstream MIT terms retained as described above.
Already-published release artifacts are not relicensed retroactively.

## Upstream attribution

The upstream project is
[countlessbats/smtvv-freeplay](https://github.com/countlessbats/smtvv-freeplay).
Its MIT license text is preserved verbatim in
[LICENSES/MIT.txt](LICENSES/MIT.txt). The fork notice in
[README.md](README.md) and [INSTALL.md](INSTALL.md) is part of the required
attribution and should not be removed.

## Contributions

Unless a contributor states otherwise, contributions to this fork are accepted
under the Apache License 2.0 for new material and under the existing MIT terms
for upstream-derived material. Do not contribute code you do not have the
right to license on those terms.
