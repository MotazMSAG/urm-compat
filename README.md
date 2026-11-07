# URM Compat

An add-on for **[Universal Ren'Py Mod (URM)](https://0x52.dev) by 0x52**.

> **All credit for URM goes to 0x52.** URM is their work: the overlay, search,
> variable editor, choice and path detection, replays, snapshots and everything
> else this builds on. This repository contains **none of URM's code** - only
> an add-on that runs on top of it, so you need URM itself from
> [0x52.dev](https://0x52.dev). If URM is useful to you, please support 0x52
> there.
>
> This project is not affiliated with or endorsed by 0x52.

## Install

You need two files in the game's `game` folder: URM, and this add-on.

1. **Install URM** the usual way: download it from [0x52.dev](https://0x52.dev)
   and put `0x52_URM.rpa` into the game's `game` folder.
2. **Download [urm_compat.rpy](https://github.com/MotazMSAG/urm-compat/releases/latest/download/urm_compat.rpy)**
   and put it in the same `game` folder.
3. Start the game.

```
Some Game/
├── Some Game.exe
└── game/
    ├── 0x52_URM.rpa      <- URM, from 0x52.dev
    └── urm_compat.rpy    <- this add-on
```

That's it - no tools to run, and it works on any game URM works on
(Ren'Py 7.2 and newer). The first launch takes a moment longer while the game
compiles the add-on.

**Update:** download the new `urm_compat.rpy` and replace the old one. URM keeps
updating itself as usual.

**Uninstall:** delete `urm_compat.rpy` and `urm_compat.rpyc` from the `game`
folder. URM itself is untouched.

**If something looks off:** the add-on writes lines starting with
`URM Compat:` to the game's `log.txt`. If a URM update changed one of the
screens this add-on adjusts, that one adjustment is skipped and logged - URM
and everything else keep working.

## What it adds

**Knowing what a variable does**
- **Script index.** When the game window opens, the game's script is read in
  the background (a small line in the corner shows progress). Every check and
  every assignment of every variable is recorded.
- **Variable panel.** Clicking a variable in URM's editor now says what the
  game does with it, in story terms: what each value gets you (which scenes,
  how many lines, the first line said), whether that scene is still ahead of
  you, which choices set it, and warnings such as *"the game turns this OFF by
  itself in ch1ep1 unless ainepoint is exactly 14"*. Number variables show the
  values the game actually checks as a ladder, with your value marked and a
  "next" helper. Every place has Lines / Replay / Code buttons.
- **Bare variables are clickable** in the code view and on the path cards (a
  condition that is just `flag` used to be plain text).

**Search**
- Dotted names (`mc.str`, `mc.inventory.gold`), depth control with a
  pay-on-click *Deeper* button, number operators (`>=5`, `3..8`), better
  ranking, a *Browse all* button, and a copy-name button in the editor.

**Paths and choices**
- Notification cards that show the condition in the path and choice rows,
  the gates that come after the detected one, and a look-ahead setting for
  cinematic games where path detection runs out of budget.
- Labels list: a filter and seen / not-seen markers.

**Settings and controls**
- **Gallery switch** (Settings > Miscellaneous, and a small button in the main
  menu): *Unlock all* or *My unlocks*. Nothing is written - it only changes
  what the game reads while a menu or the game's gallery is open, so your own
  unlocks are kept exactly and the story still sees your real progress.
- **Rollback length**: 500 steps by default instead of Ren'Py's 100 (or 2000,
  or the game's default).
- **Middle-click Skip** to roll back to the last choice you made (right-click
  Skip already skips forward to the next one).
- A quickmenu button for Ren'Py's *skip unseen text* preference.

## For developers

The add-on is written in two files, and `urm_compat.rpy` is generated from
them:

- `game_fixes.rpy` - everything that runs in the game
- `ui_tweaks.py` - the edits to URM's screens, each a passage to find and its
  replacement

```
python make_rpy.py
```

writes `dist/urm_compat.rpy`. Nothing else is needed for that - no game and
no Ren'Py.

URM loads its screens as text at startup; the generated file wraps that one
loader and applies the edits in memory, so URM's own archive is never
modified. (`build_rpa.py` can still bake everything into a single replacement
`0x52_URM.rpa` instead, if you prefer one file - see its docstring.)

**Tests** borrow any Ren'Py 8 game for its engine (nothing in it is touched)
and need your copy of URM's archive:

```
"<game>/lib/py3-windows-x86_64/python.exe" -I tests/run_tests.py "<game>" 0x52_URM.rpa
```

They parse URM's patched screens with the real Ren'Py parser, check that every
edit still matches URM's source, check that `urm_compat.rpy` produces exactly
the same screens as the archive build, and unit-test the index, the variable
panel, the gallery switch and rollback against real Ren'Py AST nodes. See
[tests/README.md](tests/README.md).

## License

The code in this repository is MIT licensed - see [LICENSE](LICENSE). That
covers this repository only. URM itself belongs to 0x52 and is not included
or covered.
