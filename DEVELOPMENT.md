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
`.original` / `.patched` files behind. Never run the patcher, `install.bat` or
`install.sh` against a real installation while developing.

## Two Pythons

| Interpreter | Purpose |
| --- | --- |
| `python\python.exe` (Windows) / `python3` (Linux) | **Shipped** runtime used by the installers and end users. Do not remove or replace it. |
| `pixi run python` | **Development** interpreter (3.12.x from conda-forge) |

The patcher is stdlib-only, so there are no dependencies to keep in sync
between the two.

## Tests

There is no test suite yet. When tests are needed:

1. Ask before adding `pytest` to the pixi environment.
2. Add a `test` task (`pytest tests`) and a `tests/` directory.
3. Write tests only for code you add or change; ask before expanding coverage
   beyond that.

## Lint and format

`ruff.toml` sets `target-version = "py312"` and `line-length = 88`. The
existing tree is **not** ruff-clean (currently 47 lint findings and 9 files
that would be reformatted). Do not mass-fix or reformat unrelated files — run
the tools against the files you touch, e.g. `pixi run lint ue_asset.py`.

## Release packaging

- Keep `python/`, `repak/` and `DualSenseHaptics` in the release zip.
- Do not ship `.pixi/` (already ignored).
- Do not make `install.bat` / `install.sh` depend on pixi: end users do not
  have it.
