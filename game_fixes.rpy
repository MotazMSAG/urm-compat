# Small compatibility fixes for URM, applied inside URM's own archive.
#
# Both of these are guarded: on a game that does not have the problem they do
# nothing at all. They run at a late init priority so they see the game's
# final state, and before screens are prepared.


init 999 python:

    # ------------------------------------------------------------------
    # A game that defines its own EndReplay
    # ------------------------------------------------------------------
    #
    # Ren'Py's EndReplay is a screen action class taking an optional `confirm`
    # argument, and URM's watchpanel uses it as `action EndReplay(False)`.
    #
    # Some games define a plain zero-argument helper of the same name in the
    # store, which replaces Ren'Py's. URM's screen then fails to prepare with
    # "EndReplay() takes 0 positional arguments but 1 was given", and the game
    # will not start with URM installed.
    #
    # The shim makes the name work for both callers: no argument keeps doing
    # whatever the game's helper did, an argument gives back a real action.

    if not isinstance(EndReplay, type) and not getattr(EndReplay, "urm_shim", False):

        _urm_game_end_replay = EndReplay

        class _URMEndReplay(Action, DictEquality):
            """
            Stands in for Ren'Py's EndReplay action.
            """

            def __init__(self, confirm=True):
                self.confirm = confirm

            def __call__(self):
                renpy.end_replay()

        def EndReplay(confirm=None):
            if confirm is None:
                return _urm_game_end_replay()

            return _URMEndReplay(confirm)

        EndReplay.urm_shim = True


    # ------------------------------------------------------------------
    # A game that redirects every hyperlink
    # ------------------------------------------------------------------
    #
    # Ren'Py routes a link by looking its protocol up in
    # config.hyperlink_handlers; URM registers its variable and label editors
    # as the "URMVarDialog" and "URMLabelDialog" protocols.
    #
    # A game that sets config.hyperlink_callback - commonly to open its Patreon
    # or Discord link in a browser - makes renpy/common/00compat replace the
    # whole style.default.hyperlink_functions tuple with
    # (config.hyperlink_styler, config.hyperlink_callback,
    # config.hyperlink_focus). That discards Ren'Py's own hyperlink_function,
    # the only thing that consults config.hyperlink_handlers, so every link in
    # the game goes to webbrowser.open() whatever its protocol - and clicking a
    # variable in URM asks the OS to find an application for a "urmvardialog:"
    # link.
    #
    # Only games that set that callback are affected, so this leaves everything
    # alone unless one has. Running at init means the style tuple is set before
    # styles are built, so no rebuild is needed; and the translation system
    # snapshots styles after init, so changing the language keeps this too.

    _urm_game_hyperlink_callback = getattr(config, "hyperlink_callback", None)

    # Bracketed, not a backslash continuation: Ren'Py's lexer does not join a
    # backslash followed by CRLF, so a file saved with Windows line endings
    # would orphan the next line and fail to parse.
    if (_urm_game_hyperlink_callback is not None
            and not getattr(_urm_game_hyperlink_callback, "urm_shim", False)):

        def _urm_split(target):

            if ":" not in target:
                default_protocol = getattr(
                    config, "hyperlink_protocol", "call_in_new_context")
                target = default_protocol + ":" + target

            protocol, _, value = target.partition(":")

            return target, protocol, value

        def _urm_styler(target):
            return style.hyperlink_text

        def _urm_dispatch(target):

            target, protocol, value = _urm_split(target)

            handlers = getattr(config, "hyperlink_handlers", None) or { }

            if protocol in handlers:
                return handlers[protocol](value)

            return _urm_game_hyperlink_callback(target)

        _urm_dispatch.urm_shim = True

        def _urm_sensitive(target):

            target, protocol, value = _urm_split(target)

            table = getattr(config, "hyperlink_sensitive", None) or { }

            if protocol not in table:
                return True

            return table[protocol](value)

        # Covers 00compat copying this into the style tuple on a later pass.
        config.hyperlink_callback = _urm_dispatch

        # Ren'Py's tuple is (styler, clicked, focus, sensitive). Keep the
        # arity: text.py indexes 2 for focus and 3 for sensitive.
        style.default.hyperlink_functions = (
            _urm_styler, _urm_dispatch,
            getattr(config, "hyperlink_focus", None), _urm_sensitive)


# ---------------------------------------------------------------------------
# What a branch tests, and what it changes - as cards
# ---------------------------------------------------------------------------
#
# URM's notification reports the first if-statement ahead of the cursor and
# stops there. When that statement has no else, not matching it does not mean
# "the other listed path" - control falls straight out of it into whatever
# comes next, which is often another if. So "1 options" can really be a chain
# of gates ending in a return, and none of that is on screen.
#
# Showing it was the easy half. The hard half was that earlier versions drew
# the effects as source code, and source code contains its own if/else - so a
# nested condition inside an effect looked exactly like the gate's own
# condition. No marker column fixes that, because the two things really are
# the same kind of text. Four changes make them different kinds of thing:
#
#   * the gate's condition is drawn bare - no leading "if", no trailing ":" -
#     so the token that caused the collision is never on screen twice;
#   * nested control flow is not drawn as code at all. A surviving test is
#     demoted to its own row reading "only if <cond>" under the statement it
#     guards;
#   * every row carries a 24px icon, and the icon fonts map only 0-9, _ and
#     a-z, so no colorize() output can ever put a glyph in that column;
#   * the screen draws a gate as a lighter band between two rules, with its
#     effects on a darker fill below. The rhythm never varies, which is why
#     the effect list here is guaranteed non-empty.
#
# Effects come from the arm's own AST, not from CodeView.nodesToCode: that
# drops every node after a Jump, shows nothing inside a While or a nested
# Menu, strips lines mentioning renpy./ui., and indents the first line of any
# block nested two deep by 4*(2n-1) spaces rather than 4*n.
#
# Only three reductions are applied, because only these three can be shown to
# be true (see _urm_reduce). Anything hidden is counted and reported as
# "+N more", never dropped silently.
#
# Nothing here raises: it all runs while the overlay is being drawn.

init 999 python:

    _URM_MAX_GATES = 4
    _URM_MAX_ROWS = 6
    _URM_MAX_TOTAL_ROWS = 12
    _URM_MAX_GUARD_CHARS = 18
    _URM_MAX_DEPTH = 3

    # Material Icons, from the font behind style_suffix 'icon'. That style is
    # `is x52URM_text` with no hover_font, so these do not change face when the
    # pointer enters the notification - unlike 'icon_button_text', which swaps
    # the Outlined face for the Solid one.
    _URM_ICON_LIVE = u""       # done (a tick; 'check' is U+E5CA)
    _URM_ICON_DEAD = u""       # close
    _URM_ICON_UNKNOWN = u""    # remove, a plain dash
    _URM_ICON_EFFECT = u""     # arrow_right_alt
    _URM_ICON_GUARD = u""      # subdirectory_arrow_right

    def _urm_colour(name):

        try:
            return getattr(x52URM.Theme.colors, name)
        except Exception:
            return None

    # Ren'Py 7 runs on Python 2, where a theme colour may be a unicode rather
    # than a str. Checking against str alone would reject every colour there
    # and quietly drop the markers back to plain text.
    # Inside a Ren'Py 7 store, `str` is Ren'Py's compat str - unicode - but
    # Python 2's parser hands back string literals as byte strings. So text
    # types come from the real builtins, never from the store's names.
    try:
        import __builtin__ as _urm_builtins
        _URM_TEXT = (_urm_builtins.str, _urm_builtins.unicode)
    except ImportError:
        _URM_TEXT = (str,)

    def _urm_hex(value):
        """
        A colour only if it really is one.

        ThemeProvider.__getattr__ has no final else, so a name it does not
        know comes back as None rather than raising. "{color=None}" would be
        drawn literally, so anything that is not a hex string is refused here.
        """

        if isinstance(value, _URM_TEXT) and value.startswith("#"):
            return value

        return None

    def _urm_rgb(value):

        value = _urm_hex(value)

        if not value:
            return None

        digits = value[1:]

        if len(digits) in (3, 4):
            digits = "".join(c + c for c in digits)

        if len(digits) < 6:
            return None

        try:
            return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            return None

    def _urm_luminance(rgb):

        channels = []

        for raw in rgb:
            c = raw / 255.0
            channels.append(c / 12.92 if c <= 0.03928
                            else ((c + 0.055) / 1.055) ** 2.4)

        return (0.2126 * channels[0] + 0.7152 * channels[1]
                + 0.0722 * channels[2])

    def _urm_contrast(one, two):
        """WCAG contrast, or 0.0 when either colour cannot be read."""

        a = _urm_rgb(one)
        b = _urm_rgb(two)

        if a is None or b is None:
            return 0.0

        la = _urm_luminance(a)
        lb = _urm_luminance(b)

        if la < lb:
            la, lb = lb, la

        return (la + 0.05) / (lb + 0.05)

    def _urm_signal(kind):
        """
        A colour for the live/dead mark that is readable on the card.

        successText and errorText are a fixed pale-background/dark-text pair
        meant for URM's message bars, so one half of each is unreadable on a
        given fill. Which half depends on the theme's actual colours, not on
        Theme.isDark: on Traffic light the "dark" flag and the real fills
        disagree, and the mark came out at 2.3:1. So both halves are measured
        against the fill the card really paints, and if neither clears 3:1 the
        mark falls back to the theme's own text colour, which by construction
        is readable there.
        """

        try:
            fill = _urm_colour("buttonBgHover")

            best = None
            ratio = 0.0

            for half in ("Bg", "Text"):
                candidate = _urm_hex(_urm_colour(kind + half))
                if candidate is None:
                    continue
                score = _urm_contrast(candidate, fill)
                if score > ratio:
                    best, ratio = candidate, score

            if best is not None and ratio >= 3.0:
                return best
        except Exception:
            pass

        return None

    def _urm_tint(text, colour):

        if colour:
            return "{color=%s}%s{/color}" % (colour, text)

        return text

    # Variables and labels in the cards are clickable, the same way they are
    # in URM's own code view: colorize wraps each one in an {a=URMVarDialog:}
    # or {a=URMLabelDialog:} hyperlink, and URM registers both protocols in
    # config.hyperlink_handlers when it loads (codeview.rpy:76-77).
    #
    # This works inside the notification's button because a Button hands an
    # event to its child before running its own action (behavior.py, Button
    # .event: `rv = super(Button, self).event(...)`, returning early if the
    # child claims it), and a Text carrying an {a=} tag registers a focus
    # rectangle per link (text.py, `rv.add_focus(self, hyperlink, ...)`) and
    # fires the handler itself on a click.
    #
    # Which rectangle wins where the button's and the link's overlap is
    # decided in focus_at_point, which lives in the compiled render module -
    # so if a future Ren'Py gives the button priority, clicking a variable
    # just opens the paths dialog, which is what the button does anyway.
    # Nothing breaks either way; set this to False to go back to plain text.
    _URM_CLICKABLE = True

    def _urm_colorize(code):
        """
        One statement, with URM's own syntax colouring.

        evaluateConditions stays off: it appends URM's "# X - Condition not
        met" comment, which belongs in the code dialog and not on a card whose
        icon already says the same thing. colorize() escapes braces itself, so
        nothing here may escape them again.

        colorize can leak its internal URMTKN placeholder when a tokenised
        name is followed by an open paren; that is worse than no colour, so it
        falls back to plain escaped text.
        """

        try:
            out = x52URM.CodeView.colorize(
                code, interactiveVariables=_URM_CLICKABLE,
                interactiveLabels=_URM_CLICKABLE,
                evaluateConditions=False)

            if out and "URMTKN" not in out:
                return out
        except Exception:
            pass

        return (code or "").replace("{", "{{")

    def _urm_words(text):
        """Our own prose: italic, so it never reads as the game's code."""

        return "{i}%s{/i}" % text.replace("{", "{{")

    def _urm_truth(expression):
        """
        Whether a condition holds right now, or None if that cannot be said.

        BaseException is caught, not Exception: this runs while the overlay is
        being built, and a game condition that calls sys.exit would otherwise
        surface as Ren'Py's exception screen rather than a quiet unknown.
        """

        try:
            return bool(eval(str(expression), renpy.store.__dict__))
        except BaseException:
            return None

    def _urm_is_condition(cond):
        """
        True when the author wrote this test.

        Ren'Py synthesises the else arm of an if-statement as a plain string
        "True"; a condition the author typed is an ast.PyExpr, which subclasses
        str. Comparing the text to "True" would therefore mistake a real
        `if True:` gate for an else.
        """

        try:
            return isinstance(cond, renpy.ast.PyExpr)
        except Exception:
            return True

    def _urm_clip(text, limit):

        if len(text) <= limit:
            return text

        # U+2026 is present in Roboto-Regular; U+2192 and the box-drawing
        # characters are not, which is why none of them appear in this file.
        return text[:limit - 1] + u"…"

    # ------------------------------------------------------------------
    # What an arm actually changes
    # ------------------------------------------------------------------

    def _urm_statement(node):
        """One AST node as one line of plain text, or None to ignore it."""

        if isinstance(node, renpy.ast.Jump):
            if getattr(node, "expression", False):
                return "jump to a computed label"
            return "jump %s" % node.target

        if isinstance(node, renpy.ast.Call):
            if getattr(node, "expression", False):
                return "call a computed label"
            return "call %s" % node.label

        if isinstance(node, renpy.ast.Return):
            return "return"

        if isinstance(node, renpy.ast.UserStatement):
            try:
                head = node.parsed[0][0]
            except Exception:
                head = None
            if head in ("show", "hide", "call"):
                return node.line.strip()

        return None

    def _urm_idempotent(text):
        """
        Whether running this twice is the same as running it once.

        This is what decides when a duplicate may be dropped. A jump or a call
        leaves the block, and a plain assignment to a value overwrites. An
        augmented assignment or a bare function call does not: `love += 1`
        drawn once for code that runs it ten times is a false statement about
        the game, and that was the single most frequent falsehood in the first
        version of this file.
        """

        if text.startswith("jump ") or text.startswith("call ") or text == "return":
            return True

        head, sep, tail = text.partition("=")

        if not sep or tail.startswith("="):
            return False

        head = head.strip()

        if not head or not (head[0].isalpha() or head[0] == "_"):
            return False

        for ch in head:
            if not (ch.isalnum() or ch in "._"):
                return False

        return True

    def _urm_python_lines(node, dropped):
        """
        The assignments in a python block, without its own control flow.

        A `python:` block is stored verbatim, so its body can contain if/for/
        while/def lines. Those are counted rather than shown: drawing them
        would put exactly the kind of text back on screen that this whole
        design removes.
        """

        out = []

        try:
            source = node.code.source
        except Exception:
            return out

        for line in (source or "").split("\n"):
            stripped = line.strip()

            if not stripped or stripped.startswith("#"):
                continue

            if line[:1] in (" ", "\t") or stripped.endswith(":"):
                dropped[0] += 1
                continue

            out.append(stripped)

        return out

    def _urm_flatten(nodes, guards=(), depth=0, dropped=None):
        """
        An arm's nodes as (guards, text) records, innermost guard last.

        A nested if does not produce a line of code - it produces a guard on
        the records inside it, which the screen draws as its own "only if"
        row. That is what keeps a nested test from looking like a gate.
        """

        if dropped is None:
            dropped = [0]

        records = []

        for node in (nodes or []):

            if isinstance(node, renpy.ast.If):

                if depth >= _URM_MAX_DEPTH:
                    dropped[0] += 1
                    continue

                arms = []

                for cond, inner in (getattr(node, "entries", None) or []):
                    if _urm_is_condition(cond):
                        guard = "only if " + _urm_clip(
                            str(cond), _URM_MAX_GUARD_CHARS)
                    else:
                        guard = "otherwise"

                    arms.append((
                        guard,
                        _urm_flatten(inner, guards + (guard,),
                                     depth + 1, dropped),
                        _urm_is_condition(cond),
                    ))

                records.extend(_urm_lift(node, arms, guards))
                continue

            if isinstance(node, renpy.ast.Python):
                for line in _urm_python_lines(node, dropped):
                    records.append((guards, line))
                continue

            text = _urm_statement(node)

            if text is not None:
                records.append((guards, text))

        return records

    def _urm_lift(node, arms, guards):
        """
        L1 - the only merge that cannot state a falsehood.

        When an if has a real else arm, every arm runs some code, so anything
        every arm does, the if does. If all of them do exactly the same thing,
        that thing is unconditional and the guards come off. This is the
        common `if A: f() else: f()` shape.

        "Exactly the same thing" has to mean the same statements under the
        same guards, not merely the same statement texts. An earlier version
        compared texts alone and assigned the outer guards to every lifted
        row, so an arm holding three mutually exclusive jumps - each under its
        own nested test - was drawn as three unconditional jumps. A player
        reading that picks a path believing it leads somewhere it does not.
        So any row carrying a guard deeper than its own arm blocks the lift.
        """

        exhaustive = any(not isCond for _guard, _rows, isCond in arms)

        if exhaustive and arms:
            keys = []

            for arm_guard, rows, _isCond in arms:
                own = tuple(guards) + (arm_guard,)

                if any(tuple(g) != own for g, _t in rows):
                    keys = []
                    break

                keys.append(tuple(text for _g, text in rows))

            if keys and keys[0] and all(k == keys[0] for k in keys):
                return [(guards, text) for text in keys[0]]

        out = []
        for _guard, rows, _isCond in arms:
            out.extend(rows)

        return out

    def _urm_reduce(records):
        """
        L2 and L3, and an honest count of what they removed.

        Both only ever remove a row that another row already accounts for, and
        both are now limited to statements where that is actually true. A
        repeated `love += 1` is not a duplicate of itself - it is ten points of
        love - so repeats are collapsed into one row carrying a multiplier
        rather than silently thrown away.

        Returns (records, removed) where a record is (guards, text, count) and
        removed is how many rows were dropped outright, for the "+N more" tally.
        """

        plain = set(text for guards, text in records if not guards)

        removed = 0
        order = []
        index = {}

        for guards, text in records:

            # L2: a guarded copy of something that also happens unguarded,
            # and only when running it twice would change nothing.
            if guards and text in plain and _urm_idempotent(text):
                removed += 1
                continue

            key = (guards, text)

            if key in index:
                # L3: the same statement under the same guards. Idempotent
                # ones collapse; the rest keep a count, because the number of
                # times they run is the whole point of them.
                if _urm_idempotent(text):
                    removed += 1
                else:
                    index[key][2] += 1
                continue

            entry = [guards, text, 1]
            index[key] = entry
            order.append(entry)

        return [(g, t, n) for g, t, n in order], removed

    def _urm_effects(nodes):
        """
        The rows for one arm: guaranteed non-empty, and never half a record.

        A record is its statement row plus one row per guard. Those are drawn
        together or not at all - a guard row stranded from its statement, or a
        statement whose guard row fell off the bottom, would promote a
        conditional change to an unconditional one. The overflow row is
        budgeted for before the loop rather than squeezed in afterwards, so
        the count it reports is never short.
        """

        dropped = [0]
        broke = False

        try:
            records, removed = _urm_reduce(_urm_flatten(nodes, dropped=dropped))
        except BaseException:
            records, removed, broke = [], 0, True

        hidden = dropped[0] + removed

        # Reserve the overflow row up front if anything might not fit.
        room = _URM_MAX_ROWS
        if hidden or sum(1 + len(g) for g, _t, _n in records) > room:
            room -= 1

        rows = []

        for index, (guards, text, count) in enumerate(records):

            needed = 1 + len(guards)

            if len(rows) + needed > room:
                hidden += sum(1 + len(g) for g, _t, _n in records[index:])
                break

            body = _urm_colorize(text)

            if count > 1:
                body += _urm_words("  x%d" % count)

            rows.append((_URM_ICON_EFFECT, body))

            for guard in guards:
                if guard == "otherwise":
                    rows.append((_URM_ICON_GUARD, _urm_words("otherwise")))
                else:
                    rows.append((
                        _URM_ICON_GUARD,
                        _urm_words("only if ")
                        + _urm_colorize(guard[len("only if "):]),
                    ))

        if hidden:
            rows.append((_URM_ICON_GUARD, _urm_words("+%d more" % hidden)))

        if not rows:
            if broke:
                # An internal failure must not look like a branch that simply
                # changes nothing - that is a confident lie.
                rows.append((_URM_ICON_GUARD,
                             _urm_words("could not read this branch")))
            else:
                # Honest: most branches in a real game are dialogue only, and
                # dialogue changes nothing URM tracks.
                rows.append((_URM_ICON_EFFECT,
                             _urm_words("no tracked changes")))

        return rows

    # ------------------------------------------------------------------
    # The chain of gates
    # ------------------------------------------------------------------

    def _urm_tail(node):
        """Where control ends up once every gate has been missed."""

        try:
            for _ in range(x52URM.PathDetection.lookAheadLimit):

                if node is None:
                    return ""

                text = _urm_statement(node)
                if text is not None:
                    return text

                if x52URM.PathDetection.nodeIsBlocking(node):
                    return ""

                node = x52URM.PathDetection.nextNode(node)
        except Exception:
            pass

        return ""

    def _urm_chain():
        """
        Every gate ahead of the cursor, in the order they are tested.

        The whole chain is collected before any card is built, so the summary
        can say how many gates there really are even when the card list is
        capped.
        """

        steps = []

        # Parallel to steps: (if-statement, arm index) for each, or (None, -1)
        # for the fall-through tail. Kept on URM's constant store, so the
        # force-a-path buttons can name the exact arm without walking again.
        meta = python_list()
        x52URM.Var._urmChainMeta = meta

        detected = x52URM.PathDetection.nextIfStatement

        if not detected:
            return steps

        node = detected[0]

        for _ in range(_URM_MAX_GATES + 4):

            closed = False

            for arm, (cond, block) in enumerate(getattr(node, "entries", None) or []):

                if not _urm_is_condition(cond):
                    steps.append(("else", None, block))
                    meta.append((node, arm))
                    closed = True
                    break

                steps.append(("gate", cond, block))
                meta.append((node, arm))

            if closed:
                return steps

            following = x52URM.PathDetection.nextNode(node)
            node = None
            ahead = following

            for _ in range(x52URM.PathDetection.lookAheadLimit):
                if ahead is None:
                    break
                if isinstance(ahead, renpy.ast.If):
                    node = ahead
                    break
                if x52URM.PathDetection.nodeIsBlocking(ahead):
                    break
                ahead = x52URM.PathDetection.nextNode(ahead)

            if node is None:
                tail = _urm_tail(following)
                if tail:
                    steps.append(("tail", None, tail))
                    meta.append((None, -1))
                return steps

        return steps

    def _urm_fallback_icon(fired, unknown, success, error):
        """
        The mark on the "nothing above matches" card.

        It only runs if every gate above it missed - so if we could not
        evaluate one of those gates, we cannot claim this one runs either.
        """

        if fired:
            return _urm_tint(_URM_ICON_DEAD, error)

        if unknown:
            return _URM_ICON_UNKNOWN

        return _urm_tint(_URM_ICON_LIVE, success)

    def _urm_summary(gates, truncated, live, unknown):

        count = "%d+" % gates if truncated else "%d" % gates
        word = "gate" if gates == 1 and not truncated else "gates"

        if unknown:
            return "%s %s, cannot tell which" % (count, word)

        if live:
            return "%s %s, #%d runs" % (count, word, live)

        return "%s %s, none match" % (count, word)

    def urm_path_cards():

        try:
            steps = _urm_chain()

            if not steps:
                return ("", [])

            success = _urm_signal("success")
            error = _urm_signal("error")

            # The closing card - what happens when nothing matches - is the
            # one a reader needs most, so it gets a reserved slot rather than
            # being pushed off the end by the gates above it.
            closes = steps and steps[-1][0] in ("else", "tail")
            budget = _URM_MAX_GATES - (1 if closes else 0)

            cards = []
            number = 0
            gates = 0
            shown = 0
            live = 0
            unknown = False
            fired = False
            skipped = False

            for kind, cond, payload in steps:

                # Only a real test is a gate. The fall-through card is what
                # happens when none of them match, not one of them.
                if kind == "gate":
                    gates += 1

                    number += 1

                    truth = None if fired else _urm_truth(cond)

                    if truth is None and not fired:
                        unknown = True

                    if truth is True and not fired and not unknown:
                        fired = True
                        live = number
                        icon = _urm_tint(_URM_ICON_LIVE, success)
                    elif unknown and not fired:
                        icon = _URM_ICON_UNKNOWN
                    else:
                        icon = _urm_tint(_URM_ICON_DEAD, error)

                    if shown >= budget:
                        skipped = True
                        continue

                    shown += 1
                    cards.append((icon, "%d" % number,
                                  _urm_colorize(str(cond)),
                                  _urm_effects(payload)))

                elif kind == "else":
                    icon = _urm_fallback_icon(fired, unknown, success, error)
                    fired = True
                    cards.append((icon, "",
                                  _urm_words("nothing above matches"),
                                  _urm_effects(payload)))

                else:
                    icon = _urm_fallback_icon(fired, unknown, success, error)
                    cards.append((icon, "",
                                  _urm_words("nothing above matches"),
                                  [(_URM_ICON_EFFECT, _urm_colorize(payload))]))

            if not cards:
                return ("", [])

            return (_urm_summary(gates, skipped, live, unknown), cards)

        except BaseException:
            return ("", [])

    def _urm_choice_nodes(choice):
        """
        A choice's own AST block.

        URM keeps the (text, condition, block) tuple on a name-mangled
        attribute. It is the only private field this file touches, so it is
        guarded and falls back to the text URM already exposes.
        """

        try:
            return choice._m1_choices__choice[2]
        except Exception:
            return None

    def urm_choice_cards():

        try:
            error = _urm_signal("error")
            success = _urm_signal("success")

            cards = []
            available = 0

            choices = x52URM.Choices.currentChoices or []

            for index, choice in enumerate(choices):

                condition = getattr(choice, "condition", None) or "True"
                open_now = (not _urm_is_condition(condition)) or (
                    _urm_truth(condition) is True)

                if open_now:
                    available += 1

                if len(cards) >= _URM_MAX_GATES:
                    continue

                if not _urm_is_condition(condition):
                    head = _urm_words("always")
                else:
                    head = _urm_colorize(str(condition))

                icon = (_urm_tint(_URM_ICON_LIVE, success) if open_now
                        else _urm_tint(_URM_ICON_DEAD, error))

                nodes = _urm_choice_nodes(choice)

                if nodes is None:
                    effects = [(_URM_ICON_EFFECT, _urm_colorize(line))
                               for line in (getattr(choice, "code", "")
                                            or "").split("\n")
                               if line.strip()][:_URM_MAX_ROWS]
                    if not effects:
                        effects = [(_URM_ICON_EFFECT,
                                    _urm_words("no tracked changes"))]
                else:
                    effects = _urm_effects(nodes)

                cards.append((icon, "%d" % (index + 1), head, effects))

            if not cards:
                return ("", [])

            # The count is the menu's, not the card list's - URM prints its own
            # "[N] hidden" line directly above this and the two must agree.
            total = len(choices)
            word = "choice" if total == 1 else "choices"
            more = total - len(cards)
            extra = _urm_words(", %d not shown" % more) if more else ""

            return ("%d %s, %d open%s" % (total, word, available, extra), cards)

        except BaseException:
            return ("", [])


# ---------------------------------------------------------------------------
# Search: dotted names, depth, value operators, and the cost of getting there
# ---------------------------------------------------------------------------
#
# URM's search is good at what it does and blind to one whole shape of game.
# Four things are wrong with it, and the first two are invisible rather than
# merely slow:
#
#   * a dotted query can never match. classes/search.rpy:227 compares the one
#     path SEGMENT against the query - matchStringValue(varName, query), not
#     fullVarName - so "mc.str" is tested against "mc" and then against "str"
#     and matches neither. Bare "str" finds mc.str, the exact name does not.
#
#   * object recursion stops at one level. The two descent branches
#     (search.rpy:206 and :216) are guarded by `not parentVarName`, which reads
#     "only descend when standing on a bare store variable". Once inside `mc`,
#     `inventory` is matched by name and never entered, so mc.inventory.gold
#     cannot be found by any query. Games that nest - mc.stats.corruption,
#     player.relationships.sarah.love - hide most of themselves from search.
#
#   * value search walks the store twice. matchVarName guards
#     `fullVarName == 'store'` at :181 because `store` is a name in the store
#     pointing at the store itself; matchVarValue has no such guard, and
#     'store' passes isSupportedVarType, so every variable is reported once
#     bare and once as store.X.
#
#   * every type lookup is an eval of a source string. Var.getVarType
#     (classes/vars.rpy:408) does eval(varName, renpy.store.__dict__), which
#     compiles the string afresh each call, and the descent branches eval the
#     same name two or three times in one pass. The count per search is
#     roughly N_names + 2*N_objects + N_attrs.
#
# What is NOT wrong, having checked: int/float queries already cross-match
# (getValType tests bool before int, so a boolean never reaches the int
# branch, and float('3') == 3.0 holds), and basestring comes from Ren'Py's own
# compat module rather than URM, so it is defined under both engines.
#
# The contract for everything below:
#
#   * nothing here may make an unasked-for search slower. The optimisations
#     return identical results for less work and are unconditional; anything
#     that scans MORE to find more is off by default and switched on by the
#     user - urmcSearchDepth, or the Deeper button, which pays per click.
#   * every patch is wrapped in its own try. A failure leaves URM's own method
#     in place, so the worst case is URM 2.6.2 behaving exactly as shipped.
#   * URM's private names are found by suffix rather than written out. The
#     compiled archive mangles them to _m1_<file>__<name>, which is a build
#     artefact, not something to depend on.

init 999 python:

    # Four levels is the point past which a result list stops being readable,
    # whatever the cost; the setting is clamped to it rather than trusted.
    _URMC_DEPTH_CAP = 4
    _URMC_PATH_LIMIT = 20000

    # Parsed paths are cached on Var, which lives in URM's `_constant` store,
    # so the cache is not written into saves. That alone is not enough: in a
    # store, dict, list and set are themselves rebound to the rollback-tracked
    # Revertable kinds (renpy/minstore.py:37-50), and [] / {} literals are
    # rewritten to them as well. A tracked cache is copied into the rollback
    # log on the first change of every interaction - 20,000 entries at a time.
    # So every container here that outlives one call is a python_dict,
    # python_list or python_set, the untracked originals minstore keeps.

    def _urmc_ident(word):
        """Is `word` a bare Python identifier?"""

        if not word:
            return False
        if not (word[0].isalpha() or word[0] == "_"):
            return False
        for char in word:
            if not (char.isalnum() or char == "_"):
                return False
        return True

    def _urmc_parse(name):
        """
        `name` as a walkable path, or None when it is an expression.

        ('a', attr) for a dotted step, ('k', key) for a subscript, with the
        store name first. Returning None for anything else is what keeps the
        eval fallback honest: a watched expression like len(items) is not a
        path and must still be evaluated.
        """

        length = len(name)
        if not length:
            return None

        end = 0
        while end < length and name[end] not in ".[":
            end += 1

        root = name[:end]
        if not _urmc_ident(root):
            return None

        parts = python_list((root,))
        index = end

        while index < length:
            char = name[index]

            if char == ".":
                index += 1
                end = index
                while end < length and name[end] not in ".[":
                    end += 1
                word = name[index:end]
                if not _urmc_ident(word):
                    return None
                parts.append(("a", word))
                index = end

            elif char == "[":
                end = name.find("]", index)
                if end < 0:
                    return None
                key = name[index + 1:end]
                if len(key) >= 2 and key[0] in "\"'" and key[-1] == key[0]:
                    parts.append(("k", key[1:-1]))
                elif key.isdigit():
                    parts.append(("k", int(key)))
                elif key[:1] == "-" and key[1:].isdigit():
                    parts.append(("k", int(key)))
                else:
                    return None
                index = end + 1

            else:
                return None

        return parts

    def _urmc_resolve(name):
        """
        (found, value) for a variable path, without eval.

        `found` is False both for a name that is not there and for one this
        cannot walk; the caller falls back to URM's own lookup for the second
        case, so the two never need telling apart here.
        """

        cache = x52URM.Var._urmcPaths

        try:
            parts = cache[name]
        except KeyError:
            parts = _urmc_parse(name)
            if len(cache) < _URMC_PATH_LIMIT:
                cache[name] = parts

        if parts is None:
            return (False, None)

        store = renpy.store.__dict__
        root = parts[0]

        if root not in store:
            return (False, None)

        value = store[root]

        for kind, key in parts[1:]:
            try:
                value = getattr(value, key) if kind == "a" else value[key]
            except Exception:
                return (False, None)

        return (True, value)

    def _urmc_join(parent, child, kind):
        """
        A child's full name. URM's own __getFullVarName asks getVarType what
        the parent is, which is one more lookup per child; the caller already
        knows, so it says.
        """

        if not parent:
            return child
        if kind == "dict":
            return parent + '["' + str(child) + '"]'
        return parent + "." + str(child)

    def _urmc_keys(value, kind):
        """The child names of a container, text keys only."""

        try:
            if kind == "dict":
                names = value.keys()
            else:
                names = value.__dict__.keys()
            return [key for key in names if isinstance(key, _URM_TEXT)]
        except Exception:
            return []

    def _urmc_num(text):
        """A number, or None. int first, so 3 stays 3 rather than 3.0."""

        text = text.strip()
        if not text:
            return None
        try:
            return int(text)
        except Exception:
            pass
        try:
            return float(text)
        except Exception:
            return None

    # Longest first: '>=' has to be tried before '>'.
    _URMC_OPS = (">=", "<=", "!=", "==", ">", "<")

    def _urmc_number(value, query):
        """
        Does a numeric variable satisfy the query?

        Equality is all URM offers, and equality is rarely what you want when
        hunting a stat. '>50', '<=10', '!=0' and '40..60' are read here; a
        query that is none of those is compared as before, so nothing that
        matched yesterday stops matching.
        """

        text = (query or "").strip()
        if not text:
            return False

        if ".." in text:
            low, _sep, high = text.partition("..")
            lower = _urmc_num(low)
            upper = _urmc_num(high)
            if lower is None or upper is None:
                return False
            if lower > upper:
                lower, upper = upper, lower
            return lower <= value <= upper

        for token in _URMC_OPS:
            if text.startswith(token):
                other = _urmc_num(text[len(token):])
                if other is None:
                    return False
                if token == ">=":
                    return value >= other
                if token == "<=":
                    return value <= other
                if token == "!=":
                    return value != other
                if token == "==":
                    return value == other
                if token == ">":
                    return value > other
                return value < other

        other = _urmc_num(text)
        return other is not None and value == other


# A second block, so a failure to read URM's internals leaves the first one's
# helpers defined and simply does not install anything.
init 999 python:

    def _urmc_private(cls, suffix):
        """URM's mangled attribute name for `suffix`, or None."""

        for key in vars(cls):
            if key.endswith(suffix):
                return key
        return None

    _urmc_installed = False

    try:
        _URMC_RESULTS = _urmc_private(x52URM.SearchClass, "__results")
        _urmc_matchstr = getattr(
            x52URM.SearchClass,
            _urmc_private(x52URM.SearchClass, "__matchStringValue"))
        _urmc_fullname = getattr(
            x52URM.SearchClass,
            _urmc_private(x52URM.SearchClass, "__getFullVarName"))

        _urmc_getValType = x52URM.Var.getValType
        _urmc_isSupported = x52URM.Var.isSupportedVarType
        _urmc_evalVarType = x52URM.Var.getVarType
        _urmc_namePath = x52URM.Var.namePath

        _urmc_orig_doSearch = x52URM.SearchClass.doSearch
        _urmc_orig_reset = x52URM.SearchClass.resetSearch

        if _URMC_RESULTS is None:
            raise AttributeError("SearchClass has no private results list")

        _urmc_ready = True
    except Exception as error:
        _urmc_ready = False
        print("URM+: leaving search as it ships (%s)" % (error,))


    def _urmc_maxDepth(search=None):
        """
        How many levels to walk: the setting, plus whatever the Deeper button
        has added to this search, clamped to the cap.
        """

        try:
            depth = int(x52URM.Settings.urmcSearchDepth)
        except Exception:
            depth = 1

        if search is not None:
            try:
                depth += int(getattr(search, "_urmcExtra", 0) or 0)
            except Exception:
                pass

        if depth < 1:
            return 1
        if depth > _URMC_DEPTH_CAP:
            return _URMC_DEPTH_CAP
        return depth

    def _urmc_visited(search):
        """The set of containers this search has already entered."""

        seen = getattr(search, "_urmcVisited", None)
        if seen is None:
            seen = python_set()
            search._urmcVisited = seen
        return seen

    def _urmc_container(varType, value, found):
        """
        'dict', 'object' or None - what this value's children are reached by.

        Lists are deliberately not containers here: their items have no names,
        which is why URM's name search never entered them either.
        """

        if not found:
            return None
        if varType == "dict":
            return "dict"
        if varType in ("string", "boolean", "int", "float"):
            return None
        try:
            if hasattr(value, "__dict__"):
                return "object"
        except Exception:
            pass
        return None

    def _urmc_type(full):
        """
        (found, value, varType) for a name, walking rather than evaluating and
        falling back to URM's eval only for names that are not plain paths.
        """

        found, value = _urmc_resolve(full)
        if found:
            return (True, value, _urmc_getValType(value))

        try:
            return (False, None, _urmc_evalVarType(full))
        except Exception:
            return (False, None, "unknown")

    def _urmc_hit(search, leaf, full, query):
        """
        Does this variable's name match?

        The leaf is tried first, which is URM's behaviour and keeps a bare
        "str" finding mc.str. The full dotted name is only tried when the
        query itself is dotted or subscripted, so this adds one string compare
        for queries that could not have matched at all before, and nothing
        otherwise. It costs no extra traversal, which is why it is not
        optional.
        """

        if _urmc_matchstr(search, leaf, query):
            return True

        if full != leaf and ("." in query or "[" in query):
            return _urmc_matchstr(search, full, query)

        return False


    def _urmc_matchVarName(search, varName, query, parentVarName=None,
                           _depth=0, _full=None):

        if not isinstance(varName, _URM_TEXT):
            return None

        try:
            settings = x52URM.Settings

            # Cheap string test before the type lookup. URM does it the other
            # way round (search.rpy:178 then :184), so every internal variable
            # was resolved and then discarded.
            if varName.startswith("_") and not settings.searchInternalVars:
                return None

            full = _full
            if full is None:
                full = _urmc_fullname(search, varName, parentVarName)

            if full == "store":
                return None

            if search.searchType == "labels":
                if _urmc_hit(search, varName, full, query):
                    return [x52URM.Var(full)]
                return None

            found, value, varType = _urmc_type(full)

            if varType == "unknown" and not settings.showUnsupportedVariables:
                return None

            if (varType not in ("persistent", "store", "unknown")
                    and not _urmc_isSupported(varType)):
                return None

            hit = _urmc_hit(search, varName, full, query)

            if full == "persistent":
                if not settings.searchPersistent:
                    return None
                return _urmc_descend(search, _urmc_matchVarName, full, value,
                                     "object", query, _depth, [])

            kind = _urmc_container(varType, value, found)

            if kind and settings.searchObjects and _depth < _urmc_maxDepth(search):
                # The container itself counts as a result when its own name
                # matched. URM records it as Var(varName) - the leaf - which is
                # the same thing only at depth 0.
                return _urmc_descend(search, _urmc_matchVarName, full, value,
                                     kind, query, _depth,
                                     [x52URM.Var(full)] if hit else [])

            return [x52URM.Var(full)] if hit else None

        except Exception as error:
            print('0x52: matchVarName failed for variable "{}". {}'.format(
                varName, error))


    def _urmc_matchVarValue(search, varName, query, parentVarName=None,
                            _depth=0, _full=None):

        if not isinstance(varName, _URM_TEXT):
            return None

        try:
            settings = x52URM.Settings

            if varName.startswith("_") and not settings.searchInternalVars:
                return None

            full = _full
            if full is None:
                full = _urmc_fullname(search, varName, parentVarName)

            # The guard matchVarName has and this did not. Without it every
            # variable is also reported as store.X, at double the cost.
            if full == "store":
                return None

            found, value, varType = _urmc_type(full)

            if varType == "persistent":
                if not settings.searchPersistent:
                    return None
                if _depth >= _urmc_maxDepth(search):
                    return None
                return _urmc_descend(search, _urmc_matchVarValue, full, value,
                                     "object", query, _depth, [])

            if not _urmc_isSupported(varType):
                return None

            if varType == "string":
                if _urmc_matchstr(search, value, query):
                    return [x52URM.Var(full)]
                return None

            if varType == "boolean":
                want = (query or "").strip().lower()
                if want not in ("true", "false"):
                    return None
                if bool(value) == (want == "true"):
                    return [x52URM.Var(full)]
                return None

            if varType in ("int", "float"):
                if _urmc_number(value, query):
                    return [x52URM.Var(full)]
                return None

            kind = _urmc_container(varType, value, found)

            if kind and settings.searchObjects and _depth < _urmc_maxDepth(search):
                return _urmc_descend(search, _urmc_matchVarValue, full, value,
                                     kind, query, _depth, [])

            return None

        except Exception as error:
            print('0x52: matchVarValue failed for variable "{}". {}'.format(
                varName, error))


    def _urmc_descend(search, matcher, full, value, kind, query, depth, found):
        """
        `matcher` over one container's children, one level down.

        The id() set holds what is on the stack right now, and the marker is
        dropped again on the way out. mc.game.player is mc is a common shape,
        and marking the whole search instead would be the wrong guard twice
        over: the depth cap already bounds the walk, and an object two store
        variables both point at would have its children scanned under
        whichever name came first and silently skipped under the other.
        """

        seen = _urmc_visited(search)
        marker = id(value)

        if marker in seen:
            return found or None

        seen.add(marker)
        out = python_list(found)

        try:
            for child in _urmc_keys(value, kind):
                hits = matcher(search, child, query, full, depth + 1,
                               _urmc_join(full, child, kind))
                if hits:
                    out.extend(hits)
        finally:
            seen.discard(marker)

        return out or None


    def _urmc_rank(name, query):
        """
        Sort key: exact leaf, then leaf prefix, then anything, then shortest.

        Results arrive in renpy.store.__dict__ order, which is arbitrary, so
        the thing you typed can sit anywhere in a hundred rows. Ordering an
        already-built list is one sort and changes nothing about what is in it.
        """

        low = (name or "").lower()
        leaf = low.rsplit(".", 1)[-1]

        if leaf == query or low == query:
            tier = 0
        elif leaf.startswith(query):
            tier = 1
        elif query in leaf:
            tier = 2
        else:
            tier = 3

        return (tier, len(low), low)


    def _urmc_after(search):
        """
        Rank the results, then say which level a further click would reach.

        Both are settled once, here, and read from the screen as a plain
        attribute. Working either of them out in a screen expression would put
        it on the redraw path, which is the exact cost this block exists to
        remove.
        """

        try:
            query = (search.searchQuery or "").strip().lower()
            results = search.results or []
            if query and len(results) > 1 and search.searchType != "values":
                setattr(search, _URMC_RESULTS,
                        sorted(results,
                               key=lambda var: _urmc_rank(var.name, query)))
        except Exception:
            pass

        try:
            if search.searchType == "labels":
                # Labels are a flat namespace; there is nothing under them.
                search.urmcNextDepth = 0
            else:
                current = _urmc_maxDepth(search)
                if current >= _URMC_DEPTH_CAP:
                    search.urmcNextDepth = 0
                else:
                    search.urmcNextDepth = current + 1
        except Exception:
            search.urmcNextDepth = 0


    def _urmc_doSearch(search):
        """URM's search, ranked, and back to the depth the settings ask for."""

        search._urmcVisited = python_set()
        search._urmcExtra = 0

        try:
            _urmc_orig_doSearch(search)
        finally:
            search._urmcVisited = python_set()
            _urmc_after(search)


    def _urmc_resetSearch(search, keepInputQuery=False):

        _urmc_orig_reset(search, keepInputQuery)

        search._urmcVisited = python_set()
        search._urmcExtra = 0
        search.urmcNextDepth = 0


    def _urmc_deepen(search):
        """
        The same query, one level deeper, paid for on click.

        An earlier version of this descended only into the containers already
        in the results, which sounded cheaper and was useless: searching
        "gold" in a game that keeps it in mc.inventory returns no containers
        at all, so there was nothing to open. The level has to be raised and
        the store walked again.

        That is still nothing until asked for - a search nobody deepens costs
        exactly what it did before - and the walk is this rather than a call
        back into URM's doSearch so that recursive search, which replaces the
        collection with the previous results, cannot turn "deeper" into
        "narrower".
        """

        try:
            query = search.searchQuery
            if not query:
                return

            if search.searchType == "labels":
                return

            before = _urmc_maxDepth(search)
            if before >= _URMC_DEPTH_CAP:
                return

            search._urmcExtra = int(getattr(search, "_urmcExtra", 0) or 0) + 1

            matcher = (_urmc_matchVarValue
                       if search.searchType == "values"
                       else _urmc_matchVarName)

            search._urmcVisited = python_set()
            results = python_list()

            for name in python_list(renpy.store.__dict__):
                hits = matcher(search, name, query)
                if hits:
                    results.extend(hits)

            # Only keep the deeper pass if it did not lose anything. A walk
            # that threw part way through would otherwise replace a good
            # result list with a short one.
            if len(results) >= len(search.results or []):
                setattr(search, _URMC_RESULTS, results)

            _urmc_after(search)

        except Exception as error:
            print("0x52: searching deeper failed. {}".format(error))

        finally:
            search._urmcVisited = python_set()


    def _urmc_namePath_get(self):
        """
        namePath, cached.

        It is two regex scans over the name, it is called by value, by
        nameShortened and by the results screen, and it cannot go stale: a
        Var's name is set in __init__ and never reassigned. That last part is
        why only this property is cached. varType, isExpandable and isSupported
        guard on hasattr(self, '__varType'), which never hits - the string
        literal is not name-mangled while the assignment is - and making them
        cache would freeze a type that the user can change from the editor
        two rows below.
        """

        cache = self.__dict__

        try:
            return cache["_urmcNamePath"]
        except KeyError:
            pass

        value = _urmc_namePath.fget(self)
        cache["_urmcNamePath"] = value
        return value


    # Registering a setting is one insert: Settings.__getattr__ and
    # __setattr__ look the name up in defaultValues on every read and write
    # (classes/settings.rpy:137,143,148) with no snapshot taken at
    # construction. The value lands in persistent.URMSettings, so it is per
    # save file, and both columns of the options table work on it unchanged.
    # Defaults are today's behaviour: depth 1 is URM's own one level, and the
    # quickmenu button starts hidden.
    #
    # This stands on its own, because the quickmenu button has nothing to do
    # with search and must not be lost if URM's search internals move.
    try:
        _urmc_defaults = x52URM.SettingsClass.defaultValues
        _urmc_defaults.setdefault("urmcSearchDepth", 1)
        _urmc_defaults.setdefault("quickmenuBtnSkipUnseen", False)
    except Exception as error:
        print("URM+: could not register settings (%s)" % (error,))


    if _urmc_ready:
        try:
            x52URM.Var._urmcPaths = python_dict()
            x52URM.Var.getVarType = staticmethod(
                lambda name: _urmc_type(name)[2])
            x52URM.Var.namePath = property(_urmc_namePath_get)

            x52URM.SearchClass.matchVarName = _urmc_matchVarName
            x52URM.SearchClass.matchVarValue = _urmc_matchVarValue
            x52URM.SearchClass.doSearch = _urmc_doSearch
            x52URM.SearchClass.resetSearch = _urmc_resetSearch
            x52URM.SearchClass.urmcDeepen = _urmc_deepen
            x52URM.SearchClass.urmcNextDepth = 0

            _urmc_installed = True

        except Exception as error:
            print("URM+: search upgrades not installed (%s)"
                  % (error,))


# ---------------------------------------------------------------------------
# Six things a player wanted and URM did not have
# ---------------------------------------------------------------------------
#
# Each one is a public helper in this store, or a method swapped on one of
# URM's classes. The screens that use them are guarded on the helper's own
# name, so a build whose zzz_urm_compat.rpyc did not compile for this engine
# draws URM's UI exactly as it ships.

init 999 python:

    # ------------------------------------------------------------------
    # Copy to clipboard
    # ------------------------------------------------------------------
    #
    # There is not one clipboard call anywhere in URM 2.6.2: a variable name,
    # a value, a condition and a file:line can only be retyped. Values are
    # less of a problem than they look - they land in an x52URM.Input, and
    # Ren'Py's Input already handles ctrl+C through its copypaste path
    # (display/behavior.py:1743) - so what is actually missing is the names,
    # which are never editable text.
    #
    # Ren'Py 7 and 8 both reach the clipboard through pygame_sdl2, which is
    # also registered under the name pygame; both are tried because which one
    # is importable from a store varies with how the game was built.

    def urm_copy(text):
        """Put `text` on the system clipboard and say so."""

        try:
            data = text if isinstance(text, bytes) else (text or u"").encode("utf-8")
        except Exception:
            return

        done = False

        for module in ("pygame_sdl2", "pygame"):
            try:
                scrap = __import__(module).scrap
                scrap.put(scrap.SCRAP_TEXT, data)
                done = True
                break
            except Exception:
                continue

        try:
            renpy.notify("Copied" if done else "This build has no clipboard")
        except Exception:
            pass


    # ------------------------------------------------------------------
    # Browse the whole store
    # ------------------------------------------------------------------
    #
    # URM can only show a variable you already found by name, or loaded from a
    # .urm file. If you do not know roughly what it is called, there is no way
    # in at all - which makes search the single entry point to every variable
    # in the game.
    #
    # Nothing new is needed to render it. Var.children already handles
    # varType 'store' (vars.rpy:361) and URM_objectVar already draws a paged,
    # expandable table of children with the breadcrumb above it, so the whole
    # feature is handing that screen a Var over the store itself.
    #
    # A list rather than a Var, so the screen can hand it straight to
    # expandObjectVars and an engine where this does not resolve gives an
    # empty browser instead of a crash.

    def urm_store_root():
        """[Var('store')], or [] if this engine will not expand it."""

        try:
            root = x52URM.Var("store")
            if root.isExpandable:
                return [root]
        except Exception:
            pass
        return []


    # ------------------------------------------------------------------
    # Remembered labels: a filter, and whether you have been there
    # ------------------------------------------------------------------
    #
    # The Labels tab paginates and sorts and nothing else, so with fifty
    # remembered labels the only way to find one is to click through pages.
    # It also cannot say whether you have already seen a label: the thumbnail
    # view colours by renpy.has_label, which is existence, not visited.

    def urm_labels(text):
        """The remembered labels narrowed by `text`, as [(name, props)]."""

        try:
            items = python_list(x52URM.LabelsStore.store.items())
        except Exception:
            return []

        needle = (text or u"").strip().lower()
        if not needle:
            return items

        found = python_list()

        for name, props in items:
            shown = u""
            try:
                shown = props.get("name") or u""
            except Exception:
                pass
            try:
                if needle in (name or u"").lower() or needle in shown.lower():
                    found.append((name, props))
            except Exception:
                continue

        return found

    def urm_seen(label):
        """
        True seen, False not seen, None when the engine cannot say.

        None covers a label that is not in this build at all, which is the
        common case for a save carried across an update - and it must not be
        drawn as "not seen", because that would read as missable content.
        """

        try:
            if not renpy.has_label(label):
                return None
            return bool(renpy.seen_label(label))
        except Exception:
            return None


    # ------------------------------------------------------------------
    # The gates the Path dialog does not show
    # ------------------------------------------------------------------
    #
    # PathDetection.statements is ifStatement[0].entries and stops there
    # (PathDetection.rpy:75), so the dialog lists the arms of one
    # if-statement. When that if has no else, not matching it falls straight
    # through to whatever check comes next, and those gates are invisible -
    # the same blind spot the notification cards already fixed with
    # _urm_chain.
    #
    # They are deliberately read-only. URM forces a path by rewriting the
    # chain up to the DETECTED node (PathDetection.rpy:160-178); a gate two
    # statements later is not that node, so a Select button there would not
    # work. Showing the rows without one is honest; showing one that silently
    # does nothing is not.

    def urm_later_gates():
        """[(icon, number, condition, effects)] for the gates after the first if."""

        out = python_list()
        for _i, icon, number, head, effects in urm_later_gate_rows():
            out.append((icon, number, head, effects))
        return out

    def urm_later_gate_rows():
        """
        [(row, icon, number, condition, effects)] for every gate after the
        if-statement the Path options table shows - the ones the script runs
        into when none of that table matches.

        This used to be "every card but the first", and the first if's own
        arms are cards too: the section repeated rows 2.. of the table. Each
        row now also remembers how to force it (urmf_force_later).
        """

        rows = python_list()
        specs = python_list()
        try:
            steps = _urm_chain()
            meta = getattr(x52URM.Var, "_urmChainMeta", None) or ()
            if not steps or len(meta) != len(steps):
                return rows
            first = meta[0][0]
            success = _urm_signal("success")
            error = _urm_signal("error")

            order = python_list()      # the if-statements, in the order run
            fired = False
            unknown = False
            number = 0
            for (kind, cond, payload), (node, arm) in zip(steps, meta):
                if node is not None and node not in order:
                    order.append(node)

                if kind == "gate":
                    number += 1
                    truth = None if fired else _urm_truth(cond)
                    if truth is None and not fired:
                        unknown = True
                    if truth is True and not fired and not unknown:
                        fired = True
                        icon = _urm_tint(_URM_ICON_LIVE, success)
                    elif unknown and not fired:
                        icon = _URM_ICON_UNKNOWN
                    else:
                        icon = _urm_tint(_URM_ICON_DEAD, error)
                    head = _urm_colorize(str(cond))
                    effects = _urm_effects(payload)
                    label = "%d" % number
                else:
                    icon = _urm_fallback_icon(fired, unknown, success, error)
                    fired = True
                    head = _urm_words("nothing above matches")
                    label = ""
                    if kind == "else":
                        effects = _urm_effects(payload)
                    else:
                        effects = python_list()
                        effects.append((_URM_ICON_EFFECT, _urm_colorize(payload)))

                if node is first or len(rows) >= _URM_MAX_GATES:
                    continue

                # Miss every if-statement before this one, then take this arm.
                spec = python_list()
                for earlier in order:
                    if earlier is node:
                        break
                    spec.append((earlier, -1))
                if node is not None:
                    spec.append((node, arm))
                rows.append((len(rows), icon, label, head, effects))
                specs.append(spec)
        except BaseException:
            del rows[:]
            del specs[:]
        x52URM.Var._urmfLaterSpecs = specs
        return rows


# A separate block: a failure to patch one of URM's classes must not take the
# helpers above with it.
init 999 python:

    # ------------------------------------------------------------------
    # How far path detection is allowed to look
    # ------------------------------------------------------------------
    #
    # lookAheadLimit is a hardcoded 20 (PathDetection.rpy:6) and it is charged
    # per NODE, not per line. `scene x with dissolve` is three nodes, so about
    # seven lines of cinematic run-up exhaust it and the player gets "No path
    # detected" with no way to look further.
    #
    # Exposing it beats refining what the budget charges for: not counting
    # Scene/Show/With/Python would mean replacing nextIfStatement, which is
    # also the node the force-a-path code rewrites, and the player-visible
    # result is the same as simply allowing a larger number. Default stays 20,
    # so detection behaves as it shipped until asked otherwise.

    _URMC_LOOKAHEAD_MIN = 5
    _URMC_LOOKAHEAD_MAX = 500

    def _urmc_lookahead():

        try:
            value = int(x52URM.Settings.urmcLookAhead)
        except Exception:
            return 20

        if value < _URMC_LOOKAHEAD_MIN:
            return _URMC_LOOKAHEAD_MIN
        if value > _URMC_LOOKAHEAD_MAX:
            return _URMC_LOOKAHEAD_MAX
        return value


    # ------------------------------------------------------------------
    # renpy.jump('label') in the code view
    # ------------------------------------------------------------------
    #
    # interactiveLabels needs the bare statement form - keywords-coloured
    # jump, one space, functions-coloured name (codeview.rpy:143) - so a
    # python jump never links, although stripRenpyCode deliberately keeps
    # those lines alive (:219). Most modern games jump from python, so the one
    # line that says where the story goes next is the one piece of dead text
    # in the view.

    def _urmc_python_label_links(view, coloredCode):

        try:
            colors = view.colors
            pattern = (r"{color=" + colors["keywords"] + r"}(?:call|jump){/color}"
                       r"\(\s*{color=" + colors["strings"]
                       + r"}['\"]([\w\.]+)['\"]{/color}")

            def addLink(match):
                return "{{a=URMLabelDialog:{}}}{}{{/a}}".format(
                    match.group(1), match.group())

            return renpy.re.sub(pattern, addLink, coloredCode)
        except Exception:
            return coloredCode


    # ------------------------------------------------------------------
    # Bare names in the code view and on the path cards
    # ------------------------------------------------------------------
    #
    # URM only colours - and so only links - a name with an operator beside
    # it (codeview.rpy:51-59). A condition that is just a flag, `if
    # lilithmad:` or a card reading `lilithmad`, stays dead text, and the most
    # common gate in these games is exactly that. Any plain word left after
    # URM's own colouring that names a value in the store gets the variables
    # colour, and URM's interactiveVariables then links it as usual. Functions,
    # classes, modules and Characters are callable or modules and stay plain;
    # a dotted name links only when every step of it resolves.

    _URMC_BARE = renpy.re.compile(
        r"(\{\{|\{color=[^}]*\}.*?\{/color\}|\{[^{}]*\})"
        r"|(?<![\w.])([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)(?![\w.(])")

    def _urmc_store_value(name):
        import keyword
        if keyword.iskeyword(name) or name in ("None", "True", "False"):
            return False
        parts = name.split(".")
        store = renpy.store.__dict__
        if parts[0] not in store:
            return False
        value = store[parts[0]]
        for part in parts[1:]:
            try:
                value = getattr(value, part)
            except Exception:
                return False
        return not (callable(value) or type(value).__name__ == "module")

    def _urmc_bare_var_links(view, coloredCode):

        try:
            color = view.colors["variables"]

            def mark(match):
                word = match.group(2)
                if word is None or not _urmc_store_value(word):
                    return match.group()
                return "{{color={}}}{}{{/color}}".format(color, word)

            return _URMC_BARE.sub(mark, coloredCode)
        except Exception:
            return coloredCode


    try:
        # Fetched again rather than reusing the search block's local: that
        # block may have declined to install, and this setting has nothing to
        # do with search.
        x52URM.SettingsClass.defaultValues.setdefault("urmcLookAhead", 20)
    except Exception as error:
        print("URM+: could not register urmcLookAhead (%s)" % (error,))

    try:
        # children carries the same dead cache guard as varType - hasattr on a
        # string literal that is never the mangled name - so it is rebuilt on
        # every access, and URM_objectVar reads it five times per execution.
        # Over the store root that is thousands of Var constructions per
        # interaction, which is the difference between a browser and a hang.
        #
        # Unlike varType this is safe to cache: the children are name HANDLES,
        # so an edited value still re-resolves and shows through. What goes
        # stale is a key added or removed while you are looking at the list,
        # and leaving the tab re-reads it.
        _urmc_children = x52URM.Var.children

        def _urmc_children_get(self):

            cache = self.__dict__

            try:
                return cache["_urmcChildren"]
            except KeyError:
                pass

            value = _urmc_children.fget(self)
            cache["_urmcChildren"] = value
            return value

        x52URM.Var.children = property(_urmc_children_get)
    except Exception as error:
        print("URM+: children left uncached (%s)" % (error,))

    try:
        x52URM.PathDetectionClass.lookAheadLimit = property(
            lambda self: _urmc_lookahead())
    except Exception as error:
        print("URM+: look-ahead left at 20 (%s)" % (error,))

    try:
        _urmc_orig_labels = x52URM.CodeViewClass.interactiveLabels

        def _urmc_interactiveLabels(self, coloredCode):
            return _urmc_python_label_links(
                self, _urmc_orig_labels(self, coloredCode))

        x52URM.CodeViewClass.interactiveLabels = _urmc_interactiveLabels
    except Exception as error:
        print("URM+: python jumps left unlinked (%s)" % (error,))

    try:
        _urmc_orig_vars = x52URM.CodeViewClass.interactiveVariables

        def _urmc_interactiveVariables(self, coloredCode):
            # Flags first (true("x") opens the flag), then bare names.
            try:
                coloredCode = _urmfl_links(self, coloredCode)
            except Exception:
                pass
            return _urmc_orig_vars(
                self, _urmc_bare_var_links(self, coloredCode))

        x52URM.CodeViewClass.interactiveVariables = _urmc_interactiveVariables
    except Exception as error:
        print("URM+: bare names left unlinked (%s)" % (error,))

# ---------------------------------------------------------------------------
# The script index: what this game checks, what it sets, and where
# ---------------------------------------------------------------------------
#
# URM's forward vision is twenty nodes. Everything it knows about a variable
# is its value right now. It has never read the game.
#
# Ren'Py keeps every node of every loaded script in one flat list for the
# whole session - renpy.game.script.all_stmts, in Ren'Py 7 and 8 alike
# (script.py, extended in finish_load, never released). This walks that list
# once and records, for every name the script touches:
#
#   reads   each condition that tests it - the operator, the literal it is
#           compared against, the label, and the menu option text when the
#           test is a menu condition
#   writes  each assignment - the operator, the literal written, the label,
#           and the menu option the player picked to reach it
#   rivals  each comparison of one name against another (rel_strong >
#           rel_passive), where no single edit can satisfy the gate
#   tokens  each `"x" in coll` test, so a word kept in a list or set is
#           findable by the word
#
# Everything is read from the script as written. Nothing is evaluated,
# nothing the game defines is called, and the store is never touched.
#
# What it cannot see, and every surface built on it must say so: tests inside
# the game's own helper functions, conditions in screens, names built at run
# time by concatenation, and anything passed through eval. So results are
# always "found in the script", never "all".
#
# Two things about Ren'Py's store decide how this is written:
#
#   * in a store, dict, list, set and object are rebound to the rollback-
#     tracked Revertable kinds (renpy/minstore.py:37-50), and [] / {} literals
#     are rewritten to them too (python.py WrapNode). An index built from
#     those would be copied into the rollback log as it grew. So it is built
#     only from python_dict / python_list / python_set / python_object, and
#     the hot code has no container literals at all.
#   * the index object lives on a URM class in URM's _constant store, which
#     is neither saved nor rolled back.

init 999 python:

    import ast as _urmi_ast

    # Inside a Ren'Py 7 store, `str` is Ren'Py's compat str - unicode - but
    # Python 2's parser hands back string literals as byte strings. So text
    # types come from the real builtins, never from the store's names.
    try:
        import __builtin__ as _urm_builtins
        _urmi_text = (_urm_builtins.str, _urm_builtins.unicode)
    except ImportError:
        _urmi_text = (str,)

    # Constant node kinds across Python 2, 3.4-3.7 and 3.8+. Missing ones are
    # simply absent from the tuple.
    _urmi_const_kinds = python_list()
    for _urmi_kind in ("Constant", "Num", "Str", "NameConstant", "Bytes"):
        if hasattr(_urmi_ast, _urmi_kind):
            _urmi_const_kinds.append(getattr(_urmi_ast, _urmi_kind))
    _urmi_const_kinds = tuple(_urmi_const_kinds)

    _URMI_OPS = python_dict()
    for _urmi_pair in (("Eq", "=="), ("NotEq", "!="), ("Lt", "<"),
                       ("LtE", "<="), ("Gt", ">"), ("GtE", ">="),
                       ("In", "in"), ("NotIn", "not in"),
                       ("Is", "is"), ("IsNot", "is not")):
        if hasattr(_urmi_ast, _urmi_pair[0]):
            _URMI_OPS[getattr(_urmi_ast, _urmi_pair[0])] = _urmi_pair[1]

    # A literal on the LEFT reads the other way round: 3 < x is x > 3.
    _URMI_FLIP = python_dict()
    for _urmi_pair in (("==", "=="), ("!=", "!="), ("<", ">"), (">", "<"),
                       ("<=", ">="), (">=", "<=")):
        _URMI_FLIP[_urmi_pair[0]] = _urmi_pair[1]

    _URMI_AUG = python_dict()
    for _urmi_pair in (("Add", "+="), ("Sub", "-="), ("Mult", "*="),
                       ("Div", "/="), ("FloorDiv", "//="), ("Mod", "%="),
                       ("Pow", "**="), ("BitOr", "|="), ("BitAnd", "&=")):
        if hasattr(_urmi_ast, _urmi_pair[0]):
            _URMI_AUG[getattr(_urmi_ast, _urmi_pair[0])] = _urmi_pair[1]

    _URMI_YIELD_EVERY = 1500


    def _urmi_literal(node):
        """(True, value) for a literal the script wrote, else (False, None)."""

        if isinstance(node, _urmi_const_kinds):
            for attr in ("value", "n", "s"):
                if hasattr(node, attr):
                    return (True, getattr(node, attr))
            return (False, None)

        # Python 2 spells True, False and None as names.
        if isinstance(node, _urmi_ast.Name):
            if node.id == "True":
                return (True, True)
            if node.id == "False":
                return (True, False)
            if node.id == "None":
                return (True, None)

        # -3 is UnaryOp(USub, 3).
        if (isinstance(node, _urmi_ast.UnaryOp)
                and isinstance(node.op, _urmi_ast.USub)):
            ok, value = _urmi_literal(node.operand)
            if ok and isinstance(value, (int, float)) and not isinstance(value, bool):
                return (True, -value)

        return (False, None)

    def _urmi_name(node):
        """
        The name URM itself would give this expression, or None.

        Matches Var naming exactly - a.b, a["k"], a[3] - so an index key and
        a search result are the same string. store.x is just x.
        """

        if isinstance(node, _urmi_ast.Name):
            if node.id in ("True", "False", "None"):
                return None
            return node.id

        if isinstance(node, _urmi_ast.Attribute):
            base = _urmi_name(node.value)
            if base is None:
                return None
            if base == "store":
                return node.attr
            return base + "." + node.attr

        if isinstance(node, _urmi_ast.Subscript):
            base = _urmi_name(node.value)
            if base is None:
                return None
            key = node.slice
            # Before 3.9 the key is wrapped in Index().
            if hasattr(_urmi_ast, "Index") and isinstance(key, _urmi_ast.Index):
                key = key.value
            ok, value = _urmi_literal(key)
            if not ok:
                return None
            if isinstance(value, _urmi_text):
                return base + '["' + value + '"]'
            if isinstance(value, int) and not isinstance(value, bool):
                return base + "[" + str(value) + "]"
            return None

        return None

    def _urmi_callee(node):
        """`setflag` for setflag(...), `kim._var` for kim._var(...)."""

        if isinstance(node, _urmi_ast.Call):
            return _urmi_name(node.func)
        return None

    _URMI_BINOPS = python_dict()
    for _urmi_pair in (("Add", "+"), ("Sub", "-"), ("Mult", "*"),
                       ("Div", "/"), ("FloorDiv", "//"), ("Mod", "%")):
        if hasattr(_urmi_ast, _urmi_pair[0]):
            _URMI_BINOPS[getattr(_urmi_ast, _urmi_pair[0])] = _urmi_pair[1]

    def _urmi_expr_text(node, depth=0):
        """
        Small arithmetic over names and numbers, written back out:
        `hard_love - 30`, `max_love - love`. None for anything bigger.

        Twisted Thoughts writes its caps as `love < hard_love-30` and
        `max_love-love>9`; without this, a comparison with arithmetic on one
        side recorded nothing at all.
        """

        if depth > 4:
            return None
        name = _urmi_name(node)
        if name is not None:
            return name
        ok, value = _urmi_literal(node)
        if ok:
            return "%r" % (value,)
        if isinstance(node, _urmi_ast.BinOp):
            op = _URMI_BINOPS.get(type(node.op))
            left = _urmi_expr_text(node.left, depth + 1)
            right = _urmi_expr_text(node.right, depth + 1)
            if op and left is not None and right is not None:
                return "%s %s %s" % (left, op, right)
        return None

    def _urmi_mentions(node, out):
        """
        Every variable named anywhere in an expression - longest chain only,
        so mc.stats.love is one mention, not three. A call's function name is
        not a variable read; its arguments are.
        """

        if isinstance(node, (_urmi_ast.Name, _urmi_ast.Attribute,
                             _urmi_ast.Subscript)):
            name = _urmi_name(node)
            if name is not None:
                out.append(name)
                return
        if isinstance(node, _urmi_ast.Call):
            for arg in node.args:
                _urmi_mentions(arg, out)
            for kw in getattr(node, "keywords", None) or ():
                _urmi_mentions(kw.value, out)
            return
        for child in _urmi_ast.iter_child_nodes(node):
            _urmi_mentions(child, out)


    class _URMIFlag(python_object):
        """One word a game keeps in a collection, named by the code that tests it."""

        def __init__(self, name, word, coll, getter, attr):
            self.name = name
            self.word = word
            self.coll = coll          # store name of the collection
            self.getter = getter      # the game's test function, or None
            self.attr = attr          # members are objects matched on this attribute
            self.objects = python_list()  # store names of objects that stand for it

    def _urmi_helper_role(fn, param):
        """("get" | "add" | "remove", collection, attribute or None), or None."""

        role = None
        coll = None
        attr = None
        remover = fn.name.lower().startswith(("remove", "del", "unset", "lose", "drop", "clear"))

        for node in _urmi_ast.walk(fn):
            # o in coll
            if isinstance(node, _urmi_ast.Compare) and len(node.ops) == 1 and \
                    isinstance(node.ops[0], _urmi_ast.In) and \
                    isinstance(node.left, _urmi_ast.Name) and node.left.id == param:
                target = _urmi_name(node.comparators[0])
                if target is not None and role is None:
                    role, coll = "get", target

            # any(x.name == i for x in coll)
            if isinstance(node, (_urmi_ast.GeneratorExp, _urmi_ast.ListComp)) and node.generators:
                gen = node.generators[0]
                target = _urmi_name(gen.iter)
                var = getattr(gen.target, "id", None)
                for sub in _urmi_ast.walk(node):
                    if not isinstance(sub, _urmi_ast.Compare) or len(sub.ops) != 1:
                        continue
                    sides = (sub.left, sub.comparators[0])
                    for one, other in (sides, sides[::-1]):
                        if isinstance(one, _urmi_ast.Attribute) and \
                                isinstance(one.value, _urmi_ast.Name) and one.value.id == var:
                            mine = (isinstance(other, _urmi_ast.Name) and other.id == param) or (
                                isinstance(other, _urmi_ast.Attribute) and
                                isinstance(other.value, _urmi_ast.Name) and other.value.id == param)
                            if mine and target is not None:
                                if remover:
                                    return ("remove", target, one.attr)
                                if role is None and isinstance(sub.ops[0], _urmi_ast.Eq):
                                    role, coll, attr = "get", target, one.attr

            # coll.add(i) / coll.append(i) / coll.remove(i) / coll.discard(i)
            if isinstance(node, _urmi_ast.Call) and isinstance(node.func, _urmi_ast.Attribute) \
                    and node.args and isinstance(node.args[0], _urmi_ast.Name) \
                    and node.args[0].id == param:
                target = _urmi_name(node.func.value)
                if target is not None:
                    if node.func.attr in ("add", "append"):
                        return ("add", target, None)
                    if node.func.attr in ("remove", "discard"):
                        return ("remove", target, None)

        if role == "get":
            return (role, coll, attr)
        return None

    class _URMIndex(python_object):
        """
        Built once, read many times. Fields are plain python containers.

        A site is a tuple: (filename, line, node id) - the id lets the label
        and the enclosing menu option be worked out on demand from `parent`
        instead of being stored on every record.
        """

        def __init__(self):
            self.state = "idle"          # idle, building, ready, failed
            self.done = 0
            self.total = 0
            self.error = None
            self.seconds = 0.0
            self.generation = 0
            self.finished_at = None
            self.checks = 0              # every recorded read, for the "done" line

            self.reads = python_dict()   # name -> [(site, op, literal)]
            self.writes = python_dict()  # name -> [(site, op, literal or None, text)]
            self.rivals = python_dict()  # name -> [(site, op, other)]
            self.tokens = python_dict()  # token -> [(site, collection, op)]
            self.calls = python_dict()   # callee -> [(site, string args)]
            self.declared = python_dict()  # name -> (site, source text)

            # Flags: games that keep choices as words in a collection rather
            # than as variables - option("x") / true("x"), new_path(p) /
            # on_path("p"). See _URMIndex._helpers and _flags.
            self.helpers = python_dict()   # function -> (role, collection, attribute or None)
            self.callreads = python_dict() # callee -> [(site, string args, "truthy"/"falsy")]
            self.callnames = python_dict() # callee -> [(site, name args)]
            self.flags = python_dict()     # flag name -> _URMIFlag

            self.parent = python_dict()  # id(node) -> (parent node, kind, extra)
            self.labels = python_dict()  # label name -> Label node
            # id(node) -> the one statement whose .next it is, or None when
            # several lead to it (the statement after an if or a menu)
            self.prev = python_dict()
            # filename -> (sorted lines, names): the label a line falls under,
            # for scripts whose label bodies are not indented under the label
            self.label_lines = python_dict()
            self.nodes = python_dict()   # id(node) -> node, for site lookups
            self._conds = python_dict()  # condition text -> parsed findings

        # -------------------------------------------------------------- build

        def _add(self, table, key, item):
            bucket = table.get(key)
            if bucket is None:
                bucket = python_list()
                table[key] = bucket
            bucket.append(item)

        def _site(self, node):
            self.nodes[id(node)] = node
            return (getattr(node, "filename", "?"),
                    getattr(node, "linenumber", 0),
                    id(node))

        def _condition(self, text):
            """
            What a condition tests, parsed once per distinct string.

            Returns a list of (kind, a, b, c) with kind one of:
                cmp    name, op, literal
                rival  name, op, other name
                token  token, collection, op
                truth  name, "truthy"/"falsy", None
                call   callee, (string args), None
            """

            cached = self._conds.get(text)
            if cached is not None:
                return cached

            found = python_list()

            try:
                tree = _urmi_ast.parse(text.strip(), mode="eval")
            except Exception:
                self._conds[text] = found
                return found

            negated = python_set()
            for node in _urmi_ast.walk(tree):
                if isinstance(node, _urmi_ast.UnaryOp) and isinstance(
                        node.op, _urmi_ast.Not) and isinstance(node.operand, _urmi_ast.Call):
                    negated.add(id(node.operand))

            for node in _urmi_ast.walk(tree):

                if isinstance(node, _urmi_ast.Compare):
                    left = node.left
                    for op_node, right in zip(node.ops, node.comparators):
                        op = _URMI_OPS.get(type(op_node))
                        if op is not None:
                            self._compare(found, left, op, right)
                        left = right

                elif isinstance(node, _urmi_ast.UnaryOp) and isinstance(
                        node.op, _urmi_ast.Not):
                    name = _urmi_name(node.operand)
                    if name is not None:
                        found.append(("truth", name, "falsy", None))

                elif isinstance(node, _urmi_ast.Call):
                    callee = _urmi_callee(node)
                    if callee is not None:
                        args = python_list()
                        for arg in node.args:
                            ok, value = _urmi_literal(arg)
                            if ok and isinstance(value, _urmi_text):
                                args.append(value)
                        found.append(("call", callee, tuple(args),
                                      "falsy" if id(node) in negated else "truthy"))

            # Bare names used as truth values: `if flag:`, `a and b`.
            self._truths(found, tree.body)

            # Anything the structured kinds above did not cover is still a
            # read: a name inside arithmetic, a function argument, a slice.
            # Gate counts and "where is this checked" must not miss it.
            covered = python_set()
            for kind, a, b, _c in found:
                if kind in ("cmp", "truth", "rival"):
                    covered.add(a)
                elif kind == "token":
                    covered.add(b)
            mentioned = python_list()
            _urmi_mentions(tree.body, mentioned)
            for name in mentioned:
                if name not in covered:
                    covered.add(name)
                    found.append(("mention", name, None, None))

            self._conds[text] = found
            return found

        def _truths(self, found, node):
            if isinstance(node, _urmi_ast.BoolOp):
                for value in node.values:
                    self._truths(found, value)
                return
            name = _urmi_name(node)
            if name is not None:
                found.append(("truth", name, "truthy", None))

        def _compare(self, found, left, op, right):

            if op in ("in", "not in"):
                ok, token = _urmi_literal(left)
                coll = _urmi_name(right)
                if ok and isinstance(token, _urmi_text) and coll is not None:
                    found.append(("token", token, coll, op))
                return

            lname = _urmi_name(left)
            rname = _urmi_name(right)
            lok, lval = _urmi_literal(left)
            rok, rval = _urmi_literal(right)

            if lname is not None and rok:
                found.append(("cmp", lname, op, rval))
            elif rname is not None and lok:
                found.append(("cmp", rname, _URMI_FLIP.get(op, op), lval))
            elif lname is not None and rname is not None:
                found.append(("rival", lname, op, rname))
                found.append(("rival", rname, _URMI_FLIP.get(op, op), lname))
            elif lname is not None:
                # love < hard_love - 30
                other = _urmi_expr_text(right)
                if other is not None:
                    found.append(("rival", lname, op, other))
            elif rname is not None:
                other = _urmi_expr_text(left)
                if other is not None:
                    found.append(("rival", rname, _URMI_FLIP.get(op, op), other))

        def _record_condition(self, node, text, extra):
            site = self._site(node)
            for kind, a, b, c in self._condition(text):
                if kind == "cmp":
                    self._add(self.reads, a, (site, b, c))
                elif kind == "truth":
                    self._add(self.reads, a, (site, b, None))
                elif kind == "rival":
                    self._add(self.rivals, a, (site, b, c))
                    self._add(self.reads, a, (site, "vs", c))
                elif kind == "token":
                    self._add(self.tokens, a, (site, b, c))
                    self._add(self.reads, b, (site, c, a))
                elif kind == "call":
                    self._add(self.calls, a, (site, b))
                    self._add(self.callreads, a, (site, b, c or "truthy"))
                elif kind == "mention":
                    self._add(self.reads, a, (site, "mention", None))

        def _python(self, node, source):
            """Every assignment and every bare helper call in a $ line or block."""

            try:
                tree = _urmi_ast.parse(source, mode="exec")
            except Exception:
                return

            site = self._site(node)
            stack = python_list()
            stack.append(tree)

            while stack:
                cur = stack.pop()

                # A def or class here is the game DEFINING a helper. Its body
                # is not a story event, and treating its locals as writes
                # would flood the index with names like `i` and `total`.
                if isinstance(cur, (_urmi_ast.FunctionDef, _urmi_ast.ClassDef,
                                    _urmi_ast.Lambda)):
                    continue
                if hasattr(_urmi_ast, "AsyncFunctionDef") and isinstance(
                        cur, _urmi_ast.AsyncFunctionDef):
                    continue

                if isinstance(cur, _urmi_ast.Assign):
                    ok, value = _urmi_literal(cur.value)
                    for target in cur.targets:
                        self._target(site, target, "=", ok, value)

                elif isinstance(cur, _urmi_ast.AugAssign):
                    ok, value = _urmi_literal(cur.value)
                    op = _URMI_AUG.get(type(cur.op), "op=")
                    self._target(site, cur.target, op, ok, value)

                elif isinstance(cur, _urmi_ast.Expr) and isinstance(
                        cur.value, _urmi_ast.Call):
                    call = cur.value
                    callee = _urmi_callee(call)
                    if callee is not None:
                        args = python_list()
                        names = python_list()
                        for arg in call.args:
                            ok, value = _urmi_literal(arg)
                            if ok and isinstance(value, _urmi_text):
                                args.append(value)
                            else:
                                argname = _urmi_name(arg)
                                if argname is not None:
                                    names.append(argname)
                        self._add(self.calls, callee, (site, tuple(args)))
                        if names:
                            self._add(self.callnames, callee, (site, tuple(names)))

                        # coll.append("x") / coll.add("x") writes a token.
                        if isinstance(call.func, _urmi_ast.Attribute) and \
                                call.func.attr in ("append", "add", "remove",
                                                   "discard"):
                            owner = _urmi_name(call.func.value)
                            if owner is not None:
                                for arg in call.args:
                                    ok, value = _urmi_literal(arg)
                                    if ok:
                                        self._add(self.writes, owner,
                                                  (site, "." + call.func.attr,
                                                   value, None))

                for child in _urmi_ast.iter_child_nodes(cur):
                    stack.append(child)

        def _target(self, site, target, op, ok, value):
            if isinstance(target, (_urmi_ast.Tuple, _urmi_ast.List)):
                for elt in target.elts:
                    self._target(site, elt, op, False, None)
                return
            name = _urmi_name(target)
            if name is not None:
                self._add(self.writes, name,
                          (site, op, value if ok else None, None))

        def _link(self, node):
            """Remember which container each block member sits in."""

            ast = renpy.ast
            pid = node

            if isinstance(node, ast.If):
                for cond, block in node.entries:
                    for child in block or ():
                        self.parent[id(child)] = (pid, "if", cond)
            elif isinstance(node, ast.Menu):
                for item in node.items:
                    label, cond, block = item[0], item[1], item[2]
                    for child in block or ():
                        self.parent[id(child)] = (pid, "option", label)
            elif isinstance(node, (ast.Label, ast.While)):
                for child in getattr(node, "block", None) or ():
                    self.parent[id(child)] = (pid, type(node).__name__.lower(),
                                              getattr(node, "name", None))
            else:
                for child in getattr(node, "block", None) or ():
                    if isinstance(child, ast.Node):
                        self.parent[id(child)] = (pid, "block", None)

        def check_count(self):
            return self.checks

        def build(self, stmts, generation=0, alive=None):
            """
            Walk every node once. Safe to call from a background thread.

            `alive` is asked every few thousand nodes; when it says no - the
            player pressed Shift+R and a newer build has started - this one
            stops rather than finishing work nobody will read.
            """

            import time

            ast = renpy.ast
            started = time.time()
            self.state = "building"
            self.generation = generation

            # Node classes vary by engine version - Default arrived later than
            # Define, and a missing one must cost that one kind of record, not
            # abort the whole walk with an AttributeError.
            def kinds(*names):
                found = python_list()
                for name in names:
                    cls = getattr(ast, name, None)
                    if cls is not None:
                        found.append(cls)
                return tuple(found) or (type(None),)

            IF = kinds("If")
            WHILE = kinds("While")
            MENU = kinds("Menu")
            PYTHON = kinds("Python")
            DECLARE = kinds("Default", "Define")
            LABEL = kinds("Label")
            pairs = python_dict()

            try:
                nodes = python_list(stmts)
                self.total = len(nodes)

                for index, node in enumerate(nodes):
                    self.done = index

                    if index % _URMI_YIELD_EVERY == 0 and index:
                        # Let the render loop have the GIL.
                        time.sleep(0.001)
                        if alive is not None and not alive():
                            self.state = "abandoned"
                            return

                    try:
                        self._link(node)

                        # Dialogue in a translation block chains as
                        # Translate -> Say -> EndTranslate -> next Translate
                        # (Ren'Py 7.5). An engine whose Translate points past
                        # its own block would give the EndTranslate two
                        # predecessors; that link is left out so the chain
                        # stays a single line either way.
                        after = getattr(node, "next", None)
                        if after is not None and not (
                                isinstance(node, renpy.ast.Translate) and node.block
                                and after is not node.block[0]):
                            key = id(after)
                            self.prev[key] = None if key in self.prev else node

                        if isinstance(node, LABEL):
                            name = getattr(node, "name", None)
                            if isinstance(name, _urmi_text):
                                self.labels[name] = node
                                fn = getattr(node, "filename", None)
                                bucket = pairs.get(fn)
                                if bucket is None:
                                    bucket = python_list()
                                    pairs[fn] = bucket
                                bucket.append((getattr(node, "linenumber", 0), name))
                            continue

                        if isinstance(node, IF):
                            for cond, _block in node.entries:
                                if cond and cond.strip() != "True":
                                    self._record_condition(node, cond, None)

                        elif isinstance(node, WHILE):
                            self._record_condition(node, node.condition, None)

                        elif isinstance(node, MENU):
                            for item in node.items:
                                cond = item[1]
                                if cond and cond.strip() != "True":
                                    self._record_condition(node, cond, item[0])

                        elif isinstance(node, PYTHON):
                            source = getattr(getattr(node, "code", None),
                                             "source", None)
                            if source:
                                self._python(node, source)
                                if "def " in source:
                                    self._helpers(source)

                        elif isinstance(node, DECLARE):
                            self._declare(node)

                    except Exception:
                        continue

                for fn, bucket in pairs.items():
                    bucket.sort()
                    lines = python_list()
                    names = python_list()
                    for line, name in bucket:
                        lines.append(line)
                        names.append(name)
                    self.label_lines[fn] = (lines, names)

                try:
                    self._flags()
                except Exception as error:
                    print("URM+: flags not indexed (%s)" % (error,))

                total = 0
                for bucket in self.reads.values():
                    total += len(bucket)
                self.checks = total

                self.done = self.total
                self.seconds = time.time() - started
                self.finished_at = time.time()
                # Last: everything above is complete before anyone sees ready.
                self.state = "ready"

            except Exception as error:
                self.error = "%s: %s" % (type(error).__name__, error)
                self.seconds = time.time() - started
                self.finished_at = time.time()
                self.state = "failed"

        def _helpers(self, source):
            """
            Learn the game's flag helpers from their definitions:

                def true(o):        if o in mc_choices: return True
                def option(i):      mc_choices.add(i)
                def on_path(i):     any(x.name == i for x in mc_paths)
                def new_path(i):    mc_paths.add(i)
                def remove_path(i): rebuilds mc_paths without i

            Only module-level functions with a first parameter; a method is
            the game's class at work, not a flag. Recorded as (role,
            collection, attribute) with role "get", "add" or "remove".
            """

            try:
                tree = _urmi_ast.parse(source, mode="exec")
            except Exception:
                return

            for fn in tree.body:
                if not isinstance(fn, _urmi_ast.FunctionDef):
                    continue
                args = getattr(fn.args, "args", None) or ()
                if not args:
                    continue
                first = args[0]
                param = getattr(first, "arg", None) or getattr(first, "id", None)
                if not param:
                    continue
                found = _urmi_helper_role(fn, param)
                if found is not None:
                    self.helpers[fn.name] = found

        def _flags(self):
            """
            Turn helper calls into flags, each a named variable of its own:
            reads for every getter call in a condition, writes for every setter
            or remover call, and the same for words tested directly with
            `"x" in coll` and written with coll.add / append / remove.

            A flag is named by the code that tests it - true("x"), or "x" in
            coll when the game has no getter - so the name is what the player
            sees in the condition.
            """

            getters = python_dict()        # collection -> getter function
            for fname, (role, coll, attr) in self.helpers.items():
                if role == "get" and coll not in getters:
                    getters[coll] = (fname, attr)

            def flag(coll, word, objname=None):
                if coll in getters:
                    fname, attr = getters[coll]
                    name = '%s("%s")' % (fname, word)
                else:
                    fname, attr = None, None
                    name = '"%s" in %s' % (word, coll)
                rec = self.flags.get(name)
                if rec is None:
                    rec = _URMIFlag(name, word, coll, fname, attr)
                    self.flags[name] = rec
                if objname and objname not in rec.objects:
                    rec.objects.append(objname)
                return name

            for coll, (fname, attr) in getters.items():
                for site, args, op in self.callreads.get(fname, ()):
                    if args:
                        self._add(self.reads, flag(coll, args[0]), (site, op, None))

            for fname, (role, coll, attr) in self.helpers.items():
                if role not in ("add", "remove"):
                    continue
                on = role == "add"
                for site, args in self.calls.get(fname, ()):
                    if args:
                        self._add(self.writes, flag(coll, args[0]), (site, "=", on, None))
                for site, names in self.callnames.get(fname, ()):
                    word = self._object_word(names[0], getters.get(coll, (None, None))[1])
                    if word:
                        self._add(self.writes, flag(coll, word, names[0]), (site, "=", on, None))

            # Words tested directly: "met_kim" in diary.
            for word, bucket in self.tokens.items():
                for site, coll, op in bucket:
                    if op in ("in", "not in"):
                        self._add(self.reads, flag(coll, word),
                                  (site, "truthy" if op == "in" else "falsy", None))
            for coll in python_list(self.writes.keys()):
                if coll in self.flags:
                    continue
                for site, op, value, _t in self.writes.get(coll) or ():
                    if op in (".add", ".append", ".remove", ".discard") and \
                            isinstance(value, _urmi_text):
                        named = flag(coll, value)
                        if named in self.reads:
                            self._add(self.writes, named, (site, "=", op in (".add", ".append"), None))

            # A word only ever written, never tested, is not a flag anyone needs.
            for name in python_list(self.flags.keys()):
                if name not in self.reads:
                    del self.flags[name]

        def _object_word(self, objname, attr):
            """The word an object stands for: Path("kim_mercy_path", ...) -> kim_mercy_path."""

            if not attr:
                return None
            declared = self.declared.get(objname)
            source = declared[1] if declared else None
            if source:
                try:
                    tree = _urmi_ast.parse(source.strip(), mode="eval").body
                    if isinstance(tree, _urmi_ast.Call):
                        for arg in tree.args:
                            ok, value = _urmi_literal(arg)
                            if ok and isinstance(value, _urmi_text):
                                return value
                        for kw in getattr(tree, "keywords", None) or ():
                            if kw.arg == attr:
                                ok, value = _urmi_literal(kw.value)
                                if ok and isinstance(value, _urmi_text):
                                    return value
                except Exception:
                    pass
            try:
                value = getattr(getattr(renpy.store, objname), attr)
                if isinstance(value, _urmi_text):
                    return value
            except Exception:
                pass
            return None

        def _declare(self, node):
            varname = getattr(node, "varname", None)
            if not varname:
                return
            store = getattr(node, "store", "store") or "store"
            if store == "store":
                name = varname
            elif store.startswith("store."):
                name = store[6:] + "." + varname
            else:
                name = varname
            source = getattr(getattr(node, "code", None), "source", None)
            self.declared[name] = (self._site(node), source)

        # -------------------------------------------------------------- query

        def where(self, site):
            """(label, option text, filename, line) for a site."""

            filename, line, nid = site
            label = None
            option = None
            cur = self.nodes.get(nid)
            guard = 0

            while cur is not None and guard < 200:
                guard += 1
                link = self.parent.get(id(cur))
                if link is None:
                    break
                parent, kind, extra = link
                if kind == "option" and option is None:
                    option = extra
                if kind == "label" and label is None:
                    label = extra
                cur = parent

            if not isinstance(label, _urmi_text):
                label = self.label_at(filename, line)

            return (label, option, filename, line)

        def label_at(self, filename, line):
            """
            The label a script line falls under. Many games write a label
            and then carry on at the same indent, so the statements are its
            siblings, not its block, and the parent chain never reaches it -
            where() used to hand back the node's internal tuple name then.
            """

            import bisect
            found = self.label_lines.get(filename)
            if not found:
                return None
            lines, names = found
            i = bisect.bisect_right(lines, line) - 1
            if i < 0:
                return None
            return names[i]


    def _urmi_all_stmts():
        try:
            stmts = renpy.game.script.all_stmts
            if stmts:
                return stmts
        except Exception:
            pass
        return ()

    def _urmi_index():
        """The live index, or None before it has been started."""
        return getattr(x52URM.Var, "_urmcIndex", None)

# ---------------------------------------------------------------------------
# Building the index as the game starts, and saying so
# ---------------------------------------------------------------------------
#
# The index is built on a background thread the moment init finishes, so the
# window and the main menu come up exactly as fast as they did before. A small
# line in the corner says it is working and disappears when it is done.
#
# It cannot use URM's own overlay for that: URM only shows URM_overlay once
# the game reaches `start` or a save is loaded (classes/main.rpy:55-75), so it
# is absent from the splash screen and the main menu - which is where this
# line matters. config.interact_callbacks runs at the start of every
# interaction in every context, menus included, and exists in every engine
# this mod supports.
#
# The thread only READS the script, which is fixed once loaded. It never
# touches the store. If threads are unavailable it builds in the foreground,
# with the same line shown on the first interaction afterwards.

init 999 python:

    def _urmi_start():

        try:
            generation = int(getattr(x52URM.Var, "_urmcIndexGeneration", 0)) + 1
        except Exception:
            generation = 1

        index = _URMIndex()
        x52URM.Var._urmcIndexGeneration = generation
        x52URM.Var._urmcIndex = index
        stmts = _urmi_all_stmts()

        def alive():
            return getattr(x52URM.Var, "_urmcIndexGeneration", generation) == generation

        def run():
            index.build(stmts, generation, alive)

        try:
            import threading
            worker = threading.Thread(target=run, name="URM script index")
            worker.daemon = True
            worker.start()
        except Exception:
            run()

    try:
        _urmi_start()
    except Exception as error:
        print("URM+: script index not started (%s)" % (error,))


    # ------------------------------------------------------------------
    # The corner line
    # ------------------------------------------------------------------

    _URMI_DONE_SHOWN_FOR = 4.0

    def _urmi_progress_text(st, at):
        """DynamicDisplayable body: redraws itself, needs no interaction."""

        import time

        index = _urmi_index()
        if index is None:
            return (Null(), None)

        if index.state == "building":
            total = max(index.total, 1)
            pct = int(100.0 * index.done / total)
            message = "URM: reading the game's script... %d%%" % pct
            again = 0.25

        elif index.state == "ready":
            finished = getattr(index, "finished_at", None)
            if finished is None or time.time() - finished > _URMI_DONE_SHOWN_FOR:
                return (Null(), None)
            message = ("URM: script read - %d checks on %d names found"
                       % (index.check_count(), len(index.reads)))
            again = 0.5

        elif index.state == "failed":
            finished = getattr(index, "finished_at", None)
            if finished is None or time.time() - finished > _URMI_DONE_SHOWN_FOR * 2:
                return (Null(), None)
            message = "URM: could not read the script; prophecy features are off"
            again = 0.5

        else:
            return (Null(), 0.25)

        # Plain ASCII and an explicit outline: this is drawn over whatever the
        # game's own font and colours are, before any of URM's styling exists.
        return (Text(message, size=16, color="#ffffffdd",
                     outlines=((2, "#000000aa", 0, 0),)), again)

    _urmi_layer = "x52Overlay" if "x52Overlay" in config.layers else "overlay"

    def _urmi_interact():
        """Show the corner line in this context if there is anything to say."""

        index = _urmi_index()
        if index is None:
            return
        # Once the line has said its piece, stop looking every interaction.
        finished = getattr(index, "finished_at", None)
        if index.state != "building" and finished and \
                __import__("time").time() - finished > _URMI_DONE_SHOWN_FOR * 2:
            return
        try:
            if not renpy.get_screen("urmi_progress", layer=_urmi_layer):
                renpy.show_screen("urmi_progress", _layer=_urmi_layer)
        except Exception:
            pass

    if _urmi_interact not in config.interact_callbacks:
        config.interact_callbacks.append(_urmi_interact)


# ---------------------------------------------------------------------------
# What the screens ask the index
# ---------------------------------------------------------------------------
#
# Every answer is ready-to-draw text, built here once, so no screen does any
# work on redraw. Every answer is also qualified: the index only knows what is
# written in the script, so it says "found in the script" and never "all".

init 999 python:

    def urm_index_status():
        """('ready'|'building'|'failed'|'off', percent or None)."""

        index = _urmi_index()
        if index is None:
            return ("off", None)
        if index.state == "building":
            return ("building", int(100.0 * index.done / max(index.total, 1)))
        return (index.state, None)

    def _urmi_num(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _urmi_show(value):
        if isinstance(value, _urmi_text):
            return '"%s"' % value
        return "%r" % (value,)

    def urm_checks(name):
        """
        What the game compares `name` against, for the editor.

        Returns (summary, rows) where each row is (button text, value to set
        or None, how many places). Rows are the literal comparisons, sorted
        numerically when they are numbers, so the editor reads like the ladder
        the game actually climbs.
        """

        index = _urmi_index()
        if index is None or index.state != "ready":
            return ("", python_list())

        reads = index.reads.get(name) or ()
        if not reads:
            return ("", python_list())

        counts = python_dict()
        truthy = 0
        rivals = 0
        mentions = 0
        ops_seen = python_set()

        for _site, op, literal in reads:
            if op in ("truthy", "falsy"):
                truthy += 1
                continue
            if op == "vs":
                rivals += 1
                continue
            if op == "mention":
                mentions += 1
                continue
            if op in ("in", "not in"):
                continue
            key = (op, literal if not isinstance(literal, list) else repr(literal))
            counts[key] = counts.get(key, 0) + 1
            ops_seen.add(op)

        rows = python_list()
        for (op, literal), count in counts.items():
            target = None
            if op in ("==", ">=", "<="):
                target = literal
            elif op == ">" and _urmi_num(literal):
                target = literal + 1 if isinstance(literal, int) else literal
            elif op == "<" and _urmi_num(literal):
                target = literal - 1 if isinstance(literal, int) else literal
            text = "%s %s" % (op, _urmi_show(literal))
            if count > 1:
                text += "  x%d" % count
            rows.append((text, target, count, op, literal))

        def order(row):
            literal = row[4]
            if _urmi_num(literal):
                return (0, literal, row[3])
            return (1, _urmi_show(literal), row[3])

        rows.sort(key=order)

        # Comparisons against another variable or a calculation: readable,
        # never clickable - there is no single value that satisfies them.
        seen_rivals = python_set()
        for _site, op, other in index.rivals.get(name) or ():
            text = "%s %s" % (op, other)
            if text in seen_rivals:
                continue
            seen_rivals.add(text)
            rows.append((text, None, 1, op, other))

        gates = len(reads)
        parts = python_list()
        parts.append("found in %d check%s in the script"
                     % (gates, "" if gates == 1 else "s"))
        if truthy:
            parts.append("%d as on/off" % truthy)
        if rivals:
            parts.append("%d against another variable" % rivals)
        if mentions:
            parts.append("%d inside a calculation or function call" % mentions)

        summary = ", ".join(parts)

        # The 99 problem: a counter the game only ever tests with == has no
        # "enough" - a value between the listed ones matches nothing at all.
        numeric_ops = python_set()
        for op, literal in counts:
            if _urmi_num(literal):
                numeric_ops.add(op)
        if numeric_ops == python_set(("==",)) and len(counts) >= 2:
            summary += (". Only these exact numbers are ever checked - "
                        "a value in between, or above them, matches none of them.")

        out = python_list()
        for row in rows:
            out.append((row[0], row[1], row[2]))
        return (summary, out)

    def _urmi_describe(index, site, op, value, use_option=True):
        label, option, filename, line = index.where(site)
        where = "%s, %s:%s" % (label or "?", (filename or "?").split("/")[-1], line)
        if use_option and option:
            return '"%s"  %s %s   (%s)' % (option, op, _urmi_show(value) if value is not None else "", where)
        return "%s %s   (%s)" % (op, _urmi_show(value) if value is not None else "...", where)

    def urm_writers(name, limit=8):
        """Where the script sets `name`, newest-looking first is not knowable - script order."""

        index = _urmi_index()
        if index is None or index.state != "ready":
            return (0, python_list())
        writes = index.writes.get(name) or ()
        rows = python_list()
        for site, op, value, _text in writes[:limit]:
            rows.append(_urmi_describe(index, site, op, value))
        return (len(writes), rows)

    def urm_readers(name, limit=8):
        """Where the script tests `name`."""

        index = _urmi_index()
        if index is None or index.state != "ready":
            return (0, python_list())
        reads = index.reads.get(name) or ()
        rows = python_list()
        for site, op, literal in reads[:limit]:
            if op in ("truthy", "falsy"):
                rows.append(_urmi_describe(index, site, "is on" if op == "truthy" else "is off", None, False))
            elif op == "vs":
                rows.append(_urmi_describe(index, site, "compared with", literal, False))
            elif op == "mention":
                rows.append(_urmi_describe(index, site, "used in a calculation", None, False))
            else:
                rows.append(_urmi_describe(index, site, op, literal, False))
        return (len(reads), rows)

    def urm_gate_count(name):
        index = _urmi_index()
        if index is None or index.state != "ready":
            return None
        return len(index.reads.get(name) or ())

    def _urmi_safe(text):
        """Script text drawn as-is: braces would be read as text tags."""
        return (u"%s" % (text,)).replace("{", "{{")

    def urm_var_panel(name):
        """
        Everything the editor shows about `name`, as one ready-to-draw tuple:
        (state, percent, summary, checks, writer count, writers, reader count).
        """

        state, pct = urm_index_status()
        if state != "ready":
            return (state, pct, "", python_list(), 0, python_list(), 0)

        summary, checks = urm_checks(name)
        wcount, writers = urm_writers(name, 6)
        rcount = urm_gate_count(name) or 0

        safe_checks = python_list()
        for text, value, count in checks:
            safe_checks.append((_urmi_safe(text), value, count))

        safe_writers = python_list()
        for line in writers:
            safe_writers.append(_urmi_safe(line))

        return ("ready", None, _urmi_safe(summary), safe_checks,
                wcount, safe_writers, rcount)

    def urmi_fill(var, valueInput, value):
        """Put one of the game's own values into the editor - not commit it."""

        if getattr(var, "isFlag", False):
            # A flag has no value box: Set ON / Set OFF switch it directly.
            urmfl_set(var.name, bool(value))
            return

        try:
            if var.varType == "boolean":
                SetScreenVariable("newValue", bool(value))()
            elif isinstance(value, _urmi_text):
                valueInput.set_text(value)
            else:
                valueInput.set_text(str(value))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# The variable panel: what a value gets the player, and whether it is too late
# ---------------------------------------------------------------------------
#
# The first panel said where a name sits in the code - "found in 18 checks,
# 18 as on/off", file:line, "== 3 x2" - and a player cannot decide anything
# with that. This one answers what they opened the editor to ask:
#
#   * what does each value get me - which scenes, how much, what is said
#   * have I played that, is it still ahead of me in this scene
#   * which choices set it, and does the game change it on its own
#   * will my edit stick, and is it enough (the game may reset it, or the
#     big scene may also need something else)
#
# Everything comes from the index's nodes, read at the moment the dialog
# opens. Nothing the game defines is called: conditions are worked out by a
# small evaluator that only reads values, and gives up on any function call
# except len().
#
# What it must not claim, and the footer says so: uses inside the game's own
# functions and screens are invisible; "played" means seen on this computer
# in any playthrough; line counts include every nested branch, so they are
# "about"; story order across scenes is not knowable from the script, so the
# only order used is line order inside the one scene the player is in.
#
# Everything cached here lives on x52URM.Var, in URM's _constant store, and
# is built from python_* containers only - nothing reaches a save or the
# rollback log.

init 999 python:

    import re as _urmp_re
    import operator as _urmp_op

    _URMP_UNK = python_object()
    _URMP_NOSET = python_object()

    _URMP_STATUS_RANK = python_dict()
    for _urmp_i, _urmp_k in enumerate(("later", "not", "never", "above", "", "played")):
        _URMP_STATUS_RANK[_urmp_k] = _urmp_i

    _URMP_STATUS_TEXT = python_dict()
    for _urmp_k, _urmp_t, _urmp_c in (
            ("later", "LATER IN THIS SCENE", "#e0a800"),
            ("not", "NOT PLAYED", "#43a047"),
            ("never", "PLAYED, NEVER SAW THIS", "#1e88e5"),
            ("above", "EARLIER IN THIS SCENE", "#9e9e9e"),
            ("played", "PLAYED", "#9e9e9e")):
        _URMP_STATUS_TEXT[_urmp_k] = "{color=%s}{b}%s{/b}{/color}" % (_urmp_c, _urmp_t)

    _URMP_BIN = python_dict()
    for _urmp_k, _urmp_f in (("Add", _urmp_op.add), ("Sub", _urmp_op.sub),
                             ("Mult", _urmp_op.mul), ("Div", _urmp_op.truediv),
                             ("FloorDiv", _urmp_op.floordiv), ("Mod", _urmp_op.mod)):
        if hasattr(_urmi_ast, _urmp_k):
            _URMP_BIN[getattr(_urmi_ast, _urmp_k)] = _urmp_f

    _URMP_CMP = python_dict()
    for _urmp_k, _urmp_f in (("Eq", _urmp_op.eq), ("NotEq", _urmp_op.ne),
                             ("Lt", _urmp_op.lt), ("LtE", _urmp_op.le),
                             ("Gt", _urmp_op.gt), ("GtE", _urmp_op.ge),
                             ("Is", _urmp_op.is_), ("IsNot", _urmp_op.is_not),
                             ("In", lambda a, b: a in b),
                             ("NotIn", lambda a, b: a not in b)):
        if hasattr(_urmi_ast, _urmp_k):
            _URMP_CMP[getattr(_urmi_ast, _urmp_k)] = _urmp_f

    _URMP_NODE_BUDGET = 40000
    _URMP_BRANCH_CAP = 3000
    _URMP_ROWS_SHOWN = 10


    # Stand-ins until the Flags block below replaces them, so the panel works
    # on its own if that block is missing or failed.
    def _urmfl_record(name):
        return None

    def _urmfl_name_of(node):
        return None

    def urmfl_is_on(name):
        return None

    def _urmp_state():
        holder = x52URM.Var
        st = getattr(holder, "_urmpState", None)
        if st is None:
            st = python_dict()
            holder._urmpState = st
        return st

    def _urmp_bucket(key):
        st = _urmp_state()
        found = st.get(key)
        if found is None:
            found = python_dict()
            st[key] = found
        return found

    def _urmp_isnum(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _urmp_isint(value):
        return isinstance(value, int) and not isinstance(value, bool)

    def _urmp_letters(text):
        n = 0
        for ch in text:
            if ch.isalpha():
                n += 1
                if n >= 2:
                    return True
        return False


    # ------------------------------------------------------------------
    # A read-only evaluator
    # ------------------------------------------------------------------

    def _urmp_parse(text):
        cache = _urmp_bucket("parse")
        try:
            return cache[text]
        except KeyError:
            pass
        try:
            tree = _urmi_ast.parse(text.strip(), mode="eval").body
        except Exception:
            tree = None
        cache[text] = tree
        return tree

    def _urmp_ev(node, target=None, cand=None, depth=0):
        """
        The value of an expression from the store as it is now - or, with
        `target`, as if that one name held `cand`. _URMP_UNK when it cannot
        tell. Only reads: the one call it makes is len().
        """

        if depth > 40 or node is None:
            return _URMP_UNK

        if isinstance(node, (_urmi_ast.Call, _urmi_ast.Compare)):
            flagname = _urmfl_name_of(node)
            if flagname is not None:
                if target is not None and flagname == target:
                    return cand
                value = urmfl_is_on(flagname)
                if value is None:
                    return _URMP_UNK
                rec = _urmp_state().get("deps")
                if rec is not None and len(rec) < 200:
                    rec[flagname] = value
                return value

        if isinstance(node, (_urmi_ast.Name, _urmi_ast.Attribute, _urmi_ast.Subscript)):
            if target is not None and _urmi_name(node) == target:
                return cand
            # While a panel is being worked out, remember every plain value it
            # read, so a cached panel is thrown away when one of them changes
            # (edit ainepoint, reopen aineroute: "you have 11" must not stay).
            rec = _urmp_state().get("deps")
            if rec is not None:
                value = _urmp_ev_inner(node, target, cand, depth)
                if len(rec) < 200 and isinstance(value, (bool, int, float, type(None)) + _urmi_text):
                    key = _urmi_name(node)
                    if key is not None:
                        rec[key] = value
                return value
        return _urmp_ev_inner(node, target, cand, depth)

    def _urmp_ev_inner(node, target, cand, depth):

        ok, value = _urmi_literal(node)
        if ok:
            return value

        try:
            if isinstance(node, _urmi_ast.Name):
                store = renpy.store.__dict__
                if node.id in store:
                    return store[node.id]
                return _URMP_UNK

            if isinstance(node, _urmi_ast.Attribute):
                base = _urmp_ev(node.value, target, cand, depth + 1)
                if base is _URMP_UNK:
                    return base
                return getattr(base, node.attr)

            if isinstance(node, _urmi_ast.Subscript):
                key = node.slice
                if hasattr(_urmi_ast, "Index") and isinstance(key, _urmi_ast.Index):
                    key = key.value
                if isinstance(key, _urmi_ast.Slice):
                    return _URMP_UNK
                base = _urmp_ev(node.value, target, cand, depth + 1)
                k = _urmp_ev(key, target, cand, depth + 1)
                if base is _URMP_UNK or k is _URMP_UNK:
                    return _URMP_UNK
                return base[k]

            if isinstance(node, _urmi_ast.BinOp):
                fn = _URMP_BIN.get(type(node.op))
                left = _urmp_ev(node.left, target, cand, depth + 1)
                right = _urmp_ev(node.right, target, cand, depth + 1)
                if fn is None or left is _URMP_UNK or right is _URMP_UNK:
                    return _URMP_UNK
                return fn(left, right)

            if isinstance(node, _urmi_ast.UnaryOp):
                inner = _urmp_ev(node.operand, target, cand, depth + 1)
                if inner is _URMP_UNK:
                    return inner
                if isinstance(node.op, _urmi_ast.Not):
                    return not inner
                if isinstance(node.op, _urmi_ast.USub):
                    return -inner
                if isinstance(node.op, _urmi_ast.UAdd):
                    return +inner
                return _URMP_UNK

            if isinstance(node, _urmi_ast.Compare):
                left = _urmp_ev(node.left, target, cand, depth + 1)
                if left is _URMP_UNK:
                    return left
                for op_node, comp in zip(node.ops, node.comparators):
                    fn = _URMP_CMP.get(type(op_node))
                    right = _urmp_ev(comp, target, cand, depth + 1)
                    if fn is None or right is _URMP_UNK:
                        return _URMP_UNK
                    if not fn(left, right):
                        return False
                    left = right
                return True

            if isinstance(node, _urmi_ast.BoolOp):
                unknown = False
                is_and = isinstance(node.op, _urmi_ast.And)
                result = is_and
                for part in node.values:
                    value = _urmp_ev(part, target, cand, depth + 1)
                    if value is _URMP_UNK:
                        unknown = True
                        continue
                    if is_and and not value:
                        return value
                    if not is_and and value:
                        return value
                    result = value
                if unknown:
                    return _URMP_UNK
                return result

            if isinstance(node, _urmi_ast.IfExp):
                test = _urmp_ev(node.test, target, cand, depth + 1)
                if test is _URMP_UNK:
                    return test
                return _urmp_ev(node.body if test else node.orelse, target, cand, depth + 1)

            if isinstance(node, _urmi_ast.Call):
                func = node.func
                if isinstance(func, _urmi_ast.Name) and func.id == "len" \
                        and len(node.args) == 1:
                    inner = _urmp_ev(node.args[0], target, cand, depth + 1)
                    if inner is _URMP_UNK:
                        return inner
                    return len(inner)
                return _URMP_UNK

        except Exception:
            return _URMP_UNK

        return _URMP_UNK

    def _urmp_value(name):
        if _urmfl_record(name) is not None:
            value = urmfl_is_on(name)
            return _URMP_UNK if value is None else value
        return _urmp_ev(_urmp_parse(name))

    def _urmp_src(node, depth=0):
        """An expression written back out, for the few that have no words."""

        if depth > 12 or node is None:
            return None
        name = _urmi_name(node)
        if name is not None:
            return name
        ok, value = _urmi_literal(node)
        if ok:
            return _urmi_show(value)
        if isinstance(node, _urmi_ast.BinOp):
            op = _URMI_BINOPS.get(type(node.op))
            left = _urmp_src(node.left, depth + 1)
            right = _urmp_src(node.right, depth + 1)
            if op and left and right:
                return "%s %s %s" % (left, op, right)
            return None
        if isinstance(node, _urmi_ast.UnaryOp):
            inner = _urmp_src(node.operand, depth + 1)
            if inner is None:
                return None
            if isinstance(node.op, _urmi_ast.Not):
                return "not " + inner
            if isinstance(node.op, _urmi_ast.USub):
                return "-" + inner
            return inner
        if isinstance(node, _urmi_ast.Compare):
            parts = python_list()
            first = _urmp_src(node.left, depth + 1)
            if first is None:
                return None
            parts.append(first)
            for op_node, comp in zip(node.ops, node.comparators):
                op = _URMI_OPS.get(type(op_node))
                right = _urmp_src(comp, depth + 1)
                if op is None or right is None:
                    return None
                parts.append(op)
                parts.append(right)
            return " ".join(parts)
        if isinstance(node, _urmi_ast.BoolOp):
            joiner = " and " if isinstance(node.op, _urmi_ast.And) else " or "
            parts = python_list()
            for value in node.values:
                text = _urmp_src(value, depth + 1)
                if text is None:
                    return None
                if isinstance(value, _urmi_ast.BoolOp):
                    text = "(" + text + ")"
                parts.append(text)
            return joiner.join(parts)
        if isinstance(node, _urmi_ast.Call):
            func = _urmi_name(node.func)
            if func is None:
                return None
            args = python_list()
            for arg in node.args:
                text = _urmp_src(arg, depth + 1)
                if text is None:
                    return None
                args.append(text)
            return "%s(%s)" % (func, ", ".join(args))
        return None

    def _urmp_names_in(node):
        found = python_list()
        _urmp_mentions(node, found)
        return found

    def _urmp_mentions(node, out):
        """_urmi_mentions, with each flag test - true("x") - as one name."""

        if isinstance(node, (_urmi_ast.Call, _urmi_ast.Compare)):
            flagname = _urmfl_name_of(node)
            if flagname is not None:
                out.append(flagname)
                return
        if isinstance(node, (_urmi_ast.Name, _urmi_ast.Attribute, _urmi_ast.Subscript)):
            name = _urmi_name(node)
            if name is not None:
                out.append(name)
                return
        if isinstance(node, _urmi_ast.Call):
            for arg in node.args:
                _urmp_mentions(arg, out)
            for kw in getattr(node, "keywords", None) or ():
                _urmp_mentions(kw.value, out)
            return
        for child in _urmi_ast.iter_child_nodes(node):
            _urmp_mentions(child, out)


    # ------------------------------------------------------------------
    # Script text, made fit to show
    # ------------------------------------------------------------------

    _URMP_TAG = _urmp_re.compile(r"\{\{|\{[^{}]*\}")
    _URMP_INTERP = _urmp_re.compile(r"\[\[|\[([A-Za-z_][\w.]*)(?:![a-z]+)?\]")

    def _urmp_interp(match):
        if match.group() == "[[":
            return "["
        value = _urmp_value(match.group(1))
        if isinstance(value, _urmi_text) and len(value) <= 40:
            return value
        name = getattr(value, "name", None) if value is not _URMP_UNK else None
        if isinstance(name, _urmi_text) and len(name) <= 40 and "[" not in name:
            return name
        return match.group()

    def _urmp_plain(text, limit=110):
        """Dialogue as plain words: tags dropped, [names] filled in, braces escaped."""

        try:
            text = u"%s" % (text,)
        except Exception:
            return u""
        text = _URMP_TAG.sub(lambda m: "{" if m.group() == "{{" else "", text)
        try:
            text = _URMP_INTERP.sub(_urmp_interp, text)
        except Exception:
            pass
        text = u" ".join(text.split())
        if len(text) > limit:
            text = text[:limit - 3].rstrip() + u"..."
        return text.replace("{", "{{")

    def _urmp_speaker(who):
        if not who:
            return None
        cache = _urmp_bucket("speakers")
        try:
            return cache[who]
        except KeyError:
            pass
        name = None
        raw = who.strip()
        if raw[:1] in ("'", '"') and raw[-1:] == raw[:1]:
            name = raw[1:-1]
        else:
            value = _urmp_value(raw)
            if value is not _URMP_UNK:
                found = getattr(value, "name", None)
                if isinstance(found, _urmi_text) and found.strip():
                    name = found
        if name is None:
            name = raw
        name = _urmp_plain(name, 30)
        cache[who] = name
        return name

    def _urmp_say_line(node, limit=110):
        text = _urmp_plain(getattr(node, "what", "") or "", limit)
        who = _urmp_speaker(getattr(node, "who", None))
        if who:
            return u'%s: "%s"' % (who, text)
        return u'"%s"' % (text,)

    def _urmp_link(name):
        if _urmfl_record(name) is not None:
            return u"{a=URMFlag:%s}%s{/a}" % (name, name.replace("{", "{{"))
        return u"{a=URMVarDialog:%s}%s{/a}" % (name, name.replace("{", "{{"))


    # ------------------------------------------------------------------
    # What a branch plays
    # ------------------------------------------------------------------

    class _URMPSum(python_object):
        def __init__(self):
            self.lines = 0
            self.pictures = 0
            self.first = None        # first say with real words
            self.first_node = None   # first say at all, for "seen"
            self.target = None       # where it jumps
            self.calls = python_list()
            self.writes = python_list()   # (name, op, ok, value)
            self.funcs = python_list()
            self.preview = python_list()
            self.truncated = False
            self.choice = False

    def _urmp_effects(source):
        """Assignments with literals and bare calls in a $ line, cached by text."""

        cache = _urmp_bucket("fx")
        try:
            return cache[source]
        except KeyError:
            pass
        writes = python_list()
        funcs = python_list()
        try:
            tree = _urmi_ast.parse(source, mode="exec")
            for stmt in tree.body:
                if isinstance(stmt, _urmi_ast.Assign):
                    ok, value = _urmi_literal(stmt.value)
                    for t in stmt.targets:
                        name = _urmi_name(t)
                        if name is not None:
                            writes.append((name, "=", ok, value))
                elif isinstance(stmt, _urmi_ast.AugAssign):
                    name = _urmi_name(stmt.target)
                    ok, value = _urmi_literal(stmt.value)
                    if name is not None:
                        writes.append((name, _URMI_AUG.get(type(stmt.op), "op="), ok, value))
                elif isinstance(stmt, _urmi_ast.Expr) and isinstance(stmt.value, _urmi_ast.Call):
                    call = stmt.value
                    if isinstance(call.func, _urmi_ast.Attribute) and call.func.attr in (
                            "append", "add", "remove", "discard") and call.args:
                        owner = _urmi_name(call.func.value)
                        ok, value = _urmi_literal(call.args[0])
                        if owner is not None:
                            writes.append((owner, "." + call.func.attr, ok, value))
                            continue
                    callee = _urmi_callee(call)
                    if callee is not None:
                        funcs.append(callee)
        except Exception:
            pass
        cache[source] = (writes, funcs)
        return (writes, funcs)

    def _urmp_walk(nodes, s, budget, depth, want):
        """Fill `s` from a block. True when the block ends here (jump/return)."""

        ast = renpy.ast
        for node in nodes or ():
            if budget[0] <= 0:
                s.truncated = True
                return True
            budget[0] -= 1

            if isinstance(node, ast.Translate):
                if _urmp_walk(node.block, s, budget, depth, want):
                    return True

            elif isinstance(node, ast.Say):
                s.lines += 1
                if s.first_node is None:
                    s.first_node = node
                if s.first is None and _urmp_letters(_urmp_plain(getattr(node, "what", "") or "", 200)):
                    s.first = _urmp_say_line(node)
                if len(s.preview) < want:
                    s.preview.append(_urmp_say_line(node, 140))

            elif isinstance(node, (ast.Show, ast.Scene)):
                s.pictures += 1
                if len(s.preview) < want:
                    if s.preview and s.preview[-1].startswith("(picture"):
                        s.preview[-1] = "(pictures)"
                    else:
                        s.preview.append("(picture)")

            elif isinstance(node, ast.Jump):
                if not getattr(node, "expression", False):
                    s.target = node.target
                    if len(s.preview) < want:
                        s.preview.append(u"\u2192 goes to %s" % (node.target,))
                return True

            elif isinstance(node, ast.Call):
                if not getattr(node, "expression", False):
                    s.calls.append(node.label)
                    if len(s.preview) < want:
                        s.preview.append(u"\u2192 plays %s, then comes back" % (node.label,))

            elif isinstance(node, ast.Python):
                source = getattr(getattr(node, "code", None), "source", None)
                if source:
                    writes, funcs = _urmp_effects(source)
                    for w in writes:
                        s.writes.append(w)
                        if len(s.preview) < want:
                            s.preview.append(_urmp_write_words(w))
                    for f in funcs:
                        s.funcs.append(f)
                        if len(s.preview) < want:
                            s.preview.append("(runs the game's code: %s)" % (f,))

            elif isinstance(node, ast.If):
                if depth < 6:
                    for _cond, block in node.entries:
                        _urmp_walk(block, s, budget, depth + 1, 0)

            elif isinstance(node, ast.Menu):
                s.choice = True
                if len(s.preview) < want:
                    texts = python_list()
                    for item in node.items:
                        if item[2] is not None and item[0]:
                            texts.append(u'"%s"' % _urmp_plain(item[0], 50))
                    s.preview.append(u"(a choice: %s)" % u" / ".join(texts[:4]))
                if depth < 6:
                    for item in node.items:
                        _urmp_walk(item[2], s, budget, depth + 1, 0)

            elif isinstance(node, ast.Return):
                return True

        return False

    def _urmp_write_words(w):
        name, op, ok, value = w
        if op == "=" and ok:
            if value is True:
                return "(turns %s ON)" % name
            if value is False:
                return "(turns %s OFF)" % name
            return "(sets %s to %s)" % (name, _urmp_plain(_urmi_show(value), 40))
        if op in ("+=", "-=") and ok and _urmp_isnum(value):
            return "(%s %s%s)" % (name, "+" if op == "+=" else "-", _urmi_show(value))
        return "(changes %s)" % name

    def _urmp_summary(block, budget, want=0):
        s = _URMPSum()
        if block:
            local = python_list()
            local.append(min(budget[0], _URMP_BRANCH_CAP))
            before = local[0]
            _urmp_walk(block, s, local, 0, want)
            budget[0] -= before - local[0]
            if local[0] <= 0:
                s.truncated = True
        return s

    def _urmp_label_size(index, label, budget):
        """Lines a jump target plays: its block, or the statements after it."""

        cache = _urmp_bucket("labelsize")
        key = (id(index), label)
        try:
            return cache[key]
        except KeyError:
            pass
        node = index.labels.get(label)
        s = _URMPSum()
        if node is not None:
            local = python_list()
            local.append(min(budget[0], 2000))
            before = local[0]
            if getattr(node, "block", None):
                _urmp_walk(node.block, s, local, 0, 0)
            else:
                cur = getattr(node, "next", None)
                one = python_list()
                one.append(None)
                while cur is not None and local[0] > 0:
                    if isinstance(cur, renpy.ast.Label):
                        break
                    one[0] = cur
                    if _urmp_walk(one, s, local, 0, 0):
                        break
                    cur = getattr(cur, "next", None)
            budget[0] -= before - local[0]
        cache[key] = s.lines
        return s.lines

    def _urmp_size_words(s, index, budget):
        if s.lines:
            if s.lines == 1:
                text = "1 line"
            else:
                text = "about %d lines" % s.lines
            if s.truncated:
                text = "at least %d lines" % s.lines
            return text
        if s.target:
            n = _urmp_label_size(index, s.target, budget)
            if n == 1:
                return "goes to %s (1 line there)" % s.target
            if n:
                return "goes to %s (about %d lines there)" % (s.target, n)
            return "goes to %s" % s.target
        if s.calls:
            return "plays %s" % s.calls[0]
        if s.pictures:
            return "pictures only"
        return "no dialogue"

    def _urmp_weight(s, index, budget):
        """How much a branch plays, counting what a jump leads into."""

        if s.lines:
            return s.lines
        if s.target:
            return _urmp_label_size(index, s.target, budget)
        return 0


    # ------------------------------------------------------------------
    # Conditions in words
    # ------------------------------------------------------------------

    def _urmp_opwords(op, lit):
        """(words, value that satisfies it or NOSET) for `<name> op lit`."""

        if op in ("==", "is"):
            if lit is True:
                return ("ON", True)
            if lit is False:
                return ("OFF", False)
        if op in ("!=", "is not"):
            if lit is True:
                return ("OFF", False)
            if lit is False:
                return ("ON", True)
        if lit is None:
            if op in ("==", "is"):
                return ("empty (None)", None)
            if op in ("!=", "is not"):
                return ("not empty", _URMP_NOSET)
        if isinstance(lit, _urmi_text):
            shown = _urmp_plain(lit, 60)
            if op == "==":
                return (u'"%s"' % shown, lit)
            if op == "!=":
                return (u'anything but "%s"' % shown, _URMP_NOSET)
        if _urmp_isnum(lit):
            shown = _urmi_show(lit)
            if op == "==":
                return ("exactly %s" % shown, lit)
            if op == "!=":
                return ("anything but %s" % shown, _URMP_NOSET)
            if op == ">=":
                return ("%s or more" % shown, lit)
            if op == "<=":
                return ("%s or less" % shown, lit)
            if op == ">":
                if _urmp_isint(lit):
                    return ("%d or more" % (lit + 1), lit + 1)
                return ("more than %s" % shown, _URMP_NOSET)
            if op == "<":
                if _urmp_isint(lit):
                    return ("%d or less" % (lit - 1), lit - 1)
                return ("less than %s" % shown, _URMP_NOSET)
        if op in ("in", "not in") and isinstance(lit, (list, tuple)):
            shown = ", ".join(_urmp_plain(_urmi_show(v), 30) for v in lit[:6])
            if op == "in":
                return ("one of %s" % shown, lit[0] if lit else _URMP_NOSET)
            return ("none of %s" % shown, _URMP_NOSET)
        return (None, _URMP_NOSET)

    def _urmp_simple(atom, target):
        """
        (words, set value) when `atom` is a plain test of `target` - flag,
        not flag, target op literal, "x" in target - else None.
        """

        flagname = _urmfl_name_of(atom) if isinstance(atom, (_urmi_ast.Call, _urmi_ast.Compare)) else None
        if flagname is not None:
            if flagname != target:
                return None
            if isinstance(atom, _urmi_ast.Compare) and isinstance(atom.ops[0], _urmi_ast.NotIn):
                return ("OFF", False)
            return ("ON", True)
        if isinstance(atom, _urmi_ast.UnaryOp) and isinstance(atom.op, _urmi_ast.Not) and \
                isinstance(atom.operand, (_urmi_ast.Call, _urmi_ast.Compare)):
            flagname = _urmfl_name_of(atom.operand)
            if flagname is not None:
                return ("OFF", False) if flagname == target else None
        if isinstance(atom, (_urmi_ast.Name, _urmi_ast.Attribute, _urmi_ast.Subscript)):
            if _urmi_name(atom) == target:
                return ("ON", True)
            return None
        if isinstance(atom, _urmi_ast.UnaryOp) and isinstance(atom.op, _urmi_ast.Not):
            if _urmi_name(atom.operand) == target:
                return ("OFF", False)
            return None
        if isinstance(atom, _urmi_ast.Compare) and len(atom.ops) == 1:
            op = _URMI_OPS.get(type(atom.ops[0]))
            left, right = atom.left, atom.comparators[0]
            if op in ("in", "not in"):
                ok, token = _urmi_literal(left)
                if ok and _urmi_name(right) == target:
                    shown = _urmp_plain(_urmi_show(token), 50)
                    if op == "in":
                        return ("contains %s" % shown, _URMP_NOSET)
                    return ("doesn't contain %s" % shown, _URMP_NOSET)
                if _urmi_name(left) == target and isinstance(right, (_urmi_ast.List, _urmi_ast.Tuple)):
                    values = python_list()
                    for elt in right.elts:
                        ok, v = _urmi_literal(elt)
                        if not ok:
                            return None
                        values.append(v)
                    words, value = _urmp_opwords(op, values)
                    if words:
                        return (words, value)
                return None
            if op is None:
                return None
            if _urmi_name(left) == target:
                ok, lit = _urmi_literal(right)
                if ok:
                    words, value = _urmp_opwords(op, lit)
                    if words:
                        return (words, value)
            if _urmi_name(right) == target:
                ok, lit = _urmi_literal(left)
                if ok:
                    words, value = _urmp_opwords(_URMI_FLIP.get(op, op), lit)
                    if words:
                        return (words, value)
        return None

    def _urmp_band(atoms, target, now):
        """
        Words for a numeric requirement that is not a plain literal test -
        love < hard_love - 30 - by trying whole numbers with everything else
        at its value now. (words, set value) or None.
        """

        lits = python_list()
        others = python_list()
        for atom in atoms:
            for sub in _urmi_ast.walk(atom):
                ok, v = _urmi_literal(sub)
                if ok and _urmp_isnum(v):
                    lits.append(v)
            for name in _urmp_names_in(atom):
                if name != target and name not in others:
                    others.append(name)
        spread = python_list()
        spread.append(100)
        for v in lits:
            spread.append(abs(int(v)))
        for name in others:
            v = _urmp_value(name)
            if _urmp_isnum(v):
                spread.append(abs(int(v)) * 2)
        if _urmp_isnum(now):
            spread.append(abs(int(now)) * 2)
        hi = min(max(spread) + 5, 600)
        lo = -5
        for v in lits:
            if v < 0:
                lo = max(int(v) - 5, -600)

        runs = python_list()
        start = None
        for c in range(lo, hi + 1):
            passed = True
            for atom in atoms:
                r = _urmp_ev(atom, target, c)
                if r is _URMP_UNK:
                    return None
                if not r:
                    passed = False
                    break
            if passed and start is None:
                start = c
            elif not passed and start is not None:
                runs.append((start, c - 1))
                start = None
        if start is not None:
            runs.append((start, hi))

        if not runs:
            words, value = "never, with things as they are", _URMP_NOSET
        elif len(runs) > 1:
            return None
        else:
            a, b = runs[0]
            if a == lo and b == hi:
                words, value = "any number, with things as they are", _URMP_NOSET
            elif a == lo:
                words, value = "%d or less" % b, b
            elif b == hi:
                words, value = "%d or more" % a, a
            elif a == b:
                words, value = "exactly %d" % a, a
            else:
                words, value = "%d to %d" % (a, b), a

        if others:
            parts = python_list()
            for name in others[:2]:
                v = _urmp_value(name)
                if v is _URMP_UNK:
                    parts.append(name)
                else:
                    parts.append("%s at %s" % (name, _urmp_plain(_urmi_show(v), 20)))
            words += " (with %s now)" % " and ".join(parts)
        return (words, value)

    def _urmp_have(name):
        v = _urmp_value(name)
        if v is _URMP_UNK:
            return None
        if v is True:
            return "it's ON"
        if v is False:
            return "it's OFF"
        if v is None:
            return "it's empty"
        if _urmp_isnum(v) or isinstance(v, _urmi_text):
            return "you have %s" % _urmp_plain(_urmi_show(v), 30)
        return None

    def _urmp_need(atom):
        """Another requirement in words, with its name linked: (words, met now)."""

        met = _urmp_ev(atom)
        names = _urmp_names_in(atom)
        words = None
        if len(names) == 1:
            simple = _urmp_simple(atom, names[0])
            if simple is not None:
                words = u"%s %s" % (_urmp_link(names[0]), simple[0])
                have = _urmp_have(names[0])
                if have and met is not True:
                    words += " (%s)" % have
        if words is None:
            text = _urmp_src(atom)
            if text is None:
                words = "another condition (see Code)"
            else:
                words = u"%s" % _urmp_plain(text, 80)
        return (words, met)


    # ------------------------------------------------------------------
    # One row per place the game checks the name
    # ------------------------------------------------------------------

    class _URMPRow(python_object):
        pass

    def _urmp_names_of(index, cond):
        cache = _urmp_bucket("condnames")
        try:
            return cache[cond]
        except KeyError:
            pass
        names = python_set()
        for kind, a, b, _c in index._condition(cond):
            if kind == "token":
                names.add(b)
            elif kind != "call":
                names.add(a)
        tree = _urmp_parse(cond)
        if tree is not None and index.flags:
            for name in _urmp_names_in(tree):
                names.add(name)
        cache[cond] = names
        return names

    def _urmp_scene(index, node, filename, line):
        cur = node
        guard = 0
        while cur is not None and guard < 200:
            guard += 1
            link = index.parent.get(id(cur))
            if link is None:
                break
            parent, kind, extra = link
            if kind == "label" and isinstance(extra, _urmi_text):
                return extra
            cur = parent
        return index.label_at(filename, line)

    def _urmp_scene_name(scene, filename):
        if isinstance(scene, _urmi_text):
            return scene
        return u"early in %s" % ((filename or "?").split("/")[-1],)

    def _urmp_rows(index, name):
        rows = python_list()
        done = python_set()
        ast = renpy.ast
        for site, _op, _lit in index.reads.get(name) or ():
            nid = site[2]
            if nid in done:
                continue
            done.add(nid)
            node = index.nodes.get(nid)
            if node is None:
                continue
            fn = getattr(node, "filename", "?")
            ln = getattr(node, "linenumber", 0)
            if (fn, ln) in done:
                continue
            done.add((fn, ln))
            scene = _urmp_scene(index, node, fn, ln)
            scene_text = _urmp_scene_name(scene, fn)

            def make(kind, cond, block):
                r = _URMPRow()
                r.node = node
                r.kind = kind
                r.cond = cond
                r.block = block
                r.other = None
                r.other_kind = None
                r.option = None
                r.scene = scene_text
                r.label = scene
                r.file = fn
                r.line = ln
                return r

            if isinstance(node, ast.If):
                entries = node.entries
                for i, (cond, block) in enumerate(entries):
                    if not cond or cond.strip() == "True":
                        continue
                    if name not in _urmp_names_of(index, cond):
                        continue
                    r = make("if", cond, block)
                    if i + 1 < len(entries):
                        nxt_cond, nxt_block = entries[i + 1]
                        if nxt_cond.strip() == "True":
                            r.other = nxt_block
                            r.other_kind = "else"
                        else:
                            r.other_kind = "elif"
                    rows.append(r)
            elif isinstance(node, ast.Menu):
                for item in node.items:
                    cond = item[1]
                    if not cond or cond.strip() == "True" or item[2] is None:
                        continue
                    if name not in _urmp_names_of(index, cond):
                        continue
                    r = make("option", cond, item[2])
                    r.option = item[0]
                    rows.append(r)
            elif isinstance(node, ast.While):
                rows.append(make("loop", node.condition, node.block))
        return rows

    def _urmp_atoms(cond, name):
        tree = _urmp_parse(cond)
        if tree is None:
            return (None, python_list(), python_list())
        if isinstance(tree, _urmi_ast.BoolOp) and isinstance(tree.op, _urmi_ast.And):
            parts = tree.values
        else:
            parts = python_list()
            parts.append(tree)
        mine = python_list()
        others = python_list()
        for part in parts:
            if name in _urmp_names_in(part) or _urmp_simple(part, name) is not None:
                mine.append(part)
            else:
                others.append(part)
        return (tree, mine, others)

    def _urmp_requirement(row, name, now):
        """(words, set value, sort number) for this variable's part of the row."""

        cache = _urmp_bucket("req")
        key = (row.cond, name)
        if key in cache:
            return cache[key]
        _tree, mine, _others = _urmp_atoms(row.cond, name)
        result = None
        if len(mine) == 1:
            simple = _urmp_simple(mine[0], name)
            if simple is not None:
                result = simple
        if result is None and mine and (_urmp_isnum(now) or now is _URMP_UNK):
            result = _urmp_band(mine, name, now)
        if result is None:
            text = _urmp_src(mine[0]) if len(mine) == 1 else None
            if text:
                result = (u"when %s" % _urmp_plain(text, 80), _URMP_NOSET)
            else:
                result = ("a condition shown in Code", _URMP_NOSET)
        words, value = result
        sort = value if _urmp_isnum(value) else None
        out = (words, value, sort)
        cache[key] = out
        return out


    # ------------------------------------------------------------------
    # Where the player is, and what they have seen
    # ------------------------------------------------------------------

    def _urmp_current(index):
        """(node name, scene, filename, line) of the statement the game is on."""

        try:
            name = renpy.game.context().current
            node = renpy.game.script.lookup(name)
        except Exception:
            return None
        if node is None:
            return None
        fn = getattr(node, "filename", None)
        ln = getattr(node, "linenumber", 0)
        return (name, _urmp_scene(index, node, fn, ln), fn, ln, id(node))

    class _URMPSeen(python_object):
        def __init__(self):
            self.labels = python_dict()
            try:
                self.ever = renpy.game.persistent._seen_ever
            except Exception:
                self.ever = None
            try:
                if _preferences.language is not None:
                    self.ever = None
            except Exception:
                pass
            try:
                self.chosen = renpy.game.persistent._chosen
            except Exception:
                self.chosen = None

        def label(self, label):
            if not isinstance(label, _urmi_text):
                return None
            try:
                return self.labels[label]
            except KeyError:
                pass
            if len(self.labels) > 400:
                return None
            found = urm_seen(label)
            self.labels[label] = found
            return found

        def node(self, node):
            if self.ever is None or node is None:
                return None
            try:
                return node.name in self.ever
            except Exception:
                return None

        def picked(self, menu, option):
            if self.chosen is None or not option or "[" in option:
                return None
            try:
                return (menu.name, option) in self.chosen
            except Exception:
                return None

    def _urmp_status(scene, filename, line, first_node, cur, seen):
        if cur is not None and scene is not None and scene == cur[1] and filename == cur[2]:
            if line > cur[3]:
                return "later"
            return "above"
        played = seen.label(scene)
        if played is False:
            return "not"
        if played is True:
            saw = seen.node(first_node)
            if saw is False:
                return "never"
            return "played"
        return ""


    # ------------------------------------------------------------------
    # Who sets it
    # ------------------------------------------------------------------

    class _URMPWrite(python_object):
        pass

    def _urmp_question(index, menu):
        """The line the choice answers: the menu's own caption, or the say before it."""

        for item in menu.items:
            if item[2] is None and item[0]:
                return _urmp_plain(item[0], 90)
        link = index.parent.get(id(menu))
        if link is None:
            return None
        parent = link[0]
        ast = renpy.ast
        if isinstance(parent, ast.If):
            blocks = [b for _c, b in parent.entries]
        elif isinstance(parent, ast.Menu):
            blocks = [i[2] for i in parent.items if i[2]]
        else:
            blocks = [getattr(parent, "block", None) or ()]
        for block in blocks:
            for i, n in enumerate(block):
                if n is menu:
                    for back in reversed(block[max(0, i - 4):i]):
                        if isinstance(back, ast.Say):
                            return _urmp_say_line(back, 90)
                        if isinstance(back, ast.Translate):
                            for s in back.block or ():
                                if isinstance(s, ast.Say):
                                    return _urmp_say_line(s, 90)
                    return None
        return None

    def _urmp_writes(index, name):
        """Every assignment of `name`, with the choice or the condition behind it."""

        out = python_list()
        done = python_set()
        for site, op, value, _text in index.writes.get(name) or ():
            key = (site[0], site[1], op, repr(value))
            if key in done:
                continue
            done.add(key)
            node = index.nodes.get(site[2])
            w = _URMPWrite()
            w.op = op
            w.value = value
            w.ok = value is not None or op == "="
            w.node = node
            w.file = site[0]
            w.line = site[1]
            w.label = _urmp_scene(index, node, site[0], site[1])
            w.scene = _urmp_scene_name(w.label, site[0])
            w.menu = None
            w.option = None
            w.cond = None
            w.unless = None
            cur = node
            guard = 0
            while cur is not None and guard < 200:
                guard += 1
                link = index.parent.get(id(cur))
                if link is None:
                    break
                parent, kind, extra = link
                if kind == "option":
                    w.menu = parent
                    w.option = extra
                    break
                if kind == "if" and w.cond is None and w.unless is None:
                    if extra and extra.strip() != "True":
                        w.cond = extra
                    else:
                        before = python_list()
                        for c, _b in parent.entries:
                            if c and c.strip() != "True":
                                before.append(c)
                        if before:
                            w.unless = before
                if kind == "label":
                    break
                cur = parent
            out.append(w)
        return out

    def _urmp_value_ok(w):
        """Whether the literal in a write is known - None from the index means 'computed'."""

        if w.op == "=":
            return w.value is not None or _urmp_assign_none(w)
        return w.value is not None

    def _urmp_assign_none(w):
        node = w.node
        source = getattr(getattr(node, "code", None), "source", "") or ""
        return "None" in source

    def _urmp_effect(w, now, boolish):
        """(words, set value) for what one write does to the name."""

        op, value = w.op, w.value
        ok = _urmp_value_ok(w)
        if op == "=":
            if not ok:
                return ("changes it (worked out by the game)", _URMP_NOSET)
            if boolish and value in (True, False) and not isinstance(value, _urmi_text):
                return ("turns it ON" if value else "turns it OFF", value)
            return ("sets it to %s" % _urmp_plain(_urmi_show(value), 50), value)
        if op in ("+=", "-=") and ok and _urmp_isnum(value):
            delta = value if op == "+=" else -value
            sign = "+" if delta >= 0 else "-"
            text = "%s%s" % (sign, _urmi_show(abs(delta)))
            if _urmp_isnum(now):
                return ("%s (you'd have %s)" % (text, _urmi_show(now + delta)), now + delta)
            return (text, _URMP_NOSET)
        if op in (".append", ".add") and ok:
            return ("adds %s" % _urmp_plain(_urmi_show(value), 40), _URMP_NOSET)
        if op in (".remove", ".discard") and ok:
            return ("removes %s" % _urmp_plain(_urmi_show(value), 40), _URMP_NOSET)
        return ("changes it", _URMP_NOSET)

    def _urmp_effect_named(w, name):
        """What a write does, as a phrase that names the variable."""

        op, value = w.op, w.value
        ok = _urmp_value_ok(w)
        if op == "=" and ok:
            if value is True:
                return "turns %s ON" % name
            if value is False:
                return "turns %s OFF" % name
            return "sets %s to %s" % (name, _urmp_plain(_urmi_show(value), 40))
        if op in ("+=", "-=") and ok and _urmp_isnum(value):
            up = (op == "+=") == (value >= 0)
            return "%s %s by %s" % ("raises" if up else "lowers", name, _urmi_show(abs(value)))
        if op in (".append", ".add") and ok:
            return "adds %s to %s" % (_urmp_plain(_urmi_show(value), 40), name)
        if op in (".remove", ".discard") and ok:
            return "removes %s from %s" % (_urmp_plain(_urmi_show(value), 40), name)
        return "changes %s" % name

    def _urmp_cond_words(cond, skip=None):
        """A whole condition in words, every name linked."""

        tree = _urmp_parse(cond)
        if tree is None:
            return _urmp_plain(cond, 80)
        if isinstance(tree, _urmi_ast.BoolOp) and isinstance(tree.op, _urmi_ast.And):
            parts = tree.values
        else:
            parts = python_list()
            parts.append(tree)
        words = python_list()
        for part in parts:
            words.append(_urmp_need(part)[0])
        return " and ".join(words)

    def _urmp_mass_labels(index):
        """Labels that set 15+ different names at once: chapter select, skip menus."""

        cache = _urmp_bucket("mass")
        key = id(index), index.finished_at
        if cache.get("key") == key:
            return cache["labels"]
        tally = python_dict()
        total = 0
        for name, bucket in index.writes.items():
            total += len(bucket)
            if total > 60000:
                break
            for site, _op, _v, _t in bucket:
                label = index.label_at(site[0], site[1])
                if label is None:
                    continue
                names = tally.get(label)
                if names is None:
                    names = python_set()
                    tally[label] = names
                names.add(name)
        found = python_set()
        for label, names in tally.items():
            if len(names) >= 15:
                found.add(label)
        cache["key"] = key
        cache["labels"] = found
        return found

    def _urmp_function_mentions(name):
        """Names of the game's own functions whose code mentions `name`."""

        cache = _urmp_bucket("funcs")
        if "map" not in cache:
            import types
            found = python_dict()
            count = 0
            try:
                for fname, value in python_list(renpy.store.__dict__.items()):
                    if not isinstance(value, types.FunctionType):
                        continue
                    count += 1
                    if count > 5000:
                        break
                    code = getattr(value, "__code__", None) or getattr(value, "func_code", None)
                    stack = python_list()
                    stack.append(code)
                    seen_names = python_set()
                    while stack:
                        c = stack.pop()
                        if c is None:
                            continue
                        for n in c.co_names:
                            seen_names.add(n)
                        for const in c.co_consts:
                            if hasattr(const, "co_names"):
                                stack.append(const)
                    if fname.startswith("_urm") or fname.startswith("urm"):
                        continue
                    for n in seen_names:
                        bucket = found.get(n)
                        if bucket is None:
                            bucket = python_list()
                            found[n] = bucket
                        if len(bucket) < 6:
                            bucket.append(fname)
            except Exception:
                pass
            cache["map"] = found
        base = _urmp_re.split(r"[.\[]", name, 1)[0]
        return cache["map"].get(base) or ()


    # ------------------------------------------------------------------
    # The panel
    # ------------------------------------------------------------------

    class _URMPanel(python_object):
        def __init__(self, name):
            self.name = name
            self.state = "ready"
            self.pct = None
            self.message = None
            self.answer = python_list()
            self.now_header = None
            self.now_lines = python_list()
            self.later = python_list()
            self.warnings = python_list()
            self.okline = None
            self.tabs = python_list()
            self.tab = "gives"
            self.blocks = python_list()
            self.gives_tail = python_list()
            self.choices = python_list()
            self.choices_tail = python_list()
            self.details = python_list()
            self.detail_checks = python_list()
            self.footer = python_list()
            self.next_line = None
            self.next_value = _URMP_NOSET
            self.deps = None
            self.mode = None

    class _URMPBlock(python_object):
        def __init__(self, header, value=None, sub=None):
            self.header = header
            self.value = _URMP_NOSET if value is None else value
            self.sub = sub
            self.rows = python_list()
            self.small = python_list()
            self.marker = False
            self.key = header

    def _urmp_row_view(index, r, name, now, cur, seen, budget):
        """The drawable form of a row: status, head, quote, extra lines, code."""

        if not hasattr(r, "summary"):
            r.summary = _urmp_summary(r.block, budget, 6)
            r.other_summary = _urmp_summary(r.other, budget, 3) if r.other else None
        s = r.summary
        r.status = _urmp_status(r.label, r.file, r.line, s.first_node, cur, seen)
        r.weight = _urmp_weight(s, index, budget)
        r.size = _urmp_size_words(s, index, budget)

        head = u"%s  \u00b7  %s" % (r.scene, r.size)
        if r.kind == "option":
            quote = u'the choice "%s" appears' % _urmp_plain(r.option, 80)
        elif r.kind == "loop":
            quote = "repeats while this holds"
        elif s.first:
            quote = s.first
        elif s.target:
            quote = None
        else:
            quote = None

        extra = python_list()
        _tree, _mine, others = _urmp_atoms(r.cond, name)
        r.needs_unmet = python_list()
        for atom in others[:3]:
            words, met = _urmp_need(atom)
            extra.append(u"also needs %s" % words)
            if met is not True:
                r.needs_unmet.append(words)
        if r.other_summary is not None:
            o = r.other_summary
            if o.lines or o.target or o.calls:
                text = u"otherwise: %s" % _urmp_size_words(o, index, budget)
                if o.first:
                    text += u" - %s" % o.first
                extra.append(text)
            for w in o.writes:
                if w[0] == name:
                    extra.append(u"and otherwise the game %s here" % _urmp_write_words(w)[1:-1])
                    break

        r.view_status = _URMP_STATUS_TEXT.get(r.status, "")
        r.view_head = head
        r.view_quote = quote
        r.view_extra = extra
        r.view_lines = s.preview
        r.view_replay = r.label if isinstance(r.label, _urmi_text) and r.label in index.labels else None
        r.key = "%s:%s:%s" % (r.file, r.line, r.cond)
        r.view_code = _urmp_code(r)
        return r

    def _urmp_stmt_code(node, indent, out, limit):
        ast = renpy.ast
        pad = "    " * indent
        if len(out) >= limit:
            return
        if isinstance(node, ast.Translate):
            for child in node.block or ():
                _urmp_stmt_code(child, indent, out, limit)
        elif isinstance(node, ast.Say):
            who = getattr(node, "who", None)
            what = (getattr(node, "what", "") or "").replace("\n", " ")
            if len(what) > 120:
                what = what[:117] + "..."
            out.append(u'%s%s"%s"' % (pad, (who + " ") if who else "", what))
        elif isinstance(node, (ast.Show, ast.Scene)) and getattr(node, "imspec", None):
            out.append(u"%s%s %s" % (pad, type(node).__name__.lower(), " ".join(node.imspec[0])))
        elif isinstance(node, ast.Python):
            source = getattr(getattr(node, "code", None), "source", "") or ""
            for line in source.split("\n")[:4]:
                out.append(u"%s$ %s" % (pad, line.strip()))
        elif isinstance(node, ast.Jump):
            out.append(u"%sjump %s" % (pad, node.target))
        elif isinstance(node, ast.Call):
            out.append(u"%scall %s" % (pad, node.label))
        elif isinstance(node, ast.If):
            for i, (cond, block) in enumerate(node.entries):
                if i == 0:
                    out.append(u"%sif %s:" % (pad, cond))
                elif cond.strip() == "True":
                    out.append(u"%selse:" % pad)
                else:
                    out.append(u"%selif %s:" % (pad, cond))
                for child in (block or ())[:3]:
                    _urmp_stmt_code(child, indent + 1, out, limit)
        elif isinstance(node, ast.Menu):
            out.append(u"%smenu:" % pad)
            for item in node.items:
                if item[2] is not None:
                    out.append(u'%s    "%s"%s:' % (pad, item[0], "" if item[1] in (None, "True") else " if " + item[1]))
        elif isinstance(node, ast.Return):
            out.append(u"%sreturn" % pad)

    def _urmp_code(r):
        out = python_list()
        out.append(u"# %s, %s line %s" % (r.scene, (r.file or "?").split("/")[-1], r.line))
        if r.kind == "option":
            out.append(u"menu:")
            out.append(u'    "%s" if %s:' % (r.option, r.cond))
            for child in (r.block or ())[:14]:
                _urmp_stmt_code(child, 2, out, 18)
        elif r.kind == "loop":
            out.append(u"while %s:" % r.cond)
            for child in (r.block or ())[:12]:
                _urmp_stmt_code(child, 1, out, 16)
        else:
            out.append(u"if %s:" % r.cond)
            for child in (r.block or ())[:12]:
                _urmp_stmt_code(child, 1, out, 16)
            if r.other is not None:
                out.append(u"else:")
                for child in (r.other or ())[:6]:
                    _urmp_stmt_code(child, 1, out, 24)
            elif r.other_kind == "elif":
                out.append(u"elif ...")
        return u"\n".join(out)

    def _urmp_sort(rows):
        rows.sort(key=lambda r: (_URMP_STATUS_RANK.get(r.status, 4), -r.weight))
        return rows

    def _urmp_fill_block(block, rows):
        """Big rows shown, small ones (3 lines or fewer) folded per scene."""

        for r in _urmp_sort(rows):
            if r.weight <= 3 and r.kind != "option" and not r.needs_unmet:
                block.small.append(r)
            else:
                block.rows.append(r)
        if not block.rows and block.small:
            block.rows = block.small
            block.small = python_list()

    def _urmp_small_line(block):
        if not block.small:
            return None
        scenes = python_list()
        never = 0
        for r in block.small:
            if r.scene not in scenes:
                scenes.append(r.scene)
            if r.status in ("not", "never"):
                never += 1
        text = u"+ %d small change%s (3 lines or fewer) in %s" % (
            len(block.small), "" if len(block.small) == 1 else "s",
            ", ".join(u"%s" % s for s in scenes[:3]) + (" and more" if len(scenes) > 3 else ""))
        if never:
            text += u" - %d not seen" % never
        return text

    def _urmp_mode(index, name, now):
        reads = index.reads.get(name) or ()
        boolish = 0
        nums = 0
        texts = 0
        for _s, op, lit in reads:
            if op in ("truthy", "falsy") or lit is True or lit is False:
                boolish += 1
            elif _urmp_isnum(lit):
                nums += 1
            elif isinstance(lit, _urmi_text) and op in ("==", "!="):
                texts += 1
        total = max(len(reads), 1)
        if isinstance(now, bool):
            return "bool"
        if (now is _URMP_UNK or now in (0, 1)) and boolish * 10 > total * 6 and not nums:
            return "bool"
        if _urmp_isnum(now) or (now is _URMP_UNK and nums >= texts and nums):
            return "number"
        if isinstance(now, _urmi_text) or (now is _URMP_UNK and texts):
            return "value"
        return "generic"

    def urm_panel(name):
        """Everything the variable panel draws, cached per name, value and position."""

        state, pct = urm_index_status()
        if state != "ready":
            p = _URMPanel(name)
            p.state = state
            p.pct = pct
            if state == "building":
                p.message = "Reading the game's script... %s%%. This fills in when it's done." % (pct or 0)
            elif state == "failed":
                p.message = "Couldn't read the game's script, so this can't show what %s does." % name
            else:
                p.message = None
            return p

        index = _urmi_index()
        now = _urmp_value(name)
        cur = _urmp_current(index)
        try:
            lang = _preferences.language
        except Exception:
            lang = None
        try:
            shown = repr(now)[:120]
        except Exception:
            shown = "?"
        key = (id(index), index.finished_at, name, shown, cur[0] if cur else None, lang)
        cache = _urmp_bucket("panels")
        found = cache.get(key)
        if found is not None and _urmp_deps_hold(found.deps):
            return found
        # Per-open caches: words like "(with hard_love at 30 now)" and
        # speaker names depend on values that may have changed since.
        st = _urmp_state()
        st["req"] = python_dict()
        st["speakers"] = python_dict()
        st["deps"] = python_dict()
        try:
            p = _urmp_compose(index, name, now, cur)
            p.deps = st["deps"]
        except Exception as error:
            p = _URMPanel(name)
            p.state = "failed"
            p.message = "The panel hit a problem reading %s (%s). URM's own editor above still works." % (
                name, _urmp_plain(u"%s: %s" % (type(error).__name__, error), 120))
            import traceback
            traceback.print_exc()
        st["deps"] = None
        if len(cache) >= 8:
            cache.clear()
        cache[key] = p
        return p

    def _urmp_deps_hold(deps):
        """The values a cached panel was worked out from are still the same."""

        if not deps:
            return True
        for dep, value in deps.items():
            current = _urmp_value(dep)
            if current is _URMP_UNK or type(current) is not type(value) or current != value:
                return False
        return True

    def _urmp_compose(index, name, now, cur):
        p = _URMPanel(name)
        budget = python_list()
        budget.append(_URMP_NODE_BUDGET)
        seen = _URMPSeen()
        mode = _urmp_mode(index, name, now)
        p.mode = mode
        boolish = mode == "bool"
        on_value, off_value = True, False
        if boolish and _urmp_isint(now):
            on_value, off_value = 1, 0

        def onoff(v):
            return "ON" if v else "OFF"

        rows = _urmp_rows(index, name)
        writes = _urmp_writes(index, name)
        funcs = _urmp_function_mentions(name)
        mass = _urmp_mass_labels(index) if writes else python_set()

        if now is _URMP_UNK:
            now_words = "not set yet"
        elif boolish:
            now_words = onoff(now)
        else:
            now_words = _urmp_plain(_urmi_show(now), 60)

        # --- edge states -------------------------------------------------
        if not rows and not writes:
            if funcs:
                p.message = (u"The story script never uses %s directly. The game's own code mentions it in %s. "
                             u"What that code does with it isn't shown." % (name, ", ".join("%s()" % f for f in funcs[:3])))
            else:
                p.message = (u"The story script never checks or sets %s by name. "
                             u"It may still be used in the game's screens or its own code." % name)
            return p

        for r in rows:
            _urmp_row_view(index, r, name, now, cur, seen, budget)

        loops = [r for r in rows if r.kind == "loop"]
        rows = [r for r in rows if r.kind != "loop"]

        # Identical outcomes (281 x "jump resetGalleryVar") collapse to one line.
        groups = python_dict()
        for r in rows:
            s = r.summary
            if s.lines or s.choice or r.kind == "option":
                continue
            if s.target:
                sig = u"goes to %s" % s.target
            elif s.calls:
                sig = u"plays %s" % s.calls[0]
            elif s.funcs:
                sig = u"runs the game's code (%s)" % s.funcs[0]
            elif s.writes:
                sig = _urmp_write_words(s.writes[0])[1:-1]
            else:
                continue
            groups.setdefault((r.cond, sig), python_list()).append(r)
        collapsed = python_set()
        collapse_lines = python_list()
        biggest_group = None
        for (cond, sig), members in groups.items():
            if len(members) < 5:
                continue
            for r in members:
                collapsed.add(id(r))
            scenes = python_set()
            for r in members:
                scenes.add(r.scene)
            req = _urmp_requirement(members[0], name, now)[0]
            line = u"In %d places in %d scene%s: when it is %s \u2192 the game %s (no dialogue)." % (
                len(members), len(scenes), "" if len(scenes) == 1 else "s", req, sig)
            collapse_lines.append(line)
            if biggest_group is None or len(members) > biggest_group[0]:
                biggest_group = (len(members), req, sig)
        shown_rows = [r for r in rows if id(r) not in collapsed]

        # Rows that only change other values, with no dialogue at all.
        quiet = [r for r in shown_rows if not r.summary.lines and not r.summary.target
                 and not r.summary.calls and not r.summary.choice and r.kind != "option"
                 and not r.summary.pictures]
        quiet_ids = python_set(id(r) for r in quiet)
        shown_rows = [r for r in shown_rows if id(r) not in quiet_ids]

        # --- writers -----------------------------------------------------
        menus = python_dict()
        menu_order = python_list()
        auto = python_list()
        mass_hidden = python_dict()
        for w in writes:
            w.status = _urmp_status(w.label, w.file, w.line, None, cur, seen)
            if w.menu is not None:
                # An option that names the variable itself - "set
                # switch_213 to True" - is the game's own scene-select or
                # cheat menu, not a story choice.
                if w.scene in mass or name.lower() in (u"%s" % (w.option,)).lower():
                    mass_hidden.setdefault(w.scene, python_list()).append(w)
                    continue
                g = menus.get(id(w.menu))
                if g is None:
                    g = python_list()
                    menus[id(w.menu)] = g
                    menu_order.append(w.menu)
                g.append(w)
            else:
                auto.append(w)

        current_menu = None
        if cur is not None:
            for m in menu_order:
                if id(m) == cur[4]:
                    current_menu = m
            for r in rows:
                if r.kind == "option" and id(r.node) == cur[4]:
                    current_menu = r.node

        choice_count = len(menu_order)
        option_count = 0
        for m in menu_order:
            options = python_set()
            for w in menus[id(m)]:
                options.add(w.option)
            option_count += len(options)

        # --- A. the answer -----------------------------------------------
        ahead = [r for r in shown_rows if r.status in ("later", "not")]
        A = p.answer

        if biggest_group is not None and biggest_group[0] * 10 >= len(rows) * 8:
            A.append(u"%s is %s. Almost every check (%d of %d) does the same thing: when it is %s, the game %s (no dialogue)." % (
                name, now_words, biggest_group[0], len(rows), biggest_group[1], biggest_group[2]))
        elif mode == "bool":
            on_rows = python_list()
            off_rows = python_list()
            both = python_list()
            for r in shown_rows:
                _t, mine, _o = _urmp_atoms(r.cond, name)
                on = all(_urmp_ev(a, name, on_value) is True for a in mine) if mine else False
                off = all(_urmp_ev(a, name, off_value) is True for a in mine) if mine else False
                if on == off:
                    r.side = None
                    both.append(r)
                    continue
                r.side = "on" if on else "off"
                if r.other_summary is not None and r.other_summary.lines:
                    both.append(r)
                elif on:
                    on_rows.append(r)
                else:
                    off_rows.append(r)
            on_lines = sum(r.weight for r in on_rows)
            off_lines = sum(r.weight for r in off_rows)
            text = u"%s is %s." % (name, now_words)
            if on_rows:
                text += u" ON plays something extra in %d place%s (about %d lines)." % (
                    len(on_rows), "" if len(on_rows) == 1 else "s", on_lines)
            if off_rows:
                text += u" OFF has its own lines in %d place%s (about %d lines)." % (
                    len(off_rows), "" if len(off_rows) == 1 else "s", off_lines)
            diff = [r for r in both if r.side is not None]
            if diff:
                text += u" Different version either way: %d place%s." % (len(diff), "" if len(diff) == 1 else "s")
            A.append(text)
            big = None
            for r in on_rows + off_rows:
                if r.needs_unmet and r.weight >= 100 and (big is None or r.weight > big.weight):
                    big = r
            if big is not None:
                A.append(u"The biggest (about %d lines, %s) also needs %s." % (big.weight, big.scene, big.needs_unmet[0]))

            sub_on = _urmp_choice_hint(writes, on_value, mass)
            sub_off = _urmp_choice_hint(writes, off_value, mass)
            b = _URMPBlock(u"ONLY WITH ON  (%d place%s, about %d lines)" % (len(on_rows), "" if len(on_rows) == 1 else "s", on_lines), on_value, sub_on)
            _urmp_fill_block(b, on_rows)
            if on_rows:
                p.blocks.append(b)
            b = _URMPBlock(u"ONLY WITH OFF  (%d place%s, about %d lines)" % (len(off_rows), "" if len(off_rows) == 1 else "s", off_lines), off_value, sub_off)
            _urmp_fill_block(b, off_rows)
            if off_rows:
                p.blocks.append(b)
            if diff:
                b = _URMPBlock(u"A DIFFERENT VERSION EITHER WAY  (%d place%s)" % (len(diff), "" if len(diff) == 1 else "s"))
                for r in diff:
                    o = r.other_summary
                    side = "ON" if r.side == "on" else "OFF"
                    other = "OFF" if r.side == "on" else "ON"
                    r.view_head = u"%s  \u00b7  %s: %s / %s: %s" % (
                        r.scene, side, r.size, other, _urmp_size_words(o, index, budget))
                    r.view_quote = u"%s: %s" % (side, r.summary.first or "(no dialogue)")
                    keep = python_list()
                    keep.append(u"%s: %s" % (other, o.first or "(no dialogue)"))
                    for e in r.view_extra:
                        if not e.startswith("otherwise:"):
                            keep.append(e)
                    r.view_extra = keep
                    r.weight = max(r.weight, _urmp_weight(o, index, budget))
                _urmp_fill_block(b, diff)
                p.blocks.append(b)
            rest = [r for r in both if r.side is None]
            if rest:
                b = _URMPBlock(u"CHECKED TOGETHER WITH OTHER THINGS  (%d)" % len(rest))
                for r in rest:
                    r.view_extra.insert(0, u"when %s" % _urmp_cond_words(r.cond))
                _urmp_fill_block(b, rest)
                p.blocks.append(b)

        elif mode == "number":
            ladder = python_dict()
            exact_only = True
            numeric_seen = False
            rival = 0
            for r in shown_rows:
                words, value, sort = _urmp_requirement(r, name, now)
                if sort is not None:
                    numeric_seen = True
                    if not words.startswith("exactly"):
                        exact_only = False
                relative = None
                if "(with " in words:
                    exact_only = False
                    words, relative = words.split(" (with ", 1)
                    relative = u"with " + relative[:-1]
                b = ladder.get(words)
                if b is None:
                    b = _URMPBlock(words, value)
                    b.sort = sort
                    b.relative = python_list()
                    ladder[words] = b
                if relative and relative not in b.relative:
                    b.relative.append(relative)
                    b.sub = u"; ".join(b.relative[:2]) + (
                        u" - it moves when that changes" if len(b.relative) == 1 else u" - it moves when those change")
                if relative:
                    rival += 1
                b.rows.append(r)
            blocks = python_list(ladder.values())
            for b in blocks:
                members = b.rows
                b.rows = python_list()
                _urmp_fill_block(b, members)
            blocks.sort(key=lambda b: (b.sort is None, b.sort if b.sort is not None else 0,
                                       0 if b.header.startswith("exactly") else 1, b.header))
            if _urmp_isnum(now):
                marker = _URMPBlock(u"\u2500\u2500  you: %s  \u2500\u2500" % _urmi_show(now))
                marker.marker = True
                pos = 0
                for i, b in enumerate(blocks):
                    if b.sort is not None and b.sort <= now:
                        pos = i + 1
                blocks.insert(pos, marker)
            p.blocks = blocks

            reqs = [b.header for b in blocks if not b.marker and b.sort is not None]
            if exact_only and numeric_seen and len(reqs) >= 2:
                nums = [_urmi_show(b.sort) for b in blocks if not b.marker and b.sort is not None]
                text = u"%s is %s. The game only checks exact numbers: %s. Any other number matches nothing." % (
                    name, now_words, _urmp_some(nums, 10))
            elif rival * 2 > max(len(shown_rows), 1):
                others = python_list()
                for _s, _op, other in index.rivals.get(name) or ():
                    tree = _urmp_parse(other)
                    if tree is None:
                        continue
                    for n in _urmp_names_in(tree):
                        if n != name and n not in others:
                            others.append(n)
                parts = python_list()
                for n in others[:2]:
                    v = _urmp_value(n)
                    parts.append(u"%s (now %s)" % (_urmp_link(n), "?" if v is _URMP_UNK else _urmp_plain(_urmi_show(v), 20)))
                text = u"%s is %s. It is mostly compared with %s, not with fixed numbers." % (
                    name, now_words, " and ".join(parts) if parts else "other values")
                bands = [b.header for b in blocks if not b.marker]
                if bands:
                    text += u" With those values, the numbers that change something are: %s." % _urmp_some(bands, 6)
            else:
                text = u"%s is %s. The numbers that change something: %s." % (
                    name, now_words, _urmp_some([b.header for b in blocks if not b.marker], 6) or "none found")
            A.append(text)
            if exact_only and numeric_seen:
                p.gives_tail.append("Any number not listed matches nothing.")

            # The NEXT helper: the smallest requirement still ahead, and the
            # choices in that same scene that come before it.
            nxt = None
            if _urmp_isnum(now):
                for b in blocks:
                    if b.marker or b.sort is None or b.sort <= now:
                        continue
                    for r in b.rows + b.small:
                        if r.status in ("later", "not"):
                            if nxt is None or (b.sort, -r.weight) < (nxt[0].sort, -nxt[1].weight):
                                nxt = (b, r)
            if nxt is not None:
                b, r = nxt
                text = u"NEXT: %s in %s (%s)." % (b.header, r.scene, r.size)
                best = python_dict()
                for w in writes:
                    if w.menu is None or w.op != "+=" or not _urmp_isnum(w.value) or w.value <= 0:
                        continue
                    if w.scene != r.scene or w.file != r.file or w.line >= r.line:
                        continue
                    if cur is not None and w.scene == cur[1] and w.line <= cur[3]:
                        continue
                    k = id(w.menu)
                    if k not in best or w.value > best[k][0]:
                        best[k] = (w.value, w.option)
                if best and _urmp_isnum(b.sort):
                    d = sum(v for v, _o in best.values())
                    opts = [u'"%s"' % _urmp_plain(o, 40) for _v, o in best.values()][:3]
                    start = b.sort - d
                    text += u" %d choice%s in that scene come%s before it: %s (+%s). Arrive with %s and take them \u2192 %s." % (
                        len(best), "" if len(best) == 1 else "s", "s" if len(best) == 1 else "",
                        ", ".join(opts), _urmi_show(d), _urmi_show(start), _urmi_show(b.sort))
                    p.next_value = start
                else:
                    p.next_value = b.sort
                p.next_line = text
            gain = python_dict()
            for w in writes:
                if w.menu is None or w.op != "+=" or not _urmp_isnum(w.value) or w.value <= 0:
                    continue
                if w.scene in mass:
                    continue
                k = id(w.menu)
                gain[k] = max(gain.get(k, 0), w.value)
            if gain:
                p.gives_tail.append(u"The story script offers at most +%s in total (one pick per choice, counting every choice that adds to it; not counting the game's own code)." % _urmi_show(sum(gain.values())))

        elif mode == "value":
            byval = python_dict()
            for r in shown_rows:
                words, value, sort = _urmp_requirement(r, name, now)
                b = byval.get(words)
                if b is None:
                    hint = None
                    if isinstance(value, _urmi_text):
                        for w in writes:
                            if w.menu is not None and w.op == "=" and w.value == value:
                                hint = u'the choice "%s" in %s' % (_urmp_plain(w.option, 60), w.scene)
                                break
                    header = words
                    if isinstance(value, _urmi_text) and value == now:
                        header += u"   \u2190 now"
                    b = _URMPBlock(header, value, hint)
                    byval[words] = b
                b.rows.append(r)
            p.blocks = python_list(byval.values())
            for b in p.blocks:
                members = b.rows
                b.rows = python_list()
                _urmp_fill_block(b, members)
            text = u"%s is %s." % (name, now_words)
            if isinstance(now, _urmi_text):
                hint = None
                for w in writes:
                    if w.menu is not None and w.op == "=" and w.value == now:
                        hint = u' That\'s the choice "%s" in %s.' % (_urmp_plain(w.option, 60), w.scene)
                        break
                text += hint or " No choice in the story script sets this value."
            A.append(text)

        else:
            b = _URMPBlock(u"WHERE THE GAME CHECKS IT  (%d)" % len(shown_rows))
            for r in shown_rows:
                r.view_extra.insert(0, u"when %s" % _urmp_cond_words(r.cond))
            _urmp_fill_block(b, shown_rows)
            p.blocks.append(b)
            scenes = python_set(r.scene for r in rows)
            A.append(u"%s is %s. It is checked in %d place%s in %d scene%s." % (
                name, now_words, len(rows), "" if len(rows) == 1 else "s",
                len(scenes), "" if len(scenes) == 1 else "s"))

        # A2: is any of it still ahead?
        if shown_rows:
            later = [r for r in shown_rows if r.status == "later"]
            notp = [r for r in shown_rows if r.status == "not"]
            never = [r for r in shown_rows if r.status == "never"]
            known = [r for r in shown_rows if r.status]
            if later or notp or never:
                parts = python_list()
                if notp:
                    parts.append(u"%d in scenes you haven't played" % len(notp))
                if later:
                    parts.append(u"%d later in this scene" % len(later))
                if never:
                    parts.append(u"%d in scenes you played but never saw that version" % len(never))
                A.append(u"Of the places shown: %s." % "; ".join(parts))
            elif known and len(known) == len(shown_rows):
                A.append(u"All of them are in scenes you've already played. Changing it now only matters on a replay, an earlier save, or inside the game's own code.")

        # A3: who sets it.
        auto_scenes = python_set(w.scene for w in auto)
        if choice_count:
            text = u"Set by %d choice%s" % (option_count, "" if option_count == 1 else "s")
            if choice_count != option_count:
                text += u" in %d menu%s" % (choice_count, "" if choice_count == 1 else "s")
            if current_menu is not None and id(current_menu) in menus:
                text += u", one of them on your screen now"
            text += "."
            if auto:
                text += u" The game also sets it by itself in %d place%s." % (len(auto), "" if len(auto) == 1 else "s")
        elif auto:
            text = u"No choice sets it. The game changes it by itself in %d place%s." % (len(auto), "" if len(auto) == 1 else "s")
        else:
            text = u"Nothing in the story script sets it - only its starting value."
        if mass_hidden:
            text += u" (Also set by %s, which look%s like the game's own chapter select or scene-select menu.)" % (
                ", ".join(python_list(mass_hidden)[:2]), "s" if len(mass_hidden) == 1 else "")
        if funcs:
            text += u" %s in the game's own code also mention%s it." % (
                ", ".join("%s()" % f for f in funcs[:3]), "s" if len(funcs) == 1 else "")
        A.append(text)

        # --- B. right now ------------------------------------------------
        if current_menu is not None:
            q = _urmp_question(index, current_menu)
            p.now_header = u"THE CHOICE ON YOUR SCREEN" + (u"  -  after %s" % q if q else "")
            mine = menus.get(id(current_menu)) or ()
            for item in current_menu.items:
                label, cond, block = item[0], item[1], item[2]
                if block is None:
                    continue
                effects = python_list()
                for w in mine:
                    if w.option == label:
                        effects.append(_urmp_effect(w, now, boolish)[0])
                text = u'"%s"  \u2192  %s' % (_urmp_plain(label, 70), "; ".join(effects) if effects else "doesn't change it")
                value = _URMP_NOSET
                if cond and cond.strip() != "True" and name in _urmp_names_of(index, cond):
                    tree = _urmp_parse(cond)
                    visible = _urmp_ev(tree)
                    words = _urmp_cond_words(cond)
                    if visible is False:
                        r = _URMPRow()
                        r.cond = cond
                        req = _urmp_requirement(r, name, now)
                        text = u'"%s" is hidden right now - it needs %s' % (_urmp_plain(label, 70), words)
                        value = req[1]
                    elif visible is True:
                        text += u"   (offered because %s)" % words
                p.now_lines.append((text, value))
            if mine:
                p.now_lines.append((u"Picking one in the game sets it the same way - you don't need to change it here.", _URMP_NOSET))

        for r in shown_rows:
            if r.status == "later":
                p.later.append(r)
        p.later.sort(key=lambda r: r.line)

        # --- C. before you change it ------------------------------------
        W = p.warnings
        ahead_auto = [w for w in auto if w.status in ("later", "not")]
        resets = python_list()
        ahead_auto.sort(key=lambda w: (0 if w.op == "=" else 1, _URMP_STATUS_RANK.get(w.status, 4)))
        for w in ahead_auto:
            text = u"The game %s by itself in %s" % (_urmp_effect_named(w, name), w.scene)
            if w.cond:
                text += u" when %s" % _urmp_cond_words(w.cond)
            elif w.unless:
                text += u" unless %s" % " or ".join(_urmp_cond_words(c) for c in w.unless[:2])
            if w.status == "later":
                text += u" (later in this scene)"
            resets.append(text + ".")
        if resets:
            more = len(resets) - 1
            W.append(u"! " + resets[0] + (u" It changes it by itself in %d more place%s you haven't reached." % (
                more, "" if more == 1 else "s") if more else ""))
        later_choices = python_list()
        for m in menu_order:
            if current_menu is not None and m is current_menu:
                continue
            g = menus[id(m)]
            if g[0].status in ("later", "not"):
                for w in g:
                    later_choices.append(u'"%s" (%s) \u2192 %s' % (_urmp_plain(w.option, 50), w.scene, _urmp_effect(w, now, boolish)[0]))
        if later_choices:
            W.append(u"! %d choice%s you haven't reached change it again: %s%s" % (
                len(later_choices), "" if len(later_choices) == 1 else "s",
                "; ".join(later_choices[:2]), u" (+%d more)" % (len(later_choices) - 2) if len(later_choices) > 2 else ""))
        big = None
        for r in ahead:
            if r.weight >= 100 and r.needs_unmet and (big is None or r.weight > big.weight):
                big = r
        if big is not None:
            W.append(u"! The biggest moment still ahead (about %d lines, %s) also needs %s." % (big.weight, big.scene, big.needs_unmet[0]))
        if mode == "number" and _urmp_isnum(now):
            exact = all(_urmp_requirement(r, name, now)[0].startswith("exactly") for r in shown_rows) if shown_rows else False
            lowers = any(w.op in ("-=",) or (w.op == "=" and _urmp_isnum(w.value) and w.value < now) for w in writes)
            if exact and not lowers and ahead:
                upcoming = sorted(python_set(_urmp_requirement(r, name, now)[2] for r in ahead if _urmp_requirement(r, name, now)[2] is not None and _urmp_requirement(r, name, now)[2] > now))
                if upcoming:
                    W.append(u"! Only exact numbers are checked and nothing in the story script lowers it. Going past %s skips that moment." % _urmi_show(upcoming[0]))
        reading_scenes = python_dict()
        for r in rows:
            reading_scenes.setdefault(r.scene, r.line)
        if len(reading_scenes) >= 3:
            reset_here = 0
            for scene, line in reading_scenes.items():
                for w in auto:
                    if w.scene == scene and w.op == "=" and w.line < line:
                        reset_here += 1
                        break
            if reset_here * 10 >= len(reading_scenes) * 8:
                W.append(u"! In %d of the %d scenes that check it, the game sets it itself shortly before - a value set here is likely replaced before it matters." % (reset_here, len(reading_scenes)))
        if not W and ahead:
            p.okline = "Nothing in scenes you haven't played resets or changes it, as far as the story script shows."

        # --- D1 tail ----------------------------------------------------
        for line in collapse_lines:
            p.gives_tail.append(line)
        if quiet:
            eg = quiet[0]
            what = _urmp_write_words(eg.summary.writes[0])[1:-1] if eg.summary.writes else "change something"
            p.gives_tail.append(u"Also: %d check%s only change other values, with no dialogue - e.g. in %s: %s." % (
                len(quiet), "" if len(quiet) == 1 else "s", eg.scene, what))
        if loops:
            lscenes = python_set(r.scene for r in loops)
            p.gives_tail.append(u"%d loop%s in %d scene%s repeat while %s holds a certain value." % (
                len(loops), "" if len(loops) == 1 else "s", len(lscenes), "" if len(lscenes) == 1 else "s", name))

        # --- D2. choices -------------------------------------------------
        ordered = sorted(menu_order, key=lambda m: (
            0 if current_menu is not None and m is current_menu else 1,
            _URMP_STATUS_RANK.get(menus[id(m)][0].status, 4),
            menus[id(m)][0].file or "", menus[id(m)][0].line))
        for m in ordered:
            g = menus[id(m)]
            first = g[0]
            status = "here, on your screen" if current_menu is not None and m is current_menu else {
                "later": "later in this scene", "not": "not played", "never": "played",
                "above": "earlier in this scene", "played": "played"}.get(first.status, "")
            q = _urmp_question(index, m)
            header = u"%s%s%s" % (first.scene, (u"  \u00b7  " + status) if status else "",
                                  (u"  \u00b7  after %s" % q) if q else "")
            lines = python_list()
            for item in m.items:
                label, block = item[0], item[2]
                if block is None:
                    continue
                effects = python_list()
                value = _URMP_NOSET
                for w in g:
                    if w.option == label:
                        words, v = _urmp_effect(w, now, boolish)
                        effects.append(words)
                        value = v
                text = u'"%s"  \u2192  %s' % (_urmp_plain(label, 70), "; ".join(effects) if effects else "doesn't change it")
                also = python_list()
                for node in (block or ())[:12]:
                    if isinstance(node, renpy.ast.Python):
                        source = getattr(getattr(node, "code", None), "source", "") or ""
                        for wr in _urmp_effects(source)[0]:
                            if wr[0] != name and len(also) < 3:
                                also.append(_urmp_write_words(wr)[1:-1])
                if also:
                    text += u"   (also: %s)" % ", ".join(also)
                if seen.label(first.scene):
                    picked = seen.picked(m, label)
                    if picked is True:
                        text += u"   {color=#1e88e5}picked before{/color}"
                lines.append((text, value))
            p.choices.append((header, lines))
        if auto:
            groups_auto = python_dict()
            order = python_list()
            for w in auto:
                k = (w.scene, w.op, repr(w.value), w.cond, tuple(w.unless or ()))
                if k not in groups_auto:
                    groups_auto[k] = python_list()
                    order.append(k)
                groups_auto[k].append(w)
            texts = python_list()
            for k in order[:8]:
                w = groups_auto[k][0]
                text = u"%s in %s" % (_urmp_effect_named(w, "it"), w.scene)
                if w.cond:
                    text += u" when %s" % _urmp_cond_words(w.cond)
                elif w.unless:
                    text += u" unless %s" % " or ".join(_urmp_cond_words(c) for c in w.unless[:2])
                if len(groups_auto[k]) > 1:
                    text += u" (x%d)" % len(groups_auto[k])
                texts.append(text)
            p.choices_tail.append(u"By itself: " + u"  \u00b7  ".join(texts) + (u"  \u00b7  and %d more" % (len(order) - 8) if len(order) > 8 else ""))
        for scene, ws in mass_hidden.items():
            p.choices_tail.append(u"%s sets it too (%d option%s) - it looks like the game's own chapter select, skip or scene-select menu, not a story choice." % (
                scene, len(ws), "" if len(ws) == 1 else "s"))

        # --- tabs ----------------------------------------------------------
        if p.blocks or p.gives_tail:
            p.tabs.append(("gives", "What each value gives"))
        p.tabs.append(("choices", "Choices that set it (%d)" % choice_count))
        p.tabs.append(("details", "Details"))
        p.tab = p.tabs[0][0]

        # --- D3. details ----------------------------------------------------
        summary, _checks = urm_checks(name)
        if summary:
            p.details.append(_urmi_safe(summary))
        rcount, readers = urm_readers(name, 40)
        if rcount:
            p.details.append(u"{b}Checked in %d place%s:{/b}" % (rcount, "" if rcount == 1 else "s"))
            for line in readers:
                p.details.append(_urmi_safe(line))
        wcount, wlines = urm_writers(name, 40)
        if wcount:
            p.details.append(u"{b}Set in %d place%s:{/b}" % (wcount, "" if wcount == 1 else "s"))
            for line in wlines:
                p.details.append(_urmi_safe(line))
        declared = index.declared.get(name)
        if declared is not None and declared[1]:
            p.details.append(_urmi_safe(u"Starting value written in the script: %s" % declared[1]))
        p.detail_checks = _checks

        # --- E. footer -----------------------------------------------------
        p.footer.append(u"From the game's story script. Uses inside the game's own functions and screens aren't shown. "
                        u"Played / seen / picked = on this computer, in any playthrough. Line counts are approximate "
                        u"and include lines inside nested choices.")
        if seen.ever is None:
            p.footer.append(u"\"Never saw this version\" is off (the game is translated, or this engine doesn't record it).")
        if budget[0] <= 0:
            p.footer.append(u"Some sizes are lower bounds - very long scenes were not fully counted.")
        return p

    def _urmp_some(items, limit):
        if len(items) <= limit:
            return u", ".join(items)
        return u"%s and %d more" % (u", ".join(items[:limit]), len(items) - limit)

    def _urmp_choice_hint(writes, value, mass):
        found = python_list()
        for w in writes:
            if w.menu is None or w.op != "=" or w.scene in mass:
                continue
            if w.value is value or (w.value == value and type(w.value) == type(value)):
                text = u'"%s" in %s' % (_urmp_plain(w.option, 50), w.scene)
                if text not in found:
                    found.append(text)
        if not found:
            return None
        return u"same as picking " + u" or ".join(found[:2])


    # ------------------------------------------------------------------
    # What the screen calls
    # ------------------------------------------------------------------

    def urmi_ui(key, default=None):
        return _urmp_bucket("ui").get(key, default)

    def urmi_ui_set(key, value):
        _urmp_bucket("ui")[key] = value
        renpy.restart_interaction()

    def urmi_ui_toggle(key):
        ui = _urmp_bucket("ui")
        ui[key] = not ui.get(key, False)
        renpy.restart_interaction()

    def urmi_block_limit(panel, block):
        """Rows shown before "Show all": a number ladder shows one place per rung."""

        if panel.mode == "number":
            return 1
        return _URMP_ROWS_SHOWN

    def urmi_small_line(block):
        return _urmp_small_line(block)

    def urmi_settable(var, value):
        """Whether a [Set] button can put this value into URM's box."""

        if value is _URMP_NOSET or value is None:
            return False
        try:
            if not var.isEditable:
                return False
            kind = var.varType
        except Exception:
            return False
        if kind == "boolean":
            return value in (True, False, 0, 1)
        if kind in ("int", "float"):
            return _urmp_isnum(value) or isinstance(value, bool)
        if kind == "string":
            return isinstance(value, _urmi_text)
        return False

    def urmi_set_words(value):
        if value is True:
            return "Set ON"
        if value is False:
            return "Set OFF"
        return u"Set %s" % _urmp_plain(_urmi_show(value), 30)


# ---------------------------------------------------------------------------
# Gallery: unlock everything, or show only what you really unlocked
# ---------------------------------------------------------------------------
#
# One switch, two places: a row in URM's settings, and a small button in the
# corner of the main and game menus - which is where galleries live, and
# where URM's own overlay is never shown.
#
# Nothing is written. Turning it on changes what the game READS, not what it
# has stored, so turning it off is exact: your own unlocks are untouched,
# nothing is saved, and uninstalling URM leaves no trace.
#
# Games build galleries in a handful of ways, and each is covered:
#
#   * Ren'Py's Replay action and most hand-made galleries ask
#     renpy.seen_label / seen_image / seen_audio - those answer yes
#   * Ren'Py's own Gallery class - its buttons and images report unlocked
#   * persistent flags (persistent.scene3_unlocked, persistent.gallery
#     ["kim"], "x" in persistent.unlocked) - read as set. Which flags: every
#     persistent name the game's own gallery screens and gallery labels test,
#     plus names that say what they are (gallery, replay, unlock, scene,
#     memory, ending, cg...) and not what they aren't (settings, pages,
#     counters, anything of URM's or Ren'Py's own)
#
# And only where it cannot change the story: while a menu is open (main menu,
# game menu - the context Ren'Py marks _menu), while one of the game's gallery
# screens is showing, or while the game is inside a gallery label. A replay
# runs in a context of its own, so the scene you replay sees your real flags.
#
# When the switch is off, nothing here is installed at all: the persistent
# class and renpy.seen_* are exactly as the engine ships them.

init 999 python:

    import re as _urmg_re
    import sys as _urmg_sys

    _URMG_WORDS = _urmg_re.compile(
        r"galler|replay|unlock|memor|album|recollect|bonus|scene|seen|reward"
        r"|ending|(?:^|_)cgs?(?:\d|_|$)", _urmg_re.I)
    _URMG_NOT = _urmg_re.compile(
        r"urm|enable|setting|option|skip|mode|volume|patch|name|lang|font"
        r"|difficult|disable|^show_|^hide_|first|warning|intro|tutorial|page"
        r"|index|count|current|select|last|version|update|notif|sort|filter",
        _urmg_re.I)
    _URMG_SCREENS = _urmg_re.compile(
        r"galler|replay|memor|album|recollect|bonus|extra|(?:^|_)cgs?(?:$|_)"
        r"|scene_?(?:select|list|menu|room|viewer)", _urmg_re.I)
    _URMG_LABELS = _urmg_re.compile(r"galler|replay|memor|album|recollect|bonus|extras", _urmg_re.I)
    # Thief of Hearts 2 shows scr_end_replay during a replay; counting it would
    # unlock flags inside the replayed scene itself. URM's own URM_replay
    # dialogs are not the game's gallery either.
    _URMG_NOT_SCREENS = _urmg_re.compile(r"end_?replay|replay_?end|exit|^urm", _urmg_re.I)
    _URMG_PERSISTENT = _urmg_re.compile(r"persistent\.([A-Za-z_]\w*)")

    # Inside a Ren'Py 7 store, `str` is Ren'Py's compat str - unicode - but
    # Python 2's parser hands back string literals as byte strings. So text
    # types come from the real builtins, never from the store's names.
    try:
        import __builtin__ as _urm_builtins
        _urmg_strings = (_urm_builtins.str, _urm_builtins.unicode)
    except ImportError:
        _urmg_strings = (str,)

    try:
        x52URM.SettingsClass.defaultValues.setdefault("urmcGalleryAll", False)
        x52URM.SettingsClass.defaultValues.setdefault("urmcGalleryBadge", True)
    except Exception as error:
        print("URM+: gallery settings not registered (%s)" % (error,))

    class _URMGState(python_object):
        def __init__(self):
            self.on = False
            self.names = python_set()      # persistent names the gallery screens/labels test
            self.screens = python_list()   # the game's gallery screens, by name
            self.wanted = python_dict()    # name -> bool, cached
            self.unlock = python_dict()    # name -> the value that means unlocked
            self.labels = python_dict()    # current statement -> inside a gallery label?
            self.originals = python_dict() # (module id, function name) -> original
            self.scanned = False

    def _urmg_state():
        holder = x52URM.Var
        st = getattr(holder, "_urmgState", None)
        if st is None:
            st = _URMGState()
            holder._urmgState = st
        return st

    def _urmg_setting(name):
        try:
            return x52URM.Settings.get(name)
        except Exception:
            return None


    # ------------------------------------------------------------------
    # Where an unlock may apply
    # ------------------------------------------------------------------

    def _urmg_active():
        st = _urmg_state()
        if not st.on:
            return False
        try:
            ctx = renpy.game.context()
        except Exception:
            return False
        if getattr(ctx, "_menu", False):
            return True
        if _urmg_gallery_showing():
            return True
        current = getattr(ctx, "current", None)
        if current is None:
            return False
        try:
            return st.labels[current]
        except KeyError:
            pass
        inside = False
        try:
            node = renpy.game.script.lookup(current)
            index = _urmi_index()
            if node is not None and index is not None and index.state == "ready":
                label = _urmp_scene(index, node, node.filename, node.linenumber)
                inside = bool(label and _URMG_LABELS.search(label))
        except Exception:
            inside = False
        if len(st.labels) > 2000:
            st.labels.clear()
        st.labels[current] = inside
        return inside

    def _urmg_in_init(index, site):
        """A write in startup code (init / default), not one the story makes."""

        cur = index.nodes.get(site[2])
        guard = 0
        while cur is not None and guard < 200:
            guard += 1
            link = index.parent.get(id(cur))
            if link is None:
                break
            parent, kind, _extra = link
            if isinstance(parent, renpy.ast.Init):
                return True
            if kind == "label":
                return False
            cur = parent
        return index.label_at(site[0], site[1]) is None

    def _urmg_unlock_value(name):
        """
        The value that means "unlocked" for one persistent flag.

        Most galleries test `if persistent.x:` and the scene sets it True, but
        Thief of Hearts 2 tests `persistent.replay_x == False` and its scenes
        set False (True is written at startup, meaning locked). So the value
        is learnt from what the story itself writes when the scene is earned -
        writes outside init code - and True is only the fallback for a flag
        the script never writes.
        """

        st = _urmg_state()
        try:
            return st.unlock[name]
        except KeyError:
            pass
        index = _urmi_index()
        if index is None or index.state != "ready":
            return True
        counts = python_dict()
        try:
            for site, op, value, _t in index.writes.get("persistent." + name) or ():
                if op != "=" or not isinstance(value, bool):
                    continue
                if _urmg_in_init(index, site):
                    continue
                counts[value] = counts.get(value, 0) + 1
        except Exception:
            counts = python_dict()
        if not counts:
            unlocked = True
        elif len(counts) == 1:
            unlocked = python_list(counts)[0]
        else:
            unlocked = counts.get(True, 0) >= counts.get(False, 0)
        st.unlock[name] = unlocked
        return unlocked

    def _urmg_gallery_showing():
        for name in _urmg_state().screens[:12]:
            try:
                if renpy.get_screen(name):
                    return True
            except Exception:
                pass
        return False

    def _urmg_is_wanted(name):
        st = _urmg_state()
        try:
            return st.wanted[name]
        except KeyError:
            pass
        if name[:1] == "_":
            found = False
        elif name in st.names:
            found = True
        else:
            found = bool(_URMG_WORDS.search(name)) and not _URMG_NOT.search(name)
        st.wanted[name] = found
        return found


    # ------------------------------------------------------------------
    # What the game reads while it applies
    # ------------------------------------------------------------------

    class _URMGAllSet(python_set):
        def __contains__(self, item):
            return True

    class _URMGAllList(python_list):
        def __contains__(self, item):
            return True

    _URMG_NO_DEFAULT = python_object()

    class _URMGAllDict(python_dict):
        """
        A stored dict as an unlocked gallery reads it. Nested containers are
        unlocked too - The Lost Guardian keeps one list per girl,
        persistent.masterreplist["Jill"] - but only a dict of flags or of
        lists says yes to a key it does not have: a dict of tooltip strings
        next to it (persistent.replay_hints) must keep answering None.
        """

        def _fill(self):
            kinds = python_set()
            for value in python_dict.values(self):
                if value is True or value is False or value is None:
                    kinds.add("flag")
                elif isinstance(value, (python_list, python_set, frozenset, python_dict)):
                    kinds.add("coll")
                else:
                    return _URMG_NO_DEFAULT
            if kinds == python_set(("coll",)):
                return _URMGAllList()
            if not kinds or kinds == python_set(("flag",)):
                return True
            return _URMG_NO_DEFAULT

        def __contains__(self, key):
            if python_dict.__contains__(self, key):
                return True
            return self._fill() is not _URMG_NO_DEFAULT

        def __getitem__(self, key):
            try:
                value = python_dict.__getitem__(self, key)
            except KeyError:
                fill = self._fill()
                if fill is _URMG_NO_DEFAULT:
                    raise
                return fill
            if value is False or value is None:
                return True
            return _urmg_wrap(value)

        def get(self, key, default=None):
            try:
                return self[key]
            except KeyError:
                return default

    def _urmg_wrap(value):
        if isinstance(value, (_URMGAllSet, _URMGAllList, _URMGAllDict)):
            return value
        if isinstance(value, python_dict):
            return _URMGAllDict(value)
        if isinstance(value, python_list):
            return _URMGAllList(value)
        if isinstance(value, (python_set, frozenset)):
            return _URMGAllSet(value)
        return value

    _urmg_plain_get = object.__getattribute__

    def _urmg_getattribute(self, name):
        if name[:1] == "_":
            return _urmg_plain_get(self, name)
        try:
            value = _urmg_plain_get(self, name)
        except AttributeError:
            # Never set: the game's own Persistent.__getattr__ would say None.
            if _urmg_is_wanted(name) and _urmg_active():
                return _urmg_unlock_value(name)
            raise
        if value is True or value is False or value is None:
            if _urmg_is_wanted(name) and _urmg_active():
                unlocked = _urmg_unlock_value(name)
                if value is not unlocked:
                    return unlocked
        elif isinstance(value, (python_set, frozenset, python_list, python_dict)):
            if _urmg_is_wanted(name) and _urmg_active():
                return _urmg_wrap(value)
        return value

    def _urmg_seen_wrapper(original):
        def seen(*args, **kwargs):
            if _urmg_active():
                return True
            return original(*args, **kwargs)
        seen._urmg_original = original
        return seen

    def _urmg_check_wrapper(original):
        def check_unlock(self, *args, **kwargs):
            if _urmg_active():
                return True
            return original(self, *args, **kwargs)
        check_unlock._urmg_original = original
        return check_unlock


    # ------------------------------------------------------------------
    # Finding the game's gallery
    # ------------------------------------------------------------------

    def _urmg_walk(root, names):
        """Every persistent.x named anywhere in a screen's parsed source."""

        stack = python_list()
        stack.append(root)
        done = python_set()
        visited = 0
        while stack and visited < 200000:
            obj = stack.pop()
            visited += 1
            if isinstance(obj, _urmg_strings):
                if "persistent." in obj:
                    for name in _URMG_PERSISTENT.findall(obj):
                        names.add(name)
                continue
            if id(obj) in done:
                continue
            done.add(id(obj))
            if isinstance(obj, (python_list, tuple)):
                for item in obj:
                    stack.append(item)
                continue
            if isinstance(obj, python_dict):
                for item in obj.values():
                    stack.append(item)
                continue
            module = getattr(type(obj), "__module__", "") or ""
            if not module.startswith("renpy."):
                continue
            try:
                attrs = vars(obj)
            except TypeError:
                attrs = None
            if attrs:
                for item in attrs.values():
                    stack.append(item)
            source = getattr(obj, "source", None)
            if isinstance(source, _urmg_strings):
                stack.append(source)

    def _urmg_scan():
        st = _urmg_state()
        names = python_set()
        screens = python_list()

        registry = getattr(_urmg_sys.modules.get("renpy.display.screen"), "screens", None) or {}
        for key, screen in python_list(registry.items()):
            try:
                name = key[0] if isinstance(key, tuple) else key
                if not isinstance(name, _urmg_strings) or not _URMG_SCREENS.search(name):
                    continue
                if _URMG_NOT_SCREENS.search(name):
                    continue
                if name not in screens:
                    screens.append(name)
                ast = getattr(screen, "ast", None)
                if ast is not None:
                    _urmg_walk(ast, names)
            except Exception:
                continue

        try:
            index = _urmi_index()
            if index is not None and index.state == "ready":
                for name, bucket in index.reads.items():
                    if not name.startswith("persistent."):
                        continue
                    base = _urmg_re.split(r"[.\[]", name[11:], 1)[0]
                    for site, _op, _lit in bucket:
                        label = index.where(site)[0]
                        if label and _URMG_LABELS.search(label):
                            names.add(base)
                            break
        except Exception:
            pass

        # Ren'Py's own Gallery: every button and image reports unlocked.
        try:
            for value in python_list(renpy.store.__dict__.values()):
                buttons = getattr(value, "buttons", None)
                if type(value).__name__ != "Gallery" or not isinstance(buttons, python_dict):
                    continue
                for button in buttons.values():
                    things = python_list()
                    things.append(button)
                    for image in getattr(button, "images", None) or ():
                        things.append(image)
                    for thing in things:
                        cls = type(thing)
                        check = cls.__dict__.get("check_unlock")
                        if check is not None and not hasattr(check, "_urmg_original"):
                            cls.check_unlock = _urmg_check_wrapper(check)
        except Exception as error:
            print("URM+: Gallery class left as is (%s)" % (error,))

        for name in python_list(names):
            if name.startswith("_") or "urm" in name.lower():
                names.discard(name)
        st.names = names
        st.screens = screens
        st.wanted = python_dict()
        st.unlock = python_dict()
        # Done for good only once the script has been read: the names gallery
        # labels test come from the index, so a scan before that runs again.
        index = _urmi_index()
        st.scanned = index is not None and index.state == "ready"

    def _urmg_modules():
        found = python_list()
        for mod in (_urmg_sys.modules.get("renpy.exports"), renpy):
            if mod is not None and hasattr(mod, "seen_label") and mod not in found:
                found.append(mod)
        return found


    # ------------------------------------------------------------------
    # The switch
    # ------------------------------------------------------------------

    def _urmg_install():
        st = _urmg_state()
        if st.on:
            return
        _urmg_scan()
        st.on = True
        try:
            type(renpy.game.persistent).__getattribute__ = _urmg_getattribute
        except Exception as error:
            print("URM+: persistent gallery flags not unlocked (%s)" % (error,))
        for mod in _urmg_modules():
            for fname in ("seen_label", "seen_image", "seen_audio"):
                current = getattr(mod, fname, None)
                if current is None or hasattr(current, "_urmg_original"):
                    continue
                st.originals[(id(mod), fname)] = current
                setattr(mod, fname, _urmg_seen_wrapper(current))

    def _urmg_uninstall():
        st = _urmg_state()
        if not st.on:
            return
        st.on = False
        try:
            cls = type(renpy.game.persistent)
            if cls.__dict__.get("__getattribute__") is _urmg_getattribute:
                del cls.__getattribute__
        except Exception:
            pass
        for mod in _urmg_modules():
            for fname in ("seen_label", "seen_image", "seen_audio"):
                original = st.originals.pop((id(mod), fname), None)
                if original is not None:
                    setattr(mod, fname, original)

    def _urmg_apply():
        if _urmg_setting("urmcGalleryAll"):
            _urmg_install()
        else:
            _urmg_uninstall()

    def urmg_toggle():
        try:
            x52URM.Settings.set("urmcGalleryAll", not _urmg_setting("urmcGalleryAll"))
        except Exception as error:
            print("URM+: gallery switch failed (%s)" % (error,))
        _urmg_apply()
        renpy.restart_interaction()

    def urmg_badge_text():
        if _urmg_state().on:
            return "{urm_notl}URM gallery: {b}everything unlocked{/b}{/urm_notl}"
        return "{urm_notl}URM gallery: my unlocks{/urm_notl}"

    def _urmg_interact():
        try:
            _urmg_apply()
        except Exception:
            pass
        try:
            st = _urmg_state()
            if not st.scanned:
                index = _urmi_index()
                if index is not None and index.state == "ready":
                    _urmg_scan()
            # Ren'Py's menus, or one of the game's own gallery screens - Thief
            # of Hearts 2 opens its gallery from an in-game menu screen.
            where = getattr(renpy.game.context(), "_menu", False) or _urmg_gallery_showing()
            want = bool(where and _urmg_setting("urmcGalleryBadge") is not False
                        and renpy.has_screen("urmg_badge"))
            shown = renpy.get_screen("urmg_badge", layer=_urmi_layer)
            if want and not shown:
                renpy.show_screen("urmg_badge", _layer=_urmi_layer)
            elif shown and not want:
                renpy.hide_screen("urmg_badge", layer=_urmi_layer)
        except Exception:
            pass

    if _urmg_interact not in config.interact_callbacks:
        config.interact_callbacks.append(_urmg_interact)


# ---------------------------------------------------------------------------
# Longer rollback, and back to the last choice with a middle click on Skip
# ---------------------------------------------------------------------------
#
# Ren'Py lets the player roll back 100 steps (config.hard_rollback_limit) out
# of a history of about 128 recorded statements (config.rollback_length) -
# a cautious default from when memory was scarce. The setting raises both,
# 500 steps by default; a game that already asks for more keeps its own. The
# cost is memory and save size: every save carries the history.
#
# Middle-clicking a Skip button rolls back to the last choice the player
# made. Right-click on Skip already skips forward to the next choice (Ren'Py's
# fast skip), so the middle button is its mirror. Middle-click everywhere else
# keeps its usual job of hiding the text window: the catcher only acts while
# the button under the mouse is a Skip button.
#
# Finding the choice: Ren'Py takes a checkpoint after each interaction and
# stores what the interaction returned on that history entry. A menu returns
# the option picked - a number, or the value a python menu or a screen
# returned - where dialogue returns True. So the newest entry holding such a
# value is the last choice, and rolling back the number of checkpoints up to
# and including it lands on that menu with its options open again.
#
# The game's own rollback blocks are respected: if one stands between here
# and the choice, nothing happens and a notification says why.

init 999 python:

    import sys as _urmr_sys

    try:
        x52URM.SettingsClass.defaultValues.setdefault("urmcRollback", 500)
    except Exception as error:
        print("URM+: rollback setting not registered (%s)" % (error,))

    class _URMRState(python_object):
        def __init__(self):
            self.game_hard = None
            self.game_length = None
            self.applied = None
            self.resume = None             # the skip path detection stopped

    def _urmr_state():
        holder = x52URM.Var
        st = getattr(holder, "_urmrState", None)
        if st is None:
            st = _URMRState()
            holder._urmrState = st
        return st

    def _urmr_apply():
        st = _urmr_state()
        if st.game_hard is None:
            # Read on the first interaction, after every init block of the
            # game has had its say.
            st.game_hard = config.hard_rollback_limit
            st.game_length = config.rollback_length
        try:
            want = x52URM.Settings.get("urmcRollback")
        except Exception:
            want = 500
        if want is None:
            want = 500
        if want == st.applied:
            return
        st.applied = want
        if want:
            config.hard_rollback_limit = max(st.game_hard, want)
            config.rollback_length = max(st.game_length, want + want // 2)
        else:
            config.hard_rollback_limit = st.game_hard
            config.rollback_length = st.game_length

    def _urmr_interact():
        try:
            _urmr_apply()
        except Exception:
            pass
        try:
            _urmr_forget_resume_at_menu()
        except Exception:
            pass

    if _urmr_interact not in config.interact_callbacks:
        config.interact_callbacks.append(_urmr_interact)


    def _urmr_is_choice(entry):
        value = getattr(entry, "forward", None)
        if value is None or isinstance(value, bool):
            return False
        try:
            return isinstance(value, (int, float) + _urmi_text)
        except Exception:
            return isinstance(value, (int, float, str))

    def urmr_back_to_choice():
        """Roll back to the last choice made. False when there is none within reach."""

        try:
            log = renpy.game.log
            entries = log.log
        except Exception:
            return False

        target = None
        for i in range(len(entries) - 1, -1, -1):
            entry = entries[i]
            if entry is log.current:
                # The statement on screen has not been answered yet.
                continue
            if _urmr_is_choice(entry):
                target = i
                break

        if target is None:
            renpy.notify("URM: no choice in the rollback history to go back to")
            return False

        steps = 0
        for entry in entries[target:]:
            if getattr(entry, "hard_checkpoint", False):
                steps += 1
        if steps <= 0:
            steps = 1

        if steps > getattr(log, "rollback_limit", 0):
            renpy.notify("URM: the game blocks going back that far")
            return False

        renpy.rollback(checkpoints=steps)
        return True

    def _urmr_skip_focused():
        try:
            focus = _urmr_sys.modules["renpy.display.focus"].get_focused()
        except Exception:
            return False
        action = getattr(focus, "action", None)
        if isinstance(action, (python_list, tuple)):
            actions = action
        else:
            actions = (action,)
        for item in actions:
            if type(item).__name__ == "Skip":
                return True
        return False

    class _URMRMiddleClick(renpy.Displayable):
        """
        Two mouse jobs, from the top layer so nothing below sees them first:

        * a middle click on a Skip button rolls back to the last choice
        * after URM stopped a skip on path detection, the next left click on
          empty space resumes that skip (see _urmr_cancel_skipping)
        """

        def render(self, width, height, st, at):
            return renpy.Render(0, 0)

        def event(self, ev, x, y, st):
            kind = getattr(ev, "type", None)
            button = getattr(ev, "button", None)
            if kind == _urmr_mouse_up and button == 1:
                state = _urmr_state()
                if state.resume and not config.skipping and _urmr_empty_click():
                    config.skipping = state.resume
                    state.resume = None
                    renpy.restart_interaction()
                    # Taken, not passed on: the dialogue's own click handler
                    # stops skipping when it sees a click while skipping.
                    raise _urmr_sys.modules["renpy.display.core"].IgnoreEvent()
            elif kind == _urmr_mouse_up and button == 2:
                if _urmr_skip_focused():
                    urmr_back_to_choice()
                    raise _urmr_sys.modules["renpy.display.core"].IgnoreEvent()
            return None

    try:
        import pygame_sdl2 as _urmr_pygame
    except Exception:
        import pygame as _urmr_pygame
    _urmr_mouse_up = _urmr_pygame.MOUSEBUTTONUP

    def _urmr_empty_click():
        """No button under the mouse: the click is one that advances dialogue."""

        try:
            focus = _urmr_sys.modules["renpy.display.focus"].get_focused()
        except Exception:
            return False
        return focus is None or type(focus).__name__ == "SayBehavior"


    # ------------------------------------------------------------------
    # Resume a skip that path detection stopped
    # ------------------------------------------------------------------
    #
    # With "Stop skipping on path detection" on, URM cancels the skip the
    # moment a path card appears (watchpanel.rpy.x52:310-311, CancelSkipping
    # in utils.rpy:121). Clicking on then only advances one line at a time.
    # The skip URM cancelled - slow, or fast to the next choice - is
    # remembered here, and the next left click on empty space picks it up
    # again. A click on a button does not, a choice menu forgets it (Ren'Py
    # stops skipping there anyway), and so does loading a save.

    def _urmr_cancel_skipping_wrap(original):
        def cancel(self, *args, **kwargs):
            if config.skipping:
                _urmr_state().resume = config.skipping
            return original(self, *args, **kwargs)
        cancel._urmr_original = original
        return cancel

    try:
        _urmr_cancel = x52URM.CancelSkipping.__call__
        if not hasattr(_urmr_cancel, "_urmr_original"):
            x52URM.CancelSkipping.__call__ = _urmr_cancel_skipping_wrap(_urmr_cancel)
    except Exception as error:
        print("URM+: skipping will not resume after path detection (%s)" % (error,))

    def _urmr_forget_resume_at_menu():
        state = _urmr_state()
        if not state.resume:
            return
        try:
            node = renpy.game.script.lookup(renpy.game.context().current)
        except Exception:
            return
        if isinstance(node, renpy.ast.Menu):
            state.resume = None

    def _urmr_forget_resume():
        _urmr_state().resume = None

    if _urmr_forget_resume not in config.after_load_callbacks:
        config.after_load_callbacks.append(_urmr_forget_resume)

    urmr_middle_click = _URMRMiddleClick()


# ---------------------------------------------------------------------------
# Force any path, even one behind a jump or call
# ---------------------------------------------------------------------------
#
# URM forces a path by rewriting the chain of statements between the cursor
# and the if-statement (PathDetection.rpy:146-184): it copies each node and
# points the last one's .next at the chosen arm. A jump or call in between
# leaves no .next to rewrite - the target is looked up by name - so URM marks
# the row "Not forceable, probably because it's behind a call or jump", and
# in a game that jumps between scenes that is most of them.
#
# This forces at the other end instead. Select remembers which arm of which
# if-statement was picked, and when the game executes that if-statement it
# goes down that arm, however it got there. It is one-shot: once taken, the
# if-statement tests its conditions normally again, and loading a save
# forgets anything not yet reached.
#
# The same works for the gates after the table: picking one makes every
# if-statement before it fall through, then takes the picked arm.

init 999 python:

    class _URMFState(python_object):
        def __init__(self):
            self.pending = python_list()   # [(if-statement, arm)], -1 = none matches

    def _urmf_state():
        holder = x52URM.Var
        st = getattr(holder, "_urmfState", None)
        if st is None:
            st = _URMFState()
            holder._urmfState = st
        return st

    def _urmf_set(spec, words):
        st = _urmf_state()
        st.pending = python_list(spec)
        renpy.notify(words)

    def _urmf_take(node):
        """The arm a pending force wants for this if-statement, or None."""

        st = _urmf_state()
        if not st.pending:
            return None
        for i, (target, arm) in enumerate(st.pending):
            if target is node:
                del st.pending[i]
                return arm
        return None

    try:
        _urmf_if_execute = renpy.ast.If.execute

        def _urmf_execute(self):
            arm = _urmf_take(self)
            if arm is None:
                return _urmf_if_execute(self)
            entries = self.entries or ()
            if 0 <= arm < len(entries) and entries[arm][1]:
                target = entries[arm][1][0]
            else:
                target = self.next
            renpy.game.context().next_node = target

        if not getattr(renpy.ast.If.execute, "_urmf", False):
            _urmf_execute._urmf = True
            renpy.ast.If.execute = _urmf_execute
    except Exception as error:
        print("URM+: paths behind a jump stay unforceable (%s)" % (error,))

    def _urmf_forget():
        _urmf_state().pending = python_list()

    if _urmf_forget not in config.after_load_callbacks:
        config.after_load_callbacks.append(_urmf_forget)

    class _URMFForce(python_object):
        """Select on a row of the Path options table that URM cannot force."""

        def __init__(self, arm):
            self.arm = arm

        def __call__(self):
            detected = x52URM.PathDetection.nextIfStatement
            if not detected:
                renpy.notify("URM: the path is no longer ahead")
                return
            spec = python_list()
            spec.append((detected[0], self.arm))
            _urmf_set(spec, "URM: path %d will be taken when the game gets there" % (self.arm + 1))

        def __eq__(self, other):
            return isinstance(other, _URMFForce) and other.arm == self.arm

        def __ne__(self, other):
            return not self.__eq__(other)

        def __hash__(self):
            return hash(("urmf", self.arm))

    def urmf_force_later(row):
        specs = getattr(x52URM.Var, "_urmfLaterSpecs", None) or ()
        if row >= len(specs):
            renpy.notify("URM: that path is no longer ahead")
            return
        _urmf_set(specs[row], "URM: that path will be taken when the game gets there")

    try:
        _urmf_action = x52URM.Path.Action

        def _urmf_action_get(self):
            action = _urmf_action.fget(self)
            if action is not None:
                return action
            arm = getattr(self, "_m1_PathDetection__index", None)
            if arm is None:
                return None
            return _URMFForce(arm)

        x52URM.Path.Action = property(_urmf_action_get)
    except Exception as error:
        print("URM+: Select stays off for paths behind a jump (%s)" % (error,))


# ---------------------------------------------------------------------------
# Flags: choices a game keeps as words in a collection
# ---------------------------------------------------------------------------
#
# Many games do not give a choice a variable of its own. Nothing Is Forever
# adds a word to one set - option("ch6_kim_accept") - and tests it with
# true("ch6_kim_accept"), 1,133 and 1,987 times; its paths are objects in
# another set, added with new_path(kim_mercy_path) and tested with
# on_path("kim_mercy_path"). URM's editor sees "a set" and stops there.
#
# The index learns each game's helpers from their definitions (_URMIndex.
# _helpers) and turns every test and every setter call into a flag named by
# the code that tests it - true("ch6_kim_accept"), on_path("kim_mercy_path"),
# or "met_kim" in diary for a word tested directly. From there a flag is a
# variable like any other to the variable panel: what each side gets you,
# which choice sets it, warnings.
#
# Reading a flag never calls the game's helper: the collection is read
# directly. Switching one edits the collection directly too - adding the word,
# or the object that stands for it - rather than calling new_path(), which
# would also pop the game's "new path" notification.

init 999 python:

    def _urmfl_index():
        index = _urmi_index()
        if index is None or index.state != "ready" or not getattr(index, "flags", None):
            return None
        return index

    def _urmfl_record(name):
        index = _urmfl_index()
        if index is None or not isinstance(name, _urmi_text):
            return None
        return index.flags.get(name)

    def _urmfl_getters(index):
        found = getattr(index, "_urmflGetters", None)
        if found is None:
            found = python_dict()
            for fname, (role, coll, _attr) in index.helpers.items():
                if role == "get" and coll not in found:
                    found[coll] = fname
            index._urmflGetters = found
        return found

    def _urmfl_name_of(node):
        """The flag a test is, for true("x") and "x" in coll - else None."""

        index = _urmfl_index()
        if index is None:
            return None
        if isinstance(node, _urmi_ast.Call):
            if not isinstance(node.func, _urmi_ast.Name) or not node.args:
                return None
            ok, word = _urmi_literal(node.args[0])
            if not ok or not isinstance(word, _urmi_text):
                return None
            name = u'%s("%s")' % (node.func.id, word)
            return name if name in index.flags else None
        if isinstance(node, _urmi_ast.Compare) and len(node.ops) == 1 and \
                isinstance(node.ops[0], (_urmi_ast.In, _urmi_ast.NotIn)):
            ok, word = _urmi_literal(node.left)
            coll = _urmi_name(node.comparators[0])
            if not ok or not isinstance(word, _urmi_text) or coll is None:
                return None
            getter = _urmfl_getters(index).get(coll)
            name = u'%s("%s")' % (getter, word) if getter else u'"%s" in %s' % (word, coll)
            return name if name in index.flags else None
        return None

    def _urmfl_collection(rec):
        try:
            value = _urmp_ev(_urmp_parse(rec.coll))
        except Exception:
            return None
        if value is _URMP_UNK:
            return None
        return value

    def _urmfl_matches(rec, member):
        if rec.attr:
            return getattr(member, rec.attr, None) == rec.word
        return member == rec.word

    def urmfl_is_on(name):
        """True / False, or None when the game has not made the collection yet."""

        rec = _urmfl_record(name)
        if rec is None:
            return None
        coll = _urmfl_collection(rec)
        if coll is None:
            return False
        try:
            if isinstance(coll, python_dict):
                return bool(coll.get(rec.word))
            for member in coll:
                if _urmfl_matches(rec, member):
                    return True
            return False
        except Exception:
            return None

    def _urmfl_object(rec):
        """The object that stands for an object-kept flag, e.g. kim_mercy_path."""

        for objname in rec.objects:
            value = _urmp_value(objname)
            if value is not _URMP_UNK and _urmfl_matches(rec, value):
                return value
        count = 0
        for value in python_list(renpy.store.__dict__.values()):
            count += 1
            if count > 50000:
                break
            try:
                if not callable(value) and getattr(value, rec.attr, None) == rec.word:
                    return value
            except Exception:
                continue
        return None

    def urmfl_set(name, on):
        rec = _urmfl_record(name)
        if rec is None:
            return
        coll = _urmfl_collection(rec)
        if coll is None:
            renpy.notify("URM: %s does not exist in this save yet" % rec.coll)
            return
        current = urmfl_is_on(name)
        try:
            if on and not current:
                member = rec.word
                if rec.attr:
                    member = _urmfl_object(rec)
                    if member is None:
                        renpy.notify("URM: could not find what stands for %s" % rec.word)
                        return
                if isinstance(coll, python_dict):
                    coll[rec.word] = True
                elif hasattr(coll, "add"):
                    coll.add(member)
                else:
                    coll.append(member)
            elif not on and current:
                if isinstance(coll, python_dict):
                    coll.pop(rec.word, None)
                else:
                    for member in python_list(coll):
                        if _urmfl_matches(rec, member):
                            coll.remove(member)
        except Exception as error:
            renpy.notify("URM: could not change %s (%s)" % (rec.word, error))
            return
        renpy.notify("URM: %s is now %s" % (rec.word, "ON" if on else "OFF"))
        renpy.restart_interaction()

    def urmfl_has():
        return _urmfl_index() is not None

    def urmfl_rows(text, limit=200):
        """([(flag, word, on, what it is)], how many match) for the Flags screen."""

        index = _urmfl_index()
        rows = python_list()
        if index is None:
            return (rows, 0)
        needle = (text or u"").strip().lower()
        matched = 0
        for name in sorted(index.flags, key=lambda n: index.flags[n].word.lower()):
            rec = index.flags[name]
            if needle and needle not in rec.word.lower() and needle not in name.lower():
                continue
            matched += 1
            if len(rows) >= limit:
                continue
            reads = len(index.reads.get(name) or ())
            writes = len(index.writes.get(name) or ())
            info = u"checked in %d place%s, set in %d" % (reads, "" if reads == 1 else "s", writes)
            rows.append((name, _urmi_safe(rec.word), urmfl_is_on(name), _urmi_safe(info)))
        return (rows, matched)

    class _URMFlagVar(python_object):
        """What the variable panel needs from a variable, for a flag."""

        isFlag = True
        isEditable = True
        varType = "boolean"

        def __init__(self, name):
            self.name = name
            rec = _urmfl_record(name)
            self.word = _urmi_safe(rec.word if rec else name)
            if rec is None:
                self.where = u""
            elif rec.getter:
                self.where = _urmi_safe(u"Kept in %s, tested with %s()" % (rec.coll, rec.getter))
            else:
                self.where = _urmi_safe(u"Kept in %s" % rec.coll)

        @property
        def value(self):
            return urmfl_is_on(self.name)

    def urmfl_var(name):
        return _URMFlagVar(name)

    def _urmfl_open(name):
        if renpy.has_screen("urmfl_flag_dialog"):
            renpy.show_screen("urmfl_flag_dialog", name=name)
            renpy.restart_interaction()

    config.hyperlink_handlers["URMFlag"] = _urmfl_open

    import re as _urmfl_re
    _URMFL_CALL = _urmfl_re.compile(
        r"(\{color=[^{}]*\})?\b([A-Za-z_]\w*)(\{/color\})?"
        r"\((\{color=[^{}]*\})?([\"'])([^\"'{}]*)\5(\{/color\})?\)")

    def _urmfl_links(view, coloredCode):
        """In the code view and on the path cards, true("x") opens the flag."""

        index = _urmfl_index()
        if index is None:
            return coloredCode

        def link(match):
            name = u'%s("%s")' % (match.group(2), match.group(6))
            if name not in index.flags:
                return match.group()
            return u"{a=URMFlag:%s}%s{/a}" % (name, match.group())

        try:
            return _URMFL_CALL.sub(link, coloredCode)
        except Exception:
            return coloredCode


# ---------------------------------------------------------------------------
# Keep skipping past a small change - a typo fix, a reworded line
# ---------------------------------------------------------------------------
#
# A developer who fixes a typo gives that line a new identity, so a player who
# has read the scene before is stopped by a skip on one changed line. Ren'Py
# decides "seen" in one place, Context.seen_current (execution.py:888), asked
# by the say statement and the dialogue's skip handling for both slow and fast
# skip (behavior.py:814, character.py:483 and :536).
#
# While skipping, an unseen line now counts as seen when it is one of at most
# N unseen lines sitting between seen lines - a seen line before them in the
# same passage, and one after them - so N new lines in a row are skipped and
# N+1 stop the skip as before:
#
#     seen  new  new  new  seen         -> keeps skipping (N = 3)
#     seen  new  new  new  new  seen    -> stops
#
# The look-ahead follows the script the way it will run: through jumps, into
# calls, and down the if-branch whose condition is true now. A choice menu, a
# return or anything it cannot follow ends it as "not a small change", so new
# content still stops the skip. The look back stays inside the passage: a short
# reply to a choice the player never made starts a block of its own and still
# stops the skip. Only while skipping; reading is untouched.

init 999 python:

    import sys as _urms_sys

    try:
        x52URM.SettingsClass.defaultValues.setdefault("urmcSkipTypos", 3)
    except Exception as error:
        print("URM+: skip-past-small-changes setting not registered (%s)" % (error,))

    _URMS_WALK = 400

    def _urms_limit():
        try:
            value = x52URM.Settings.get("urmcSkipTypos")
        except Exception:
            value = None
        if value is None:
            return 3
        try:
            return int(value)
        except Exception:
            return 0

    def _urms_lookup(name):
        try:
            return renpy.game.script.lookup(name)
        except Exception:
            return None

    def _urms_next(node):
        """The statement that runs after `node`, or None where it cannot be told."""

        ast = renpy.ast
        if isinstance(node, ast.Translate):
            return node.block[0] if node.block else node.next
        if isinstance(node, ast.Jump):
            if getattr(node, "expression", False):
                return None
            return _urms_lookup(node.target)
        if isinstance(node, ast.Call):
            if getattr(node, "expression", False):
                return None
            return _urms_lookup(node.label)
        if isinstance(node, (ast.Menu, ast.Return, ast.While)):
            return None
        if isinstance(node, ast.If):
            for cond, block in node.entries:
                try:
                    taken = renpy.python.py_eval(cond)
                except Exception:
                    return None
                if taken:
                    return block[0] if block else node.next
            return node.next
        if isinstance(node, ast.Label):
            return node.block[0] if getattr(node, "block", None) else node.next
        return getattr(node, "next", None)

    def _urms_line(node):
        """The dialogue line a statement is, or None."""

        return node if isinstance(node, renpy.ast.Say) else None

    # Statements a line can sit next to without leaving its passage.
    def _urms_passes(node):
        ast = renpy.ast
        kinds = python_list()
        for name in ("Translate", "EndTranslate", "Show", "Scene", "Hide", "With", "Python",
                     "Pass", "UserStatement", "ShowLayer", "Camera"):
            cls = getattr(ast, name, None)
            if cls is not None:
                kinds.append(cls)
        return isinstance(node, tuple(kinds))

    def _urms_back(index, node):
        """The statement before `node` in the same passage, or None at its start."""

        return index.prev.get(id(node))

    def _urms_small_change(current, limit):
        """
        True when `current` is one of at most `limit` unseen lines sitting
        between seen lines: a seen line before them in the same passage, and a
        seen line after them on the way the game will run.

        The line before must be in the same passage - not across a menu option
        or an if-branch - because a short reply to a choice the player never
        made also sits between seen lines, after the menu and before the merge.
        A typo fix sits inside text already read; a new reply starts its own
        block, with nothing before it there.
        """

        index = _urmi_index()
        if index is None or index.state != "ready" or not getattr(index, "prev", None):
            return False

        cache = getattr(x52URM.Var, "_urmsCache", None)
        if cache is None or len(cache) > 500:
            cache = python_dict()
            x52URM.Var._urmsCache = cache
        key = (current, limit)
        if key in cache:
            return cache[key]

        result = False
        node = _urms_lookup(current)
        seen = renpy.game.persistent._seen_ever
        if isinstance(node, renpy.ast.Say):
            unseen = 1

            # Backwards, inside this passage, to a seen line.
            before = False
            walk = _urms_back(index, node)
            steps = 0
            while walk is not None and steps < _URMS_WALK and unseen <= limit:
                steps += 1
                line = _urms_line(walk)
                if line is not None:
                    if line.name in seen:
                        before = True
                        break
                    unseen += 1
                elif not _urms_passes(walk):
                    break
                walk = _urms_back(index, walk)

            # Forwards, the way the game will run, to a seen line.
            if before and unseen <= limit:
                walk = _urms_next(node)
                steps = 0
                while walk is not None and steps < _URMS_WALK:
                    steps += 1
                    if isinstance(walk, renpy.ast.Say):
                        if walk.name in seen:
                            result = True
                            break
                        unseen += 1
                        if unseen > limit:
                            break
                    walk = _urms_next(walk)
        cache[key] = result
        return result

    try:
        _urms_context = _urms_sys.modules["renpy.execution"].Context
        _urms_original = _urms_context.seen_current
        # The plain function: on Python 2 the unbound method insists on a real
        # Context as self, which a test's stand-in is not.
        _urms_original = getattr(_urms_original, "__func__", _urms_original)

        def _urms_seen_current(self, ever):
            if _urms_original(self, ever):
                return True
            if not ever or not config.skipping:
                return False
            limit = _urms_limit()
            if limit <= 0:
                return False
            try:
                return _urms_small_change(self.current, limit)
            except Exception:
                return False

        if not getattr(_urms_original, "_urms", False):
            _urms_seen_current._urms = True
            _urms_context.seen_current = _urms_seen_current
    except Exception as error:
        print("URM+: skipping still stops on small changes (%s)" % (error,))
