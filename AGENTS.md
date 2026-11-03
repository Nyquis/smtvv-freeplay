# AGENTS.md

Working rules for AI agents and contributors in this repository
(**SMT5V: Vengeance — Freeplay Mod**). These rules take precedence over speed or
convenience. If a rule blocks the task, stop and ask the user — do not work
around it.

## 1. Work locally — never touch the host system

- **All development tooling and Python environments go through `pixi`.**
  Declare environments and dependencies in `pixi.toml` (or `pyproject.toml`
  with a `[tool.pixi]` table) and run tasks as `pixi run <task>`. Never use a
  system/global Python, `pip install`, or an ad-hoc `venv` / `virtualenv`.
- Current tasks: `pixi run patch`, `pixi run lint`, `pixi run fmt`,
  `pixi run fmt-check`. `pixi.toml` and `pixi.lock` are committed — do not
  hand-edit the lock file. See `DEVELOPMENT.md` for setup and examples.
- `pixi` is already installed (v0.59). Do not upgrade it or install it
  globally without asking. `.pixi/` is ignored in both `.gitignore` and
  `.kopiaignore`.
- The bundled `python\python.exe` (Windows) / `python3` (Linux) is what ships
  to users and what the installers invoke. Use it only to verify end-user
  behaviour — never to install development dependencies.
- **NEVER install anything globally.** No `pip install` outside pixi, no
  `pip install --user`, no `winget` / `scoop` / `choco` / `npm -g` / `apt` /
  `brew`, and no changes to `PATH`, the registry, shell profiles, services,
  scheduled tasks, firewall rules or global git config.
- A new dependency still requires asking first (§8). Once approved, add it to
  the pixi environment — never install it outside pixi.
- Do not download tools or binaries at runtime. Ask first, and vendor or pin
  anything that is approved — the bundled `python/` and `repak/` exist for
  exactly this reason.
- Shipped code must contain no telemetry, analytics, auto-updaters or
  background network calls.

## 2. Never touch the game install during development

`install.bat`, `install.sh` and the patchers rewrite the live game executable
(`SMT5V-Win64-Shipping.exe`) and leave `.original` / `.patched` files behind.

- **NEVER run an installer or patcher against a real game installation** as
  part of development, testing or verification.
- Use a disposable copy or synthetic fixture instead. If a real install must be
  touched, stop and ask the user explicitly.
- Any action that writes outside this repository needs explicit approval.

## 3. Keep `.gitignore` and `.kopiaignore` in sync

Both files live at the repository root and **MUST be updated together in the
same change**.

- New generated file type → add the same pattern to **both** files.
- Keep sections, ordering and comments aligned so the two stay reviewable
  side by side.
- Ignore: caches, virtualenvs, build output, patcher output, and binaries
  copied from the game.
- **NEVER ignore** source, tests, assets or binaries the project needs to run.
- `.kopiaignore` uses gitignore syntax and is read by Kopia. `.git/` is
  deliberately **not** ignored there so unpushed work stays recoverable;
  explain the reason in a comment before changing that.

## 4. Tests

- Tests are **change-scoped by default**: write tests only for code you add or
  modify. Do not build out a full suite retroactively.
- **Ask before expanding coverage beyond the changed code** — a full test
  suite, refactoring the test layout, or covering untouched modules all need
  the user's approval first.
- A change must cover both the new behaviour and the regression it fixes. If a
  change cannot reasonably be tested, say so and explain why.
- Put tests in `tests/`. **`pytest` is deliberately not installed yet** and
  there is no `test` task — ask before adding both, then run them with
  `pixi run test`.
- Test pure logic that does not need the real game: patch selection,
  offset/byte patching, argument parsing, install-path discovery, pak handling.
- Tests must be hermetic: no network, no real game install, no writes outside
  the repository or a temp directory.
- Run the tests covering the changed code before reporting a change as done,
  and state what you ran and the result. Never claim success without running
  them.
- Adding `pytest` or any other dependency counts as a global install question:
  see §1 and ask first.

## 5. Never leak private information

**NEVER** put any of the following in code, tests, fixtures, documentation,
examples, commit messages or branch names:

- tokens, API keys, passwords, cookies, `.env` contents
- Steam IDs or account names, email addresses, real names, machine names, IPs
- save files, dumped game assets, or logs containing any of the above
- absolute paths that identify the user — write `C:\Users\<user>\...` instead

Before every commit:

- review `git diff` and `git status` for files staged by accident
- confirm generated output (`*.patched`, `*.original`, `*.pak`, caches) is not
  staged
- use placeholders in examples and fixtures

## 6. Git and remotes

- `origin` is the `Nyquis` fork; `upstream` is `countlessbats`. Push to
  `origin` only.
- **NEVER** push to `upstream`, force-push, or rewrite published history
  without explicit permission.
- This checkout authenticates `origin` as `Nyquis` through repo-local config.
  Do not change `credential.*` or `user.*`, and do not run `gh auth switch`.
- Keep commits focused and explain the *why* in the message.

## 7. Project conventions

- Python 3.12; prefer the standard library over new dependencies.
- `pixi.toml` (plus `pixi.lock`) is the source of truth for the development
  environment — commit the lock file, and never hand-edit `.pixi/`.
- `ruff.toml` configures linting/formatting (`py312`, line length 88). The
  existing tree is not ruff-clean: do not mass-fix or reformat unrelated
  files — run `pixi run lint <file>` / `pixi run fmt-check <file>` on what you
  change.
- `DEVELOPMENT.md` documents the dev workflow. Keep it in sync when tasks or
  setup change.
- `install.bat` and `install.sh` must stay feature-matched — a change to one
  usually needs the matching change in the other.
- When behaviour changes, update `README.md`, `INSTALL.md` and `uninstall.*`
  so they stay consistent with the installers.
- Bundled binaries (`python/`, `repak/`, `DualSenseHaptics`) are committed.
  Do not rebuild or replace them without asking.
- Line endings are enforced by `.gitattributes` (`*.sh` → LF, `*.bat` → CRLF).
  Do not change it or renormalise existing files.
- Keep the version string in `README.md` in sync with any release change.

## 8. Ask, don't assume

Ask before:

- installing anything (§1), including adding a dependency to pixi
- touching anything outside this repository (§2)
- changing defaults, the install flow, or patched game behaviour
- expanding tests beyond the changed code (§4)
- adding CI or new top-level directories
- deleting or renaming files, or rewriting history
- changing the release version

State assumptions explicitly when you proceed. If a request is ambiguous, ask
one focused question instead of guessing.
