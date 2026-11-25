# AGENTS.md

Working rules for AI agents and contributors in this repository
(**SMT5V: Vengeance — Freeplay Mod**). These rules take precedence over speed or
convenience. If a rule blocks the task, stop and ask the user — do not work
around it.

## 1. Work locally — never touch the host system

- **All development tooling and Python environments go through `pixi`.**
  Declare environments and dependencies in `pixi.toml` (or `pyproject.toml`
  with a `[tool.pixi]` table) and run tasks as `pixi run <task>`.
- Current tasks: `pixi run patch`, `pixi run lint`, `pixi run fmt`,
  `pixi run fmt-check`, `pixi run test`, `pixi run package`. `pixi.toml` and
  `pixi.lock` are committed — do not hand-edit the lock file. See
  `DEVELOPMENT.md` for setup and examples.
- `pixi` is already installed (v0.59). Do not upgrade it or install it
  globally without asking. `.pixi/` is ignored in both `.gitignore` and
  `.kopiaignore`.
- The bundled `python\python.exe` (Windows) / `python3` (Linux) is what ships
  to users and what the installers invoke. Use it only to verify end-user
  behaviour — never to install development dependencies.
- Do not download tools or binaries at runtime. Ask first, and vendor or pin
  anything that is approved — the bundled `python/` and `repak/` exist for
  exactly this reason.
- If a firewall, proxy, sandbox or permission rule blocks a network or tool
  operation, **STOP and tell the user** so they can unblock it. Never work
  around the block: no alternate mirrors, no disabling security controls, no
  guessing at the missing data.
- Shipped code must contain no telemetry, analytics, auto-updaters or
  background network calls.

## 2. Never touch the game install during development

`install.bat`, `install.sh` and the patchers rewrite the live game executable
(`SMT5V-Win64-Shipping.exe`) and leave `.original` / `.patched` files behind.

- **NEVER run an installer or patcher against a real game installation** as
  part of development, testing or verification.
- Use a disposable copy or synthetic fixture instead. If a real install must be
  touched, stop and ask the user explicitly.
- **Never create new files or directories inside the game or any program
  install tree** while developing or analysing. Leave those installs clean:
  write scratch data to this repository or the system temp directory. Reading
  is fine; writing is not. (The shipped installer writes its paks and exe
  backups there when a *user* runs it — that is product behaviour, not
  development.)
- Any action that writes outside this repository needs explicit approval.

## 3. Keep `.gitignore` and `.kopiaignore` in sync

Both live at the repository root and **MUST be updated together in the same
change**, with matching sections and comments.

- Ignore caches, virtualenvs, build output, patcher output, and binaries copied
  from the game. **NEVER ignore** source, tests, assets or binaries the project
  needs to run.
- `.kopiaignore` is a superset for backups. `.git/` is deliberately **not**
  ignored there so unpushed work stays recoverable; explain the reason in a
  comment before changing that.

## 4. Tests

- Tests are **change-scoped by default**: write them only for code you add or
  modify. A change must cover both the new behaviour and the regression it
  fixes. If it cannot reasonably be tested, say so and explain why.
- Put tests in `tests/` and run them with `pixi run test` (`pytest.ini` sets the
  import path).
- Test pure logic that does not need the real game: patch selection,
  offset/byte patching, argument parsing, install-path discovery, pak handling.
- Tests must be hermetic: no network, no real game install, no writes outside
  the repository or a temp directory.
- State what you ran and the result. Never claim success without running it.

## 5. Never leak private information

**NEVER** put any of the following in code, tests, fixtures, documentation,
examples, commit messages or branch names:

- tokens, API keys, passwords, cookies, `.env` contents
- Steam IDs or account names, email addresses, real names, machine names, IPs
- save files, dumped game assets, or logs containing any of the above
- absolute paths that identify the user — write `C:\Users\<user>\...` instead
- generated caches that embed absolute paths (`__pycache__/*.pyc`,
  `.pytest_cache/`); both are ignored and must never be committed

Before every commit, review `git diff` and `git status` for files staged by
accident, and confirm generated output (`*.patched`, `*.original`, `*.pak`,
caches) is not staged.

## 6. Git and remotes

- `origin` is the `Nyquis` fork; `upstream` is `countlessbats`. When the user
  asks for a push in that same request, push to `origin` only.
- **NEVER** push to `upstream`, force-push, or rewrite published history
  without explicit permission.
- This checkout authenticates `origin` as `Nyquis` through repo-local config.
  Do not change `credential.*` or `user.*`, and do not run `gh auth switch`.
- Before every push, audit what is being published for machine-identifying
  text: `C:\Users\<name>`, `C:/Users/<name>`, `/home/<name>`, `AppData`, the
  machine hostname and account names. Check the staged diff **and**
  `git log -p --all`; both must come back clean.

## 7. Project conventions

- Python 3.12; prefer the standard library over new dependencies.
- `ruff.toml` configures linting/formatting (`py312`, line length 88). The
  existing tree is not ruff-clean: do not mass-fix or reformat unrelated
  files — run `pixi run lint <file>` / `pixi run fmt-check <file>` on what you
  change.
- `DEVELOPMENT.md` documents the dev workflow. Keep it in sync when tasks or
  setup change.
- `install.bat` and `install.sh` must stay feature-matched — a change to one
  usually needs the matching change in the other. Update `README.md`,
  `INSTALL.md` and `uninstall.*` when behaviour changes.
- Bundled binaries (`python/`, `repak/`, `DualSenseHaptics`) are committed.
  Do not rebuild or replace them without asking.
- Keep `LICENSE`, `NOTICE`, `LICENSING.md` and `LICENSES/MIT.txt` in sync.
  Nyquis-authored code is Apache-2.0; upstream-derived files stay MIT and must
  keep the upstream notice. `tests/test_license.py` enforces the file-level
  declarations and the release archive contents.
- Line endings are enforced by `.gitattributes` (`*.sh` → LF, `*.bat` → CRLF).
  Do not change it or renormalise existing files.
- Keep the version string in `README.md` in sync with any release change.

## 8. Ask, don't assume

Ask before changing defaults, the install flow, or patched game behaviour;
before adding a dependency to pixi; before adding CI or new top-level
directories; before deleting or renaming files or rewriting history; and before
changing the release version.

State assumptions explicitly when you proceed. If a request is ambiguous, ask
one focused question instead of guessing.
