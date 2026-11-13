"""
Checks flags - choices a game keeps as words in a collection.

    <a game's bundled python> -I -B check_flags.py <that game folder>

The script below copies the shapes of Nothing Is Forever, word for word where
it matters: option() / true() over a set of strings, new_path() / remove_path()
/ on_path() over a set of objects matched on .name, plus a word tested
directly with `in`. It is parsed and indexed by the game's own Ren'Py, then
the variable panel, the switch and the code-view links are checked.
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

    def __getattr__(self, name):
        return None


renpy.game.script = FakeScript()
renpy.game.log = type("L", (), {"mutated": {}})()
if not renpy.game.contexts:
    renpy.game.contexts = [type("C", (), {"init_phase": True})()]

SOURCE = u'''
init python:
    class Path(object):
        def __init__(self, name, img, li):
            self.name = name
            self.img = img
            self.li = li

    def new_path(i):
        global mc_paths
        mc_paths.add(i)
        renpy.show_screen("new_path_screen")

    def remove_path(i):
        global mc_paths
        mc_paths_tmp = [x for x in mc_paths if not x.name == i.name]
        mc_paths.clear()
        for x in mc_paths_tmp: mc_paths.add(x)

    def on_path(i):
        global mc_paths
        if any (x.name == i for x in mc_paths):
            return True
        else:
            return False

    def true(o):
        if o in mc_choices:
            return True

    def option(i):
        global mc_choices
        mc_choices.add(i)

default mc_choices = set()
default mc_paths = set()
default diary = []
define kim_mercy_path = Path("kim_mercy_path", "kim_mercy_icon", "kim")
define kim_beg_path = Path("kim_beg_path", "kim_beg_icon", "kim")

label start:
    "Kim" "Well? Will you do it?"
    menu:
        "Accept":
            $ option("ch6_kim_accept")
            $ remove_path(kim_beg_path)
            $ new_path(kim_mercy_path)
        "No way I'm doing that":
            $ option("ch6_kim_refuse")
    if true("ch6_kim_accept"):
        "Kim" "You're mine now."
        "Kim" "Two."
        "Kim" "Three."
        "Kim" "Four."
    if not true("ch6_kim_refuse") and on_path("kim_mercy_path"):
        "Kim" "Mercy scene."
    if on_path("kim_beg_path"):
        "Kim" "Beg scene."
    $ diary.append("met_kim")
    if "met_kim" in diary:
        "I met Kim."
    return
'''


def parse(source):
    folder = tempfile.mkdtemp(prefix="urm_check_flags_")
    path = os.path.join(folder, "urmflags.rpy")
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
    pass


class X52URM(object):
    Var = FakeVar


notes = []


class StoreRenpy(object):
    def __getattr__(self, name):
        if name in ("game", "ast", "store", "display", "python"):
            return getattr(renpy, name)
        if name == "notify":
            return notes.append
        if name == "restart_interaction":
            return lambda: None
        return getattr(sys.modules["renpy.exports"], name)


import types  # noqa
store = types.ModuleType("store")
renpy.store = store

config = type("Config", (), {"hyperlink_handlers": {}, "interact_callbacks": [],
                             "after_load_callbacks": []})()
ns = {"renpy": StoreRenpy(), "x52URM": X52URM(), "config": config,
      "python_dict": dict, "python_list": list, "python_set": set,
      "python_object": object,
    # A Ren'Py 7 store's str is unicode (renpy.compat); literals parsed on
    # Python 2 are byte strings. Run the blocks under the store's names.
    "str": type(u""),  # STORE_STR
    "__name__": "urm_flags_check"}

for wanted in ("class _URMIndex", "def urm_checks", "def urm_panel", "def urmfl_set"):
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
ns["urm_seen"] = lambda label: False if label in index.labels else None


class Path(object):
    def __init__(self, name, img, li):
        self.name = name
        self.img = img
        self.li = li


store.kim_mercy_path = Path("kim_mercy_path", "kim_mercy_icon", "kim")
store.kim_beg_path = Path("kim_beg_path", "kim_beg_icon", "kim")
store.mc_choices = set()
store.mc_paths = set([store.kim_beg_path])
store.diary = []

failures = []


def check(name, got, want):
    if got == want:
        print("pass  %s" % name)
    else:
        failures.append(name)
        print("FAIL  %s" % name)
        print("        expected %r" % (want,))
        print("        got      %r" % (got,))


def panel(name):
    ns["_urmp_bucket"]("panels").clear()
    return ns["urm_panel"](name)


ACCEPT = 'true("ch6_kim_accept")'
REFUSE = 'true("ch6_kim_refuse")'
MERCY = 'on_path("kim_mercy_path")'
BEG = 'on_path("kim_beg_path")'
DIARY = '"met_kim" in diary'

print("-- the game's helpers, learnt from their definitions")
check("each helper's role", dict((k, v) for k, v in index.helpers.items()), {
    "true": ("get", "mc_choices", None), "option": ("add", "mc_choices", None),
    "on_path": ("get", "mc_paths", "name"), "new_path": ("add", "mc_paths", None),
    "remove_path": ("remove", "mc_paths", "name")})
check("every tested word is a flag, named by its test",
      sorted(index.flags), sorted([ACCEPT, REFUSE, MERCY, BEG, DIARY]))
check("a negated test is an OFF check", [op for _s, op, _l in index.reads.get(REFUSE, ())], ["falsy"])
check("option() under a menu option sets the flag ON",
      [(op, v) for _s, op, v, _t in index.writes.get(ACCEPT, ())], [("=", True)])
check("new_path(kim_mercy_path) is matched to on_path(\"kim_mercy_path\")",
      [(op, v) for _s, op, v, _t in index.writes.get(MERCY, ())], [("=", True)])
check("remove_path(kim_beg_path) turns that path OFF",
      [(op, v) for _s, op, v, _t in index.writes.get(BEG, ())], [("=", False)])
check("a word appended to a list is set ON", [v for _s, _o, v, _t in index.writes.get(DIARY, ())], [True])

print()
print("-- reading a flag never calls the game")
check("off while the word is not in the set", ns["urmfl_is_on"](ACCEPT), False)
check("an object-kept flag is read by its name", (ns["urmfl_is_on"](BEG), ns["urmfl_is_on"](MERCY)), (True, False))

print()
print("-- the variable panel, for a flag")
p = panel(ACCEPT)
check("an on/off flag", p.mode, "bool")
check("the answer names it", p.answer[0].startswith(ACCEPT + " is OFF."), True)
rows = [r for b in p.blocks for r in b.rows + b.small]
check("the scene it opens is a row, with its first line",
      [r.summary.first for r in rows], [u'Kim: "You\'re mine now."'])
check("the choice that sets it, in the player's words",
      [t for t, _v in p.choices[0][1]] if p.choices else None,
      [u'"Accept"  \u2192  turns it ON', u'"No way I\'m doing that"  \u2192  doesn\'t change it'])
p = panel(MERCY)
rows = [r for b in p.blocks for r in b.rows + b.small]
check("another flag in the same condition is an \"also needs\"",
      [e for r in rows for e in r.view_extra if "also needs" in e],
      [u'also needs {a=URMFlag:true("ch6_kim_refuse")}true("ch6_kim_refuse"){/a} OFF'])

print()
print("-- switching")
ns["urmfl_set"](ACCEPT, True)
check("ON adds the word to the set", "ch6_kim_accept" in store.mc_choices, True)
ns["urmfl_set"](MERCY, True)
check("an object-kept flag adds the object that stands for it", store.kim_mercy_path in store.mc_paths, True)
ns["urmfl_set"](BEG, False)
check("OFF removes it", store.kim_beg_path in store.mc_paths, False)
ns["urmfl_set"](DIARY, True)
check("a list gets the word appended", store.diary, ["met_kim"])
check("a panel worked out before notices the change",
      panel(ACCEPT).answer[0].startswith(ACCEPT + " is ON."), True)
ns["urmfl_set"](ACCEPT, False)
check("and OFF takes it back out", "ch6_kim_accept" in store.mc_choices, False)

print()
print("-- the Flags list and the links")
rows, matched = ns["urmfl_rows"]("kim")
check("the filter finds flags by their word", sorted(r[1] for r in rows),
      ["ch6_kim_accept", "ch6_kim_refuse", "kim_beg_path", "kim_mercy_path", "met_kim"])
colored = u'{color=#DCDCAA}true{/color}({color=#ce9178}"ch6_kim_accept"{/color})'
check("true(\"x\") in the code view opens the flag",
      ns["_urmfl_links"](None, colored), u'{a=URMFlag:%s}%s{/a}' % (ACCEPT, colored))
check("a call that is not a flag stays as it is",
      ns["_urmfl_links"](None, u'renpy.pause("x")'), u'renpy.pause("x")')
check("the link handler is registered", "URMFlag" in config.hyperlink_handlers, True)
var = ns["urmfl_var"](MERCY)
check("the dialog's variable says where the flag lives",
      (var.word, var.where, var.isFlag, var.value), ("kim_mercy_path", "Kept in mc_paths, tested with on_path()", True, True))

print()
print("all passed" if not failures else "%d FAILED" % len(failures))
sys.exit(1 if failures else 0)
