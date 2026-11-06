# Development

Developer setup for the SMT5V Freeplay patch bundle. End users should read
[INSTALL.md](INSTALL.md) instead — they never need pixi.

## Requirements

- [pixi](https://pixi.sh) 0.59 or newer on `PATH`.
- Nothing else. Do **not** install a global Python, use `pip install`, or
  create an ad-hoc virtualenv.

## First-time setup

```pwsh
pixi install
```

This reads the committed `pixi.lock` and creates `.pixi/` inside the repo
(ignored by git and Kopia). Later `pixi run ...` calls reuse it.

## Tasks

| Task | Command | What it does |
| --- | --- | --- |
| `patch` | `pixi run patch` | Runs `patch_smtvv_freeplay.py` with the pixi Python |
| `package` | `pixi run package` | Builds the release zip in `dist/` |
| `test` | `pixi run test` | Runs the test suite (`pytest tests`) |
| `lint` | `pixi run lint` | `ruff check` |
| `fmt` | `pixi run fmt` | `ruff format` — **rewrites files** |
| `fmt-check` | `pixi run fmt-check` | `ruff format --check` |

Append flags and paths directly to the command:

```pwsh
pixi run patch --help
pixi run patch --game-dir "C:\temp\SMT5V-copy" --no-heal
pixi run lint stockpile.py
pixi run fmt-check ue_asset.py
```

`--` is only needed for tasks that declare typed arguments (none of these do),
so passing `--` here would reach the program literally.

## Never patch a real game install

`--game-dir` must point at a **disposable copy** of the game folder. The
patcher backs up and rewrites `SMT5V-Win64-Shipping.exe` and leaves
`.original` / `.patched` files behind. Never run the patcher, `installer.py`,
`install.bat` or `install.sh` against a real installation while developing;
point them at a copy instead.

## Installer

`install.bat` and `install.sh` are thin launchers: they pick the interpreter
and run `installer.py`. All interactive logic lives in Python, stdlib only:

| File | Role |
| --- | --- |
| `installer.py` | Entry point, argument handling, install flow |
| `installer_ui.py` | Terminal layer: colours, key handling, checklist/radio screens |
| `installer_state.py` | Mod catalogue, `Freeplay.features` parsing, patcher flags |
| `installer_platform.py` | Game discovery, haptics, exe/pak file operations |

Keep the two launchers trivial; do not add questions or platform logic to
`install.bat` / `install.sh`. The default interactive flow writes only after
the review screen and the `--check` preflight pass.

## Two Pythons

| Interpreter | Purpose |
| --- | --- |
| `python\python.exe` (Windows) / `python3` (Linux) | **Shipped** runtime used by the installers and end users. Do not remove or replace it; `python/RUNTIME.md` records its source, hash and strip list. |
| `pixi run python` | **Development** interpreter (3.12.x from conda-forge) |

The patcher is stdlib-only, so there are no dependencies to keep in sync
between the two.

## Tests

`pixi run test` runs `pytest tests`. `pytest` is part of the pixi environment
and `pytest.ini` adds the repository root to the import path.

- Tests are change-scoped: cover the code you add or change.
- Ask before expanding coverage beyond that.
- Tests must be hermetic: synthetic fixtures only, no game files, no network.

## Feature registry

`patch_manifest.FEATURES` is the single table for each patch feature: its
installer flag(s), patch entry point, verification sites and data pak.
`static_sites`, `verification_sites` and `FEATURE_PAKS` are derived from it, so
a feature is described in one place. `tests/test_installers.py` checks the
registry against the installer catalogue and flags, while
`tests/test_install_e2e.py` runs the real patcher on a synthetic PE, activates
the result through `installer_platform` and checks the feature record.

## Lint and format

`ruff.toml` sets `target-version = "py312"` and `line-length = 88`. The
existing tree is **not** fully ruff-clean yet. Do not mass-fix or reformat
unrelated files — run the tools against the files you touch, e.g.
`pixi run lint ue_asset.py`.

## Check a game update

```pwsh
pixi run patch -- --check
```

This verifies every executable AOB guard and the data tables the mods depend
on, then stops. It writes nothing — no backup, no `.patched`, no paks. Add the
feature flags you actually use (for example `--reveal both`) so the report
matches your install. Run it first after a game update.

## Release packaging

- `pixi run package` builds `dist/smtvv-freeplay-<version>.zip` from an explicit
  allowlist (`package.py`). Commit nothing in `dist/` — it is ignored.
- Keep `python/`, `repak/` and `DualSenseHaptics` in the zip.
- Do not ship `.pixi/`, tests, CI files or development docs.
- Do not make `install.bat` / `install.sh` depend on pixi: end users do not
  have it.
