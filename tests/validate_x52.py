"""
Parse URM .x52 screen files with a real Ren'Py parser to check syntax.

    python -I validate_x52.py <game folder> <file.x52> [more...]

A .x52 file is plain Ren'Py source, so renpy.parser.parse() is the exact same
check the engine applies when URM loads it. Parsing does not evaluate, so the
x52URM.* references do not need to exist.
"""

import os
import shutil
import sys
import tempfile

base = os.path.abspath(sys.argv[1])
targets = sys.argv[2:]

os.chdir(base)
sys.path.insert(0, base)

import renpy  # noqa

renpy.import_all()
renpy.config.basedir = base
renpy.config.gamedir = os.path.join(base, "game")

# Screen language statements (screen/default/use/showif/...) are registered by
# the SL2 parser, which main() initialises before loading any script.
renpy.sl2.slparser.init()

# ATL warpers come from renpy/common/000atl.rpy, which is not loaded here. The
# parser only checks membership, so registering the names is enough.
for _warper in ("linear", "ease", "easein", "easeout", "pause", "instant",
                "ease_back", "ease_bounce", "ease_circ", "ease_cubic",
                "ease_elastic", "ease_expo", "ease_quad", "ease_quart",
                "ease_quint", "ease_sine", "easein_back", "easein_bounce",
                "easein_circ", "easein_cubic", "easein_elastic", "easein_expo",
                "easein_quad", "easein_quart", "easein_quint", "easein_sine",
                "easeout_back", "easeout_bounce", "easeout_circ",
                "easeout_cubic", "easeout_elastic", "easeout_expo",
                "easeout_quad", "easeout_quart", "easeout_quint",
                "easeout_sine"):
    renpy.atl.warpers.setdefault(_warper, lambda t: t)


class FakeScript(object):
    record_pycode = False
    all_pycode = []
    serial = 0

    def __getattr__(self, name):
        return None


class FakeContext(object):
    init_phase = True


renpy.game.script = FakeScript()
if not renpy.game.contexts:
    renpy.game.contexts = [FakeContext()]

failed = 0

for target in targets:
    target = os.path.abspath(target)

    # The parser keys off the extension, so hand it a .rpy copy.
    tmpdir = tempfile.mkdtemp(prefix="x52check_")
    copy = os.path.join(tmpdir, os.path.basename(target).replace(".x52t", "").replace(".x52", ""))
    if not copy.endswith(".rpy"):
        copy += ".rpy"
    shutil.copyfile(target, copy)

    renpy.parser.parse_errors = []

    try:
        result = renpy.parser.parse(copy)
    except Exception as e:
        result = None
        renpy.parser.parse_errors.append("%s: %s" % (type(e).__name__, e))

    errors = list(renpy.parser.parse_errors)

    name = os.path.basename(target)

    if result is None or errors:
        failed += 1
        print("FAIL %s" % name)
        for err in errors[:12]:
            print("      %s" % err.replace("\n", "\n      "))
        if result is None and not errors:
            print("      parse() returned None with no recorded error")
    else:
        print("ok   %s  (%d top-level statements)" % (name, len(result)))

    shutil.rmtree(tmpdir, ignore_errors=True)

sys.exit(1 if failed else 0)
