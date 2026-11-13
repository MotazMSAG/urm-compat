"""
Checks "skip past small changes" against the engine's own Context.seen_current.

    <a game's bundled python> -I -B check_skip.py <that game folder>

The script below is parsed by the game's Ren'Py and named the way the engine
names statements; a line counts as seen when its name is in _seen_ever, as in
a running game. Then the patched seen_current is asked about each line.
"""

from __future__ import print_function

import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLKIT = os.path.dirname(HERE)

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(2)

base = os.path.abspath(sys.argv[1])
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
    names = {}

    def __getattr__(self, name):
        return None

    def lookup(self, name):
        return self.names[name]


renpy.game.script = FakeScript()
renpy.game.log = type("L", (), {"mutated": {}})()
if not renpy.game.contexts:
    renpy.game.contexts = [type("C", (), {"init_phase": True})()]

SOURCE = u'''
label start:
    "s1"
    "u1"
    "u2"
    "u3"
    "s2"
    "u4"
    "u5"
    "u6"
    "u7"
    "s3"
    "u9"
    if flag:
        "u8"
    else:
        "s4"
    jump later

label later:
    "s7"
    "u10"
    "s5"
    menu:
        "Pick":
            "s6"
    return

label choice:
    "s8"
    menu:
        "Taken before":
            "s9"
        "Never taken":
            "u11"
    "s10"
    return
'''


def parse(source):
    folder = tempfile.mkdtemp(prefix="urm_check_skip_")
    path = os.path.join(folder, "urmskip.rpy")
    io.open(path, "w", encoding="utf-8").write(source)
    try:
        stmts = renpy.parser.parse(path)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    assign = renpy.script.Script.assign_names
    assign = getattr(assign, "__func__", assign)  # Python 2: an unbound method
    assign(renpy.game.script, stmts, "urmskip")
    renpy.ast.chain_block(stmts, None)
    flat = []
    for node in stmts:
        node.get_children(flat.append)
    return stmts, flat


labels, nodes = parse(SOURCE)
says = {}
for node in nodes:
    FakeScript.names[node.name] = node
    if isinstance(node, renpy.ast.Label):
        FakeScript.names[node.name] = node
    if isinstance(node, renpy.ast.Say):
        says[node.what] = node

import types  # noqa
store = types.ModuleType("store")
store.flag = False
renpy.store = store
renpy.game.persistent = type("P", (), {})()
renpy.game.persistent._seen_ever = dict((says[w].name, True) for w in
                                       ("s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10"))


def blocks(text, needle):
    out = []
    for chunk in text.split("init 999 python:")[1:]:
        lines = []
        for line in chunk.split("\n"):
            if line and not line.startswith(" ") and not line.startswith("#"):
                break
            lines.append(line[4:] if line.startswith("    ") else line)
        body = "\n".join(lines)
        if needle in body:
            out.append(body)
    return out


class Settings(object):
    value = 3

    def get(self, name):
        return self.value


class X52URM(object):
    class Var(object):
        pass
    Settings = Settings()
    SettingsClass = type("SC", (), {"defaultValues": {}})


class StoreRenpy(object):
    ast = renpy.ast
    game = renpy.game
    store = store

    class python(object):
        @staticmethod
        def py_eval(code):
            return eval(code, vars(store))


config = type("Config", (), {"skipping": "slow"})()
ns = {"renpy": StoreRenpy, "x52URM": X52URM(), "config": config,
      "python_dict": dict, "python_list": list, "python_set": set,
      "python_object": object, "__name__": "urm_skip_check"}

Context = renpy.execution.Context
original = Context.seen_current
fixes = io.open(os.path.join(TOOLKIT, "game_fixes.rpy"), encoding="utf-8").read()
for wanted in ("class _URMIndex", "def _urms_small_change"):
    found = blocks(fixes, wanted)
    if len(found) != 1:
        print("FAIL  expected one block holding %r, found %d" % (wanted, len(found)))
        sys.exit(1)
    exec(compile(found[0], "game_fixes.rpy", "exec"), ns)
index = ns["_URMIndex"]()
index.build(nodes)
ns["_urmi_index"] = lambda: index

failures = []


def check(name, got, want):
    if got == want:
        print("pass  %s" % name)
    else:
        failures.append(name)
        print("FAIL  %s" % name)
        print("        expected %r" % (want,))
        print("        got      %r" % (got,))


class Ctx(object):
    """Stands in for a Context: seen_current only reads .current."""

    def __init__(self, line):
        self.current = says[line].name


def seen(line):
    X52URM.Var._urmsCache = None
    method = Context.seen_current
    method = getattr(method, "__func__", method)  # Python 2: an unbound method
    return method(Ctx(line), True)


try:
    print("-- while skipping, up to 3 new lines in a row")
    check("a seen line is still seen", seen("s1"), True)
    check("seen new new new seen: the first new line is skipped", seen("u1"), True)
    check("and the last of them", seen("u3"), True)
    check("seen new new new new seen: stops", seen("u4"), False)
    check("every line of a 4-line run stops, not just the first", seen("u6"), False)
    check("an if-branch is followed the way it will run", seen("u9"), True)
    store.flag = True
    check("the other branch is new, then a jump - still followed", seen("u9"), True)
    check("across the jump, a seen line after one new one", seen("u10"), True)
    check("a reply to a choice never taken still stops", seen("u11"), False)
    store.flag = False

    print()
    print("-- when it must not apply")
    config.skipping = None
    check("reading, not skipping: an unseen line stays unseen", seen("u1"), False)
    config.skipping = "fast"
    check("fast skip to the next choice is covered too", seen("u1"), True)
    X52URM.Settings.value = 0
    check("switched off", seen("u1"), False)
    X52URM.Settings.value = 1
    check("set to 1 line: two or three new in a row stop", (seen("u2"), seen("u3")), (False, False))
    check("set to 1 line: one new line between seen ones is skipped", seen("u10"), True)
    X52URM.Settings.value = 3
    check("the patch is installed once", getattr(Context.seen_current, "_urms", False), True)
finally:
    Context.seen_current = original

print()
print("all passed" if not failures else "%d FAILED" % len(failures))
sys.exit(1 if failures else 0)
