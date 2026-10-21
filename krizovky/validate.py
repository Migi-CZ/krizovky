"""Puzzle validator: SČHAK hard rules + PROJECT_SPEC §3 acceptance criteria.

``validate(puzzle)`` returns a list of human-readable violations; an empty
list means the puzzle is valid. ``clue_violations`` is shared with clues.py.
"""
from __future__ import annotations

import re
from collections import Counter

from . import alphabet
from .model import ACROSS, DIRECTIONS, DOWN, MODES, Puzzle

# Clue length caps: a clue list (column/web) vs. an in-cell clue (swedish).
CLUE_MAX = {"column": 70, "web": 70, "swedish": 28}

Coord = tuple[int, int]


def answer_stem(answer: str) -> str:
    """Lower-case ASCII prefix of the answer that a clue must not start a word
    with (directive §50: the clue may not repeat the answer)."""
    plain = re.sub(r"[^a-z]", "", alphabet.strip_diacritics(answer).lower())
    return plain[: max(4, len(plain) - 2)]


def clue_violations(answer: str, clue: str | None, mode: str) -> list[str]:
    out: list[str] = []
    if clue is None or not clue.strip():
        return [f"clue for {answer}: empty"]
    text = clue.strip()
    cap = CLUE_MAX.get(mode, 70)
    if len(text) > cap:
        out.append(f"clue for {answer}: {len(text)} chars, max {cap} in mode {mode}")
    stem = answer_stem(answer)
    words = re.findall(r"[a-z]+", alphabet.strip_diacritics(text).lower())
    if stem and any(w.startswith(stem) for w in words):
        out.append(f"clue for {answer}: contains the answer stem {stem!r} ({text!r})")
    return out


def _runs(grid: list[list[str | None]], direction: str) -> list[list[Coord]]:
    """Maximal runs (length >= 2) of filled cells along rows or columns."""
    h, w = len(grid), len(grid[0]) if grid else 0
    runs: list[list[Coord]] = []
    lines = (
        [[(r, c) for c in range(w)] for r in range(h)] if direction == ACROSS
        else [[(r, c) for r in range(h)] for c in range(w)]
    )
    for line in lines:
        run: list[Coord] = []
        for r, c in line + [(-1, -1)]:
            if (r, c) != (-1, -1) and grid[r][c] is not None:
                run.append((r, c))
            else:
                if len(run) >= 2:
                    runs.append(run)
                run = []
    return runs


def validate(p: Puzzle) -> list[str]:
    v: list[str] = []
    if p.mode not in MODES:
        v.append(f"unknown mode {p.mode!r}")
    if p.match not in alphabet.MATCH_MODES:
        v.append(f"unknown match mode {p.match!r}")
    if p.width < 1 or p.height < 1:
        v.append(f"grid size {p.width}x{p.height} is empty")
    if len(p.entries) != len(p.placements):
        v.append(f"{len(p.entries)} entries but {len(p.placements)} placements")
    if v:
        return v  # the rest assumes a sane shape

    grid = p.grid()
    coords_of: list[list[Coord]] = []
    seen_keys: Counter = Counter()
    for i, (entry, pl) in enumerate(zip(p.entries, p.placements)):
        label = f"entry {i} {entry.answer}"
        if pl.direction not in DIRECTIONS:
            v.append(f"{label}: unknown direction {pl.direction!r}")
            coords_of.append([])
            continue
        if p.mode == "column" and pl.direction != ACROSS:
            v.append(f"{label}: mode column needs across placements")
        if len(entry) < alphabet.MIN_LEN:
            v.append(f"{label}: too short ({len(entry)} cells, min {alphabet.MIN_LEN})")
        if len(entry) > alphabet.MAX_LEN:
            v.append(f"{label}: too long ({len(entry)} cells, max {alphabet.MAX_LEN})")
        bad = [c for c in entry.cells if c not in alphabet.CELLS]
        if bad:
            v.append(f"{label}: cells not in the alphabet: {bad}")
        seen_keys[entry.keys(p.match)] += 1
        coords = pl.coords(len(entry))
        coords_of.append(coords)
        if any(not (0 <= r < p.height and 0 <= c < p.width) for r, c in coords):
            v.append(f"{label}: out of bounds at ({pl.row},{pl.col}) {pl.direction}")
            continue
        for (r, c), key in zip(coords, entry.keys(p.match)):
            if grid[r][c] != key:
                v.append(f"{label}: conflict at ({r},{c}): wants {key}, grid has {grid[r][c]}")
        if entry.clue is not None:
            v.extend(clue_violations(entry.answer, entry.clue, p.mode))

    for key, n in seen_keys.items():
        if n > 1:
            v.append(f"entry {''.join(key)} appears twice (directive §16)")

    placed = {e.keys(p.match) for e in p.entries}
    for word in p.dropped:
        try:
            if alphabet.word_key(alphabet.tokenize(word, ch_one_cell=p.ch_one_cell), p.match) in placed:
                v.append(f"dropped word {word} is also placed")
        except alphabet.AlphabetError:
            v.append(f"dropped word {word!r} is not a valid word")

    # crossings: every entry shares a cell with another one (web, swedish)
    if p.mode in ("web", "swedish"):
        cell_owners: Counter = Counter(c for coords in coords_of for c in coords)
        for i, coords in enumerate(coords_of):
            if coords and not any(cell_owners[c] > 1 for c in coords):
                v.append(f"entry {i} {p.entries[i].answer} does not cross any other entry")

    # runs: every maximal run of >= 2 filled cells must be exactly one entry
    span_set = {(pl.direction, tuple(coords)) for pl, coords in zip(p.placements, coords_of) if coords}
    run_dirs = (ACROSS,) if p.mode == "column" else DIRECTIONS
    for direction in run_dirs:
        for run in _runs(grid, direction):
            if (direction, tuple(run)) not in span_set:
                letters = "".join(grid[r][c] or "" for r, c in run)
                v.append(f"unintended {direction} word {letters} at {run[0]}")

    if p.mode == "swedish":
        owners = {d: Counter(c for coords, pl in zip(coords_of, p.placements) if pl.direction == d
                             for c in coords) for d in DIRECTIONS}
        block_set = set(p.blocks)
        for r in range(p.height):
            for c in range(p.width):
                if grid[r][c] is None and (r, c) not in block_set:
                    v.append(f"cell ({r},{c}) is empty: neither a letter nor a block")
                elif grid[r][c] is not None:
                    for d in DIRECTIONS:
                        if not owners[d][(r, c)]:
                            v.append(f"cell ({r},{c}) is in no {d} word")
        for i, (entry, pl) in enumerate(zip(p.entries, p.placements)):
            # the clue sits in the block just before the first letter; out of bounds counts as missing
            before = (pl.row, pl.col - 1) if pl.direction == ACROSS else (pl.row - 1, pl.col)
            if pl.direction in DIRECTIONS and before not in block_set:
                v.append(f"entry {i} {entry.answer} has no clue cell before it")
        by_coords = Counter(tuple(coords) for coords in coords_of if coords)
        for k, run in enumerate(p.tajenka_run_cells()):
            if by_coords[tuple(run)] != 1:
                v.append(f"tajenka run {k} is not a whole entry")

    # tajenka
    if p.tajenka:
        try:
            keys = p.tajenka_keys()
        except alphabet.AlphabetError as exc:
            keys = ()
            v.append(f"tajenka: {exc}")
        if not p.tajenka_cells:
            v.append("tajenka declared but no tajenka cells marked (directive §65)")
        elif len(p.tajenka_cells) != len(keys):
            v.append(f"tajenka has {len(keys)} cells but {len(p.tajenka_cells)} are marked")
        else:
            for (r, c), key in zip(p.tajenka_cells, keys):
                if not (0 <= r < p.height and 0 <= c < p.width):
                    v.append(f"tajenka cell ({r},{c}) out of bounds")
                elif grid[r][c] != key:
                    v.append(f"tajenka cell ({r},{c}) has {grid[r][c]}, expected {key}")
    elif p.tajenka_cells:
        v.append("tajenka cells marked but no tajenka text")

    # blocks: empty; 180° symmetric except in mode swedish (PROJECT_SPEC §2, directive §19)
    if p.blocks:
        block_set = set(p.blocks)
        for r, c in p.blocks:
            if not (0 <= r < p.height and 0 <= c < p.width):
                v.append(f"block ({r},{c}) out of bounds")
            elif grid[r][c] is not None:
                v.append(f"block ({r},{c}) is filled with {grid[r][c]}")
            if p.mode != "swedish" and (p.height - 1 - r, p.width - 1 - c) not in block_set:
                v.append(f"blocks are not symmetric: ({r},{c}) has no mirror (directive §19)")
    return v
