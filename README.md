# URM Compat

An add-on layer for **[Universal Ren'Py Mod (URM)](https://0x52.dev) by 0x52**.

> **All credit for URM goes to 0x52.** URM is their work: the overlay, search,
> variable editor, choice and path detection, replays, snapshots and everything
> else this builds on. This repository contains **none of URM's code** - only
> patches applied on top of it. To use it you need your own copy of URM 2.6.2
> from [0x52.dev](https://0x52.dev). If URM is useful to you, please support 0x52
> there.
>
> This project is not affiliated with or endorsed by 0x52.

## What it adds

**Knowing what a variable does**
- **Script index.** When the game window opens, the game's whole script is read
  in the background (a small line in the corner shows progress). Every check
  and every assignment of every variable is recorded.
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

Works on Ren'Py 7.2.1 through 8.x.

## Building

1. Get URM 2.6.2 from [0x52.dev](https://0x52.dev) and put its
   `0x52_URM.rpa` next to `build_rpa.py`.
2. Build with the Python bundled in any ordinary Ren'Py 8 game (the game is
   only borrowed for its engine; nothing in it is touched):

   ```
   "<game>/lib/py3-windows-x86_64/python.exe" -I build_rpa.py "<game>"
   ```

3. Copy `dist/0x52_URM.rpa` into the `game/` folder of the game you want to
   use it in, in place of URM's own archive.

The build refuses to run if any patch no longer matches URM's source - for
example after a URM update - instead of producing a half-patched archive.

## Tests

```
"<game>/lib/py3-windows-x86_64/python.exe" -I tests/run_tests.py "<game>" 0x52_URM.rpa
```

The suite parses URM's patched screens with the real Ren'Py parser, checks
that every patch still matches, and unit-tests the index, the variable panel,
the gallery switch and rollback against real Ren'Py AST nodes. See
[tests/README.md](tests/README.md).

## License

The code in this repository is MIT licensed - see [LICENSE](LICENSE). That
covers this repository only. URM itself belongs to 0x52 and is not included
or covered.
