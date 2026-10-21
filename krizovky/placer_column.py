"""Mode A (column / doplňovačka): one word per row, aligned so that one column
reads the tajenka top to bottom.

Row i needs a distinct entry containing tajenka key i at some index a. The
shared column is tcol = max(a); the grid needs max(a) + max(len - a) cells.
For a fixed column T and right extent R every (row, entry) pair is feasible or
not independently, so the choice is a bipartite matching (rows to entries).
We try widths from small to the limit and every column T, and match with
augmenting paths; this finds a solution within the width whenever one exists.
"""
from __future__ import annotations

import random

from . import alphabet
from .model import ACROSS, Entry, Placement, Puzzle

Options = list[dict[int, list[tuple[int, int]]]]  # per row: entry -> [(left, right)]


class PlacementError(ValueError):
    """The words cannot cover the tajenka within the width."""


def _options(rows: list[str], keys: list[tuple[str, ...]]) -> Options:
    out: Options = []
    for letter in rows:
        per_entry = {}
        for j, k in enumerate(keys):
            spots = [(a, len(k) - a) for a, key in enumerate(k) if key == letter]
            if spots:
                per_entry[j] = spots
        out.append(per_entry)
    return out


def _match(options: Options, order: list[list[int]], left: int, right: int
           ) -> dict[int, tuple[int, int]] | None:
    """Rows -> (entry, index) with index <= left and length - index <= right."""
    def pick(row: int, j: int) -> int | None:
        for a, b in options[row][j]:
            if a <= left and b <= right:
                return a
        return None

    owner: dict[int, int] = {}  # entry -> row

    def augment(row: int, seen: set[int]) -> bool:
        for j in order[row]:
            if j in seen or pick(row, j) is None:
                continue
            seen.add(j)
            if j not in owner or augment(owner[j], seen):
                owner[j] = row
                return True
        return False

    # most constrained row first
    for row in sorted(range(len(options)), key=lambda r: len(options[r])):
        if not augment(row, set()):
            return None
    return {row: (j, pick(row, j)) for j, row in owner.items()}  # type: ignore[misc]


def _solve(options: Options, order: list[list[int]], max_width: int, rng: random.Random
           ) -> dict[int, tuple[int, int]] | None:
    for w in range(alphabet.MIN_LEN, max_width + 1):
        for left in rng.sample(range(w), w):
            found = _match(options, order, left, w - left)
            if found is not None:
                return found
    return None


def place(entries: list[Entry], tajenka: str, *, width: int = 11, match: str = "strict",
          ch_one_cell: bool = True, rng: random.Random | None = None) -> Puzzle:
    if match not in alphabet.MATCH_MODES:
        raise PlacementError(f"unknown match mode {match!r}; use one of {alphabet.MATCH_MODES}")
    if width < alphabet.MIN_LEN:
        raise PlacementError(f"width {width} is too small (min {alphabet.MIN_LEN})")
    if not entries:
        raise PlacementError("no words to place")
    rng = rng or random.Random(0)
    cells = alphabet.flatten(alphabet.tokenize_phrase(tajenka, ch_one_cell=ch_one_cell))
    rows = [alphabet.cell_key(c, match) for c in cells]

    # Candidates: length rules, duplicates (by key) only once, and never a word
    # of the tajenka itself (it would give the secret away). Usable = candidates
    # that also fit the width.
    tajenka_keys = {alphabet.word_key(w, match)
                    for w in alphabet.tokenize_phrase(tajenka, ch_one_cell=ch_one_cell)}
    candidates: list[int] = []
    seen_keys: set[tuple[str, ...]] = set(tajenka_keys)
    for i, e in enumerate(entries):
        k = e.keys(match)
        if alphabet.MIN_LEN <= len(e) <= alphabet.MAX_LEN and k not in seen_keys:
            seen_keys.add(k)
            candidates.append(i)
    usable = [i for i in candidates if len(entries[i]) <= width]
    keys = [entries[i].keys(match) for i in usable]
    options = _options(rows, keys)

    missing = [f"{cells[r]} (row {r + 1})" for r, o in enumerate(options) if not o]
    if missing:
        raise PlacementError("no usable word for tajenka letters: " + ", ".join(missing))

    order = [rng.sample(list(o), len(o)) for o in options]
    found = _solve(options, order, width, rng)
    if found is None:
        raise PlacementError(_explain_failure(rows, [entries[i].keys(match) for i in candidates], width, rng))

    chosen = [found[r] for r in range(len(rows))]
    tcol = max(a for _, a in chosen)
    used = [usable[j] for j, _ in chosen]
    placed = [entries[i] for i in used]
    placements = [Placement(r, tcol - a, ACROSS) for r, (_, a) in enumerate(chosen)]
    return Puzzle(
        mode="column", width=max(pl.col + len(e) for e, pl in zip(placed, placements)),
        height=len(rows), match=match, ch_one_cell=ch_one_cell, entries=placed,
        placements=placements, tajenka=tajenka, tajenka_cells=[(r, tcol) for r in range(len(rows))],
        meta={"unused": [e.answer for i, e in enumerate(entries) if i not in set(used)]},
    )


def _explain_failure(rows: list[str], keys: list[tuple[str, ...]], width: int,
                     rng: random.Random) -> str:
    """Say whether a wider grid would help, and how wide it must be. ``keys``
    are the same candidates the search used, without the width limit."""
    options = _options(rows, keys)
    order = [list(o) for o in options]
    found = _solve(options, order, 2 * alphabet.MAX_LEN, rng) if all(options) else None
    if found is None:
        return (f"the {len(keys)} distinct words cannot cover the "
                f"{len(rows)} tajenka letters (not enough different words with the right letters)")
    tcol = max(a for _, a in found.values())
    need = max(tcol - a + len(keys[j]) for j, a in found.values())
    return f"width {width} is too small; width {need} would work with these words"
