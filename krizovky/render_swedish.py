"""Swedish crossword (mode swedish): clues inside the grid cells, one A4 SVG page.

1 SVG user unit = 1 mm, stdlib only. Block cells carry the clue text (split cell =
across above the line, down below); a block without a clue is a black cell (disc).
Text size is chosen from a ladder with a DejaVu Sans width table, so the layout is
computed here and the SVG needs no tspan / textLength (LibreOffice-safe).
"""
from __future__ import annotations

import logging
import textwrap

from .model import ACROSS, Puzzle
from .render_svg import (BOX_MM, CLUE_BOTTOM, FONT_FAMILY, GRID_MAX_W, GRID_TOP,
                         MARGIN, MISSING_CLUE, PAGE_W, TAJENKA_FILL, RenderError, _fmt,
                         _tajenka_box_rows, _text)

logger = logging.getLogger("krizovky.render_swedish")

# DejaVu Sans advance widths in em, measured once with Pillow on
# /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf (dev-only; Pillow is not a dependency).
_ADVANCE = {
    "A": 0.684, "B": 0.686, "C": 0.698, "D": 0.77, "E": 0.632, "F": 0.575, "G": 0.775,
    "H": 0.752, "I": 0.295, "J": 0.295, "K": 0.656, "L": 0.557, "M": 0.863, "N": 0.748,
    "O": 0.787, "P": 0.603, "Q": 0.787, "R": 0.695, "S": 0.635, "T": 0.611, "U": 0.732,
    "V": 0.684, "W": 0.989, "X": 0.685, "Y": 0.611, "Z": 0.685, "Á": 0.684, "Č": 0.698,
    "Ď": 0.77, "É": 0.632, "Ě": 0.632, "Í": 0.295, "Ň": 0.748, "Ó": 0.787, "Ř": 0.695,
    "Š": 0.635, "Ť": 0.611, "Ú": 0.732, "Ů": 0.732, "Ý": 0.611, "Ž": 0.685, "a": 0.613,
    "b": 0.635, "c": 0.55, "d": 0.635, "e": 0.615, "f": 0.352, "g": 0.635, "h": 0.634,
    "i": 0.278, "j": 0.278, "k": 0.579, "l": 0.278, "m": 0.974, "n": 0.634, "o": 0.612,
    "p": 0.635, "q": 0.635, "r": 0.411, "s": 0.521, "t": 0.392, "u": 0.634, "v": 0.592,
    "w": 0.818, "x": 0.592, "y": 0.592, "z": 0.525, "á": 0.613, "č": 0.55, "ď": 0.635,
    "é": 0.615, "ě": 0.615, "í": 0.278, "ň": 0.634, "ó": 0.612, "ř": 0.411, "š": 0.521,
    "ť": 0.392, "ú": 0.634, "ů": 0.634, "ý": 0.592, "ž": 0.525, "0": 0.636, "1": 0.636,
    "2": 0.636, "3": 0.636, "4": 0.636, "5": 0.636, "6": 0.636, "7": 0.636, "8": 0.636,
    "9": 0.636, " ": 0.318, ".": 0.318, ",": 0.318, ";": 0.337, ":": 0.337, "(": 0.39,
    ")": 0.39, "„": 0.518, "“": 0.518, '"': 0.46, "'": 0.275, "-": 0.361, "–": 0.5, "/": 0.337,
    "&": 0.78, "!": 0.401, "?": 0.531,
}
BOLD_FACTOR = 1.12       # measured DejaVu Sans Bold / Sans width ratio
UNKNOWN_EM = 0.7

CELL_MAX, CELL_MIN = 15.0, 9.0
LADDER = (0.16, 0.145, 0.13, 0.115)     # clue font size as a share of the cell size
LINE_H = 1.1                            # line height in em (caps only: tight, as the magazines set it)
BASELINE = 0.78                         # baseline offset from the line top, in em (cap height + descent balance)
PAD, SPLIT_GAP = 0.6, 0.3               # clue box padding; extra gap from the split line
TITLE_Y, HEADER_FONT, HEADER_LH, HEADER_WRAP = MARGIN + 7, 3.2, 4.4, 95
HEADER_GAP = 6.0                        # last header baseline -> grid top
POMUCKA_FONT, POMUCKA_GAP, POMUCKA_EXTRA = 3.2, 5.0, 8.0
BOX_ROW_MM = 10.0                       # one answer-box row (6 mm box + 4 mm gap)


def text_width(text: str, size: float, bold: bool = False) -> float:
    em = sum(_ADVANCE.get(ch, UNKNOWN_EM) for ch in text)
    return em * size * (BOLD_FACTOR if bold else 1.0)


VOWELS = frozenset("aeiouyáéěíóúůý")
MIN_PIECE = 2                           # a cut never leaves fewer letters on either side


def syllable_breaks(word: str) -> list[int]:
    """Positions k where word[:k] | word[k:] is a Czech syllable boundary (rule of thumb,
    no dictionary): one consonant goes with the next vowel, of a cluster only the last
    one, or the last two when they are an onset (consonant + R/L, TR, PŘ); CH is one
    letter, OU / AU / EU one vowel, R / L between consonants carry a syllable (KR-TEK); a
    cluster of three or more ends in a syllable opening with SK / ŠK / ST (FRANCOUZ-SKÉ)."""
    w = word.lower()
    n = len(w)
    nuclei: list[tuple[int, int]] = []
    i = 0
    while i < n:
        ch = w[i]
        if ch in VOWELS:
            j = i + 2 if ch in "aeo" and w[i + 1:i + 2] == "u" else i + 1
            nuclei.append((i, j))
            i = j
            continue
        if ch in "rl" and (i == 0 or w[i - 1] not in VOWELS) and w[i + 1:i + 2] not in tuple(VOWELS):
            nuclei.append((i, i + 1))
        i += 1
    cuts: list[int] = []
    for (_, end), (start, _) in zip(nuclei, nuclei[1:]):
        units: list[int] = []               # start of every consonant (CH counts once) between the nuclei
        k = end
        while k < start:
            units.append(k)
            k += 2 if w[k:k + 2] == "ch" else 1
        if not units:
            cut = start                     # two vowels in a row: cut between them
        elif len(units) > 1 and w[units[-1]] in "rlř" and w[units[-2]] not in "rlřnm":
            cut = units[-2]
        elif len(units) > 2 and w[units[-2]] in "sš" and w[units[-1]] in "kt":
            cut = units[-2]                 # FRANCOUZ-SKÉ, SLABOŠ-SKÝ: SK / ŠK / ST open a syllable
        else:
            cut = units[-1]
        if MIN_PIECE <= cut <= n - MIN_PIECE and word[cut - 1].isalpha() and word[cut].isalpha():
            cuts.append(cut)
    return cuts


def _cut(word: str, size: float, max_w: float, bold: bool) -> int:
    """Letters of an over-wide word that stay on this line: up to the last syllable boundary that
    fits with its '-', else as many as fit, but never leaving a single letter for the next line."""
    fitting = max((k for k in range(1, len(word)) if text_width(word[:k] + "-", size, bold) <= max_w),
                  default=1)
    at_syllable = [k for k in syllable_breaks(word) if k <= fitting]
    if at_syllable:
        return at_syllable[-1]
    return fitting - 1 if fitting > 1 and len(word) - fitting == 1 else fitting


def wrap(text: str, size: float, max_w: float, bold: bool = False) -> list[str]:
    """Greedy word wrap; a word wider than max_w is cut into pieces (between syllables where it
    can) that carry a trailing '-' on every piece but the last."""
    lines: list[str] = []
    cur = ""
    for word in text.split():
        if cur and text_width(f"{cur} {word}", size, bold) <= max_w:
            cur = f"{cur} {word}"
            continue
        if cur:
            lines.append(cur)
        while len(word) > 1 and text_width(word, size, bold) > max_w:
            k = _cut(word, size, max_w, bold)
            lines.append(word[:k] + "-")
            word = word[k:]
        cur = word
    if cur:
        lines.append(cur)
    return lines


def fit(text: str, box_w: float, box_h: float, S: float, bold: bool = False) -> tuple[float, list[str], int]:
    """(font size, lines, dropped lines): the largest ladder size whose wrapped lines fit
    the box height; at the smallest size the lines beyond the box are dropped."""
    for f in LADDER:
        size = f * S
        lines = wrap(text, size, box_w, bold)
        room = int(box_h / (LINE_H * size) + 1e-9)
        if len(lines) <= room:
            return size, lines, 0
    return size, lines[:room], len(lines) - room


def baselines(n: int, size: float, box_top: float, box_h: float) -> list[float]:
    """Baselines of n lines, the block centred vertically in the box."""
    lh = LINE_H * size
    top = box_top + (box_h - n * lh) / 2
    return [top + i * lh + BASELINE * size for i in range(n)]


def _ctext(cls: str, *args, **kwargs) -> str:
    return _text(*args, **kwargs).replace("<text ", f'<text class="{cls}" ', 1)


def _line(cls: str, x1, y1, x2, y2, sw) -> str:
    return (f'<line class="{cls}" x1="{_fmt(x1)}" y1="{_fmt(y1)}" x2="{_fmt(x2)}" y2="{_fmt(y2)}" '
            f'stroke="#000000" stroke-width="{sw}"/>')


def render_svg(p: Puzzle, *, solution: bool, title: str | None = None) -> str:
    rows, cols = p.height, p.width
    if rows < 1 or cols < 1:
        raise RenderError("empty grid")
    title = (title or "Křížovka") + (" – řešení" if solution else "")
    header_text = p.meta.get("header") or p.meta.get("theme")
    header = textwrap.wrap(str(header_text), HEADER_WRAP) if header_text else []
    header_y = [TITLE_Y + 7 + i * HEADER_LH for i in range(len(header))]
    grid_top = header_y[-1] + HEADER_GAP if header else GRID_TOP

    pomucka = p.meta.get("pomucka")
    pomucka = [str(x) for x in pomucka] if isinstance(pomucka, list) and pomucka else []
    box_rows = _tajenka_box_rows(p, GRID_MAX_W) if p.tajenka_cells else []
    extras = (POMUCKA_EXTRA if pomucka else 0.0) + BOX_ROW_MM * len(box_rows)
    S = min(CELL_MAX, GRID_MAX_W / cols, (CLUE_BOTTOM - grid_top - extras) / rows)
    if S < CELL_MIN:
        raise RenderError(f"cell size {S:.1f} mm is below {CELL_MIN:g} mm: grid {rows}x{cols} "
                          "with header, Pomůcka and answer boxes does not fit one A4 page")
    gw = cols * S
    x0 = MARGIN + (GRID_MAX_W - gw) / 2
    grid_bottom = grid_top + rows * S

    grid = p.grid()
    blocks = {tuple(b) for b in p.blocks}
    tset = {tuple(c) for c in p.tajenka_cells}
    across_at: dict[tuple[int, int], int] = {}     # clue cell -> entry index
    down_at: dict[tuple[int, int], int] = {}
    tajenka_entry: set[int] = set()
    for i, (pl, e) in enumerate(zip(p.placements, p.entries)):
        cell = (pl.row, pl.col - 1) if pl.direction == ACROSS else (pl.row - 1, pl.col)
        (across_at if pl.direction == ACROSS else down_at)[cell] = i
        if cell not in blocks:
            logger.warning("entry %s at (%d,%d) %s has no clue cell before it",
                           e.answer, pl.row, pl.col, pl.direction)
        if tset and all(c in tset for c in pl.coords(len(e))):
            tajenka_entry.add(i)

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm" '
        f'viewBox="0 0 210 297" font-family="{FONT_FAMILY}">',
        _ctext("title", PAGE_W / 2, TITLE_Y, 7, title, anchor="middle", bold=True),
    ]
    for line, y in zip(header, header_y):
        parts.append(_ctext("header", PAGE_W / 2, y, HEADER_FONT, line, anchor="middle"))

    def cx(c): return x0 + c * S
    def cy(r): return grid_top + r * S

    for r in range(rows):
        for c in range(cols):
            fill = TAJENKA_FILL if (r, c) in tset and (r, c) not in blocks else "#ffffff"
            parts.append(f'<rect class="cell" x="{_fmt(cx(c))}" y="{_fmt(cy(r))}" width="{_fmt(S)}" '
                         f'height="{_fmt(S)}" fill="{fill}" stroke="#000000" stroke-width="0.3"/>')

    texts: list[str] = []

    def put_clue(i: int, box: tuple[float, float, float, float], x_mid: float) -> None:
        e = p.entries[i]
        given = bool(e.clue and e.clue.strip())
        text = e.clue.strip().upper() if given else MISSING_CLUE
        bold = i in tajenka_entry
        size, lines, dropped = fit(text, box[2], box[3], S, bold)
        if dropped:
            pl = p.placements[i]
            logger.warning("clue for %s at (%d,%d) does not fit: %d line(s) dropped",
                           e.answer, pl.row, pl.col, dropped)
        for line, y in zip(lines, baselines(len(lines), size, box[1], box[3])):
            texts.append(_ctext("clue", x_mid, y, size, line, anchor="middle", bold=bold))

    for r in range(rows):
        for c in range(cols):
            if (r, c) not in blocks:
                continue
            a, d = across_at.get((r, c)), down_at.get((r, c))
            x, y = cx(c), cy(r)
            if a is None and d is None:
                parts.append(f'<circle class="black" cx="{_fmt(x + S / 2)}" cy="{_fmt(y + S / 2)}" '
                             f'r="{_fmt(0.3 * S)}" fill="#000000"/>')
            elif a is not None and d is not None:
                parts.append(_line("split", x, y + S / 2, x + S, y + S / 2, "0.3"))
                half = S / 2 - PAD - SPLIT_GAP
                put_clue(a, (x + PAD, y + PAD, S - 2 * PAD, half), x + S / 2)
                put_clue(d, (x + PAD, y + S / 2 + SPLIT_GAP, S - 2 * PAD, half), x + S / 2)
            else:
                put_clue(a if a is not None else d,
                         (x + PAD, y + PAD, S - 2 * PAD, S - 2 * PAD), x + S / 2)

    if solution:
        for r in range(rows):
            for c in range(cols):
                key = grid[r][c]
                if key and (r, c) not in blocks:
                    size = (0.6 if len(key) == 1 else 0.42) * S
                    parts.append(_ctext("letter", cx(c) + S / 2, cy(r) + S / 2 + size * 0.35, size,
                                        key, anchor="middle"))
    parts += texts
    parts.append(f'<rect class="border" x="{_fmt(x0)}" y="{_fmt(grid_top)}" width="{_fmt(gw)}" '
                 f'height="{_fmt(rows * S)}" fill="none" stroke="#000000" stroke-width="0.8"/>')

    if pomucka:
        body = ", ".join(pomucka)
        body += "" if body.endswith(".") else "."
        y = grid_bottom + POMUCKA_GAP
        label_w = text_width("Pomůcka:", POMUCKA_FONT, True) + text_width(" ", POMUCKA_FONT)
        parts.append(_ctext("pomucka", x0, y, POMUCKA_FONT, "Pomůcka:", bold=True))
        parts.append(_ctext("pomucka", x0 + label_w, y, POMUCKA_FONT, body))
        if x0 + label_w + text_width(body, POMUCKA_FONT) > PAGE_W - MARGIN:
            logger.warning("Pomůcka line is wider than the text area")

    box_top = grid_bottom + (POMUCKA_EXTRA if pomucka else 0.0) + 4.0
    for k, row in enumerate(box_rows):
        top = box_top + k * BOX_ROW_MM
        shift = x0 + (gw - (row[-1][1] + BOX_MM)) / 2     # centred under the grid
        for i, off in row:
            bx = shift + off
            parts.append(f'<rect class="tajenka-box" x="{_fmt(bx)}" y="{_fmt(top)}" '
                         f'width="{_fmt(BOX_MM)}" height="{_fmt(BOX_MM)}" fill="#ffffff" '
                         f'stroke="#000000" stroke-width="0.6"/>')
            r, c = p.tajenka_cells[i - 1]
            key = grid[r][c] if solution and 0 <= r < rows and 0 <= c < cols else None
            if key:
                size = 4.5 if len(key) == 1 else 3.2
                parts.append(_ctext("box-letter", bx + BOX_MM / 2, top + BOX_MM / 2 + size * 0.35,
                                    size, key, anchor="middle"))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
