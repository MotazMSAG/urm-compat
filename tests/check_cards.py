"""
Unit-checks the effect flattener against real Ren'Py AST nodes.

    <a game's bundled python> -I check_cards.py <that game folder>

The rows under a gate are built by walking the arm's own AST, not by parsing
CodeView.nodesToCode's text. This exercises that walk, and in particular the
three reductions - the only places where the display can say something the
code does not do:

  L1  an If with a real else arm whose every arm does the same thing is lifted
      out, unguarded. This is the user's own gate 2 collapsing from six rows
      to one.
  L2  a guarded row is dropped when the same statement also happens unguarded.
  L3  an exact (guards, text) duplicate is dropped.

Nothing else may merge. A test here that starts failing because a fourth
reduction was added is doing its job.

The nodes are built with the engine's real parser from source text, so they
are the same objects the game would hand us.
"""

from __future__ import print_function

import io
import os
import sys
import textwrap

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

    def __getattr__(self, name):
        return None


renpy.game.script = FakeScript()
renpy.game.log = type("L", (), {"mutated": {}})()
if not renpy.game.contexts:
    renpy.game.contexts = [type("C", (), {"init_phase": True})()]


def parse(source):
    """The statements of a label, as real AST nodes."""

    path = os.path.join(base, "_urm_check_cards.rpy")
    io.open(path, "w", encoding="utf-8").write(
        u"label _urm_check:\n" + textwrap.indent(textwrap.dedent(source), "    "))
    try:
        block = renpy.parser.parse(path)
    finally:
        os.remove(path)

    renpy.ast.chain_block(block, None)
    return block[0].block


# ---------------------------------------------------------------- the helper

class Colors(object):
    def __getattr__(self, name):
        return None


class Theme(object):
    colors = Colors()
    isDark = True


class CodeView(object):
    @staticmethod
    def colorize(code, **kw):
        return code.replace("{", "{{")


class X52URM(object):
    Theme = Theme()
    CodeView = CodeView()

    @staticmethod
    def scalePxInt(n):
        return n


source = io.open(os.path.join(TOOLKIT, "game_fixes.rpy"),
                 encoding="utf-8").read()


def body(block):
    """
    One init block's code at column 0.

    Four spaces off whatever has them, rather than textwrap.dedent: a block is
    followed by the next block's comment header at column 0, so the common
    prefix is "" and dedent strips nothing. A comment left at column 0 is
    legal anywhere.
    """

    newline = chr(10)
    return newline.join(line[4:] if line.startswith("    ") else line
                        for line in block.split(newline))


# By content, not position. game_fixes.rpy has several init 999 blocks and
# gained one at the end; taking the last would silently test the wrong code.
blocks = [b for b in source.split("init 999 python:")
          if "def _urm_flatten" in b]

if len(blocks) != 1:
    print("FAIL  found %d init blocks defining _urm_flatten, expected 1"
          % len(blocks))
    sys.exit(1)

ns = {"x52URM": X52URM(), "renpy": renpy, "__name__": "urm_helpers"}
exec(compile(body(blocks[0]), "game_fixes.rpy", "exec"), ns)

flatten = ns["_urm_flatten"]
reduce_ = ns["_urm_reduce"]
effects = ns["_urm_effects"]


def rows(src):
    records, _removed = reduce_(flatten(parse(src)))
    return [(tuple(g), t) if n == 1 else (tuple(g), t, n)
            for g, t, n in records]


def removed(src):
    return reduce_(flatten(parse(src)))[1]


def bodies(src):
    return [body for _icon, body in effects(parse(src))]


CASES = []


def case(name, source, expected):
    CASES.append((name, source, expected))


case("plain assignments",
     """
     $ love = 1
     $ dom += 2
     """,
     [((), "love = 1"), ((), "dom += 2")])

case("dialogue alone changes nothing tracked",
     """
     "She looks at you."
     "And says nothing."
     """,
     [])

case("a jump is an effect",
     """
     $ seen = True
     jump somewhere
     """,
     [((), "seen = True"), ((), "jump somewhere")])

# L1 - the user's own gate 2.
case("L1 identical arms with an else are lifted unguarded",
     """
     if richard_power:
         $ hide_videos = 1
     else:
         $ hide_videos = 1
     """,
     [((), "hide_videos = 1")])

case("L1 does NOT lift when the arms differ",
     """
     if richard_power:
         $ a = 1
     else:
         $ b = 2
     """,
     [(("only if richard_power",), "a = 1"),
      (("otherwise",), "b = 2")])

case("L1 does NOT lift without an else - the if may not run at all",
     """
     if richard_power:
         $ a = 1
     """,
     [(("only if richard_power",), "a = 1")])

case("L2 an unqualified row absorbs its guarded copy",
     """
     $ a = 1
     if richard_power:
         $ a = 1
     """,
     [((), "a = 1")])

case("L3 the same statement under the same guard, once",
     """
     if richard_power:
         $ a = 1
         $ a = 1
     """,
     [(("only if richard_power",), "a = 1")])

case("nesting keeps both guards, outermost first",
     """
     if a:
         if b:
             $ x = 1
     """,
     [(("only if a", "only if b"), "x = 1")])

case("a python block's own control flow is not drawn as a row",
     """
     python:
         total = 0
         if flag:
             total = 1
     """,
     [((), "total = 0")])

# ---------------------------------------------------------------------------
# The three falsehoods an adversarial pass found in the first version. Each
# of these cases failed before the reductions were made guard-aware.
# ---------------------------------------------------------------------------

# L1 compared statement TEXTS and then stamped the outer guards on every
# lifted row, so an arm holding mutually exclusive jumps - each under its own
# nested test - was drawn as three unconditional jumps. A player reading that
# picks a path believing it leads somewhere it does not.
case("L1 does NOT lift rows that carry a deeper guard",
     """
     if videos:
         if rosie_love > 95:
             jump A
         if seen:
             jump B
         else:
             jump C
     else:
         if rosie_love > 95:
             jump A
         if seen:
             jump B
         else:
             jump C
     """,
     [(("only if videos", "only if rosie_love > 95"), "jump A"),
      (("only if videos", "only if seen"), "jump B"),
      (("only if videos", "otherwise"), "jump C"),
      (("otherwise", "only if rosie_love > 95"), "jump A"),
      (("otherwise", "only if seen"), "jump B"),
      (("otherwise", "otherwise"), "jump C")])

# L2 dropped any guarded row whose text appeared unguarded. For a counter that
# is wrong twice over: the card showed one increment for code that runs two,
# and the guard - the only thing a player could act on - vanished entirely.
case("L2 does NOT drop a guarded counter that also runs unguarded",
     """
     $ prelove(1)
     if per > 30:
         $ prelove(1)
     """,
     [((), "prelove(1)"),
      (("only if per > 30",), "prelove(1)")])

case("L2 still drops a guarded assignment, which is idempotent",
     """
     $ flag = True
     if per > 30:
         $ flag = True
     """,
     [((), "flag = True")])

# L3 collapsed exact duplicates and counted nothing, so ten points of love
# were drawn as one.
case("L3 keeps a count for a repeated counter",
     """
     $ love += 1
     $ love += 1
     $ love += 1
     """,
     [((), "love += 1", 3)])

case("L3 still collapses a repeated assignment",
     """
     $ flag = True
     $ flag = True
     """,
     [((), "flag = True")])

failures = 0

for name, src, expected in CASES:
    try:
        got = rows(src)
    except Exception as e:
        got = "raised %s: %s" % (type(e).__name__, e)

    if got == expected:
        print("pass  %s" % name)
    else:
        failures += 1
        print("FAIL  %s" % name)
        print("        expected %r" % (expected,))
        print("        got      %r" % (got,))

# The screen's band/rule/effects rhythm only reads if it never varies, so an
# arm that changes nothing must still produce exactly one row.
print()
for name, src, least in (
        ("a dialogue-only arm still produces a row",
         '"She says nothing."', 1),
        ("a python block\'s dropped lines are reported, not hidden",
         "python:\n    total = 0\n    if flag:\n        total = 1", 2)):
    got = bodies(src)
    if len(got) >= least:
        print("pass  %s  -> %r" % (name, got))
    else:
        failures += 1
        print("FAIL  %s  -> %r" % (name, got))

# Anything removed has to be admitted. A card that drops a row without saying
# so reads as complete, which is the whole failure this design exists to stop.
print()
CUT = """
$ flag = True
if per > 30:
    $ flag = True
"""
if removed(CUT) == 1 and any("more" in b for b in bodies(CUT)):
    print("pass  a dropped row is reported as '+N more'  -> %r" % (bodies(CUT),))
else:
    failures += 1
    print("FAIL  a dropped row vanished without a '+N more'  -> %r  removed=%d"
          % (bodies(CUT), removed(CUT)))

# A guard row must never be stranded from the statement it qualifies: a
# half-drawn record promotes a conditional change to an unconditional one.
WIDE = "\n".join("if c%d:\n    $ v%d += 1" % (i, i) for i in range(8))
got = bodies(WIDE)
pairs = [i for i, b in enumerate(got) if "only if" in b]
orphan = [i for i in pairs if i == 0 or "only if" in got[i - 1]]
if not orphan and any("more" in b for b in got):
    print("pass  records are drawn whole, and the remainder is counted")
    print("        -> %r" % (got,))
else:
    failures += 1
    print("FAIL  a guard row was stranded or the overflow was not reported")
    print("        -> %r" % (got,))

print()
print("all passed" if not failures else "%d FAILED" % failures)
sys.exit(1 if failures else 0)
