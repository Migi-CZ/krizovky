"""Render a Puzzle to printable A4 SVG (puzzle / solution) and a Markdown solution.

1 SVG user unit = 1 mm. The grid sits in a group that is scaled down uniformly
when it would not fit; the clue list follows below in two columns (three when
two would shrink the grid too much).
"""
from __future__ import annotations

import math
import textwrap
from pathlib import Path
from xml.sax.saxutils import escape

from .model import ACROSS, DOWN, Entry, Puzzle

CELL_MM = 10.0
FONT_FAMILY = "DejaVu Sans, Noto Sans, Arial, sans-serif"

PAGE_W, PAGE_H, MARGIN = 210.0, 297.0, 15.0
GRID_MAX_W = PAGE_W - 2 * MARGIN          # 180 mm
GRID_TOP = 30.0
CLUE_BOTTOM = PAGE_H - MARGIN - 8         # leave room for the footer
COL_W, COL_GAP = 85.0, 10.0
WRAP = 45
COL_W3 = (GRID_MAX_W - 2 * COL_GAP) / 3   # three-column fallback
WRAP3 = 28
MIN_SCALE_2COL = 0.75                     # below this, switch to three columns
BOX_MM, BOX_WORD_GAP, BOX_TOP_GAP = 6.0, 4.0, 8.0   # tajenka answer boxes (web mode)
CLUE_FONT, CLUE_LH = 3.4, 4.6
GUTTER = 7.0                              # row numbers left of a column-mode grid
TAJENKA_FILL = "#e0e0e0"
MIN_SCALE = 0.4
MISSING_CLUE = "(doplňte)"

Group = tuple["str | None", "list[tuple[int | None, Entry]]"]


class RenderError(ValueError):
    """The puzzle cannot be drawn (does not fit a page)."""


def _fmt(x: float) -> str:
    return f"{x:.3f}".rstrip("0").rstrip(".")


def _text(x, y, size, content, *, anchor="start", bold=False) -> str:
    weight = ' font-weight="bold"' if bold else ""
    return (f'<text x="{_fmt(x)}" y="{_fmt(y)}" font-size="{_fmt(size)}" '
            f'text-anchor="{anchor}"{weight}>{escape(content)}</text>')


def _clue_text(entry: Entry) -> str:
    return entry.clue.strip() if entry.clue and entry.clue.strip() else MISSING_CLUE


def clue_groups(p: Puzzle) -> list[Group]:
    """Clue numbers with their entries. Column mode: one group numbered by row
    order; other modes: Vodorovně / Svisle sorted by clue number."""
    pairs = list(zip(p.placements, p.entries))
    if p.mode == "swedish":                   # no clue numbers: order by position
        pairs.sort(key=lambda pe: (pe[0].row, pe[0].col))
    if p.mode == "column":
        pairs.sort(key=lambda pe: (pe[0].row, pe[0].col))
        return [(None, [(i + 1, e) for i, (_, e) in enumerate(pairs)])]
    groups: list[Group] = []
    for title, direction in (("Vodorovně", ACROSS), ("Svisle", DOWN)):
        items = [(pl.number, e) for pl, e in pairs if pl.direction == direction]
        items.sort(key=lambda ne: (ne[0] is None, ne[0] or 0))
        if items:
            groups.append((title, items))
    return groups


def _clue_lines(p: Puzzle, wrap: int = WRAP) -> list[tuple[str, bool]]:
    """(text, is_heading) lines, already wrapped."""
    lines: list[tuple[str, bool]] = []
    for title, items in clue_groups(p):
        if title:
            if lines:
                lines.append(("", False))
            lines.append((title, True))
        for number, entry in items:
            label = f"{number}. " if number is not None else "– "
            wrapped = textwrap.wrap(label + _clue_text(entry), wrap, subsequent_indent="   ")
            lines.extend((w, False) for w in wrapped)
    return lines


def _separator_rows(p: Puzzle) -> list[int]:
    """Column mode: rows after which a thick line separates tajenka words."""
    words = p.tajenka_words() if p.tajenka else []
    if p.mode != "column" or len(words) < 2 or sum(map(len, words)) != len(p.tajenka_cells):
        return []
    rows, done = [], 0
    for word in words[:-1]:
        done += len(word)
        rows.append(p.tajenka_cells[done - 1][0])
    return rows


def _tajenka_box_rows(p: Puzzle, max_w: float) -> list[list[tuple[int, float]]]:
    """Answer boxes as rows of (tajenka index 1..k, x offset within the row), wrapped
    at word boundaries when possible. Rows are returned with x relative to the row start."""
    n = len(p.tajenka_cells)
    words = [len(w) for w in p.tajenka_words()]
    if sum(words) != n:
        words = [n]                           # no usable word split: one block, no gaps
    rows: list[list[tuple[int, float]]] = [[]]
    x, idx = 0.0, 0
    for wi, wlen in enumerate(words):
        gap = BOX_WORD_GAP if rows[-1] else 0.0
        if rows[-1] and x + gap + wlen * BOX_MM > max_w and wlen * BOX_MM <= max_w:
            rows.append([])
            x, gap = 0.0, 0.0
        x += gap
        for _ in range(wlen):
            if rows[-1] and x + BOX_MM > max_w:       # word longer than a row: break at the width
                rows.append([])
                x = 0.0
            idx += 1
            rows[-1].append((idx, x))
            x += BOX_MM
    return rows


def _grid_svg(p: Puzzle, solution: bool) -> tuple[list[str], float, float]:
    """Grid drawing in local mm coordinates; returns (elements, width, height)."""
    grid = p.grid()
    gutter = GUTTER if p.mode == "column" else 0.0
    tajenka = {tuple(c): i + 1 for i, c in enumerate(p.tajenka_cells)}
    blocks = {tuple(b) for b in p.blocks}
    out: list[str] = []

    def rect(r, c, fill, sw):
        return (f'<rect class="cell" x="{_fmt(gutter + c * CELL_MM)}" y="{_fmt(r * CELL_MM)}" '
                f'width="{_fmt(CELL_MM)}" height="{_fmt(CELL_MM)}" fill="{fill}" '
                f'stroke="#000000" stroke-width="{sw}"/>')

    filled = [(r, c) for r in range(p.height) for c in range(p.width)
              if grid[r][c] is not None or (r, c) in blocks]
    for r, c in filled:                       # normal cells first, tajenka on top
        if (r, c) not in tajenka:
            out.append(rect(r, c, "#000000" if (r, c) in blocks else "#ffffff", "0.4"))
    for r, c in filled:
        if (r, c) in tajenka:
            out.append(rect(r, c, TAJENKA_FILL, "0.9"))

    for r, c in filled:                       # letters
        key = grid[r][c]
        if solution and key is not None:
            size = 6.0 if len(key) == 1 else 4.2
            out.append(_text(gutter + (c + 0.5) * CELL_MM, (r + 0.5) * CELL_MM + size * 0.35,
                             size, key, anchor="middle"))
    if p.mode != "column":                    # clue numbers and tajenka indexes
        seen: set[tuple[int, int]] = set()
        for pl in p.placements:
            if pl.number is not None and (pl.row, pl.col) not in seen:
                seen.add((pl.row, pl.col))
                out.append(_text(gutter + pl.col * CELL_MM + 0.6, pl.row * CELL_MM + 2.8,
                                 2.8, str(pl.number)))
        for (r, c), i in tajenka.items():
            out.append(_text(gutter + (c + 1) * CELL_MM - 0.6, (r + 1) * CELL_MM - 0.8,
                             2.2, str(i), anchor="end"))
    else:                                     # row numbers and word separators
        rank = {pl.row: i + 1 for i, pl in enumerate(sorted(p.placements, key=lambda x: x.row))}
        for r, n in rank.items():
            out.append(_text(gutter - 1.5, (r + 0.5) * CELL_MM + 1.2, 3.5, str(n), anchor="end"))
        for r in _separator_rows(p):
            y = (r + 1) * CELL_MM
            out.append(f'<line x1="{_fmt(gutter)}" y1="{_fmt(y)}" x2="{_fmt(gutter + p.width * CELL_MM)}" '
                       f'y2="{_fmt(y)}" stroke="#000000" stroke-width="0.9"/>')
    width, height = gutter + p.width * CELL_MM, p.height * CELL_MM
    if p.mode == "web" and p.tajenka_cells:   # boxes to write the tajenka into
        max_w = max(width, BOX_MM)
        for k, row in enumerate(_tajenka_box_rows(p, max_w)):
            top = height + BOX_TOP_GAP + k * (BOX_MM + 4.0)
            shift = (width - (row[-1][1] + BOX_MM)) / 2     # centre under the grid
            for i, x in row:
                bx = shift + x
                out.append(f'<rect class="tajenka-box" x="{_fmt(bx)}" y="{_fmt(top)}" '
                           f'width="{_fmt(BOX_MM)}" height="{_fmt(BOX_MM)}" fill="#ffffff" '
                           f'stroke="#000000" stroke-width="0.6"/>')
                out.append(_text(bx + BOX_MM / 2, top - 0.8, 2.4, str(i), anchor="middle"))
                r, c = p.tajenka_cells[i - 1]
                key = grid[r][c] if solution and 0 <= r < p.height and 0 <= c < p.width else None
                if key:
                    size = 4.5 if len(key) == 1 else 3.2
                    out.append(_text(bx + BOX_MM / 2, top + BOX_MM / 2 + size * 0.35, size,
                                     key, anchor="middle"))
        height = top + BOX_MM
    return out, width, height


def render_svg(p: Puzzle, *, solution: bool, title: str | None = None) -> str:
    title = (title or "Křížovka") + (" – řešení" if solution else "")
    grid_els, gw, gh = _grid_svg(p, solution)
    scale0 = min(1.0, GRID_MAX_W / gw) if gw else 1.0

    def fit(cols, wrap, min_scale):           # shrink the grid until the clues fit too
        lines = _clue_lines(p, wrap)
        scale = scale0
        while True:
            clue_top = GRID_TOP + gh * scale + 8
            per_col = int((CLUE_BOTTOM - clue_top) // CLUE_LH)
            if per_col * cols >= len(lines):
                return lines, scale, clue_top, per_col
            scale *= 0.95
            if scale < min_scale:
                return None, scale, clue_top, per_col, len(lines)

    two = fit(2, WRAP, MIN_SCALE)
    if two[0] is not None and two[1] >= min(MIN_SCALE_2COL, scale0):
        (lines, scale, clue_top, per_col), cols, col_w = two, 2, COL_W
    else:                                     # 2 columns would shrink the grid too much
        three = fit(3, WRAP3, MIN_SCALE)
        best = max((r for r in (two, three) if r[0] is not None),
                   key=lambda r: r[1], default=None)   # ties go to two columns
        if best is None:
            raise RenderError(f"{three[4]} clue lines do not fit on one A4 page")
        (lines, scale, clue_top, per_col) = best
        cols, col_w = (2, COL_W) if best is two else (3, COL_W3)

    x0 = MARGIN + (GRID_MAX_W - gw * scale) / 2
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm" '
        f'viewBox="0 0 210 297" font-family="{FONT_FAMILY}">',
        _text(PAGE_W / 2, MARGIN + 7, 7, title, anchor="middle", bold=True),
        f'<g transform="translate({_fmt(x0)} {_fmt(GRID_TOP)}) scale({_fmt(scale)})" '
        'fill="#000000" font-family="' + FONT_FAMILY + '">',
        *grid_els, "</g>",
    ]
    for i, (text, heading) in enumerate(lines):
        col, row = divmod(i, per_col) if per_col else (0, 0)
        if text:
            parts.append(_text(MARGIN + col * (col_w + COL_GAP), clue_top + (row + 1) * CLUE_LH - 1,
                               CLUE_FONT, text, bold=heading))
    theme = p.meta.get("theme")
    if theme:
        parts.append(_text(PAGE_W / 2, PAGE_H - MARGIN, 3, str(theme), anchor="middle"))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render_solution_md(p: Puzzle, *, title: str | None = None) -> str:
    blocks = {tuple(b) for b in p.blocks}
    grid = p.grid()
    width = max([len(k) for row in grid for k in row if k] or [1])
    rows = []
    for r in range(p.height):
        cells = ["#" if (r, c) in blocks else (grid[r][c] or ".") for c in range(p.width)]
        rows.append(" ".join(k.ljust(width) for k in cells).rstrip())
    out = [f"# {(title or 'Křížovka')} – řešení", ""]
    if p.tajenka:
        out += [f"**Tajenka:** {p.tajenka}", ""]
    pomucka = p.meta.get("pomucka")
    if isinstance(pomucka, list) and pomucka:
        out += [f"**Pomůcka:** {', '.join(map(str, pomucka))}", ""]
    out += ["```text", *rows, "```", ""]
    for heading, items in clue_groups(p):
        out += [f"## {heading or 'Nápovědy'}", ""]
        for number, entry in items:
            label = f"{number}." if number is not None else "-"
            out.append(f"{label} {entry.answer} — {_clue_text(entry)}")
        out.append("")
    if p.dropped:
        out += ["## Neumístěná slova", "", *(f"- {w}" for w in p.dropped), ""]
    return "\n".join(out).rstrip("\n") + "\n"


def write_all(p: Puzzle, out_dir: Path, *, title: str | None = None) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if p.mode == "swedish":
        from . import render_swedish          # imported here: render_swedish imports this module
        draw = render_swedish.render_svg
    else:
        draw = render_svg
    files = {
        "puzzle_svg": (out_dir / "puzzle.svg", draw(p, solution=False, title=title)),
        "solution_svg": (out_dir / "solution.svg", draw(p, solution=True, title=title)),
        "solution_md": (out_dir / "solution.md", render_solution_md(p, title=title)),
    }
    for path, content in files.values():
        path.write_text(content, encoding="utf-8")
    return {k: path for k, (path, _) in files.items()}
