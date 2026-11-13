# URM+

Extra features for **[Universal Ren'Py Mod](https://0x52.dev)** by 0x52.
All credit for URM goes to 0x52; this repo holds none of its code, so you need
URM itself. Not affiliated with 0x52.

## Install

Put two files in the game's `game` folder and start the game:

- `0x52_URM.rpa` - URM, from [0x52.dev](https://0x52.dev)
- **[urm_plus.rpy](https://github.com/MotazMSAG/urm-plus/releases/latest/download/urm_plus.rpy)** - URM+

To update, replace `urm_plus.rpy`. To remove, delete `urm_plus.rpy` and
`urm_plus.rpyc`. Coming from URM Compat (the old name)? Delete
`urm_compat.rpy` and `urm_compat.rpyc`.

Ren'Py 7.2 and newer.

## Features

**Know what a variable does** - the game's script is read in the background at
startup. Click any variable to see what each value gets you (scenes, lines,
the first line said), whether it's still ahead, which choices set it, and
warnings like *"the game turns this OFF by itself unless ainepoint is exactly
14"*. Numbers show as a ladder of the values the game checks.

**Flags** - games that store choices as words (`option("x")` / `true("x")`,
`new_path` / `on_path`) get a **Flags** list beside Search with ON/OFF
switches, and flags in conditions are clickable.

**Force any path** - Select works even on paths URM marks "Not forceable"
(behind a jump or call), and on the gates after the detected one.

**Skipping**
- Skip past small changes: typo fixes and reworded lines no longer stop a
  skip (up to 1-3 new lines between lines you've read).
- With "Stop skipping on path detection" on, your next click on empty space
  resumes the skip.
- Middle-click Skip to roll back to your last choice; rollback goes 500 steps
  instead of 100.

**Gallery switch** - *Unlock all* or *My unlocks*, in settings and in the
corner of the main menu and gallery. Nothing is written, so your own unlocks
stay exactly as they are.

**Search** - dotted names (`mc.str`), number operators (`>=5`, `3..8`),
deeper search, Browse all, and one-click *Ignore in paths / code* on any
variable.

## For developers

`game_fixes.rpy` is everything that runs in the game; `ui_tweaks.py` holds
the edits to URM's screens. `python make_rpy.py` builds `dist/urm_plus.rpy`.

Tests borrow any Ren'Py 8 game's engine and need your copy of URM:

```
"<game>/lib/py3-windows-x86_64/python.exe" -I tests/run_tests.py "<game>" 0x52_URM.rpa
```

## License

MIT for this repository's code. URM belongs to 0x52 and is not included or
covered.
