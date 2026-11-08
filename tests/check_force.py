"""
Checks forcing a path that URM itself calls "not forceable".

    <a game's bundled python> -I -B check_force.py <that game folder>

URM forces a path by rewriting the statements between the cursor and the
if-statement, so it gives up when a jump or call lies in between. The add-on
forces at the if-statement instead: Select records the arm, and the engine's
own If.execute - patched once - takes it when the game gets there.

The script below is parsed by the game's own Ren'Py and run through the real
If.execute. It also checks the gates after the Path options table: they used
to repeat the table's own rows, and each now carries how to force it.
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
    labels = {}

    def __getattr__(self, name):
        return None

    def lookup(self, name):
        return self.labels[name]


renpy.game.script = FakeScript()
renpy.game.log = type("L", (), {"mutated": {}})()
if not renpy.game.contexts:
    renpy.game.contexts = [type("C", (), {"init_phase": True})()]

SOURCE = u'''
label start:
    "Intro"
    jump middle

label middle:
    if a == 1:
        jump one
    elif a == 2:
        jump two
    else:
        "other"
    "after"

label later:
    if a == 1:
        jump one
    elif a == 2:
        jump two
    if b == 1:
        jump three
    jump four
'''


def parse(source):
    folder = tempfile.mkdtemp(prefix="urm_check_force_")
    path = os.path.join(folder, "urmforce.rpy")
    io.open(path, "w", encoding="utf-8").write(source)
    try:
        stmts = renpy.parser.parse(path)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    renpy.ast.chain_block(stmts, None)
    flat = []
    for node in stmts:
        node.get_children(flat.append)
    return stmts, flat


labels, nodes = parse(SOURCE)
for label in labels:
    FakeScript.labels[label.name] = label
ifs = [n for n in nodes if isinstance(n, renpy.ast.If)]
middle_if = ifs[0]
later_first, later_second = ifs[1], ifs[2]


def column0(block):
    out = []
    for line in block.split("\n"):
        if line and not line.startswith(" ") and not line.startswith("#"):
            break
        out.append(line[4:] if line.startswith("    ") else line)
    return "\n".join(out)


def functions(body, names):
    """The listed top-level defs of a block, without the rest of the block."""
    lines = body.split("\n")
    out = []
    for name in names:
        start = None
        for i, line in enumerate(lines):
            if line.startswith("def %s(" % name):
                start = i
                break
        if start is None:
            raise SystemExit("FAIL  no def %s" % name)
        end = start + 1
        while end < len(lines) and (not lines[end].strip() or lines[end].startswith((" ", "#"))):
            end += 1
        out.append("\n".join(lines[start:end]))
    return "\n\n".join(out)


source = io.open(os.path.join(TOOLKIT, "game_fixes.rpy"), encoding="utf-8").read()
chunks = [column0(c) for c in source.split("init 999 python:")[1:]]


class Ctx(object):
    next_node = None
    current = None


ctx = Ctx()
notes = []


class Var(object):
    pass


class PathBase(object):
    """URM's Path: Action is None when it cannot rewrite the chain."""

    def __init__(self, index, forceable):
        self._m1_PathDetection__index = index
        self.forceable = forceable

    @property
    def Action(self):
        return "urm's own" if self.forceable else None


class PathDetection(object):
    lookAheadLimit = 20
    target = None

    @property
    def nextIfStatement(self):
        return (self.target, False) if self.target is not None else None

    @staticmethod
    def nextNode(node):
        if isinstance(node, renpy.ast.Jump):
            return FakeScript.labels.get(node.target)
        return getattr(node, "next", None)

    @staticmethod
    def nodeIsBlocking(node):
        return isinstance(node, (renpy.ast.Say, renpy.ast.Menu))


class Colors(object):
    def __getattr__(self, name):
        return None


class Theme(object):
    colors = Colors()
    isDark = True


class CodeView(object):
    @staticmethod
    def colorize(code, **kw):
        return code


class X52URM(object):
    Var = Var
    Path = PathBase
    PathDetection = PathDetection()
    Theme = Theme()
    CodeView = CodeView()

    @staticmethod
    def scalePxInt(n):
        return n


class StoreRenpy(object):
    ast = renpy.ast
    python = renpy.python

    class game(object):
        script = renpy.game.script

        @staticmethod
        def context():
            return ctx

    @staticmethod
    def notify(text):
        notes.append(text)


config = type("Config", (), {"after_load_callbacks": []})()
ns = {"renpy": StoreRenpy, "x52URM": X52URM(), "config": config,
      "python_dict": dict, "python_list": list, "python_set": set,
      "python_object": object, "__name__": "urm_force_check"}

force = [c for c in chunks if "class _URMFState" in c]
cards = [c for c in chunks if "def _urm_flatten" in c]
later = [c for c in chunks if "def urm_later_gate_rows" in c]
if len(force) != 1 or len(cards) != 1 or len(later) != 1:
    print("FAIL  blocks not found (%d, %d, %d)" % (len(force), len(cards), len(later)))
    sys.exit(1)

original_execute = renpy.ast.If.execute
exec(compile(cards[0], "game_fixes.rpy", "exec"), ns)
exec(compile(functions(later[0], ["urm_later_gates", "urm_later_gate_rows"]), "game_fixes.rpy", "exec"), ns)
exec(compile(force[0], "game_fixes.rpy", "exec"), ns)

failures = []


def check(name, got, want):
    if got == want:
        print("pass  %s" % name)
    else:
        failures.append(name)
        print("FAIL  %s" % name)
        print("        expected %r" % (want,))
        print("        got      %r" % (got,))


def say_of(node):
    return getattr(node, "what", None) or getattr(node, "target", None)


try:
    print("-- a row URM calls not forceable")
    X52URM.PathDetection.target = middle_if
    action = PathBase(2, False).Action
    check("now has a Select action", action is not None, True)
    check("URM's own action is kept where it has one", PathBase(0, True).Action, "urm's own")
    action()
    check("Select says what will happen", "path 3 will be taken" in (notes[-1] if notes else ""), True)
    middle_if.execute()
    check("the if-statement takes the chosen arm, not its condition", say_of(ctx.next_node), "other")
    check("and only once", ns["_urmf_state"]().pending, [])

    print()
    print("-- the gates after the table")
    X52URM.PathDetection.target = later_first
    rows = ns["urm_later_gate_rows"]()
    check("only gates after the first if-statement are listed",
          [(r[2], r[3]) for r in rows], [("3", "b == 1"), ("", "{i}nothing above matches{/i}")])
    check("the old four-column form still works for older screens",
          len(ns["urm_later_gates"]()[0]), 4)
    ns["urmf_force_later"](0)
    later_first.execute()
    check("picking one makes the if-statement before it fall through",
          ctx.next_node is later_first.next, True)
    later_second.execute()
    check("and takes the picked arm of the next one", say_of(ctx.next_node), "three")
    ns["urm_later_gate_rows"]()
    ns["urmf_force_later"](1)
    later_first.execute()
    later_second.execute()
    check("\"nothing above matches\" falls through both", say_of(ctx.next_node), "four")

    print()
    print("-- forgetting")
    ns["urm_later_gate_rows"]()
    ns["urmf_force_later"](0)
    for callback in config.after_load_callbacks:
        callback()
    check("loading a save forgets a force not yet reached", ns["_urmf_state"]().pending, [])
    check("the patch is installed once", renpy.ast.If.execute is not original_execute
          and getattr(renpy.ast.If.execute, "_urmf", False), True)
finally:
    renpy.ast.If.execute = original_execute

print()
print("all passed" if not failures else "%d FAILED" % len(failures))
sys.exit(1 if failures else 0)
