"""
Checks the rollback length setting and "back to the last choice".

    <a game's bundled python> -I -B check_rollback.py <that game folder>

The rollback history is modelled the way Ren'Py keeps it (rollback.py): one
entry per stretch of statements, a hard checkpoint taken after each
interaction, and the value the interaction returned stored on the entry - True
for dialogue, the option for a menu. The step count handed to renpy.rollback()
is then replayed through Ren'Py's own walk to see where it lands.
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


class Entry(object):
    def __init__(self, name, forward=None, hard=False):
        self.name = name
        self.forward = forward
        self.hard_checkpoint = hard


class Log(object):
    def __init__(self, entries, limit=100):
        self.log = entries
        self.current = entries[-1]
        self.rollback_limit = limit


calls = []
notes = []


class StoreRenpy(object):
    Displayable = renpy.display.core.Displayable
    Render = renpy.display.render.Render

    def __init__(self):
        self.game = type("G", (), {})()

    def rollback(self, checkpoints=1, **kwargs):
        calls.append(checkpoints)

    def notify(self, text):
        notes.append(text)


store_renpy = StoreRenpy()


class Settings(object):
    values = {}

    def get(self, name):
        return self.values.get(name, 500 if name == "urmcRollback" else None)


class Config(object):
    hard_rollback_limit = 100
    rollback_length = 128
    interact_callbacks = []


config = Config()
x52 = type("X", (), {})()
x52.Var = type("V", (), {})
x52.Settings = Settings()
x52.SettingsClass = type("SC", (), {"defaultValues": {}})

try:
    text_types = (str, unicode)  # noqa
except NameError:
    text_types = (str,)

ns = {"renpy": store_renpy, "x52URM": x52, "config": config,
      "python_dict": dict, "python_list": list, "python_set": set,
      "python_object": object, "_urmi_text": text_types, "__name__": "urm_rollback_check"}

source = io.open(os.path.join(TOOLKIT, "game_fixes.rpy"), encoding="utf-8").read()
found = blocks(source, "def urmr_back_to_choice")
if len(found) != 1:
    print("FAIL  expected one init block holding urmr_back_to_choice, found %d" % len(found))
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


def lands(entries, steps):
    """Ren'Py's own walk (RollbackLog.rollback, greedy), on names."""
    log = list(entries)
    while log:
        rb = log.pop()
        if rb.hard_checkpoint:
            steps -= 1
        if steps <= 0:
            break
    while log and not log[-1].hard_checkpoint:
        rb = log.pop()
    return rb.name


def go(entries, limit=100):
    del calls[:]
    del notes[:]
    store_renpy.game.log = Log(entries, limit)
    ns["urmr_back_to_choice"]()
    return calls[0] if calls else None


print("-- back to the last choice")
history = [Entry("say a", True, True), Entry("menu 1", 1, True), Entry("say b", True, True),
           Entry("python + say c", True, True), Entry("say d (on screen)")]
steps = go(history)
check("three checkpoints back from two lines after the choice", steps, 3)
check("which lands on the menu", lands(history, steps), "menu 1")

history = [Entry("say a", True, True), Entry("menu 1", 0, True), Entry("say b", True, True),
           Entry("menu 2 (on screen, not chosen yet)")]
steps = go(history)
check("standing at a new menu goes back to the one before it", lands(history, steps), "menu 1")

history = [Entry("menu 1", 1, True), Entry("call screen map", "park", True), Entry("say (on screen)")]
check("a value a screen returned counts as a choice", lands(history, go(history)), "call screen map")

history = [Entry("say a", True, True), Entry("pause", False, True), Entry("say b")]
check("no choice: nothing rolls back", go(history), None)
check("and it says so", len(notes), 1)

history = [Entry("menu 1", 1, True), Entry("say a", True, True), Entry("say b", True, True), Entry("say c")]
check("a block the game set is respected", go(history, limit=2), None)
check("with a notification", "blocks" in (notes[0] if notes else ""), True)

print()
print("-- rollback length")
ns["_urmr_apply"]()
check("500 by default, history half again as long",
      (config.hard_rollback_limit, config.rollback_length), (500, 750))
Settings.values["urmcRollback"] = 0
ns["_urmr_apply"]()
check("game default puts the game's own back", (config.hard_rollback_limit, config.rollback_length), (100, 128))
Settings.values["urmcRollback"] = 2000
ns["_urmr_apply"]()
check("2000", config.hard_rollback_limit, 2000)
st = ns["_urmr_state"]()
st.game_hard, st.game_length, st.applied = 5000, 6000, None
Settings.values["urmcRollback"] = 500
ns["_urmr_apply"]()
check("a game that asks for more keeps its own", (config.hard_rollback_limit, config.rollback_length), (5000, 6000))

print()
print("all passed" if not failures else "%d FAILED" % len(failures))
sys.exit(1 if failures else 0)
