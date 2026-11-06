# SMT5V: Vengeance - Freeplay Mod

Quality-of-life patch bundle for Shin Megami Tensei V: Vengeance.

> **Fork notice**
>
> This is a personal fork of
> [countlessbats/smtvv-freeplay](https://github.com/countlessbats/smtvv-freeplay),
> maintained by [Nyquis](https://github.com/Nyquis). It is provided on a
> **best-effort basis**: updates happen when time allows, features are not
> guaranteed to work with every game update, and there is no support
> commitment. Back up your saves and use it at your own risk. This project is
> not affiliated with ATLUS or SEGA.

**Current version: 5.22.1**

## Features

1. **Reusable Essences** - essences are no longer consumed when used.
   Discover an essence once, then apply it repeatedly for skills or
   resistances.

2. **Miman Reveal** - every Miman's position is shown on the map from the
   start of the game.

3. **Leyline Auto-Heal** - accessing a leyline fount restores the full
   party's HP and MP for free.

4. **NG+ Miracles From Start** - selected NG+ miracle gates are bypassed so
   they are available without a cleared save.

5. **Free Compendium** - summoning a registered demon from the compendium
   costs no Macca.

6. **Item Hacks** - choose one:
   - **Battle Refill** - any battle item you've found once tops off at the
     start of every battle.
   - **Stockpile** - battle items stack to 99, but each battle still lets you
     use only the normal carry limit of each (for example 5 Somas). Menus show
     the normal limit as the maximum, so extra stock shows as overflow (for
     example 11/10). Items used in battle come out of your stock.

7. **Superjump** - hold jump (Space, or A/B on a controller) to keep rising;
   release to fall. Pressing jump in mid-air starts rising again. While
   airborne you move 50% faster and turn almost instantly. You can fly over
   story triggers, which are not always marked on the map; if events aren't
   triggering after flying over terrain, backtrack and walk.

8. **Shop Stock** - choose per category (consumables, growth items, essences,
   misc) whether stock is free and whether it appears immediately. The growth
   category covers Gospels, Grimoires, Sutras, Balms and Incenses.

9. **Full Magatsuhi** - battles start with a full Magatsuhi gauge: either
   every battle (default) or once per chain. Magatsuhi gain during battle is
   unchanged.

10. **Skip Intro** - no logo or warning screens, no opening movie and no
    "press any button" screen: after a few seconds of black screen the game
    opens straight to the title menu. Controller input sometimes stalls on
    launch; tab out and back in, or open and close the Steam overlay, to
    restore control.

11. **Masakado Unlock** - Masakado offers his powered-up fight without the
    Kiou Sword.

12. **Newborn Clears Compendium** - starting a New Game+ with the Newborn
    method also empties the Demon Compendium, so the compendium, reverse
    fusion and summoning start fresh. The English carry-over lists on the New
    Game+ screen say so; Reborn and Godborn still keep the compendium.

13. **Autosave After Battle** (off unless chosen) - after every battle, once
    you are back on the field, the game saves to a save slot you pick at
    install time (1-20). That slot is overwritten after each battle, so pick
    one you don't use for anything else.

14. **DualSense Haptics** (Windows only) - haptic effects on a DualSense
    controller for battle hits by element, criticals, blocks and misses,
    skills, press turns, Magatsuhi, field actions and menus, triggered by the
    sounds the game plays. Haptics will only work with a wired DualSense
    controller, or wirelessly with the utility DSX, available on Steam. Tune
    each effect with the panel, `DualSenseHaptics\SMTVHaptics.exe` in the
    game's `Project\Binaries\Win64` folder.

15. **Free Estoma** - the Estoma Barrier costs no Magatsuhi: summoning it and
    keeping it through moon phases leave the gauge untouched. Estoma Field I
    still has to be learned, and Estoma Field II becomes redundant.

16. **Leyline Founts** - fount icons are drawn through unexplored fog on the
    main map. The minimap keeps its normal local range, so a fount appears
    there only when it is nearby. This does not unlock the founts or change
    fast travel.

## Requirements

- Shin Megami Tensei V: Vengeance — the **Steam** version, on Windows or
  Steam Deck / Linux (via Proton). Game Pass / Microsoft Store editions use a
  different executable and are not supported.
- No separate Python install is required when using the packaged release.
  A portable Python runtime is included (Windows); on Linux it uses `python3`.
- Nothing else to install: the [repak](https://github.com/trumank/repak)
  pak tool used by the NG+ Miracles patch is bundled (`repak/`, MIT/Apache-2.0
  licensed) for both Windows and Linux/Steam Deck.
- **Internet is needed once on the first install.** repak downloads the Oodle
  runtime (`oo2core_9_win64.dll`) to read the game's compressed paks. It is
  cached in `repak/win64/`, so later runs work offline. If a firewall blocks
  it, allow `repak.exe` and run the installer again.

See **[INSTALL.md](INSTALL.md)** for the full step-by-step. Quick version below.

## Install (Windows)

1. Place this folder inside or near your SMT5V install directory. The
   installer also searches common Steam library locations automatically,
   and if it still can't find the game it asks you to paste your SMT5V
   folder path (in Steam: right-click SMT5V > Manage > Browse local files,
   then copy the path from the address bar).

2. Double-click `install.bat`.

3. Use the installer. It walks through four screens: **Core Mods** (Space
   toggles; the focused mod's description and any warning appear below the
   list), **Gameplay** (Item Hacks, Full Magatsuhi mode, autosave slot),
   **Shop** (a mode per category), and **Review** (what will be installed,
   changed or removed). Enter continues, Esc goes back. The review is the
   first point at which anything is written.

   After the review, a preflight check runs with a progress bar and a summary
   (source, cave, data tables and selected patches). When it passes, the
   installer continues automatically; failures wait so you can read them. The
   install screen tracks each stage and ends with a Done card. Press `d` on the
   Done card (or a failure) to read the full patcher log. The interface follows
   the window if you resize it.

   Run `install.bat` again later to add or remove mods: installed mods are
   pre-selected, and the first screen offers to uninstall everything.

The installer backs up the original executable as:

```text
Project/Binaries/Win64/SMT5V-Win64-Shipping.exe.original
```

It writes the patched executable as:

```text
Project/Binaries/Win64/SMT5V-Win64-Shipping.exe.patched
```

Then it installs the patched executable over the live executable.

## Steam Deck / Linux

Steam Deck runs the same Steam Windows build through Proton, so the patches are
identical. Only the installer differs. In **Desktop Mode**, open the extracted
`SMTVV Freeplay` folder in a terminal (Konsole), or `cd` into it, and run:

```bash
chmod +x install.sh
./install.sh
```

The interface is the same as on Windows (arrow keys, Space, Enter), minus
DualSense Haptics, which needs Windows. Run it again later to add or remove
mods; installed mods are pre-selected and the first screen offers to uninstall
everything. If it can't find the game automatically, it asks you to paste your
SMT5V folder path.

Uninstall with `./uninstall.sh`. (`python3`, used by the patcher, ships with
Desktop Mode.)

If you previously installed an older build with Superjump, remove the old
`WINEDLLOVERRIDES="xinput1_3=n,b" %command%` launch option. The current
installers also remove the known legacy Superjump DLL when they find it.

## Manual Usage

```powershell
python patch_smtvv_freeplay.py
python patch_smtvv_freeplay.py --game-dir "D:\Games\SMT5V"
```

Optional patch flags:

```text
--no-essences
--no-heal
--no-mimans
--leylines
--no-miracles
--no-compendium
--no-refill
--stockpile
--no-jump
--no-shop
--shop-consumables {default,free,immediate}
--shop-growth {default,free,immediate}
--shop-essences {default,free,immediate}
--shop-misc {default,free,immediate}
--no-magatsuhi
--magatsuhi-chain
--no-estoma
--no-intro
--no-masakado
--no-newborn
--autosave-slot N
--game-dir PATH
--check
```

`patch_essences.py` is kept as a compatibility wrapper for older instructions.
New work should use `patch_smtvv_freeplay.py`.

## Uninstall

Run `uninstall.bat` (Windows) or `./uninstall.sh` (Linux), or run `install.bat`
and choose **Restore the original game files** on the first screen. This
restores the original executable and removes the mod's data paks, haptics and
feature record.

You can also restore the executable through Steam:

```text
Steam -> SMT5V -> Properties -> Installed Files -> Verify integrity
```

Note that Verify Integrity does not remove
`pakchunk99_NGPlusMiracles_P.pak` (Steam leaves unknown files alone) — use the
uninstall scripts, or delete that file from `Project/Content/Paks` yourself.

## Building from source

Nothing needs to be compiled to *use* this bundle — the executable patcher
(`patch_smtvv_freeplay.py`) is plain Python, a portable runtime is bundled in
`python/`, and prebuilt [repak](https://github.com/trumank/repak) binaries are
bundled in `repak/` (win64 + linux64, v0.2.3, dual MIT/Apache-2.0 — see
`repak/LICENSE-MIT` and `repak/LICENSE-APACHE`).

`pixi run package` builds the release zip; see `DEVELOPMENT.md`.

## How It Works

### Reusable Essences

Essences are regular inventory items with IDs 311-615. When the player applies
an essence, the game calls `ItemErase` to remove it from inventory. The patch
redirects that trampoline through a code cave that checks the item ID in `ECX`
and returns early for essences. Other items still erase normally.

### Leyline Auto-Heal

The leyline access trampoline is redirected through a code cave that calls the
game's own `PartyAllCure` implementation before continuing to normal leyline
logic.

### Miman Reveal

The map asks `CheckMimanPositionFlag(index)` for each Miman when it builds its
markers. The patch makes that function always return true, so every position
shows without changing save data.

### Leyline Founts

The icon renderer already lets Mimans and Magatsuka icons through the fog-of-war
test. The patch adds `E_MINIMAP_POI_TYPE_RYUKETSU` to that check. The table rows
keep their normal `ShowFar` setting, so the minimap only shows a fount when it is
nearby, while the full map shows founts through unexplored fog. Nothing is
unlocked: fast travel and the founts themselves are unchanged.

### Free Compendium

The demon-cost formula behind every compendium summon price is patched to
return 0, so the compendium shows and charges 0 Macca.

### Shop Stock

Like the NG+ miracle pak, this is a small override pak built at install time
from your own `pakchunk0`. Four categories can be set independently:

| Category | Items |
| --- | --- |
| Consumables | 1-81 |
| Growth items | 82-108: Gospels, Grimoires, Sutras, Balms, Incenses |
| Essences | 311-615 |
| Misc | 109-113: Glory Crystals, Demon Boxes, New Testament Tablet |

Each category has one of three modes:

- **Game default** - nothing changes.
- **Free, default game timing** - buying and selling prices are set to 0, but
  the items keep the shop's original unlock conditions and stock list.
- **Free, available immediately** - prices are set to 0, unlock conditions are
  cleared, and missing entries are added for growth items and misc items.

Essences have no selling price (the game does not sell them), so only their
buying price is cleared. The uninstallers remove the pak.

### Skip Intro

Another small override pak built at install time from your own `pakchunk0`.
The logo sequence starts at its last, invisible hold step, which is lengthened
to four seconds so Steam Input has attached the controller before the title
menu reads it, and the logo game mode no longer requests the title movie, so the title level opens its menu directly, as it
does when you return to the title from in-game. The uninstallers remove the pak.
Because the title menu otherwise comes up with the controller reported as
disconnected, the executable also hooks the title menu's first tick and posts
the window deactivate/activate messages a tab-out and tab-in would send.

### Masakado Unlock

A small override pak built at install time from your own `pakchunk3`.
Masakado's sub-quest script checks for the Kiou Sword in three places before
the scene that leads to his powered-up battle; each check's conditional jump is
pointed at the next instruction, so the script carries on as if the sword were
held. The uninstallers remove the pak.

### Full Magatsuhi

Uses the same `SetNextStep` hook as Battle Refill (below). A battle keeps
its own Magatsuhi gauge for each side, copied from the party's gauge as it
starts and written back as it ends. On the battle's opening steps the
player's gauge is set to its maximum of 100.

Two refill modes are available when installing:

- **Every battle** (default) fills the gauge at the start of every battle,
  including every Boss Rush or chain encounter. Those rounds reuse the same
  battle object; the gauge is full from the start of the round, but the meter
  only redraws on your first action, so it can briefly look unchanged.
- **Once per chain** fills only the first battle of a chain. Later rounds keep
  whatever gauge is left, which matches what the meter shows.

### Free Estoma

In Vengeance, Estoma is a Miracle: the Estoma Barrier drains the Magatsuhi
gauge when it is summoned and again each time the Moon Phase advances. The
costs live in the `BP_EstomaData` Blueprint asset as four integers - the
summon and moon-phase costs, plus the reduced pair used after Estoma Field II.
A small override pak built from your own `pakchunk0` sets all four to zero,
so the barrier never touches the gauge. Estoma Field I still has to be
learned. The uninstallers remove the pak.

### Autosave After Battle

When a battle reaches its last step (`SetNextStep` hook), a save is queued.
It runs from the player's field movement update a couple of seconds later,
after the battle has written its results back, and calls the game's own save
routine for the chosen slot. The battle has already stored the player's
position for saving, so loading the slot returns you to where the battle
started. While it saves, the header the load menu reads is filled the way a
menu save fills it: the player name, the location (the field's current area
name, looked up in your game's own `MapAreaName` table at install time), and
the current text language, which the load menu checks before loading.

### Newborn Clears Compendium

The Newborn carry-over routine is followed by the game's own compendium reset,
which refills the compendium with unregistered entries, exactly as a new game
starts. A small override pak built from your own `pakchunk0` updates the
English carry-over lists: Newborn no longer lists the Demon Compendium and states
that it is not carried over, and Reborn, whose list builds on Newborn's, lists it. Other
languages show the original lists. The uninstallers remove the pak.

### Stockpile

Item tables are left as they are. The item menus show each item's normal
carry limit, while the game's own carry checks are told 99 for every
battle-usable item with a lower limit, so stock above the limit shows as
overflow (for example 11/10). A small override pak built from your own
`pakchunk0` makes the camp item list colour such counts like a full stack
(it normally does so only when the count equals the limit); the
uninstallers remove it. When a battle enters its first step, the stock above each item's
normal limit is set aside; until the battle ends, the item count the game
reports is the real count minus that amount, so the battle offers at most the
normal limit. Using an item takes it from the real stock.

### Battle Refill

The battle step machine's `SetNextStep` is hooked. When a battle enters its
first step, every item that is usable in battle and has been obtained at
least once is topped up to its carry limit with the game's own item calls.
Camp-only consumables such as incenses and Gospels are not refilled.

### Superjump

While jump is held in the focused game window, the rising part of the jump arc
is held at a steady climb speed; releasing it lets the arc continue into the
fall. Pressing jump in mid-air starts a new climb from the current height. While
airborne, the fall-speed cap that governs air movement is raised by 50%, and
the input and rotation damping applied in the air is lifted so the character
turns nearly instantly.

### DualSense Haptics

Installed as `xinput1_3.dll`, which the game loads as its XInput library and
which forwards XInput to the system's, plus the `DualSenseHaptics` folder; the
executable is not patched. The plugin watches the sound cues the game starts
and plays the effect `DualSenseHaptics\cue-map.txt` assigns to each, through
a small bridge program that drives the controller's actuators. The installer
leaves an `xinput1_3.dll` that belongs to another mod in place and skips
DualSense Haptics. Settings in `SMTVHaptics.ini` are kept when reinstalling.

### NG+ Miracles From Start

This combines executable hooks for miracle visibility and purchasability with
a data-pak edit for `GodParameterDataTable`. The installer extracts the table
from your own `pakchunk0-WindowsNoEditor.pak` with the bundled `repak` tool,
applies the edits, and packs the result as
`Project/Content/Paks/pakchunk99_NGPlusMiracles_P.pak`. No game data is
redistributed with the mod — everything is derived from your installed copy
at install time.

## Compatibility Notes

- The executable patches are AOB guarded. If a game update changes the
  expected bytes, the patcher refuses that patch instead of writing blindly.
- Safe to use with existing saves. The installer modifies the executable and
  optional pak files, not save data.

## Development

Working on the patcher or installers uses [pixi](https://pixi.sh) for the
development environment and tasks. See [DEVELOPMENT.md](DEVELOPMENT.md) for
setup, `pixi run` tasks, and testing notes. The bundled `python/` runtime
stays the one end users run.

## License

Nyquis-authored code and modifications are licensed under the **Apache License
2.0** - see [LICENSE](LICENSE) and [NOTICE](NOTICE).

This project is a fork of the MIT-licensed
[countlessbats/smtvv-freeplay](https://github.com/countlessbats/smtvv-freeplay).
Upstream-derived files remain subject to the MIT License, reproduced verbatim
in [LICENSES/MIT.txt](LICENSES/MIT.txt). See [LICENSING.md](LICENSING.md) for
the file-level scope and the release-license history.

The bundled portable Python runtime in `python/` is distributed under the Python
Software Foundation License (see `python/LICENSE.txt`). The bundled `repak`
tool in `repak/` is distributed under its dual MIT/Apache-2.0 license (see
`repak/LICENSE-MIT` and `repak/LICENSE-APACHE`). The bundled DualSense Haptics
bridge includes third-party .NET libraries; see
`haptics/DualSenseHaptics/licenses/THIRD-PARTY-NOTICES.md`.
