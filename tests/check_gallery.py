"""
Checks the gallery switch against the engine's own Persistent class.

    <a game's bundled python> -I -B check_gallery.py <that game folder>

A gallery screen is parsed and registered from real screen language, the
switch is turned on and off, and every way a game stores its gallery is read
back - inside a menu, where it must read unlocked, and in the story, where it
must read exactly what is stored.
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
renpy.sl2.slparser.init()


class FakeScript(object):
    record_pycode = False
    all_pycode = []
    serial = 0
    bytecode_oldcache = {}
    bytecode_newcache = {}

    def __getattr__(self, name):
        return None

    def lookup(self, name):
        return None


renpy.game.script = FakeScript()
renpy.game.log = type("L", (), {"mutated": {}})()


class Ctx(object):
    init_phase = True
    _menu = False
    current = None


ctx = Ctx()
renpy.game.contexts = [ctx]
renpy.game.context = lambda *a: ctx

SCREEN = u'''
screen my_gallery():
    if persistent.kimscene_done:
        text "Kim"
    if "b" in persistent.masterreplist["Jill"]:
        text persistent.replay_hints.get("b")
    if persistent.replay_earned == False:
        text "Earned"
    if persistent.replay_unearned == False:
        text "Unearned"
'''


def register(source):
    import shutil
    import tempfile
    folder = tempfile.mkdtemp(prefix="urm_check_gallery_")
    path = os.path.join(folder, "urmgallery.rpy")
    io.open(path, "w", encoding="utf-8").write(source)
    try:
        stmts = renpy.parser.parse(path)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    flat = []
    for node in stmts:
        node.get_children(flat.append)
    for node in flat:
        if isinstance(node, renpy.ast.Screen):
            node.execute()


register(SCREEN)


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
    values = {}

    def get(self, name):
        return self.values.get(name)

    def set(self, name, value):
        self.values[name] = value


class SettingsClass(object):
    defaultValues = {}


class FakeVar(object):
    pass


class X52URM(object):
    Var = FakeVar


x52 = X52URM()
x52.Settings = Settings()
x52.SettingsClass = SettingsClass

persistent = renpy.persistent.Persistent()
persistent._seen_ever = {}
persistent.scene3_unlocked = False
persistent.kimscene_done = None          # odd name, but the gallery screen tests it
persistent.gallery = {"kim": False, "ann": True}
persistent.unlocked_scenes = ["intro"]
persistent.music_volume_set = False      # a setting, never touched
# Thief of Hearts 2: False means unlocked. Startup code writes True (locked),
# the scene itself writes False when it is earned.
persistent.replay_earned = False
persistent.replay_unearned = True
persistent.chapter = 0                   # a number, never touched
persistent.masterreplist = {"Jill": ["a"]}   # The Lost Guardian: a list per girl
persistent.replay_hints = {"a": "hint"}      # tooltips: never invent one
renpy.game.persistent = persistent

import types  # noqa
store = types.ModuleType("store")
renpy.store = store

class StoreRenpy(object):
    """What `renpy` is inside a store: renpy.exports, with the package's
    submodules (game, ast, store) reachable the way game code reaches them."""

    def __getattr__(self, name):
        exports = sys.modules["renpy.exports"]
        if name in ("game", "ast", "store", "display", "persistent"):
            return getattr(renpy, name)
        return getattr(exports, name)


class FakeIndex(object):
    """Just what the switch asks the script index: who writes a flag, where."""
    state = "ready"
    nodes = {}
    parent = {}
    writes = {}
    for _flag in ("persistent.replay_earned", "persistent.replay_unearned"):
        writes[_flag] = [(("game/gallery.rpy", 2, 1), "=", True, None),     # init: locked
                         (("game/story.rpy", 40, 2), "=", False, None)]     # the scene: earned

    @staticmethod
    def label_at(filename, line):
        return "lb_scene" if filename == "game/story.rpy" else None


ns = {
    "renpy": StoreRenpy(),
    "x52URM": x52,
    "config": type("Config", (), {"interact_callbacks": []})(),
    "python_dict": dict, "python_list": list,
    "python_set": set, "python_object": object,
    # A Ren'Py 7 store's str is unicode (renpy.compat); literals parsed on
    # Python 2 are byte strings. Run the blocks under the store's names.
    "str": type(u""),  # STORE_STR
    "_urmi_index": lambda: FakeIndex,
    "_urmi_layer": "overlay",
    "__name__": "urm_gallery_check",
}

source = io.open(os.path.join(TOOLKIT, "game_fixes.rpy"), encoding="utf-8").read()
found = blocks(source, "def urmg_toggle")
if len(found) != 1:
    print("FAIL  expected one init block holding urmg_toggle, found %d" % len(found))
    sys.exit(1)
exec(compile(found[0], "game_fixes.rpy", "exec"), ns)

failures = []


def check(name, got, want):
    if got == want:
        print("pass  %s" % name)
    else:
        failures.append(name)
        print("FAIL  %s" % name)
        print("        expected %r" % (want,))
        print("        got      %r" % (got,))


exports = sys.modules["renpy.exports"]
original_seen = exports.seen_label
P = type(persistent)


def reads():
    return (persistent.scene3_unlocked, persistent.kimscene_done,
            persistent.never_set_replay, "ann2" in persistent.unlocked_scenes,
            persistent.gallery["kim"], persistent.music_volume_set,
            persistent.chapter, exports.seen_label("ending_scene"),
            "b" in persistent.masterreplist["Jill"],
            "x" in persistent.masterreplist.get("Nobody", ()),
            persistent.replay_hints.get("b"), persistent.replay_hints.get("a"),
            persistent.replay_earned, persistent.replay_unearned)


REAL = (False, None, None, False, False, False, 0, False, False, False, None, "hint", False, True)
ALL = (True, True, True, True, True, False, 0, True, True, True, None, "hint", False, False)

print("-- switched off")
check("everything reads as stored", reads(), REAL)
check("nothing is installed", ("__getattribute__" in P.__dict__, exports.seen_label is original_seen), (False, True))

print()
print("-- switched on")
ns["urmg_toggle"]()
check("the setting is saved", x52.Settings.get("urmcGalleryAll"), True)
check("the gallery screen was found", "my_gallery" in ns["_urmg_state"]().screens, True)
check("and the flags it tests", ("kimscene_done" in ns["_urmg_state"]().names,
                                 "masterreplist" in ns["_urmg_state"]().names), (True, True))
ctx._menu = True
check("in a menu: unlocked, settings and numbers left alone", reads(), ALL)
ctx._menu = False
check("in the story: exactly what is stored", reads(), REAL)
check("the stored values were never written",
      (persistent.__dict__["scene3_unlocked"], persistent.__dict__["gallery"]["kim"],
       "never_set_replay" in persistent.__dict__),
      (False, False, False))
check("the badge says so", "everything unlocked" in ns["urmg_badge_text"](), True)

print()
print("-- switched back")
ns["urmg_toggle"]()
ctx._menu = True
check("in a menu: your own unlocks again", reads(), REAL)
check("and nothing is left installed",
      ("__getattribute__" in P.__dict__, exports.seen_label is original_seen), (False, True))

print()
print("all passed" if not failures else "%d FAILED" % len(failures))
sys.exit(1 if failures else 0)
