"""
Unit-checks the script index against real Ren'Py AST nodes.

    <a game's bundled python> -I -B check_index.py <that game folder>

The script below is parsed by the engine's own parser, flattened with
get_children() exactly as script.py builds all_stmts, and handed to the index.
Every shape asserted here was seen in a real game of the 163-game corpus:

  ainepoint      MyBullyIsMyLover - a "score" the game only ever tests with ==
  aineroute      set by a menu option, which must be named
  hard_love      Twisted Thoughts - caps written as arithmetic
  nosex24        TheLostGuardian - a word kept in a list, tested with `in`
  rel_strong     Vulgar Reverie - two counters raced against each other
  setflag(...)   Newlyweds-to-be / The Office Wife - flags behind a helper
"""

from __future__ import print_function

import io
import os
import sys

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

SOURCE = u'''
default ainepoint = 0
default chapter = 0

label urmcheck:
    if ainepoint == 3:
        "a"
    elif ainepoint == 8:
        "b"
    if chapter == 1:
        "c1"
    elif chapter == 5:
        "c5"
    elif chapter == 2:
        "c2"
    menu:
        "Agree with her":
            $ aineroute = False
        "Tease her" if ainepoint >= 2:
            $ ainepoint += 1
    if love < hard_love - 30:
        "cap"
    if max_love - love > 9:
        "gap"
    if "nosex24" not in oneupdvars:
        "tag"
    if flags["intro"] and not mc.met:
        "dict"
    $ flags["intro"] = True
    $ setflag("vasectomy")
    $ oneupdvars.append("nosex24")
    python:
        def helper():
            local_x = 5
        total = 0
    if rel_strong > rel_passive:
        "race"
    if 10 <= day:
        "flip"
    return
'''


def parse(source):
    # A temp folder, not the game folder: this also runs against real games
    # downloaded from the internet (to test under their own Python 2), and
    # nothing should be written into those, even briefly.
    import shutil
    import tempfile
    folder = tempfile.mkdtemp(prefix="urm_check_index_")
    path = os.path.join(folder, "urmcheck.rpy")
    io.open(path, "w", encoding="utf-8").write(source)
    try:
        stmts = renpy.parser.parse(path)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    renpy.ast.chain_block(stmts, None)
    flat = []
    for node in stmts:
        node.get_children(flat.append)
    return flat


def blocks(text, needle):
    """
    The init blocks of game_fixes.rpy that contain `needle`, each at column 0.

    A block runs until the first line back at column 0 that is not a comment -
    a `screen` statement, say - so screen language never reaches exec().
    """

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


source = io.open(os.path.join(TOOLKIT, "game_fixes.rpy"), encoding="utf-8").read()


class Holder(object):
    pass


class FakeVar(object):
    _urmcIndex = None


class X52URM(object):
    Var = FakeVar


ns = {
    "renpy": renpy,
    "x52URM": X52URM(),
    "python_dict": dict, "python_list": list,
    "python_set": set, "python_object": object,
    # A Ren'Py 7 store's str is unicode (renpy.compat); literals parsed on
    # Python 2 are byte strings. Run the blocks under the store's names.
    "str": type(u""),  # STORE_STR
    "__name__": "urm_index_check",
}

for wanted in ("class _URMIndex", "def urm_checks"):
    found = blocks(source, wanted)
    if len(found) != 1:
        print("FAIL  expected one init block holding %r, found %d" % (wanted, len(found)))
        sys.exit(1)
    exec(compile(found[0], "game_fixes.rpy", "exec"), ns)

index = ns["_URMIndex"]()
index.build(parse(SOURCE))
FakeVar._urmcIndex = index

failures = []


def check(name, got, want):
    if got == want:
        print("pass  %s" % name)
    else:
        failures.append(name)
        print("FAIL  %s" % name)
        print("        expected %r" % (want,))
        print("        got      %r" % (got,))


def reads(name):
    return sorted((op, lit) for _s, op, lit in index.reads.get(name, ()))


def writes(name):
    return [(op, val) for _s, op, val, _t in index.writes.get(name, ())]


def option_of(name):
    for site, _op, _v, _t in index.writes.get(name, ()):
        return index.where(site)[1]


def label_of(name):
    for site, _op, _v, _t in index.writes.get(name, ()):
        return index.where(site)[0]


check("the build finishes", index.state, "ready")

print()
print("-- what the game checks")
check("every literal a counter is compared against",
      reads("ainepoint"), [("==", 3), ("==", 8), (">=", 2)])
check("a literal on the left reads the other way round",
      reads("day"), [(">=", 10)])
check("a dict key is named the way URM names it",
      reads('flags["intro"]'), [("truthy", None)])
check("an attribute tested with not is an off check",
      reads("mc.met"), [("falsy", None)])

print()
print("-- what the game sets, and which choice set it")
check("an assignment under a menu option", writes("aineroute"), [("=", False)])
check("names the option the player picked", option_of("aineroute"), "Agree with her")
check("and the label it sits in", label_of("aineroute"), "urmcheck")
check("an increment under a conditional option", writes("ainepoint"), [("+=", 1)])
check("names that option too", option_of("ainepoint"), "Tease her")
check("a dict key assignment", writes('flags["intro"]'), [("=", True)])
check("an append writes the token into the collection",
      writes("oneupdvars"), [(".append", "nosex24")])
check("a helper's own locals are not story writes",
      "local_x" in index.writes, False)
check("but a plain assignment beside the helper is",
      writes("total"), [("=", 0)])

print()
print("-- shapes that are not variable-against-number")
check("a cap written as arithmetic is still read",
      [(op, other) for _s, op, other in index.rivals.get("love", ())],
      [("<", "hard_love - 30")])
check("a name inside a calculation counts as a read",
      "max_love" in index.reads, True)
check("two counters raced against each other, from both sides",
      ([(o, x) for _s, o, x in index.rivals.get("rel_strong", ())],
       [(o, x) for _s, o, x in index.rivals.get("rel_passive", ())]),
      ([(">", "rel_passive")], [("<", "rel_strong")]))
check("a word kept in a list is findable by the word",
      [(coll, op) for _s, coll, op in index.tokens.get("nosex24", ())],
      [("oneupdvars", "not in")])
check("a flag set through a helper is recorded with its argument",
      [args for _s, args in index.calls.get("setflag", ())], [("vasectomy",)])
check("declarations are recorded", "ainepoint" in index.declared, True)

print()
print("-- what the editor shows")
summary, rows = ns["urm_checks"]("chapter")
check("a counter only ever tested with == says so",
      "Only these exact numbers" in summary, True)
check("its values come back in the order the game climbs them",
      [r[0] for r in rows], ["== 1", "== 2", "== 5"])
check("each row fills the box with that value", [r[1] for r in rows], [1, 2, 5])

summary, rows = ns["urm_checks"]("ainepoint")
check("a counter with a threshold does not get the warning",
      "Only these exact numbers" in summary, False)
check("> and >= rows offer the smallest value that passes",
      [(r[0], r[1]) for r in rows], [(">= 2", 2), ("== 3", 3), ("== 8", 8)])

summary, rows = ns["urm_checks"]("love")
check("a rival comparison is shown but cannot be clicked",
      [(r[0], r[1]) for r in rows if r[0].startswith("<")],
      [("< hard_love - 30", None)])

count, lines = ns["urm_writers"]("aineroute")
check("writers are described by the option's own words",
      count == 1 and '"Agree with her"' in lines[0] and "urmcheck" in lines[0],
      True)

state, pct = ns["urm_index_status"]()
check("status reports ready", (state, pct), ("ready", None))

print()
print("all passed" if not failures else "%d FAILED" % len(failures))
sys.exit(1 if failures else 0)
