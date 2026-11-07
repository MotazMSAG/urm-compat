"""
Runs the shipped urm_path_lines() against a real game script, without a game.

    python -I check_gates.py <game folder> <a .rpyc file> <condition text>

Loads the compiled script, chains the nodes the way the engine does on load,
finds the if-statement whose first condition is <condition text>, then execs
the helper block straight out of game_fixes.rpy against stand-ins for the bits
of URM it calls. What it prints is what the notification would draw.

The stand-ins are deliberately thin. nodesToCode is the one with real
behaviour to mimic - URM emits python statements, jumps and calls and drops
dialogue - so it is reproduced here rather than imported, and the ... markers
show where this test's rendering could differ from URM's own.

Run it with the engine belonging to the game the .rpyc came from: an AST
pickled by one Ren'Py does not always unpickle in another.
"""

import io
import os
import re
import struct
import sys
import textwrap
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLKIT = os.path.dirname(HERE)

base = os.path.abspath(sys.argv[1])
script = os.path.abspath(sys.argv[2])
wanted = sys.argv[3] if len(sys.argv) > 3 else None

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


class FakeLog(object):
    mutated = {}


class FakeContext(object):
    init_phase = True


renpy.game.script = FakeScript()
renpy.game.log = FakeLog()
if not renpy.game.contexts:
    renpy.game.contexts = [FakeContext()]

from renpy.compat.pickle import loads  # noqa

raw = open(script, "rb").read()
pos, payload = 10, None
while True:
    slot, start, length = struct.unpack("III", raw[pos:pos + 12])
    if slot == 0:
        break
    if slot == 1:
        payload = zlib.decompress(raw[start:start + length])
        break
    pos += 12

_data, stmts = loads(payload)
renpy.ast.chain_block(stmts, None)


def find(block):
    for node in block:
        if isinstance(node, renpy.ast.If):
            if node.entries and (wanted is None
                                 or str(node.entries[0][0]) == wanted):
                return node
            for _cond, inner in node.entries:
                hit = find(inner)
                if hit is not None:
                    return hit
        elif isinstance(node, renpy.ast.Label):
            hit = find(node.block)
            if hit is not None:
                return hit
    return None


target = find(stmts)

if target is None:
    raise SystemExit("no if-statement with condition %r" % wanted)


# ---------------------------------------------------------------- stand-ins


def nodes_to_code(nodes, indent=0):
    """URM's CodeView.nodesToCode, reproduced: dialogue is not emitted."""
    out = ""
    pad = "    " * indent

    for node in nodes or []:
        if isinstance(node, renpy.ast.Python) and hasattr(node.code, "source"):
            out += pad + node.code.source + "\n"
        elif isinstance(node, renpy.ast.If):
            for i, (cond, inner) in enumerate(node.entries):
                if i == 0:
                    out += pad + "if %s:\n" % cond
                elif str(cond) == "True":
                    out += pad + "else:\n"
                else:
                    out += pad + "elif %s:\n" % cond
                out += nodes_to_code(inner, indent + 1)
        elif isinstance(node, renpy.ast.Jump):
            out += pad + "jump %s\n" % node.target
            break
        elif isinstance(node, renpy.ast.Call):
            out += pad + "call %s\n" % node.label

    return out.rstrip()


class Colors(object):
    # The helper picks Bg or Text by theme, so both halves are present.
    successText = "#107c10"
    successBg = "#9f9"
    errorText = "#a01010"
    errorBg = "#f99"
    buttonBg = "#202020"
    buttonBgHover = "#303030"
    buttonBorder = "#e0e0e0"


class Theme(object):
    colors = Colors()
    textTranslucent140 = "#8888"
    isDark = True


class CodeView(object):
    nodesToCode = staticmethod(nodes_to_code)


class PathDetection(object):
    lookAheadLimit = 20
    nextIfStatement = (target, True)

    @staticmethod
    def nextNode(node):
        if isinstance(node, renpy.ast.Jump):
            return None
        return getattr(node, "next", None)

    @staticmethod
    def nodeIsBlocking(node):
        return bool(getattr(node, "interact", False))


class Choices(object):
    currentChoices = []


class X52URM(object):
    Theme = Theme()
    CodeView = CodeView()
    PathDetection = PathDetection()
    Choices = Choices()

    @staticmethod
    def scaleText(text, width, style=None, pixelTarget=False,
                  escapeStyling=False, reverse=False):
        # No font here, so approximate: URM trims to fit a pixel width.
        text = re.sub(r"\{.*?\}", lambda m: "{" + m.group(), text) \
            if escapeStyling else re.sub(r"\{.*?\}", "", text)
        limit = max(10, int(width / 7))
        return text if len(text) <= limit else text[:limit - 1] + "..."


# Pull the helper block out of game_fixes.rpy and run the real thing.
source = io.open(os.path.join(TOOLKIT, "game_fixes.rpy"),
                 encoding="utf-8").read()

marker = "init 999 python:"
blocks = source.split(marker)
body = textwrap.dedent(blocks[-1])

namespace = {
    "x52URM": X52URM(),
    "renpy": renpy,
    "__name__": "urm_helpers",
}

exec(compile(body, "game_fixes.rpy", "exec"), namespace)

print("detected if:")
for cond, _block in target.entries:
    print("    %s" % ("else" if str(cond) == "True" else "if %s" % cond))
print("has else   : %s" % (str(target.entries[-1][0]) == "True"))

def strip(text):
    text = re.sub(r"\{/?urm_notl\}", "", text)
    text = re.sub(r"\{/?color[^}]*\}", "", text)
    return text.replace("{{", "{")


print("\nwhat the notification draws:")
ICONS = {
    u"": "[ok]",
    u"": "[no]",
    u"": "[--]",
    u"": " ->",
    u"": "  >",
}


def plain(text):
    text = strip(text)
    text = re.sub(r"\{/?i\}", "", text)
    for code, label in ICONS.items():
        text = text.replace(code, label)
    return text


summary, cards = namespace["urm_path_cards"]()

print("    %s" % summary)
for icon, number, head, effects in cards:
    print("    " + "=" * 54)
    print("    %-4s %-2s %s" % (plain(icon), number, plain(head)))
    print("    " + "-" * 54)
    for bullet, body in effects:
        print("    %-4s    %s" % (plain(bullet), plain(body)))
print("    " + "=" * 54)
