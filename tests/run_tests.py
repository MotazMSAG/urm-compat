"""
Checks the UI tweaks against a real URM archive, without launching a game.
    python run_tests.py "<a Ren'Py game folder>" [path to 0x52_URM.rpa]
The game folder is only borrowed for its bundled Ren'Py - the tests parse
URM's screens with the same parser the engine uses, so a screen that would
fail to load fails here instead. Nothing in the game is read or written.
What it checks:
  1. every tweak still matches URM's current screen source
  2. applying them twice changes nothing (installing over an install is safe)
  3. the patched screens parse as valid Ren'Py screen language
  4. the unpatched screens parse too, so a failure in 3 is really the tweak
  5. the condition text actually reaches the places it should
Exit code 0 means everything passed.
"""
from __future__ import print_function
import io
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
import zlib
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLKIT = os.path.dirname(HERE)
sys.path.insert(0, TOOLKIT)
import ui_tweaks  # noqa
PYTHONS = [
    "lib/py3-windows-x86_64/python.exe",
    "lib/py3-windows-i686/python.exe",
    "lib/py3-linux-x86_64/python",
    "lib/py3-mac-universal/python",
]
# Text that must survive into the patched screens, per file.
EXPECTED = {
    "0x52-URM/screens/paths.rpy.x52": [
        "x52URM.scaleText(statement.condition",
        # The gates after the detected one, read-only because URM can only
        # force a path through the node it detected.
        "urm_later_gate_rows()",
        "urmf_force_later",
    ],
    "0x52-URM/screens/choices.rpy.x52": ["x52URM.scaleText(choice.condition"],
    "0x52-URM/screens/watchpanel.rpy.x52": [
        "$ _urmGates = (urm_path_cards()",
        "$ _urmGates = (urm_choice_cards()",
        "for _urmIcon, _urmNum, _urmHead, _urmEffects in _urmCards",
        "for _urmBullet, _urmBody in _urmEffects",
        # The degradation contract: a missing helper must not raise.
        "hasattr(renpy.store, 'urm_path_cards')",
        "hasattr(renpy.store, 'urm_choice_cards')",
        # The rule that bounds a gate. buttonBorder rather than the style's
        # own Theme.primary default, which fails contrast in five themes.
        "background x52URM.Theme.colors.buttonBorder",
        # The icon column - the one channel colorize() output cannot forge.
        "style_suffix 'icon' substitute False yalign 0.0",
    ],
    "0x52-URM/screens/search.rpy.x52": [
        # The Deeper button, and its degradation guard: no helper, no button.
        "getattr(x52URM.Search, 'urmcNextDepth', 0) > 0",
        "Function(x52URM.Search.urmcDeepen)",
        # The depth rows, hidden unless the setting was actually registered.
        "'urmcSearchDepth' in x52URM.SettingsClass.defaultValues",
        "SetField(x52URM.Settings, 'urmcSearchDepth', 2)",
        # Browse the whole store, without knowing a name.
        "SetLocalVariable('expandObjectVars', urm_store_root())",
    ],
    "0x52-URM/screens/vars.rpy.x52": [
        "Function(urm_copy, var.name)",
        # The prophecy panel, and its guard: no compiled helper, no panel.
        "renpy.has_screen('urmi_var_panel')",
        "use urmi_var_panel(var, valueInput)",
    ],
    "0x52-URM/screens/labels.rpy.x52": [
        "urm_labels(str(labelFilter))",
        "enumerate(_urmLabels[",
        "urm_seen(labelName)",
        "title='What the marks mean'",
    ],
    "0x52-URM/screens/quickmenu.rpy.x52": [
        "if x52URM.Settings.quickmenuBtnSkipUnseen:",
        # Straight at the field, not Preference("skip", ...), whose name
        # lookup compares against the translated word.
        "ToggleField(_preferences, 'skip_unseen', True, False)",
    ],
    "0x52-URM/screens/options.rpy.x52": [
        "('quickmenuBtnSkipUnseen', {",
        "'urmcLookAhead': {",
    ],
}
# Text that must NOT survive - an older version of a tweak left in place
# alongside the new one would render every line twice.
FORBIDDEN = {
    "0x52-URM/screens/watchpanel.rpy.x52": [
        "_urmItem.condition",
        "urm_summary(_urmItem)",
        "urm_condition(_urmItem)",
        "urm_next_gates()",
        # URM's bundled Roboto is subsetted and has no U+2192, so an arrow
        # renders as a missing-glyph box.
        "\\u2192",
        # v7's two-value row, and the xsize that did not pad the column.
        "for _urmMark, _urmBody in ",
        "xsize x52URM.scalePxInt(52)",
        # v8's marker column and its single-rule-between-gates layout.
        "_urmRows",
        "min_width x52URM.scalePxInt(44)",
        # Solid(None) raises while the overlay is drawn, and a theme name that
        # does not resolve returns None silently - so backgrounds stay bare.
        "background Solid(",
    ],
}
# The helpers the patched screens call, which the installer compiles into the
# archive from game_fixes.rpy. A screen calling a helper that is not there
# raises while the overlay is being drawn.
HELPERS = ["urm_path_cards", "urm_choice_cards", "urm_copy", "urm_store_root",
           "urm_labels", "urm_seen", "urm_later_gates",
           # The script index and what the editor asks it.
           "urm_index_status", "urm_checks", "urm_writers", "urm_readers",
           "urm_gate_count", "urm_var_panel", "urmi_fill",
           # The variable panel the editor draws.
           "urm_panel", "urmi_ui", "urmi_ui_set", "urmi_ui_toggle",
           "urmi_settable", "urmi_set_words", "urmi_block_limit",
           "urmi_small_line",
           # The gallery switch.
           "urmg_toggle", "urmg_badge_text",
           # Rollback: back to the last choice.
           "urmr_back_to_choice",
           # Forcing paths URM marks "not forceable".
           "urm_later_gate_rows", "urmf_force_later",
           # Flags: choices kept as words in a collection.
           "urmfl_has", "urmfl_rows", "urmfl_set", "urmfl_var", "urmfl_is_on"]

# Inside a Ren'Py store, dict / list / set are rebound to the rollback-tracked
# Revertable kinds (minstore.py:37-50) and [] / {} literals are rewritten to
# them. A long-lived cache built from those is copied into the rollback log on
# every interaction it changes in. Code in these blocks must use python_dict,
# python_list and python_set - and the unit tests cannot see the difference,
# because plain Python maps those straight back to the builtins. So it is
# checked here, as text.
import re as _re
TRACKED = _re.compile(r"(?<![\w.])(dict|list|set)\(|=\s*(\[\]|\{\})\s*$")
TRACKED_BLOCKS = ("_urmc_", "_urmi_", "_URMIndex", "_urmp_")
def find_python(game):
    for rel in PYTHONS:
        path = os.path.join(game, rel)
        if os.path.exists(path):
            return path
    return None
def read_archive(path):
    with open(path, "rb") as f:
        parts = f.readline().split()
        offset = int(parts[1], 16)
        key = int(parts[2], 16) if parts[0] == b"RPA-3.0" else 0
        f.seek(offset)
        index = pickle.loads(zlib.decompress(f.read()))
        out = {}
        for name, entries in index.items():
            if isinstance(name, bytes):
                name = name.decode("utf-8")
            chunks = []
            for entry in entries:
                start = entry[0] ^ key
                length = entry[1] ^ key
                prefix = entry[2] if len(entry) > 2 else b""
                if isinstance(prefix, str):
                    prefix = prefix.encode("latin-1")
                f.seek(start)
                chunks.append(prefix + f.read(length - len(prefix)))
            out[name] = b"".join(chunks)
    return out
def parse_screens(python, game, paths):
    """Returns (ok, output) from the Ren'Py parser."""
    cmd = [python, "-I", "-B", os.path.join(HERE, "validate_x52.py"), game] + paths
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
    return result.returncode == 0, result.stdout.decode("utf-8", "replace")
def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    game = os.path.abspath(argv[1])
    rpa = os.path.abspath(argv[2]) if len(argv) > 2 else os.path.join(
        TOOLKIT, "0x52_URM.rpa")
    if not os.path.isdir(os.path.join(game, "renpy")):
        print("%s has no renpy/ in it - point me at a Ren'Py game folder." % game)
        return 2
    if not os.path.exists(rpa):
        print("No URM archive at %s" % rpa)
        return 2
    python = find_python(game)
    if python is None:
        print("No bundled Python under %s/lib" % game)
        return 2
    print("URM archive: %s" % rpa)
    print("Ren'Py from: %s" % game)
    print()
    failures = []
    work = tempfile.mkdtemp(prefix="urm_tests_")
    try:
        contents = read_archive(rpa)
        screens = sorted(n for n in contents
                         if n.endswith(".x52") and "/screens/" in n)
        # --- 4. the unpatched screens parse -----------------------------
        plain = os.path.join(work, "plain")
        os.makedirs(plain)
        for name in screens:
            with open(os.path.join(plain, os.path.basename(name)), "wb") as f:
                f.write(contents[name])
        ok, out = parse_screens(
            python, game,
            [os.path.join(plain, os.path.basename(n)) for n in screens])
        print("[1] URM's own screens parse")
        if ok:
            print("    pass  (%d files)" % len(screens))
        else:
            failures.append("URM's unpatched screens do not parse")
            print(out)
        # --- 1. every tweak matches -------------------------------------
        applied, skipped = ui_tweaks.apply(contents)
        print("[2] every tweak still matches URM's source")
        for name, note in applied:
            print("    pass  %s%s" % (name, "  (%s)" % note if note else ""))
        for name, why in skipped:
            failures.append("tweak not applied: %s (%s)" % (name, why))
            print("    FAIL  %s  -- %s" % (name, why))
        # --- 2. applying twice is a no-op -------------------------------
        before = dict(contents)
        ui_tweaks.apply(contents)
        changed = [n for n in before if before[n] != contents[n]]
        print("[3] applying the tweaks twice changes nothing")
        if changed:
            failures.append("second apply rewrote: %s" % ", ".join(changed))
            print("    FAIL  rewrote %s" % ", ".join(changed))
        else:
            print("    pass")
        # --- 5. the condition text reached the right places -------------
        print("[4] the condition reaches the screens that show it")
        for name, needles in EXPECTED.items():
            data = contents.get(name, b"")
            for needle in needles:
                if needle.encode("utf-8") in data:
                    print("    pass  %s <- %s" % (os.path.basename(name), needle))
                else:
                    failures.append("%s is missing %s" % (name, needle))
                    print("    FAIL  %s is missing %s" % (name, needle))
        for name, needles in FORBIDDEN.items():
            data = contents.get(name, b"")
            for needle in needles:
                if needle.encode("utf-8") in data:
                    failures.append("%s still contains %s" % (name, needle))
                    print("    FAIL  %s still contains %s" % (
                        os.path.basename(name), needle))
                else:
                    print("    pass  %s has no stale %s" % (
                        os.path.basename(name), needle))
        # --- 6. an archive patched by an older build upgrades cleanly ----
        print("[5] an archive from an older build upgrades, not doubles")
        wp = "0x52-URM/screens/watchpanel.rpy.x52"
        for version, template in (("v1", ui_tweaks._LINE_V1),
                                  ("v2", ui_tweaks._LINE_V2),
                                  ("v3", ui_tweaks._LINE_V3),
                                  ("v4", ui_tweaks._LINE_V4)):
            older = read_archive(rpa)
            # Reproduce what that build wrote, then re-apply.
            text = older[wp]
            for anchor, source in (
                    (ui_tweaks._PATH_COUNT, "x52URM.PathDetection.statements"),
                    (ui_tweaks._CHOICE_HIDDEN, "x52URM.Choices.currentChoices")):
                text = text.replace(
                    ui_tweaks._as_bytes(anchor),
                    ui_tweaks._as_bytes(anchor + "\n\n" + template % source), 1)
            older[wp] = text
            ui_tweaks.apply(older)
            upgraded = older[wp]
            # Two: one call per block. The hasattr guard names the helper as
            # a quoted string, so it does not match "name()".
            blocks = (upgraded.count(b"urm_path_cards()")
                      + upgraded.count(b"urm_choice_cards()"))
            stale = sum(upgraded.count(n.encode("utf-8"))
                        for n in FORBIDDEN[wp])
            if blocks == 2 and stale == 0:
                print("    pass  %s upgraded: both blocks carded, 0 left over"
                      % version)
            else:
                failures.append(
                    "%s upgrade left %d calls and %d stale lines"
                    % (version, blocks, stale))
                print("    FAIL  %s: %d calls, %d stale lines"
                      % (version, blocks, stale))

        # v5 and v7 appended their block after URM's own line; v8 replaced it
        # outright and carried its own fallback, so it is rebuilt from the
        # template the installer still keeps for exactly this purpose.
        def put_v5_v7(text, template):
            for anchor, helper in (
                    (ui_tweaks._PATH_COUNT, "urm_path_lines"),
                    (ui_tweaks._CHOICE_HIDDEN, "urm_choice_lines")):
                text = text.replace(
                    ui_tweaks._as_bytes(anchor),
                    ui_tweaks._as_bytes(anchor + template % helper), 1)
            return text

        def put_v8(text, _template):
            text = text.replace(
                ui_tweaks._as_bytes(ui_tweaks._PATH_COUNT),
                ui_tweaks._as_bytes(ui_tweaks._draw_v8(
                    "urm_path_lines", ui_tweaks._PATH_FALLBACK)), 1)
            return text.replace(
                ui_tweaks._as_bytes(ui_tweaks._CHOICE_HIDDEN),
                ui_tweaks._as_bytes(ui_tweaks._CHOICE_HIDDEN + "\n"
                                    + ui_tweaks._draw_v8("urm_choice_lines")), 1)

        for version, template, place in (("v5", ui_tweaks._DRAW_V5, put_v5_v7),
                                         ("v7", ui_tweaks._DRAW_V7, put_v5_v7),
                                         ("v8", None, put_v8)):
            older = read_archive(rpa)
            older[wp] = place(older[wp], template)

            ui_tweaks.apply(older)
            upgraded = older[wp]
            blocks = (upgraded.count(b"urm_path_cards()")
                      + upgraded.count(b"urm_choice_cards()"))
            carded = upgraded.count(
                b"for _urmIcon, _urmNum, _urmHead, _urmEffects in _urmCards")
            stale = sum(upgraded.count(n.encode("utf-8"))
                        for n in FORBIDDEN[wp])

            if blocks == 2 and carded == 2 and stale == 0:
                print("    pass  %s upgraded: both blocks carded, 0 left over"
                      % version)
            else:
                failures.append(
                    "%s upgrade left %d calls, %d carded, %d stale"
                    % (version, blocks, carded, stale))
                print("    FAIL  %s: %d calls, %d carded, %d stale"
                      % (version, blocks, carded, stale))

        # --- 6b. game_fixes.rpy parses at all ----------------------------
        print("[6] game_fixes.rpy parses with the real Ren'Py parser")
        result = subprocess.run(
            [python, "-I", "-B", os.path.join(HERE, "check_rpy.py"), game],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
        out = result.stdout.decode("utf-8", "replace")
        if result.returncode == 0:
            for line in out.splitlines():
                if line.startswith("pass"):
                    print("    %s" % line)
        else:
            failures.append("game_fixes.rpy does not parse")
            print(out)

        # --- 8. the effect flattener and its three reductions ------------
        print("[7] the effect flattener only merges what it can prove")
        result = subprocess.run(
            [python, "-I", "-B", os.path.join(HERE, "check_cards.py"), game],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
        out = result.stdout.decode("utf-8", "replace")
        if result.returncode == 0:
            print("    pass  (%d cases)" % out.count("pass  "))
        else:
            failures.append("the statement filter unit checks failed")
            print(out)

        # --- 8b. the search upgrades -------------------------------------
        # Its stand-ins are 0x52's own code, so it is not published.
        print("[7b] the search upgrades do what they claim")
        if not os.path.exists(os.path.join(HERE, "check_search.py")):
            print("    skip  (check_search.py is not part of the public tests)")
        else:
            result = subprocess.run(
                [python, "-I", "-B", os.path.join(HERE, "check_search.py"), game],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
            out = result.stdout.decode("utf-8", "replace")
            if result.returncode == 0:
                print("    pass  (%d cases)" % out.count("pass  "))
            else:
                failures.append("the search unit checks failed")
                print(out)

        # --- 8c. the script index -----------------------------------------
        print("[7c] the script index reads what the game checks and sets")
        result = subprocess.run(
            [python, "-I", "-B", os.path.join(HERE, "check_index.py"), game],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
        out = result.stdout.decode("utf-8", "replace")
        if result.returncode == 0:
            print("    pass  (%d cases)" % out.count("pass  "))
        else:
            failures.append("the script index unit checks failed")
            print(out)

        print("[7e] the variable panel tells the player what a value gets them")
        result = subprocess.run(
            [python, "-I", "-B", os.path.join(HERE, "check_panel.py"), game],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
        out = result.stdout.decode("utf-8", "replace")
        if result.returncode == 0:
            print("    pass  (%d cases)" % out.count("pass  "))
        else:
            failures.append("the variable panel unit checks failed")
            print(out)

        print("[7h] urm_plus.rpy patches URM's screens exactly as the archive build does")
        result = subprocess.run(
            [python, "-I", "-B", os.path.join(HERE, "check_runtime.py"), game, rpa],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
        out = result.stdout.decode("utf-8", "replace")
        if result.returncode == 0:
            print("    pass  (%d cases)" % out.count("pass  "))
        else:
            failures.append("the one-file install checks failed")
            print(out)

        print("[7i] any path can be forced, even behind a jump")
        result = subprocess.run(
            [python, "-I", "-B", os.path.join(HERE, "check_force.py"), game],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
        out = result.stdout.decode("utf-8", "replace")
        if result.returncode == 0:
            print("    pass  (%d cases)" % out.count("pass  "))
        else:
            failures.append("the force-a-path checks failed")
            print(out)

        print("[7j] flags: choices a game keeps as words in a collection")
        result = subprocess.run(
            [python, "-I", "-B", os.path.join(HERE, "check_flags.py"), game],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
        out = result.stdout.decode("utf-8", "replace")
        if result.returncode == 0:
            print("    pass  (%d cases)" % out.count("pass  "))
        else:
            failures.append("the flag checks failed")
            print(out)

        print("[7k] skipping carries on past a small change")
        result = subprocess.run(
            [python, "-I", "-B", os.path.join(HERE, "check_skip.py"), game],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
        out = result.stdout.decode("utf-8", "replace")
        if result.returncode == 0:
            print("    pass  (%d cases)" % out.count("pass  "))
        else:
            failures.append("the skip-past-small-changes checks failed")
            print(out)

        print("[7g] rollback goes back to the last choice, and further")
        result = subprocess.run(
            [python, "-I", "-B", os.path.join(HERE, "check_rollback.py"), game],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
        out = result.stdout.decode("utf-8", "replace")
        if result.returncode == 0:
            print("    pass  (%d cases)" % out.count("pass  "))
        else:
            failures.append("the rollback checks failed")
            print(out)

        print("[7f] the gallery switch unlocks in menus and writes nothing")
        result = subprocess.run(
            [python, "-I", "-B", os.path.join(HERE, "check_gallery.py"), game],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
        out = result.stdout.decode("utf-8", "replace")
        if result.returncode == 0:
            print("    pass  (%d cases)" % out.count("pass  "))
        else:
            failures.append("the gallery switch checks failed")
            print(out)

        # --- 8d. no rollback-tracked containers in long-lived code --------
        print("[7d] long-lived caches use untracked containers")
        fixes_text = io.open(os.path.join(TOOLKIT, "game_fixes.rpy"),
                             encoding="utf-8").read()
        bad = []
        for chunk in fixes_text.split("init 999 python:")[1:]:
            if not any(tag in chunk for tag in TRACKED_BLOCKS):
                continue
            for line in chunk.split("\n"):
                code = line.split("#", 1)[0]
                if not code.strip() or code.lstrip().startswith(('"', "'")):
                    continue
                if TRACKED.search(code):
                    bad.append(line.strip())
        if bad:
            failures.append("%d tracked container(s) in index/search code"
                            % len(bad))
            for line in bad[:12]:
                print("    FAIL  %s" % line)
        else:
            print("    pass")

        # --- 7. the helpers the screens call actually exist --------------
        print("[8] game_fixes.rpy defines the helpers the screens call")
        fixes_path = os.path.join(TOOLKIT, "game_fixes.rpy")
        try:
            with open(fixes_path, "rb") as f:
                fixes = f.read().decode("utf-8", "replace")
        except Exception as e:
            fixes = ""
            failures.append("could not read game_fixes.rpy: %s" % e)
        for helper in HELPERS:
            if ("def %s(" % helper) in fixes:
                print("    pass  %s" % helper)
            else:
                failures.append("game_fixes.rpy has no %s()" % helper)
                print("    FAIL  game_fixes.rpy has no %s()" % helper)
        # --- 9b. the compiled helper loads on Ren'Py 7 too ---------------
        # This one needs the BUILT archive: the helper is compiled into it by
        # build_rpa.py and is not in the URM archive the tweaks are read from.
        print("[10] the compiled helper loads on Ren'Py 7 as well as 8")
        built = os.path.join(TOOLKIT, "dist", "0x52_URM.rpa")
        if not os.path.exists(built):
            print("    skip  no build yet - run build_rpa.py first")
        else:
            result = subprocess.run(
                [python, "-I", "-B", os.path.join(HERE, "check_rpyc7.py"),
                 game, os.path.abspath(built)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
            out = result.stdout.decode("utf-8", "replace")
            if result.returncode == 0:
                for line in out.splitlines():
                    if line.startswith("pass"):
                        print("    %s" % line)
            else:
                failures.append("the helper cannot load on Ren'Py 7")
                print(out)

        # --- 3. the patched screens parse -------------------------------
        patched = os.path.join(work, "patched")
        os.makedirs(patched)
        for name in screens:
            with open(os.path.join(patched, os.path.basename(name)), "wb") as f:
                f.write(contents[name])
        ok, out = parse_screens(
            python, game,
            [os.path.join(patched, os.path.basename(n)) for n in screens])
        print("[9] the patched screens parse")
        if ok:
            print("    pass  (%d files)" % len(screens))
        else:
            failures.append("the patched screens do not parse")
            print(out)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print()
    if failures:
        print("%d FAILED" % len(failures))
        for item in failures:
            print("  - %s" % item)
        return 1
    print("all passed")
    return 0
if __name__ == "__main__":
    sys.exit(main(sys.argv))
