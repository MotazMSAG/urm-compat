"""
Checks the compiled helper loads on Ren'Py 7 as well as Ren'Py 8.

    <a game's bundled python> -I check_rpyc7.py <that game folder> <a .rpa>

PyCode is the only AST class with its own pickle hooks, and the two engine
lines disagree about the shape of its state:

    Ren'Py 8   __getstate__ -> (1, source, location, mode, py)    5 items
    Ren'Py 7   __setstate__ -> (_, source, location, mode)        unpacks 4

Ren'Py 8 deliberately reads an old 4-tuple as well, so writing the 4-tuple
form makes one archive work on both. Ren'Py 7 cannot read a 5-tuple: it
raises ValueError, Script.load_file swallows it and returns (None, None), and
the game dies at startup with

    Exception: Could not load from archive 0x52-URM/zzz_urm_compat.rpyc.

which names the file and not the reason. That is what shipped, and it made the
mod unusable on every Ren'Py 7 game.

This test replaces PyCode.__setstate__ with Ren'Py 7.3.5's implementation,
verbatim, and loads the archive's helper through it.
"""

from __future__ import print_function

import os
import pickle
import struct
import sys
import zlib

if len(sys.argv) < 3:
    print(__doc__)
    sys.exit(2)

base = os.path.abspath(sys.argv[1])
archive = os.path.abspath(sys.argv[2])
entry = "0x52-URM/zzz_urm_compat.rpyc"

os.chdir(base)
sys.path.insert(0, base)

import renpy  # noqa

renpy.import_all()
renpy.config.basedir = base
renpy.config.gamedir = os.path.join(base, "game")


class FakeScript(object):
    record_pycode = False
    all_pycode = []
    serial = 0

    def __getattr__(self, name):
        return None


renpy.game.script = FakeScript()
renpy.game.log = type("L", (), {"mutated": {}})()
if not renpy.game.contexts:
    renpy.game.contexts = [type("C", (), {"init_phase": True})()]

from renpy.compat.pickle import loads  # noqa


def renpy7_setstate(self, state):
    """Ren'Py 7.3.5 renpy/ast.py:275-277, verbatim."""

    (_, self.source, self.location, self.mode) = state
    self.bytecode = None


def read_entry(path, name):
    with open(path, "rb") as f:
        parts = f.readline().split()
        offset = int(parts[1], 16)
        key = int(parts[2], 16) if parts[0] == b"RPA-3.0" else 0
        f.seek(offset)
        index = pickle.loads(zlib.decompress(f.read()))

        key_names = [k for k in index
                     if (k.decode("utf-8") if isinstance(k, bytes) else k) == name]
        if not key_names:
            return None

        first = index[key_names[0]][0]
        f.seek(first[0] ^ key)
        return f.read(first[1] ^ key)


def slot_one(blob):
    pos = 10
    while True:
        slot, start, length = struct.unpack("III", blob[pos:pos + 12])
        pos += 12
        if slot == 0:
            return None
        if slot == 1:
            return zlib.decompress(blob[start:start + length])


failures = []

blob = read_entry(archive, entry)

if blob is None:
    failures.append("%s is not in the archive" % entry)
    print("FAIL  %s is not in the archive" % entry)
else:
    payload = slot_one(blob)

    renpy.ast.PyCode.__setstate__ = renpy7_setstate

    try:
        data, statements = loads(payload)
        print("pass  loads through Ren'Py 7's PyCode.__setstate__  "
              "(%d statements)" % len(statements))
    except Exception as e:
        failures.append("the helper cannot load on Ren'Py 7: %s" % e)
        print("FAIL  %s: %s" % (type(e).__name__, e))
        print("      The build wrote a 5-tuple PyCode state. See rpatools.py,")
        print("      compile_rpy - it must write the 4-tuple form.")

print()
print("all passed" if not failures else "%d FAILED" % len(failures))
sys.exit(1 if failures else 0)
