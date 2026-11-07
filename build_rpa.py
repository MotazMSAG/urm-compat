"""
Builds a drop-in 0x52_URM.rpa - URM with the interface tweaks and the game
compatibility fixes baked in, in stock Ren'Py format.

    python build_rpa.py "<a normal Ren'Py game>" [output path]

The game folder is borrowed for its Ren'Py, which compiles game_fixes.rpy.
It must be an ordinary game, not one that encrypts its script cache, or the
compiled file comes out in that game's private format and works nowhere else.
Nothing in it is read or written.

URM itself is not part of this repository. Put your copy of URM's own
0x52_URM.rpa (from https://0x52.dev) next to this file; the build reads it,
applies the tweaks and writes the result to dist/.

The result is used exactly like URM's own archive: put it in the game's game/
folder. That covers every game whose engine reads add-on scripts as they come,
which is almost all of them.
"""

from __future__ import print_function

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, HERE)

import rpatools    # noqa
import ui_tweaks   # noqa

FIX_NAME = "0x52-URM/zzz_urm_compat.rpyc"


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2

    game = os.path.abspath(argv[1])
    source = os.path.join(HERE, "0x52_URM.rpa")
    fixes = os.path.join(HERE, "game_fixes.rpy")
    output = os.path.abspath(argv[2]) if len(argv) > 2 else os.path.join(
        HERE, "dist", "0x52_URM.rpa")
    output = os.path.abspath(output)

    for path in (source, fixes):
        if not os.path.exists(path):
            print("Missing %s" % path)
            return 1

    contents = rpatools.read_archive(source)
    print("Read %s  (%d entries)" % (source, len(contents)))

    applied, skipped = ui_tweaks.apply(contents)
    for name, note in applied:
        print("  tweak: %s%s" % (name, "  (%s)" % note if note else ""))
    for name, why in skipped:
        print("  ! skipped %s - %s" % (name, why))

    if skipped:
        print()
        print("Refusing to build with a tweak missing - run tests/run_tests.py")
        print("to see which pattern URM moved.")
        return 1

    # load_engine chdirs, so everything above has to be resolved by now.
    renpy = rpatools.load_engine(game)

    header = getattr(renpy, "_RPYC_HEADER", rpatools.STOCK_HEADER)
    if header != rpatools.STOCK_HEADER or getattr(renpy, "compress_bytecode_stream", None):
        print()
        print("%s encrypts its script cache. Build from an ordinary game." % game)
        return 1

    print("Compiling game_fixes.rpy with Ren'Py %s" % renpy.version_only)

    payload, digest = rpatools.compile_rpy(renpy, fixes, FIX_NAME[:-1])
    contents[FIX_NAME] = rpatools.write_rpyc([(1, payload)], digest)

    if not os.path.isdir(os.path.dirname(output)):
        os.makedirs(os.path.dirname(output))

    rpatools.write_archive(output, contents)

    print()
    print("Wrote %s  (%.0f KB)" % (output, os.path.getsize(output) / 1024.0))
    print("Drop it in a game's game/ folder, like URM's own archive.")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
