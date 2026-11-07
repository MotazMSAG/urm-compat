"""
Text edits applied to URM's own screen files as it is installed.

URM's .x52 / .x52t files are plain Ren'Py screen-language source carried inside
its archive, so a UI change is a literal text replacement on those entries -
no decompiling, no recompiling, and nothing to re-derive when URM updates
except these patterns.

Every tweak is guarded three ways:

  * `check` must be absent - if it is already there the tweak is a no-op, so
    installing twice (or over an already-patched archive) changes nothing.
  * `old` must occur EXACTLY once - zero or several means URM moved the code,
    and the tweak is skipped rather than guessed at.
  * a failed tweak never fails the install. URM still works; it just does not
    get that tweak, and the caller is told which one was skipped.

apply() returns (applied, skipped) so the installer can report honestly.
"""

SCREENS = "0x52-URM/screens/"

TWEAKS = []


def _as_bytes(text):
    # The .x52 files are CRLF; keep edits in the same shape as the file.
    return text.replace("\n", "\r\n").encode("utf-8")


def tweak(name, path, check, old, new):
    """
    Registers one edit. `check`, `old` and `new` are written with plain \n and
    converted to CRLF here, so the patterns below stay readable.

    `old` may be a list. Earlier versions of a tweak are listed after the
    original, so an archive patched by an older build is upgraded in place
    rather than skipped - the installer prefers an already-installed archive
    over its built-in copy, so without this a second run would keep the old
    version forever.
    """

    if not isinstance(old, (list, tuple)):
        old = [old]

    TWEAKS.append({
        "name": name,
        "path": path,
        "check": _as_bytes(check),
        "old": [_as_bytes(o) for o in old],
        "new": _as_bytes(new),
    })


def apply(contents):
    """
    Applies every registered tweak to `contents`, a {archive name: bytes} dict,
    in place. Returns (applied, skipped) where each is a list of
    (name, reason) - reason is None for applied tweaks.
    """

    applied = []
    skipped = []

    for item in TWEAKS:
        data = contents.get(item["path"])


        if data is None:
            skipped.append((item["name"], "%s is not in the archive" % item["path"]))
            continue

        if item["check"] and item["check"] in data:
            applied.append((item["name"], "already present"))
            continue

        match = None
        counts = []

        for candidate in item["old"]:
            count = data.count(candidate)
            counts.append(count)
            if count == 1:
                match = candidate
                break

        if match is None:
            best = max(counts) if counts else 0
            skipped.append((
                item["name"],
                "the code it patches %s in %s - URM probably changed it" % (
                    "was not found" if best == 0 else "appears %d times" % best,
                    item["path"]),
            ))
            continue

        contents[item["path"]] = data.replace(match, item["new"])
        applied.append((item["name"], None))

    return applied, skipped


# ---------------------------------------------------------------------------
# Show the gating condition without having to ask for it
# ---------------------------------------------------------------------------
#
# URM knows a path's or choice's condition as a plain string - Path.condition
# and URMChoice.condition are just the text taken off the renpy.ast node - but
# only ever shows it behind two clicks: open the dialog, then press Condition.
#
# These four tweaks put the text in front of you instead. The Condition button
# stays: its popup renders the condition with URM's syntax highlighting and
# clickable variables, which a one-line label cannot.
#
# A condition of 'True' is Ren'Py's way of saying "no condition" - the else
# branch of an if, or a menu choice with no `if` clause - so those are left
# out rather than printed as noise.
#
# Conditions are untrusted text as far as the text engine goes: they can
# contain [ and { , which Ren'Py reads as interpolation and tag markers. Each
# one is passed through scaleText(escapeStyling=True), which neutralises the
# braces and trims it to fit, and [ is then doubled, which is how Ren'Py
# escapes it. The notification lines also carry substitute False.

_BUTTON = (
    # \\u here is the two characters a backslash and a u, which is what the
    # screen file literally contains - not a unicode escape.
    "                            use x52URM_iconButton('\\uf1c2',"
    " If(selectedIndex==i, '{u}C{/u}ondition', %s), %s.OpenConditionView)"
)

# Same line in both dialogs, differing only in the name of the row variable.
for _file, _var, _width in (("paths", "statement", 14), ("choices", "choice", 12)):
    tweak(
        "condition on the %s row" % ("path" if _file == "paths" else "choice"),
        SCREENS + _file + ".rpy.x52",
        check="x52URM.scaleText(%s.condition" % _var,
        old=_BUTTON % ("'{urm_notl}Condition{/urm_notl}'", _var),
        new=_BUTTON % (
            "'{urm_notl}' + x52URM.scaleText(%s.condition, %d,"
            " 'x52URM_button_text', escapeStyling=True).replace('[', '[[')"
            " + '{/urm_notl}'" % (_var, _width),
            _var,
        ),
    )


# The corner notification - a card per gate
# ---------------------------------------------------------------------------
#
# Both blocks sit in a vbox whose children are at 20 spaces.
#
# A gate is a lighter band between two rules, with its effects on a darker
# fill underneath. The pattern never varies - the helper guarantees at least
# one effect row - so "a lighter strip between two lines" always means a
# condition, and the darker fill under it always means what that condition
# changes. That is the separation earlier versions tried, and failed, to carry
# with a marker column alone.
#
# Every choice here is deliberate:
#
#   * zero new styles. A bare `frame:` resolves to x52URM_frame, which brings
#     background Solid(Theme.background) AND padding (7,5), so both are
#     overridden inline on every frame. Missing either one puts the fill wrong
#     and every width out by 14px. Inline frames are URM's own idiom here.
#   * the rules are `frame style_suffix 'seperator'` with an inline
#     background. x52URM_seperator is `is x52URM_default`, so its padding is
#     already 0, and overriding its background is what URM's own call sites
#     do - the style's default is Theme.primary, which fails contrast in five
#     themes, while buttonBorder clears it in all thirteen. ysize is
#     scalePxInt(2), never 1: int(1 * 720/1080) is 0, an invisible rule at
#     720p.
#   * backgrounds are bare theme strings, never Solid(...). A theme name that
#     does not resolve comes back as None, and `background None` is simply no
#     fill, where Solid(None) would raise while the overlay is being drawn.
#   * padding is always a 2-tuple, which is URM's own arity.
#   * no xfill and no yfill anywhere, and an explicit xsize on every frame. A
#     Window only raises the offered width to xminimum, so an xfill child
#     claims the whole layer. fill semantics are not even constant across host
#     games: 00compat flips config.fill_shrinks_frame for any game declaring
#     script_version <= 8.2.1.
#   * every text carries an explicit xmaximum. Without one it lays out at
#     layer width and is then clipped by the frame, losing its tail silently.
#   * yalign 0.0 on every text. x52URM_icon is `is x52URM_text` (yalign 0)
#     while notification_text is `is x52URM_button_text` (yalign .5); mixing
#     them floats the ordinal to the middle of a two-line condition while the
#     glyph stays at the top.
#   * substitute False everywhere, and nothing escapes "[". colorize() escapes
#     braces itself, so no row may escape them twice.
#
# The width is not set through the screen's `default width`: that value is
# read as xminimum by all four notifications and as the slide distance by both
# transforms. Content widens the button on its own instead.
#
# The hasattr guard is the degradation contract - no helper, no exception,
# URM's own line draws instead.

_CARDS = """                    $ _urmGates = (%(fn)s() if hasattr(renpy.store, '%(fn)s') else None)
                    if _urmGates and _urmGates[1]:
                        $ _urmSummary = _urmGates[0]
                        $ _urmCards = _urmGates[1]
                        $ _urmW = x52URM.scalePxInt(344)
                        vbox:
                            spacing 0
                            frame:
                                background x52URM.Theme.colors.buttonBg
                                xsize _urmW
                                padding (x52URM.scalePxInt(6), x52URM.scalePxInt(3))
                                text _urmSummary style_suffix 'notification_text' substitute False bold True yalign 0.0 xmaximum (_urmW - x52URM.scalePxInt(12))
                            for _urmIcon, _urmNum, _urmHead, _urmEffects in _urmCards:
                                frame style_suffix 'seperator' background x52URM.Theme.colors.buttonBorder xsize _urmW ysize x52URM.scalePxInt(2)
                                frame:
                                    background x52URM.Theme.colors.buttonBgHover
                                    xsize _urmW
                                    padding (x52URM.scalePxInt(6), x52URM.scalePxInt(4))
                                    hbox:
                                        spacing x52URM.scalePxInt(4)
                                        text _urmIcon style_suffix 'icon' substitute False yalign 0.0
                                        text _urmNum style_suffix 'notification_text' substitute False bold True yalign 0.0 min_width x52URM.scalePxInt(18) text_align 1.0
                                        text _urmHead style_suffix 'notification_text' substitute False yalign 0.0 xmaximum (_urmW - x52URM.scalePxInt(62)) rest_indent x52URM.scalePxInt(10)
                                frame style_suffix 'seperator' background x52URM.Theme.colors.buttonBorder xsize _urmW ysize x52URM.scalePxInt(2)
                                frame:
                                    background x52URM.Theme.colors.buttonBg
                                    xsize _urmW
                                    padding (x52URM.scalePxInt(6), x52URM.scalePxInt(4))
                                    vbox:
                                        spacing x52URM.scalePxInt(2)
                                        for _urmBullet, _urmBody in _urmEffects:
                                            hbox:
                                                spacing x52URM.scalePxInt(4)
                                                text _urmBullet style_suffix 'icon' substitute False yalign 0.0
                                                text _urmBody style_suffix 'notification_text' substitute False yalign 0.0 xmaximum (_urmW - x52URM.scalePxInt(40)) rest_indent x52URM.scalePxInt(10)"""


def _draw(helper, fallback=None):
    """The card block for one helper, with URM's own line as the fallback."""

    block = _CARDS % {"fn": helper}

    if fallback is None:
        return block

    return block + "\n                    else:\n" + fallback


def _check(helper):
    """Text that is in this build's block and no other - it names the helper."""

    return "$ _urmGates = (%s()" % helper


# Earlier shapes of the same block, so an archive from those builds upgrades.
# The block this build replaces: a marker column and a rule between gates.
# Kept so an archive patched by that build upgrades in place rather than being
# skipped - the installer prefers an already-installed archive over its own
# copy, so without this a second run would keep the old version forever.
_DRAW_V8_BODY = """                    $ _urmRows = %(fn)s()
                    if _urmRows:
                        for _urmMark, _urmBody, _urmNew in _urmRows:
                            if _urmNew:
                                frame style_suffix 'seperator' ysize x52URM.scalePxInt(2) xsize x52URM.scalePxInt(252) background x52URM.Theme.secondary
                            hbox:
                                spacing x52URM.scalePxInt(6)
                                text _urmMark style_suffix 'notification_text' substitute False min_width x52URM.scalePxInt(44)
                                text _urmBody style_suffix 'notification_text' substitute False xmaximum x52URM.scalePxInt(208) rest_indent x52URM.scalePxInt(12)"""


def _draw_v8(helper, fallback=None):

    block = _DRAW_V8_BODY % {"fn": helper}

    if fallback is None:
        return block

    return block + "\n                    else:\n" + fallback


_DRAW_V7 = (
    "\n\n"
    "                    for _urmMark, _urmBody in %s():\n"
    "                        hbox:\n"
    "                            spacing x52URM.scalePxInt(6)\n"
    "                            text _urmMark style_suffix 'notification_text'"
    " substitute False xsize x52URM.scalePxInt(52)\n"
    "                            text _urmBody style_suffix 'notification_text'"
    " substitute False xmaximum x52URM.scalePxInt(300)"
    " rest_indent x52URM.scalePxInt(12)"
)

_DRAW_V6 = (
    "\n\n"
    "                    for _urmLine in %s():\n"
    "                        text _urmLine style_suffix 'notification_text'"
    " substitute False xmaximum (width - x52URM.scalePxInt(20))"
)

_DRAW_V5 = (
    "\n\n"
    "                    for _urmLine in %s():\n"
    "                        text _urmLine style_suffix 'notification_text'"
    " substitute False"
)


# Earlier shapes, kept so an archive patched by an older build is upgraded
# rather than left alone. Longest first - see tweak().
_LINE_V4 = (
    "                    for _urmIdx, _urmItem in enumerate(%s or []):\n"
    "                        $ _urmCond = urm_condition(_urmItem)\n"
    "                        $ _urmEff = urm_effect(_urmItem)\n"
    "                        if _urmCond:\n"
    "                            text ('{urm_notl}' + str(_urmIdx + 1)"
    " + ': if ' + _urmCond + '{/urm_notl}')"
    " style_suffix 'notification_text' substitute False\n"
    "                        if _urmEff:\n"
    # A word, not a glyph: URM ships a subsetted Roboto that has no U+2192,
    # so an arrow renders as a missing-glyph box. 'if' / 'do' also reads as a
    # pair, which a symbol would not.
    "                            text ('{urm_notl}' + str(_urmIdx + 1)"
    " + ': do ' + _urmEff + '{/urm_notl}')"
    " style_suffix 'notification_text' substitute False"
)

# Earlier shapes of this tweak, so an archive patched by an older build is
# upgraded rather than left alone. Longest first - see tweak().
_LINE_V3 = _LINE_V4.replace("+ ': do ' + _urmEff", "+ ': \\u2192 ' + _urmEff")

_LINE_V2 = (
    "                    for _urmIdx, _urmItem in enumerate(%s or []):\n"
    "                        $ _urmText = urm_summary(_urmItem)\n"
    "                        if _urmText:\n"
    "                            text ('{urm_notl}' + str(_urmIdx + 1) + ': '"
    " + _urmText + '{/urm_notl}')"
    " style_suffix 'notification_text' substitute False"
)

_LINE_V1 = (
    "                    for _urmIdx, _urmItem in enumerate(%s or []):\n"
    "                        if _urmItem.condition != 'True':\n"
    "                            text ('{urm_notl}' + str(_urmIdx + 1) + ': '"
    " + x52URM.scaleText(_urmItem.condition, 225, 'x52URM_notification_text',"
    " pixelTarget=True, escapeStyling=True).replace('[', '[[')"
    " + '{/urm_notl}') style_suffix 'notification_text' substitute False"
)

_PATH_COUNT = (
    "                    text '[x52URM.PathDetection.statementsCount] options'"
    " style_suffix 'notification_text'"
)

# When the detected if-statement has no else, not matching it falls straight
# through into whatever check comes next. URM stops at the first if, so those
# follow-on gates are invisible - "1 options" reads as one decision when it is
# a chain. These are labelled "next N" rather than numbered with the rows
# above, because they are not rows in the Path options table.
_NEXT_GATES = (
    "\n"
    "                    for _urmIdx, _urmItem in enumerate(urm_next_gates()):\n"
    "                        $ _urmCond = urm_condition(_urmItem)\n"
    "                        $ _urmEff = urm_effect(_urmItem)\n"
    "                        if _urmCond:\n"
    "                            text ('{urm_notl}next ' + str(_urmIdx + 1)"
    " + ': if ' + _urmCond + '{/urm_notl}')"
    " style_suffix 'notification_text' substitute False\n"
    "                        if _urmEff:\n"
    "                            text ('{urm_notl}next ' + str(_urmIdx + 1)"
    " + ': do ' + _urmEff + '{/urm_notl}')"
    " style_suffix 'notification_text' substitute False"
)

# "[N] options" counts the one if-statement URM found, so it reads "1 options"
# above a chain of two gates. It is only drawn now when the rows are missing,
# where a count is better than nothing - one indent deeper, inside the else.
_PATH_FALLBACK = "    " + _PATH_COUNT

tweak(
    "what each path needs and does, under Path detected",
    SCREENS + "watchpanel.rpy.x52",
    check=_check("urm_path_cards"),
    # Most specific first: the pristine line is a prefix of the patched one,
    # so matching it first would leave the old block behind.
    old=[
        _draw_v8("urm_path_lines", _PATH_FALLBACK),
        _PATH_COUNT + _DRAW_V7 % "urm_path_lines",
        _PATH_COUNT + _DRAW_V6 % "urm_path_lines",
        _PATH_COUNT + _DRAW_V5 % "urm_path_lines",
        _PATH_COUNT + "\n\n" + _LINE_V4 % "x52URM.PathDetection.statements"
            + _NEXT_GATES,
        _PATH_COUNT + "\n\n" + _LINE_V4 % "x52URM.PathDetection.statements",
        _PATH_COUNT + "\n\n" + _LINE_V3 % "x52URM.PathDetection.statements",
        _PATH_COUNT + "\n\n" + _LINE_V2 % "x52URM.PathDetection.statements",
        _PATH_COUNT + "\n\n" + _LINE_V1 % "x52URM.PathDetection.statements",
        _PATH_COUNT,
    ],
    new=_draw("urm_path_cards", _PATH_FALLBACK),
)

_CHOICE_HIDDEN = (
    "                    if x52URM.Choices.hiddenCount > 0:\n"
    "                        text '[x52URM.Choices.hiddenCount] hidden'"
    " style_suffix 'notification_text'"
)

# Unlike the path count, the hidden-choice count says something the rows do
# not - choices URM can see and you cannot - so it stays above them.
tweak(
    "what each choice needs and does, under Choices detected",
    SCREENS + "watchpanel.rpy.x52",
    check=_check("urm_choice_cards"),
    old=[
        _CHOICE_HIDDEN + "\n" + _draw_v8("urm_choice_lines"),
        _CHOICE_HIDDEN + _DRAW_V7 % "urm_choice_lines",
        _CHOICE_HIDDEN + _DRAW_V6 % "urm_choice_lines",
        _CHOICE_HIDDEN + _DRAW_V5 % "urm_choice_lines",
        _CHOICE_HIDDEN + "\n\n" + _LINE_V4 % "x52URM.Choices.currentChoices",
        _CHOICE_HIDDEN + "\n\n" + _LINE_V3 % "x52URM.Choices.currentChoices",
        _CHOICE_HIDDEN + "\n\n" + _LINE_V2 % "x52URM.Choices.currentChoices",
        _CHOICE_HIDDEN + "\n\n" + _LINE_V1 % "x52URM.Choices.currentChoices",
        _CHOICE_HIDDEN,
    ],
    new=_CHOICE_HIDDEN + "\n" + _draw("urm_choice_cards"),
)


# ---------------------------------------------------------------------------
# Search: the Deeper button and the depth selector
# ---------------------------------------------------------------------------
#
# Both are guarded on something only the helper defines, so an archive whose
# zzz_urm_compat.rpyc failed to compile for this engine draws URM's own UI
# instead of a dead control:
#
#   * the button is hidden unless SearchClass carries urmcNextDepth, which
#     the helper sets as a class attribute. The level is worked out once per
#     search, not per redraw - anything resolved on every frame is the cost
#     the helper exists to remove, and a screen expression would put it
#     straight back. It reads 0 for a label search and at the depth cap, so
#     the button also disappears when there is nothing further to try.
#   * the depth rows are hidden unless urmcSearchDepth is a registered
#     setting. Without the helper, SetField would be dropped silently by
#     Settings.__setattr__ and the radiobuttons would never light up.

_SEARCH = SCREENS + "search.rpy.x52"

_RESULTS_COUNT = """                hbox xalign 1.0 yalign .5:
                    text 'Results: {}'.format(len(x52URM.Search.results))
                    null width x52URM.scalePxInt(10)"""

# \\ue5da is the two characters backslash and u, which is what the screen file
# literally holds - subdirectory_arrow_right, from the Material Icons face
# behind style_suffix 'icon'. It is already used by the notification cards, so
# it is known to be in the subset URM ships.
_DEEPER = """                hbox xalign 1.0 yalign .5 spacing x52URM.scalePxInt(6):
                    if getattr(x52URM.Search, 'urmcNextDepth', 0) > 0:
                        textbutton '{urm_notl}\\ue5da Deeper ([x52URM.Search.urmcNextDepth] levels){/urm_notl}' style_suffix 'buttonPrimary' yalign .5 selected False hovered x52URM.Tooltip('Run this same search again, looking one level further inside objects. Costs nothing until you press it.') unhovered x52URM.Tooltip() action Function(x52URM.Search.urmcDeepen)
                    text 'Results: {}'.format(len(x52URM.Search.results)) yalign .5
                    null width x52URM.scalePxInt(10)"""

tweak(
    "a Deeper button over the search results",
    _SEARCH,
    check="urmcNextDepth",
    old=_RESULTS_COUNT,
    new=_DEEPER,
)


# The last row of the search-options dialog, which is where "Search in
# objects/lists/dicts" already lives - the depth rows belong with it rather
# than on the options page, because this is the dialog you are already in when
# a search came back empty.
_UNSUPPORTED = """            hbox:
                use x52URM_checkbox(checked=x52URM.Settings.showUnsupportedVariables, text='Show unsupported variables', action=ToggleField(x52URM.Settings, 'showUnsupportedVariables', True, False))
                textbutton "\\ueb8b" style_suffix "icon_button" yalign .5 tooltip "Explain unsupported variables" action x52URM.Confirm(\"\"\"Show variables that URM cannot modify\"\"\", title='Unsupported variables')"""

_DEPTH = _UNSUPPORTED + """

        if 'urmcSearchDepth' in x52URM.SettingsClass.defaultValues:
            null height x52URM.scalePxInt(10)
            hbox:
                text 'Search depth:' yalign .5
                textbutton "\\ueb8b" style_suffix "icon_button" yalign .5 hovered x52URM.Tooltip("Explain search depth") unhovered x52URM.Tooltip() action x52URM.Confirm(\"\"\"URM looks one level inside an object, and no further.\\n\\nSo if the game keeps {b}gold{/b} in {b}mc.inventory{/b}, searching {b}gold{/b} finds nothing: {b}mc.inventory{/b} is one level down and {b}mc.inventory.gold{/b} is two.\\n\\nRaising this finds those, but every extra level scans more variables and takes longer. Leave it at 1 and use the {b}Deeper{/b} button above the results when you want one more level just this once.\"\"\", title='Search depth')
            hbox spacing 2 box_wrap True:
                use x52URM_radiobutton(checked=(x52URM.Settings.urmcSearchDepth==1), text='{urm_notl}1 level (default){/urm_notl}', action=SetField(x52URM.Settings, 'urmcSearchDepth', 1), xsize=x52URM.scalePxInt(150))
                use x52URM_radiobutton(checked=(x52URM.Settings.urmcSearchDepth==2), text='{urm_notl}2 levels{/urm_notl}', action=SetField(x52URM.Settings, 'urmcSearchDepth', 2), xsize=x52URM.scalePxInt(110))
                use x52URM_radiobutton(checked=(x52URM.Settings.urmcSearchDepth==3), text='{urm_notl}3 levels{/urm_notl}', action=SetField(x52URM.Settings, 'urmcSearchDepth', 3), xsize=x52URM.scalePxInt(110))"""

tweak(
    "a search-depth selector in the search options",
    _SEARCH,
    check="urmcSearchDepth",
    old=_UNSUPPORTED,
    new=_DEPTH,
)


# ---------------------------------------------------------------------------
# Skip unseen text, on the quickmenu
# ---------------------------------------------------------------------------
#
# preferences.skip_unseen is the engine's "skip: all text / seen text" switch,
# and on most games it is three clicks into the preferences screen - which
# cannot be reached mid-scene without leaving the scene.
#
# ToggleField(_preferences, 'skip_unseen', ...) is what Ren'Py's own
# Preference("skip", "toggle") resolves to (common/00preferences.rpy:360).
# Going straight to the field skips that action's name lookup, which compares
# against _("skip") - the TRANSLATED word - and so quietly does nothing on a
# game running in another language. URM's own Auto button has that exposure;
# this one does not.
#
# State has to live in the icon, not the label: two of the four quickmenu
# styles draw the icon alone. \\ue834 and \\ue835 are check_box and
# check_box_outline_blank, the pair x52URM_checkbox itself uses, so they are
# certainly in the shipped font subset.
#
# It is inserted above Exit rather than appended, so Exit stays last.

_EXIT_BUTTON = """    if x52URM.Settings.quickmenuBtnExit:
        use URM_quickmenu_button('\\ueb4f', '{urm_notl}Exit{/urm_notl}', Quit())"""

_SKIP_UNSEEN = """    if x52URM.Settings.quickmenuBtnSkipUnseen:
        use URM_quickmenu_button(If(_preferences.skip_unseen, '\\ue834', '\\ue835'), '{urm_notl}Unseen{/urm_notl}', ToggleField(_preferences, 'skip_unseen', True, False))
""" + _EXIT_BUTTON

tweak(
    "a skip-unseen-text button on the quickmenu",
    SCREENS + "quickmenu.rpy.x52",
    check="quickmenuBtnSkipUnseen",
    old=_EXIT_BUTTON,
    new=_SKIP_UNSEEN,
)


# The matching row on the quickmenu options page. URM_options_settings
# (options.rpy.x52:606) iterates whatever dict it is handed, so a new control
# is one entry - and it gets the Local and Global columns and the Clear and
# Default buttons without asking.
_EXIT_ROW = """                ('quickmenuBtnExit', {
                    'title': '{urm_notl}{b}Button:{/b} Exit{/urm_notl}',
                    'effective': If(x52URM.Settings.quickmenuBtnExit, '{urm_notl}Show{/urm_notl}', '{urm_notl}Hide{/urm_notl}'),
                    'options': {
                        '{urm_notl}Show{/urm_notl}': True,
                        '{urm_notl}Hide{/urm_notl}': False,
                    },
                }),"""

_SKIP_UNSEEN_ROW = """                ('quickmenuBtnSkipUnseen', {
                    'title': '{urm_notl}{b}Button:{/b} Unseen{/urm_notl}',
                    'description': \"\"\"Toggles the engine's own "skip unseen text" preference.\\n\\nWith it on, holding Ctrl or pressing Skip runs through text you have never read; with it off, skipping stops at anything new.\\n\\nThe button shows a ticked box while it is on.\"\"\",
                    'effective': If(x52URM.Settings.quickmenuBtnSkipUnseen, '{urm_notl}Show{/urm_notl}', '{urm_notl}Hide{/urm_notl}'),
                    'options': {
                        '{urm_notl}Show{/urm_notl}': True,
                        '{urm_notl}Hide{/urm_notl}': False,
                    },
                }),
""" + _EXIT_ROW

tweak(
    "a row for the skip-unseen button in the quickmenu options",
    SCREENS + "options.rpy.x52",
    check="quickmenuBtnSkipUnseen",
    old=_EXIT_ROW,
    new=_SKIP_UNSEEN_ROW,
)


# ---------------------------------------------------------------------------
# Browse every variable, without knowing its name
# ---------------------------------------------------------------------------
#
# Search was the only way into the store. This hands URM_objectVar a Var over
# the store itself, which it already knows how to page and expand.

_RESET = ("                textbutton \"{urm_notl}Reset{/urm_notl}\" yalign .5"
          " action Function(x52URM.Search.resetSearch)")

tweak(
    "a Browse all button beside Search",
    _SEARCH,
    check="urm_store_root",
    old=_RESET,
    new=_RESET + """
                if hasattr(renpy.store, 'urm_store_root'):
                    textbutton "{urm_notl}Browse all{/urm_notl}" yalign .5 selected False hovered x52URM.Tooltip('Open every variable in the game as a browsable tree. No search, and no guessing at names.') unhovered x52URM.Tooltip() action SetLocalVariable('expandObjectVars', urm_store_root())""",
)


# ---------------------------------------------------------------------------
# Copy a variable's name
# ---------------------------------------------------------------------------
#
# One button in URM_modify_value covers every surface, because that dialog is
# where search results, the object browser and the watch panel all end up.
# Values need no button: they sit in an x52URM.Input, and Ren'Py's Input
# already handles ctrl+C itself.
#
# \\ue14d is content_copy. Verified present in the MaterialIcons-Regular.ttf
# URM ships (2226 glyphs), which is the face behind style_suffix 'icon_button'.

_NAME_LABEL = """    use x52URM_Dialog(title=If(var.isEditable,'{urm_notl}Modify variable{/urm_notl}','{urm_notl}View variable{/urm_notl}'), closeAction=Hide('URM_modify_value'), modal=True, icon='\\ue3c9'):
            vbox xminimum x52URM.scalePxInt(450) # To force a minimum width on the dialog
            label "[var.nameShortened]\""""

tweak(
    "a copy button on the variable name",
    SCREENS + "vars.rpy.x52",
    check="urm_copy",
    old=_NAME_LABEL,
    new=_NAME_LABEL.replace(
        '            label "[var.nameShortened]"',
        """            hbox spacing x52URM.scalePxInt(4):
                label "[var.nameShortened]"
                if hasattr(renpy.store, 'urm_copy'):
                    textbutton '\\ue14d' style_suffix 'icon_button' yalign .5 selected False hovered x52URM.Tooltip('Copy the full name to the clipboard') unhovered x52URM.Tooltip() action Function(urm_copy, var.name)"""),
)


# ---------------------------------------------------------------------------
# How far path detection looks ahead
# ---------------------------------------------------------------------------
#
# Settings.get() rather than attribute access, because __getattr__ prints a
# line for an unregistered name and this is read on every redraw - so without
# the helper the row reports the default instead of filling the log.

_TIMEOUT_ROW = """                'notificationTimeout': {
                    'title': '{urm_notl}Time-out{/urm_notl}',
                    'description': \"\"\"Automatically close the notification after this number of seconds\"\"\",
                    'effective': If(x52URM.Settings.notificationTimeout, '{urm_notl}[x52URM.Settings.notificationTimeout]s{/urm_notl}', '{urm_notl}Never{/urm_notl}'),
                    'options': {
                        '{urm_notl}Never{/urm_notl}': 0,
                        '{urm_notl}5s{/urm_notl}': 5,
                        '{urm_notl}10s{/urm_notl}': 10,
                    },
                },"""

_LOOKAHEAD_ROW = _TIMEOUT_ROW + """
                'urmcLookAhead': {
                    'title': '{urm_notl}Path look-ahead{/urm_notl}',
                    'description': \"\"\"How far ahead URM reads the script when looking for the next choice or if-statement.\\n\\nThe budget is counted in script nodes, not lines, and one {b}scene x with dissolve{/b} costs three of them - so a long cutscene can use up the default 20 before the if is reached, and URM reports no path when there is one.\\n\\nRaise this if {b}Path detected{/b} stops appearing in a cinematic game. Higher costs a little more work each time the text advances.\"\"\",
                    'effective': If(x52URM.Settings.get('urmcLookAhead'), '{urm_notl}' + str(x52URM.Settings.get('urmcLookAhead')) + ' nodes{/urm_notl}', '{urm_notl}20 (default){/urm_notl}'),
                    'options': {
                        '{urm_notl}20{/urm_notl}': 20,
                        '{urm_notl}50{/urm_notl}': 50,
                        '{urm_notl}100{/urm_notl}': 100,
                        '{urm_notl}200{/urm_notl}': 200,
                    },
                },"""

tweak(
    "a look-ahead setting for path detection",
    SCREENS + "options.rpy.x52",
    check="urmcLookAhead",
    old=_TIMEOUT_ROW,
    new=_LOOKAHEAD_ROW,
)


# ---------------------------------------------------------------------------
# Gallery: unlock everything, or only what you really unlocked
# ---------------------------------------------------------------------------
#
# Two rows in Miscellaneous. The work is in game_fixes.rpy (_urmg_*); the
# switch is also a small button in the corner of the main and game menus,
# screen urmg_badge, because that is where galleries are and URM's own
# overlay is never shown there.

_SPLASH_ROW = """                ('skipSplashscreen', {
                    'title': '{urm_notl}Skip splashscreen{/urm_notl}',
                    'description': \"\"\"This option skips the splashscreen at the start of the game (if any) and takes you directly to the menu\"\"\",
                    'effective': If(x52URM.Settings.skipSplashscreen, '{urm_notl}On{/urm_notl}', '{urm_notl}Off{/urm_notl}'),
                    'options': {
                        '{urm_notl}On{/urm_notl}': True,
                        '{urm_notl}Off{/urm_notl}': False,
                    },
                }),"""

_GALLERY_ROWS = _SPLASH_ROW + """
                ('urmcGalleryAll', {
                    'title': '{urm_notl}Gallery{/urm_notl}',
                    'description': \"\"\"{b}Unlock all{/b} opens every scene, image and replay in the game's gallery. {b}My unlocks{/b} shows only what you have really unlocked.\\n\\nNothing is written: your own unlocks are kept exactly as they are, so switching back is instant and exact. It only applies in the menus and the game's gallery screens, so the story itself still sees your real progress.\\n\\nAlso switchable from the small button in the corner of the main menu.\"\"\",
                    'effective': If(x52URM.Settings.get('urmcGalleryAll'), '{urm_notl}Unlock all{/urm_notl}', '{urm_notl}My unlocks{/urm_notl}'),
                    'options': {
                        '{urm_notl}My unlocks{/urm_notl}': False,
                        '{urm_notl}Unlock all{/urm_notl}': True,
                    },
                }),
                ('urmcGalleryBadge', {
                    'title': '{urm_notl}Gallery switch in menus{/urm_notl}',
                    'description': \"\"\"Shows the gallery switch as a small button in the top-right corner of the main menu and game menu.\"\"\",
                    'effective': If(x52URM.Settings.get('urmcGalleryBadge') is not False, '{urm_notl}Show{/urm_notl}', '{urm_notl}Hide{/urm_notl}'),
                    'options': {
                        '{urm_notl}Show{/urm_notl}': True,
                        '{urm_notl}Hide{/urm_notl}': False,
                    },
                }),"""

tweak(
    "a gallery switch: unlock all, or my unlocks",
    SCREENS + "options.rpy.x52",
    check="urmcGalleryAll",
    old=_SPLASH_ROW,
    new=_GALLERY_ROWS,
)


# ---------------------------------------------------------------------------
# Rollback: how far back, and middle-click Skip to go back to the last choice
# ---------------------------------------------------------------------------
#
# The limits are applied by _urmr_apply in game_fixes.rpy. The middle click is
# caught by screen urmr_middle, used once at the top of URM's quickmenu so it
# is there whenever the quickmenu is.

_ROLLBACK_ROWS = _GALLERY_ROWS + """
                ('urmcRollback', {
                    'title': '{urm_notl}Rollback length{/urm_notl}',
                    'description': \"\"\"How many steps back you can scroll. Ren'Py allows 100; a game that asks for more keeps its own.\\n\\nLonger history costs memory and makes save files larger, since every save carries it. The extra length builds up as you play - it does not reach back past what was already recorded.\\n\\nMiddle-click URM's Skip button to go back to the last choice you made.\"\"\",
                    'effective': If(x52URM.Settings.get('urmcRollback'), '{urm_notl}' + str(x52URM.Settings.get('urmcRollback')) + ' steps{/urm_notl}', '{urm_notl}Game default{/urm_notl}'),
                    'options': {
                        '{urm_notl}Game default{/urm_notl}': 0,
                        '{urm_notl}500{/urm_notl}': 500,
                        '{urm_notl}2000{/urm_notl}': 2000,
                    },
                }),"""

tweak(
    "a rollback length setting",
    SCREENS + "options.rpy.x52",
    check="urmcRollback",
    old=_GALLERY_ROWS,
    new=_ROLLBACK_ROWS,
)

_QUICKMENU_TOP = """screen URM_quickmenu:
    layer 'x52Overlay'
    style_prefix 'x52URM'
    default hovered = False
"""

tweak(
    "middle-click Skip goes back to the last choice",
    SCREENS + "quickmenu.rpy.x52",
    check="use urmr_middle",
    old=_QUICKMENU_TOP,
    new=_QUICKMENU_TOP + """
    if renpy.has_screen('urmr_middle'):
        use urmr_middle
""",
)


# ---------------------------------------------------------------------------
# Remembered labels: filter, and whether you have been there
# ---------------------------------------------------------------------------

_LABELS = SCREENS + "labels.rpy.x52"

tweak(
    "a filter box for the labels list",
    _LABELS,
    check="default labelFilter",
    old="    default nameSorted = None",
    new="""    default nameSorted = None
    default labelFilter = x52URM.Input()""",
)

_LABELS_RIGHT = """        hbox:
            xalign 1.0
            if x52URM.Settings.labelsView == 'list':"""

tweak(
    "the labels filter input",
    _LABELS,
    check="labelFilter.Enable()",
    old=_LABELS_RIGHT,
    new="""        hbox:
            xalign 1.0
            if hasattr(renpy.store, 'urm_labels'):
                hbox yalign .5 spacing x52URM.scalePxInt(4):
                    text '\\ue8b6' style_suffix 'icon' yalign .5
                    button:
                        xminimum x52URM.scalePxInt(160)
                        key_events True
                        action labelFilter.Enable()
                        input value labelFilter
                    if str(labelFilter):
                        textbutton '\\ue5cd' style_suffix 'icon_button' yalign .5 selected False hovered x52URM.Tooltip('Clear the filter') unhovered x52URM.Tooltip() action Function(labelFilter.set_text, '')
                null width x52URM.scalePxInt(10)
            if x52URM.Settings.labelsView == 'list':""",
)

# The filtered list is bound once and used for both the page count and the
# rows, or the pager and the table disagree about how many there are.
tweak(
    "page the filtered labels, not all of them",
    _LABELS,
    check="_urmLabels",
    old="""            python:
                if len(x52URM.LabelsStore.store) != labelListPages.itemCount:
                    SetField(labelListPages, 'itemCount', len(x52URM.LabelsStore.store))()""",
    new="""            python:
                _urmLabels = (urm_labels(str(labelFilter)) if hasattr(renpy.store, 'urm_labels') else list(x52URM.LabelsStore.store.items()))
                if len(_urmLabels) != labelListPages.itemCount:
                    SetField(labelListPages, 'itemCount', len(_urmLabels))()""",
)

tweak(
    "draw the filtered labels",
    _LABELS,
    check="enumerate(_urmLabels[",
    old="                    for i,(labelName,props) in enumerate(list(x52URM.LabelsStore.store.items())[labelListPages.pageStartIndex:labelListPages.pageEndIndex]):",
    new="                    for i,(labelName,props) in enumerate(_urmLabels[labelListPages.pageStartIndex:labelListPages.pageEndIndex]):",
)

# The markers cannot explain themselves: `text` takes no hovered/unhovered,
# those are button properties, and three help buttons per row would be worse
# than the ambiguity. So the legend goes once on the Name header, beside the
# sort control, using URM's own help-button idiom.
_LABELS_HEADER = """                hbox xsize colWidth[0]:
                    hbox:
                        label "{urm_notl}Name{/urm_notl}\""""

tweak(
    "a legend for the seen markers",
    _LABELS,
    check="What the marks mean",
    old=_LABELS_HEADER,
    new=_LABELS_HEADER + """
                        if hasattr(renpy.store, 'urm_seen'):
                            textbutton '{size=-8}\\ueb8b{/size}' style_suffix 'icon_textbutton' action x52URM.Confirm(\"\"\"{b}\\ue876{/b}  seen - you have read this label already\\n{b}\\ue836{/b}  not seen yet\\n{b}\\ue15b{/b}  this label is not in this version of the game\\n\\nThe last one usually means the save came from an older build, or the label was renamed. It is not the same as unseen content.\"\"\", title='What the marks mean')""",
)

# A tick for seen, an empty circle for not seen, a dash when the label is not
# in this build at all - which is the common case for a save carried across an
# update, and must not be drawn as "not seen" or it reads as missable content.
_LABEL_NAME_CELL = """                            hbox xsize colWidth[0] yalign .5:
                                if 'name' in props:
                                    text x52URM.scaleText(props['name'], 20) substitute False
                                else:
                                    text x52URM.scaleText(labelName, 20) substitute False"""

tweak(
    "a seen marker on each remembered label",
    _LABELS,
    check="urm_seen(labelName)",
    old=_LABEL_NAME_CELL,
    new="""                            hbox xsize colWidth[0] yalign .5 spacing x52URM.scalePxInt(4):
                                if hasattr(renpy.store, 'urm_seen'):
                                    python:
                                        _urmSeen = urm_seen(labelName)
                                    if _urmSeen:
                                        text '\\ue876' style_suffix 'icon' yalign .5
                                    elif _urmSeen == False:
                                        text '\\ue836' style_suffix 'icon' yalign .5
                                    else:
                                        text '\\ue15b' style_suffix 'icon' yalign .5
                                if 'name' in props:
                                    text x52URM.scaleText(props['name'], 20) substitute False
                                else:
                                    text x52URM.scaleText(labelName, 20) substitute False""",
)


# ---------------------------------------------------------------------------
# The gates the Path dialog never showed
# ---------------------------------------------------------------------------
#
# Read-only on purpose. URM forces a path by rewriting the chain up to the
# DETECTED node, so a gate two statements later cannot be forced - and a
# Select button that silently does nothing is worse than no button. The
# wording says so rather than leaving the player to find out.

_PATHS_TAIL = ("                            use x52URM_iconButton('\\ue86c',"
               " '{urm_notl}Select{/urm_notl}')\n"
               "                            use x52URM_iconButton('\\ueb8b',"
               " action=x52URM.Confirm(title='Not forceable',"
               " prompt='This path cannot be force selected\\nProbably because"
               " it\\'s behind a call or jump'))")

tweak(
    "the gates after this one, under the Path options table",
    SCREENS + "paths.rpy.x52",
    check="urm_later_gates",
    old=_PATHS_TAIL,
    new=_PATHS_TAIL + """

        if hasattr(renpy.store, 'urm_later_gates'):
            python:
                _urmLater = urm_later_gates()
            if _urmLater:
                null height x52URM.scalePxInt(10)
                frame style_suffix 'seperator' background x52URM.Theme.colors.buttonBorder ysize x52URM.scalePxInt(2)
                null height x52URM.scalePxInt(6)
                text 'Match none of the above and the script runs straight into these. URM can show them, but cannot force them.' style_suffix 'description'
                null height x52URM.scalePxInt(6)
                vbox spacing x52URM.scalePxInt(4):
                    for _urmIcon, _urmNum, _urmHead, _urmEffects in _urmLater:
                        frame:
                            background x52URM.Theme.colors.buttonBgHover
                            xsize x52URM.scalePxInt(760)
                            padding (x52URM.scalePxInt(6), x52URM.scalePxInt(4))
                            hbox:
                                spacing x52URM.scalePxInt(4)
                                text _urmIcon style_suffix 'icon' substitute False yalign 0.0
                                text _urmHead style_suffix 'button_text' substitute False yalign 0.0 xmaximum x52URM.scalePxInt(700) rest_indent x52URM.scalePxInt(10)
                        frame:
                            background x52URM.Theme.colors.buttonBg
                            xsize x52URM.scalePxInt(760)
                            padding (x52URM.scalePxInt(6), x52URM.scalePxInt(4))
                            vbox:
                                spacing x52URM.scalePxInt(2)
                                for _urmBullet, _urmBody in _urmEffects:
                                    hbox:
                                        spacing x52URM.scalePxInt(4)
                                        text _urmBullet style_suffix 'icon' substitute False yalign 0.0
                                        text _urmBody style_suffix 'button_text' substitute False yalign 0.0 xmaximum x52URM.scalePxInt(690) rest_indent x52URM.scalePxInt(10)""",
)


# ---------------------------------------------------------------------------
# The prophecy panel: what the game does with this variable
# ---------------------------------------------------------------------------
#
# One `use` line in URM_modify_value - the dialog every route to a variable
# ends in: search, browse, the watch panel. Everything the panel draws lives in
# game_fixes.rpy as screen urmi_var_panel, so this anchor never has to move
# when the panel changes.
#
# Guarded on the screen existing: a helper that failed to compile for this
# engine leaves URM's editor exactly as it ships.

_EDITOR_ERRORS = """            if errorMessage != None:
                use x52URM_messagebar('error', errorMessage)

            if allowRemember:"""

tweak(
    "what the game does with this variable, in the editor",
    SCREENS + "vars.rpy.x52",
    check="use urmi_var_panel(",
    old=_EDITOR_ERRORS,
    new="""            if errorMessage != None:
                use x52URM_messagebar('error', errorMessage)

            if renpy.has_screen('urmi_var_panel'):
                use urmi_var_panel(var, valueInput)

            if allowRemember:""",
)



# ---------------------------------------------------------------------------
# The index's two screens, compiled by the game's own engine
# ---------------------------------------------------------------------------
#
# These used to live in game_fixes.rpy, and that would have broken every
# Ren'Py 7.3 game. game_fixes.rpy is compiled once, by Ren'Py 8, and its
# pickle is loaded by whatever engine the game runs. Every expression in a
# screen is pickled as a PyExpr, and PyExpr.__new__ takes (s, filename,
# linenumber) on 7.3.5 and 7.2.1 but (s, filename, linenumber, py) on 7.4+ -
# so on the older engines the whole helper, cards and search included, would
# have failed to load. rpatools.py only ever had to make PyCode portable because
# the helper never held a PyExpr before.
#
# URM's own screens are plain text that each game compiles itself, which is
# why they run from 6.99 to 8. These two now go the same way: inserted as text
# into vars.rpy.x52, just above URM_add_item, and game_fixes.rpy stays pure
# init python. run_tests.py checks that it stays that way.
#
# urmi_progress is the corner line shown while the index is built - see
# _urmi_progress_text. urmi_var_panel is drawn by the one `use` line in
# URM_modify_value - see urm_var_panel.

_PROGRESS_SCREEN = '''screen urmi_progress():
    zorder 1000
    add DynamicDisplayable(_urmi_progress_text) xpos 12 yalign 1.0 yoffset -10'''

# The panel itself. Everything it shows is worked out by urm_panel() in
# game_fixes.rpy; this only draws, so the logic can be tested offline
# against real games without an engine running.
_PANEL_SCREEN = r'''screen urmi_var_panel(var, valueInput):
    # A `use`d screen does not inherit the caller's style_prefix, and without
    # it every text here would take the game's own styles.
    style_prefix "x52URM"

    python:
        _urmiP = urm_panel(var.name)
        _urmiTab = urmi_ui(("tab", var.name), _urmiP.tab)
        if _urmiTab not in [_urmiT[0] for _urmiT in _urmiP.tabs]:
            _urmiTab = _urmiP.tab
        _urmiW = x52URM.scalePxInt(1400)
        _urmiText = x52URM.scalePxInt(1080)

    null height x52URM.scalePxInt(10)
    frame style_suffix 'seperator' background x52URM.Theme.colors.buttonBorder ysize x52URM.scalePxInt(2)
    null height x52URM.scalePxInt(6)

    if _urmiP.message:
        text _urmiP.message substitute False size x52URM.scalePxInt(20) xmaximum _urmiW
        if _urmiP.state == 'building':
            timer 0.5 repeat True action Function(renpy.restart_interaction)

    elif _urmiP.state == 'ready':
        viewport:
            xsize _urmiW
            ymaximum x52URM.scalePxInt(430)
            mousewheel True
            draggable True
            scrollbars "vertical"

            vbox:
                xsize _urmiW - x52URM.scalePxInt(30)
                spacing x52URM.scalePxInt(3)

                # The answer: what it is, what it gets you, who sets it.
                for _urmiI, _urmiLine in enumerate(_urmiP.answer):
                    text _urmiLine substitute False size x52URM.scalePxInt(22 if _urmiI == 0 else 20) bold (_urmiI == 0)

                # The choice on the screen right now.
                if _urmiP.now_header:
                    null height x52URM.scalePxInt(8)
                    text _urmiP.now_header substitute False bold True size x52URM.scalePxInt(19) color '#e0a800'
                    for _urmiLine, _urmiValue in _urmiP.now_lines:
                        hbox:
                            spacing x52URM.scalePxInt(10)
                            null width x52URM.scalePxInt(16)
                            text _urmiLine substitute False size x52URM.scalePxInt(19) xmaximum _urmiText
                            if urmi_settable(var, _urmiValue):
                                textbutton urmi_set_words(_urmiValue) substitute False text_size x52URM.scalePxInt(17) action Function(urmi_fill, var, valueInput, _urmiValue)

                if _urmiP.later and not _urmiP.now_header:
                    null height x52URM.scalePxInt(8)
                    text "{urm_notl}LATER IN THIS SCENE{/urm_notl}" bold True size x52URM.scalePxInt(19) color '#e0a800'
                    for _urmiRow in _urmiP.later[:2]:
                        text (_urmiRow.view_head + ('  -  ' + _urmiRow.view_quote if _urmiRow.view_quote else '')) substitute False size x52URM.scalePxInt(18) xmaximum _urmiW - x52URM.scalePxInt(40)

                # Will the change stick, and is it enough.
                if _urmiP.warnings or _urmiP.okline:
                    null height x52URM.scalePxInt(8)
                    for _urmiLine in _urmiP.warnings:
                        text _urmiLine substitute False size x52URM.scalePxInt(19) color '#ff8a65' xmaximum _urmiW - x52URM.scalePxInt(40)
                    if _urmiP.okline:
                        text _urmiP.okline substitute False size x52URM.scalePxInt(19) color '#66bb6a'

                null height x52URM.scalePxInt(10)
                hbox:
                    spacing x52URM.scalePxInt(8)
                    for _urmiKey, _urmiTitle in _urmiP.tabs:
                        textbutton _urmiTitle substitute False text_size x52URM.scalePxInt(19) selected (_urmiTab == _urmiKey) action Function(urmi_ui_set, ("tab", var.name), _urmiKey)
                null height x52URM.scalePxInt(6)

                if _urmiTab == 'gives':
                    for _urmiBlock in _urmiP.blocks:
                        if _urmiBlock.marker:
                            text _urmiBlock.header substitute False size x52URM.scalePxInt(18) color '#e0a800'
                        else:
                            null height x52URM.scalePxInt(6)
                            hbox:
                                spacing x52URM.scalePxInt(10)
                                text _urmiBlock.header substitute False bold True size x52URM.scalePxInt(20) yalign .5
                                if urmi_settable(var, _urmiBlock.value):
                                    textbutton urmi_set_words(_urmiBlock.value) substitute False text_size x52URM.scalePxInt(17) action Function(urmi_fill, var, valueInput, _urmiBlock.value)
                            if _urmiBlock.sub:
                                text _urmiBlock.sub substitute False italic True size x52URM.scalePxInt(17)

                            $ _urmiOpen = urmi_ui(("more", var.name, _urmiBlock.key), False)
                            $ _urmiLimit = (60 if _urmiOpen else urmi_block_limit(_urmiP, _urmiBlock))
                            for _urmiRow in (_urmiBlock.rows + (_urmiBlock.small if _urmiOpen else []))[:_urmiLimit]:
                                hbox:
                                    xfill True
                                    vbox:
                                        xmaximum _urmiText
                                        hbox:
                                            spacing x52URM.scalePxInt(10)
                                            null width x52URM.scalePxInt(16)
                                            if _urmiRow.view_status:
                                                text _urmiRow.view_status substitute False size x52URM.scalePxInt(16) yalign .5
                                            text _urmiRow.view_head substitute False size x52URM.scalePxInt(19)
                                        if _urmiRow.view_quote:
                                            text _urmiRow.view_quote substitute False italic True size x52URM.scalePxInt(18) xoffset x52URM.scalePxInt(40) xmaximum _urmiText - x52URM.scalePxInt(40)
                                        for _urmiLine in _urmiRow.view_extra:
                                            text _urmiLine substitute False size x52URM.scalePxInt(17) xoffset x52URM.scalePxInt(40) xmaximum _urmiText - x52URM.scalePxInt(40)
                                        if urmi_ui(("lines", var.name, _urmiRow.key), False):
                                            for _urmiLine in _urmiRow.view_lines:
                                                text _urmiLine substitute False size x52URM.scalePxInt(17) color '#9e9e9e' xoffset x52URM.scalePxInt(60) xmaximum _urmiText - x52URM.scalePxInt(60)
                                    hbox:
                                        xalign 1.0
                                        spacing x52URM.scalePxInt(6)
                                        if _urmiRow.view_lines:
                                            textbutton "{urm_notl}Lines{/urm_notl}" text_size x52URM.scalePxInt(16) selected urmi_ui(("lines", var.name, _urmiRow.key), False) action Function(urmi_ui_toggle, ("lines", var.name, _urmiRow.key))
                                        if _urmiRow.view_replay:
                                            textbutton "{urm_notl}Replay{/urm_notl}" text_size x52URM.scalePxInt(16) action Show('URM_replay_jump', jumpTo=_urmiRow.view_replay)
                                        textbutton "{urm_notl}Code{/urm_notl}" text_size x52URM.scalePxInt(16) action [Hide('URM_CodeView'), Show('URM_CodeView', code=_urmiRow.view_code, title=_urmiRow.scene)]

                            $ _urmiHidden = len(_urmiBlock.rows) + (len(_urmiBlock.small) if _urmiOpen else 0) - _urmiLimit
                            $ _urmiSmall = urmi_small_line(_urmiBlock)
                            if _urmiSmall and not _urmiOpen:
                                text _urmiSmall substitute False size x52URM.scalePxInt(17) xoffset x52URM.scalePxInt(16) color '#9e9e9e'
                            if _urmiHidden > 0 or (_urmiBlock.small and not _urmiOpen):
                                textbutton ("{urm_notl}Show all{/urm_notl}" if not _urmiOpen else "{urm_notl}Show fewer{/urm_notl}") text_size x52URM.scalePxInt(16) xoffset x52URM.scalePxInt(16) action Function(urmi_ui_toggle, ("more", var.name, _urmiBlock.key))
                            elif _urmiOpen:
                                textbutton "{urm_notl}Show fewer{/urm_notl}" text_size x52URM.scalePxInt(16) xoffset x52URM.scalePxInt(16) action Function(urmi_ui_toggle, ("more", var.name, _urmiBlock.key))

                    if _urmiP.next_line:
                        null height x52URM.scalePxInt(8)
                        hbox:
                            spacing x52URM.scalePxInt(10)
                            text _urmiP.next_line substitute False size x52URM.scalePxInt(19) color '#e0a800' xmaximum _urmiText
                            if urmi_settable(var, _urmiP.next_value):
                                textbutton urmi_set_words(_urmiP.next_value) substitute False text_size x52URM.scalePxInt(17) action Function(urmi_fill, var, valueInput, _urmiP.next_value)
                    for _urmiLine in _urmiP.gives_tail:
                        text _urmiLine substitute False size x52URM.scalePxInt(18) xmaximum _urmiW - x52URM.scalePxInt(40)

                elif _urmiTab == 'choices':
                    if not _urmiP.choices:
                        text "{urm_notl}No choice in the story script sets it.{/urm_notl}" size x52URM.scalePxInt(19)
                    $ _urmiOpen = urmi_ui(("more", var.name, "choices"), False)
                    for _urmiHeader, _urmiOptions in _urmiP.choices[:(60 if _urmiOpen else 8)]:
                        null height x52URM.scalePxInt(6)
                        text _urmiHeader substitute False bold True size x52URM.scalePxInt(19) xmaximum _urmiW - x52URM.scalePxInt(40)
                        for _urmiLine, _urmiValue in _urmiOptions:
                            hbox:
                                spacing x52URM.scalePxInt(10)
                                null width x52URM.scalePxInt(16)
                                text _urmiLine substitute False size x52URM.scalePxInt(18) xmaximum _urmiText
                                if urmi_settable(var, _urmiValue):
                                    textbutton urmi_set_words(_urmiValue) substitute False text_size x52URM.scalePxInt(16) action Function(urmi_fill, var, valueInput, _urmiValue)
                    if len(_urmiP.choices) > 8:
                        textbutton ("{urm_notl}Show all{/urm_notl}" if not _urmiOpen else "{urm_notl}Show fewer{/urm_notl}") text_size x52URM.scalePxInt(16) action Function(urmi_ui_toggle, ("more", var.name, "choices"))
                    for _urmiLine in _urmiP.choices_tail:
                        null height x52URM.scalePxInt(4)
                        text _urmiLine substitute False size x52URM.scalePxInt(18) xmaximum _urmiW - x52URM.scalePxInt(40)

                else:
                    text "{urm_notl}The raw facts behind the other tabs.{/urm_notl}" italic True size x52URM.scalePxInt(17)
                    if _urmiP.detail_checks:
                        hbox:
                            box_wrap True
                            spacing x52URM.scalePxInt(4)
                            xmaximum _urmiW - x52URM.scalePxInt(40)
                            for _urmiLine, _urmiValue, _urmiCount in _urmiP.detail_checks:
                                if _urmiValue is not None and var.isEditable:
                                    textbutton _urmi_safe(_urmiLine) substitute False text_size x52URM.scalePxInt(16) action Function(urmi_fill, var, valueInput, _urmiValue)
                                else:
                                    textbutton _urmi_safe(_urmiLine) substitute False text_size x52URM.scalePxInt(16) action NullAction()
                    for _urmiLine in _urmiP.details:
                        text _urmiLine substitute False size x52URM.scalePxInt(17) xmaximum _urmiW - x52URM.scalePxInt(40)

                null height x52URM.scalePxInt(10)
                for _urmiLine in _urmiP.footer:
                    text _urmiLine substitute False size x52URM.scalePxInt(17) color '#9e9e9e' xmaximum _urmiW - x52URM.scalePxInt(40)'''

# The gallery switch in the corner of the menus - see _urmg_interact.
_GALLERY_BADGE = """screen urmg_badge():
    zorder 1001
    style_prefix "x52URM"
    textbutton urmg_badge_text() text_size x52URM.scalePxInt(17) xalign 1.0 yalign 0.0 xoffset -x52URM.scalePxInt(10) yoffset x52URM.scalePxInt(8) action Function(urmg_toggle)"""

# Middle click on Skip rolls back to the last choice - see urmr_back_to_choice.
# A zero-size displayable; it only acts while a Skip button is under the mouse.
_MIDDLE_CLICK = """screen urmr_middle():
    add urmr_middle_click"""

_INDEX_SCREENS = (_PROGRESS_SCREEN + "\n\n" + _PANEL_SCREEN + "\n\n"
                  + _GALLERY_BADGE + "\n\n" + _MIDDLE_CLICK + "\n\n")

_ADD_ITEM = "screen URM_add_item(parentVar):"

tweak(
    "the script index's progress line and editor panel screens",
    SCREENS + "vars.rpy.x52",
    check="screen urmi_var_panel(",
    old=_ADD_ITEM,
    new=_INDEX_SCREENS + _ADD_ITEM,
)
