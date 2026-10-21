"""Generic grid helpers shared by the placers (modes column and web)."""
from __future__ import annotations

import copy

from .model import Puzzle

Coord = tuple[int, int]


def filled_cells(p: Puzzle) -> dict[Coord, str]:
    return {(r, c): key
            for r, row in enumerate(p.grid()) for c, key in enumerate(row) if key is not None}


def bounding_box(p: Puzzle) -> tuple[int, int, int, int]:
    """(min_row, min_col, max_row, max_col) of the filled cells."""
    cells = filled_cells(p)
    if not cells:
        raise ValueError("puzzle has no filled cells")
    rows = [r for r, _ in cells]
    cols = [c for _, c in cells]
    return min(rows), min(cols), max(rows), max(cols)


def trim(p: Puzzle) -> Puzzle:
    """Copy of the puzzle shifted so the filled cells start at (0, 0)."""
    r0, c0, r1, c1 = bounding_box(p)
    out = copy.deepcopy(p)
    out.width, out.height = c1 - c0 + 1, r1 - r0 + 1
    for pl in out.placements:
        pl.row -= r0
        pl.col -= c0
    out.tajenka_cells = [(r - r0, c - c0) for r, c in out.tajenka_cells]
    # Blocks are shifted like everything else; the placer owns their symmetry.
    out.blocks = [(r - r0, c - c0) for r, c in out.blocks]
    return out


def number_entries(p: Puzzle) -> None:
    """Crossword numbering: row-major scan, one number per start cell, shared by
    an across and a down entry that start together. Sets placement.number."""
    starts = sorted({(pl.row, pl.col) for pl in p.placements})
    number = {start: n for n, start in enumerate(starts, 1)}
    for pl in p.placements:
        pl.number = number[(pl.row, pl.col)]
