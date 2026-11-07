"""
Reading and writing stock Ren'Py archives, and compiling one .rpy into a .rpyc
that loads on Ren'Py 7 and 8 alike. Used by build_rpa.py.

Everything here is the standard format any stock Ren'Py writes and reads.
"""

from __future__ import print_function

import os
import pickle
import struct
import sys
import zlib

STOCK_HEADER = b"RENPY RPC2"

# A .rpyc reserves three slot entries of twelve bytes each.
SLOT_ENTRIES = 3
SLOT_TABLE_SIZE = SLOT_ENTRIES * 12


def load_engine(base):
    """
    Imports a game's bundled Ren'Py, so its parser and pickler can be used.
    """

    base = os.path.abspath(base)
    os.chdir(base)
    sys.path.insert(0, base)

    import renpy

    return renpy


def read_archive(path):
    """
    Reads a stock RPA-2.0 or RPA-3.0 archive. Returns {name: bytes}.
    """

    with open(path, "rb") as f:
        parts = f.readline().split()

        if parts[0] == b"RPA-3.0":
            offset = int(parts[1], 16)
            key = int(parts[2], 16)
        elif parts[0] == b"RPA-2.0":
            offset = int(parts[1], 16)
            key = 0
        else:
            raise SystemExit("%s is not an RPA-2.0 or RPA-3.0 archive." % path)

        f.seek(offset)
        index = pickle.loads(zlib.decompress(f.read()))

        contents = {}

        for name, entries in index.items():
            if isinstance(name, bytes):
                name = name.decode("utf-8")

            chunks = []

            for entry in entries:
                start = entry[0] ^ key
                length = entry[1] ^ key
                prefix = entry[2] if len(entry) > 2 else b""

                if isinstance(prefix, str):
                    prefix = prefix.encode("latin-1")

                # The stored length covers the bytes in the file only; any
                # prefix is held in the index and sits in front of them.
                f.seek(start)
                chunks.append(prefix + f.read(length))

            contents[name] = b"".join(chunks)

    return contents


def write_rpyc(slots, digest):
    """
    A stock .rpyc: the header, a three entry slot table, each slot's payload,
    then the md5 of the source.
    """

    out = bytearray()
    out += STOCK_HEADER
    out += b"\x00" * SLOT_TABLE_SIZE

    table = []

    for slot, payload in slots:
        table.append((slot, len(out), len(payload)))
        out += payload

    pos = len(STOCK_HEADER)

    for entry in table:
        out[pos:pos + 12] = struct.pack("III", *entry)
        pos += 12

    out += digest

    return bytes(out)


def compile_rpy(renpy, path, script_name):
    """
    Compiles a .rpy into the slot 1 payload of a .rpyc, the same way
    Script.load_file does when it compiles a source file it has just read.

    Slot 1 holds the tree before static transforms; the engine applies those
    itself when it loads a file that has no slot 2.
    """

    import hashlib

    # The parser needs the whole engine, not just the package.
    renpy.import_all()

    from renpy.compat.pickle import dumps

    # The parser wants enough of a live engine to resolve line numbers.
    class FakeScript(object):
        record_pycode = False
        all_pycode = [ ]
        serial = 0

        def __getattr__(self, name):
            return None

    class FakeContext(object):
        init_phase = True

    script = FakeScript()
    renpy.game.script = script

    if not renpy.game.contexts:
        renpy.game.contexts = [ FakeContext() ]

    statements = renpy.parser.parse(path)

    if statements is None:
        raise SystemExit("%s failed to parse." % path)

    # Every node needs a unique name, the way load_file gives them one after
    # parsing. Without this the loader rejects the file as defining a name
    # twice. The name is what shows up in tracebacks, so use the path the file
    # will have inside the archive.
    renpy.script.Script.assign_names(script, statements, script_name)

    data = { }
    data['version'] = renpy.script_version
    data['key'] = 'unlocked'
    data['deferred_parse_errors'] = renpy.parser.deferred_parse_errors

    # ------------------------------------------------------------------
    # Make the result loadable by Ren'Py 7 as well as Ren'Py 8
    # ------------------------------------------------------------------
    #
    # PyCode is the only AST class with its own pickle hooks, and the two
    # engine lines disagree about the shape:
    #
    #   Ren'Py 8  __getstate__ -> (1, source, location, mode, py)   5 items
    #   Ren'Py 7  __setstate__ -> (_, source, location, mode)       unpacks 4
    #
    # Ren'Py 8 reads an old 4-tuple on purpose - `if len(state) == 4` - but
    # Ren'Py 7 cannot read a 5-tuple: it raises ValueError, Script.load_file
    # swallows it, and the game dies with "Could not load from archive",
    # naming the file but not the reason.
    #
    # So the tree is always written in the 4-tuple form. On Ren'Py 8 that
    # makes it set py = 2, which only selects a small source-compatibility
    # pass - the file must therefore avoid python-3-only syntax, which it
    # does, since it has to run on a Python 2 engine anyway.
    #
    # Everything else in the tree pickles its plain __dict__, so this one
    # class is the whole difference between the two engine lines.

    PyCode = renpy.ast.PyCode
    original = PyCode.__getstate__

    def portable_getstate(self):
        state = original(self)
        return state[:4] if len(state) > 4 else state

    PyCode.__getstate__ = portable_getstate

    try:
        payload = zlib.compress(dumps((data, statements)), 3)
    finally:
        PyCode.__getstate__ = original

    with open(path, "rb") as f:
        digest = hashlib.md5(f.read()).digest()

    return payload, digest


def write_archive(path, contents):
    """
    Writes a stock RPA-3.0 archive. The container format is not what the build
    changed, so this stays standard.
    """

    key = 0x42424242
    index = {}

    with open(path, "wb") as f:
        f.write(b" " * 34)

        for name in sorted(contents):
            data = contents[name]
            start = f.tell()
            f.write(data)
            index[name] = [(start ^ key, len(data) ^ key, b"")]

        offset = f.tell()
        f.write(zlib.compress(pickle.dumps(index, 2), 3))

        f.seek(0)
        f.write(b"RPA-3.0 %016x %08x\n" % (offset, key))
