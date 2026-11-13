"""
Unit-checks the variable panel against real Ren'Py AST nodes.

    <a game's bundled python> -I -B check_panel.py <that game folder>

The script below is parsed by the engine's own parser and indexed exactly as
in a running game; then urm_panel() is asked about each variable, with the
"played" record and the player's position faked. Each shape asserted here was
found in a real game while the panel was designed:

  route/pts    My Bully Is My Lover - the game turns the route OFF by itself
               unless the points are exactly right, and only checks exact
               numbers
  gal          Bound by Lust - 281 checks that all do the same thing
  pick         Anna Exciting Affection - a decision kept as a string
  sw           Anna (remake) - a scene-select menu "set sw to True"
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
default route = False
default pts = 0
default pick = ""
default gal = False
default sw = False
default hard = 30
default love = 0

label start:
    "Girl" "Will you help me?"
    menu:
        "Be nice":
            $ pts += 1
            $ route = True
        "Be rude":
            $ route = False
    if route and pts == 2:
        "Girl" "{b}A long[[ish] scene{/b}, line one."
        "Girl" "line two"
        "Girl" "line three"
        "Girl" "line four"
    else:
        $ route = False
        "Nothing happens."
    if pts == 1:
        "Girl" "One point scene."
    menu:
        "Secret option" if pts >= 2:
            "Girl" "Secret!"
        "Normal":
            pass
    menu:
        "Flirt":
            $ pick = "flirt"
        "Money":
            $ pick = "money"
    if pick == "flirt":
        "Girl" "Flirty."
    if love < hard - 25:
        "Girl" "Cold."
    menu:
        "set sw to True":
            $ sw = True
        "set sw to False":
            $ sw = False
    if sw:
        "Girl" "Switched."
    return

label reset:
    $ gal = False
    return

label g1:
    if gal:
        jump reset
    return

label g2:
    if gal:
        jump reset
    return

label g3:
    if gal:
        jump reset
    return

label g4:
    if gal:
        jump reset
    return

label g5:
    if gal:
        jump reset
    return
'''


def parse(source):
    import shutil
    import tempfile
    folder = tempfile.mkdtemp(prefix="urm_check_panel_")
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


class FakeVar(object):
    _urmcIndex = None


class X52URM(object):
    Var = FakeVar


import types  # noqa
store = types.ModuleType("store")
renpy.store = store

ns = {
    "renpy": renpy,
    "x52URM": X52URM(),
    "python_dict": dict, "python_list": list,
    "python_set": set, "python_object": object,
    # A Ren'Py 7 store's str is unicode (renpy.compat); literals parsed on
    # Python 2 are byte strings. Run the blocks under the store's names.
    "str": type(u""),  # STORE_STR
    "__name__": "urm_panel_check",
}

for wanted in ("class _URMIndex", "def urm_checks", "def urm_panel"):
    found = blocks(source, wanted)
    if len(found) != 1:
        print("FAIL  expected one init block holding %r, found %d" % (wanted, len(found)))
        sys.exit(1)
    exec(compile(found[0], "game_fixes.rpy", "exec"), ns)

nodes = parse(SOURCE)
index = ns["_URMIndex"]()
index.build(nodes)
FakeVar._urmcIndex = index
ns["_urmi_index"] = lambda: index


class Prefs(object):
    language = None


ns["_preferences"] = Prefs()
# Nothing played yet: every check is still ahead.
ns["urm_seen"] = lambda label: False if label in index.labels else None

for name, value in (("route", False), ("pts", 0), ("pick", ""), ("gal", False),
                    ("sw", False), ("hard", 30), ("love", 0)):
    setattr(store, name, value)

failures = []


def check(name, got, want):
    if got == want:
        print("pass  %s" % name)
    else:
        failures.append(name)
        print("FAIL  %s" % name)
        print("        expected %r" % (want,))
        print("        got      %r" % (got,))


def has(lines, text):
    import re
    for line in lines:
        if text in re.sub(r"\{/?a[^}]*\}", "", line):
            return True
    return False


def panel(name):
    ns["_urmp_bucket"]("panels").clear()
    return ns["urm_panel"](name)


print("-- a route flag")
p = panel("route")
check("it is read as an on/off flag", p.mode, "bool")
check("the answer starts with its value", p.answer[0].startswith("route is OFF."), True)
check("a scene with an else is a different version either way",
      "Different version either way: 1 place" in p.answer[0], True)
check("the reset is a warning, with its condition in words",
      has(p.warnings, "turns route OFF by itself in start unless") and has(p.warnings, "pts exactly 2"), True)
on = [b for b in p.blocks if b.header.startswith("A DIFFERENT VERSION") or b.header.startswith("ONLY WITH ON")]
rows = [r for b in on for r in b.rows + b.small]
big = [r for r in rows if r.cond == "route and pts == 2"]
check("the gated scene is a row", len(big), 1)
if big:
    check("its first line is dialogue with tags stripped and [[ unescaped",
          big[0].summary.first, u'Girl: "A long[ish] scene, line one."')
    check("the other condition is named as also needed",
          has(big[0].view_extra, "also needs"), True)
    check("not played yet", big[0].status, "not")
    check("Code shows the real condition", "if route and pts == 2:" in big[0].view_code, True)
check("the choice tab names both options", len(p.choices) >= 1 and len(p.choices[0][1]), 2)

print()
print("-- the player is at the first menu")
menu = [n for n in nodes if isinstance(n, renpy.ast.Menu)][0]
cur = ("here", "start", menu.filename, menu.linenumber, id(menu))
ns["_urmp_current"] = lambda index: cur
p = panel("route")
check("the choice on screen is shown", p.now_header is not None and p.now_header.startswith("THE CHOICE ON YOUR SCREEN"), True)
check("with the question it answers", "Will you help me?" in (p.now_header or ""), True)
check("and what each option does", [t for t, _v in p.now_lines][:2],
      [u'"Be nice"  \u2192  turns it ON', u'"Be rude"  \u2192  turns it OFF'])
check("checks below the menu are later in this scene",
      all(r.status == "later" for r in p.later) and len(p.later) >= 1, True)
ns["_urmp_current"] = lambda index: None

print()
print("-- a points counter")
p = panel("pts")
check("it is read as a number", p.mode, "number")
headers = [b.header for b in p.blocks]
check("one rung per requirement, in order",
      [h for h in headers if not h.startswith(u"\u2500")], ["exactly 1", "exactly 2", "2 or more"])
check("the player's own value is marked", has(headers, "you: 0"), True)
check("the hidden option is a row on its rung",
      [r.option for b in p.blocks if b.header == "2 or more" for r in b.rows], ["Secret option"])
check("the NEXT helper picks the smallest number ahead", (p.next_line or "").startswith("NEXT: exactly 1"), True)
check("the most it can gain is summed per menu", has(p.gives_tail, "at most +1"), True)

print()
print("-- a decision kept as text")
p = panel("pick")
check("it is read as a value", p.mode, "value")
check("the block is the value, with the choice that sets it",
      [(b.header, b.sub) for b in p.blocks], [(u'"flirt"', u'the choice "Flirt" in start')])

print()
print("-- a threshold written as arithmetic")
p = panel("love")
check("worked out with the other value as it is now",
      [b.header for b in p.blocks if not b.marker], ["4 or less"])
check("and says what it moves with", p.blocks[-1].sub if p.blocks else None,
      "with hard at 30 now - it moves when that changes")

print()
print("-- the same check everywhere")
p = panel("gal")
check("collapsed into one sentence", "Almost every check (5 of 5)" in p.answer[0], True)
check("which says what it does", "goes to reset" in p.answer[0], True)

print()
print("-- a scene-select menu")
p = panel("sw")
check("its options are not counted as story choices", len(p.choices), 0)
check("but it is mentioned", has(p.choices_tail, "scene-select"), True)

print()
print("-- the evaluator only reads")
ev = ns["_urmp_ev"]
parse_ = ns["_urmp_parse"]
UNK = ns["_URMP_UNK"]
store.items = ["a", "b"]
check("len() is allowed", ev(parse_("len(items) > 1")), True)
check("any other call is unknown", ev(parse_("print(1)")) is UNK, True)
check("a name it does not know is unknown", ev(parse_("nosuchname")) is UNK, True)
check("one name can be tried at another value", ev(parse_("pts == 3"), "pts", 3), True)

print()
print("-- a variable the script never uses")
p = panel("nothing_here")
check("says so plainly", "never checks or sets nothing_here" in (p.message or ""), True)

print()
print("all passed" if not failures else "%d FAILED" % len(failures))
sys.exit(1 if failures else 0)
