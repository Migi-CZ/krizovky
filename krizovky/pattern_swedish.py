"""Mode C (swedish): the clue-cell layout of a dense Swedish-style grid.

A pattern is a rectangle of cells in which every cell is either a *block* (a clue or
black cell) or white. Conventions of the slice-4 spike:

* row 0 and column 0 are blocks, so every word has a block right before its first cell;
* no white run is shorter than two cells in either direction, i.e. every white cell
  belongs to an across and a down word;
* the tajenka (hidden phrase) is pre-placed as whole across runs: each run is a maximal
  white run, on its own row, rows not adjacent;
* the white cells form one connected area; there is no symmetry requirement.

``generate`` builds such a pattern at random (best of ``tries`` by an estimated
difficulty); ``filler_dense`` fills it with words.
"""
from __future__ import annotations

import math
import random
import warnings
from dataclasses import dataclass, field

from .alphabet import MIN_LEN
from .model import ACROSS, DOWN

Coord = tuple[int, int]

_ALPHABET = 18.0   # effective number of equally likely letters, for the difficulty estimate
_LONG_PENALTY = 5.0
_DEFAULT_COUNT = 1000
_PLACE_TRIES = 30
_EXCESS_BLOCK = 6.0   # difficulty credit a block above the target share must not earn


class PatternError(ValueError):
    """No pattern can be built for the requested size and tajenka."""


@dataclass
class Slot:
    """One word position: a maximal white run of at least two cells."""
    cells: list[Coord]            # (row, col) in reading order
    direction: str                # ACROSS or DOWN
    tajenka: int | None = None    # index of the tajenka run it carries


@dataclass
class Pattern:
    rows: int
    cols: int
    blocks: set[Coord]
    tajenka_runs: list[list[Coord]] = field(default_factory=list)

    def white(self) -> set[Coord]:
        return {(r, c) for r in range(self.rows) for c in range(self.cols)} - self.blocks

    def block_share(self) -> float:
        return len(self.blocks) / (self.rows * self.cols)

    def inner_share(self) -> float:
        """Blocks among the (rows-1)(cols-1) cells inside row 0 / column 0: the magazine's shape
        number (12.7-13.3 % on the three examples), independent of the grid size."""
        inner = (self.rows - 1) * (self.cols - 1)
        return sum(1 for r, c in self.blocks if r > 0 and c > 0) / inner if inner else 0.0

    def slots(self) -> list[Slot]:
        """Maximal white runs of >= 2 cells: across words row by row, then down words column by column."""
        tag = {tuple(run): k for k, run in enumerate(self.tajenka_runs)}
        out: list[Slot] = []
        for direction in (ACROSS, DOWN):
            for cells in _runs(self.rows, self.cols, self.blocks, direction):
                out.append(Slot(cells, direction, tag.get(tuple(cells)) if direction == ACROSS else None))
        return out

    def is_valid(self) -> list[str]:
        """The violations of the pattern rules; ``[]`` = valid."""
        v: list[str] = []
        if self.rows < 2 or self.cols < 2:
            return [f"grid {self.rows}x{self.cols} is too small"]
        outside = [b for b in self.blocks if not (0 <= b[0] < self.rows and 0 <= b[1] < self.cols)]
        if outside:
            return [f"block {outside[0]} is outside the grid"]
        for c in range(self.cols):
            if (0, c) not in self.blocks:
                v.append(f"cell (0,{c}) of the first row is not a block")
        for r in range(self.rows):
            if (r, 0) not in self.blocks:
                v.append(f"cell ({r},0) of the first column is not a block")
        white = self.white()
        for r, c in sorted(white):
            if not ((r, c - 1) in white or (r, c + 1) in white):
                v.append(f"white cell ({r},{c}) is in no across word")
            if not ((r - 1, c) in white or (r + 1, c) in white):
                v.append(f"white cell ({r},{c}) is in no down word")
        across = {tuple(s.cells) for s in self.slots() if s.direction == ACROSS}
        for k, run in enumerate(self.tajenka_runs):
            if len(run) < 2 or len({r for r, _ in run}) != 1 or [c for _, c in run] != list(range(run[0][1], run[0][1] + len(run))):
                v.append(f"tajenka run {k} is not a straight across run of >= 2 cells")
            elif tuple(run) not in across:
                v.append(f"tajenka run {k} is not a maximal white run (block before and after it, or the edge)")
        starts = [run[0][0] for run in self.tajenka_runs if run]
        for a, b in zip(starts, starts[1:]):
            if b - a < 2:
                v.append(f"tajenka runs on rows {a} and {b} must be in order and not adjacent")
        if white and not _connected(white):
            v.append("white cells are not connected")
        return v


# --- helpers ------------------------------------------------------------------------
def _runs(rows: int, cols: int, blocks: set[Coord], direction: str, min_len: int = 2) -> list[list[Coord]]:
    """Maximal white runs of at least ``min_len`` cells along rows or columns."""
    lines = ([[(r, c) for c in range(cols)] for r in range(rows)] if direction == ACROSS
             else [[(r, c) for r in range(rows)] for c in range(cols)])
    out: list[list[Coord]] = []
    for line in lines:
        run: list[Coord] = []
        for cell in line + [None]:
            if cell is not None and cell not in blocks:
                run.append(cell)
                continue
            if len(run) >= min_len:
                out.append(run)
            run = []
    return out


def _connected(white: set[Coord]) -> bool:
    start = min(white)
    seen = {start}
    stack = [start]
    while stack:
        r, c = stack.pop()
        for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if nb in white and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return len(seen) == len(white)


def _connected_blocks(rows: int, cols: int, blocks: set[Coord]) -> bool:
    """Like ``_connected`` for the white cells left by ``blocks`` (frame included)."""
    total = rows * cols - (len(blocks) - 2 * (rows + cols + 2))
    start = next(((r, c) for r in range(rows) for c in range(cols) if (r, c) not in blocks), None)
    if start is None:
        return True
    seen = {start}
    stack = [start]
    while stack:
        r, c = stack.pop()
        for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if nb not in blocks and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return len(seen) == total


def _run_lengths(rows: int, cols: int, blocks: set[Coord]) -> tuple[dict[Coord, int], dict[Coord, int]]:
    """Length of the across and of the down white run through every white cell."""
    across: dict[Coord, int] = {}
    down: dict[Coord, int] = {}
    for direction, table in ((ACROSS, across), (DOWN, down)):
        for run in _runs(rows, cols, blocks, direction, 1):
            for cell in run:
                table[cell] = len(run)
    return across, down


def _frame(rows: int, cols: int) -> set[Coord]:
    """The ring of cells just outside the grid; adding it to the blocks removes bounds checks."""
    return ({(-1, c) for c in range(-1, cols + 1)} | {(rows, c) for c in range(-1, cols + 1)}
            | {(r, -1) for r in range(rows)} | {(r, cols) for r in range(rows)})


def _cell_ok(r: int, c: int, blocks: set[Coord]) -> bool:
    """White cell (r, c) has a white neighbour left-or-right and above-or-below
    (``blocks`` includes the frame)."""
    return ((r, c - 1) not in blocks or (r, c + 1) not in blocks) \
        and ((r - 1, c) not in blocks or (r + 1, c) not in blocks)


def _block_closure(r: int, c: int, blocks: set[Coord], protected: set[Coord]) -> list[Coord] | None:
    """Block (r, c) and, repeatedly, every white neighbour that thereby loses its across or down
    partner. Returns the cells added to ``blocks`` (the caller removes them to undo), or None
    (``blocks`` unchanged) when a protected (tajenka) cell would have to be blocked."""
    added = [(r, c)]
    blocks.add((r, c))
    todo = [(r, c)]
    while todo:
        cr, cc = todo.pop()
        for nr, nc in ((cr - 1, cc), (cr + 1, cc), (cr, cc - 1), (cr, cc + 1)):
            if (nr, nc) not in blocks and not _cell_ok(nr, nc, blocks):
                if (nr, nc) in protected:
                    blocks.difference_update(added)
                    return None
                blocks.add((nr, nc))
                added.append((nr, nc))
                todo.append((nr, nc))
    return added


def _split_weight(r: int, c: int, blocks: set[Coord], stump: float = 0.1) -> float:
    """How much blocking (r, c) is worth: a long run split into two even pieces scores high,
    a split that leaves a short stump (or none: a block next to a block) scores low; every
    piece of exactly 2 cells multiplies by ``stump``, every piece of 3 cells by ``sqrt(stump)``
    (slice 4d: the magazines have 25-38 % 2-3-cell words, the plain product gave 44-48 %, the
    2-cell factor alone still 39-44 %; with both the magazine sizes land at 29-34 %)."""
    def pieces(dr: int, dc: int) -> int:
        n, rr, cc = 0, r + dr, c + dc
        while (rr, cc) not in blocks:
            n += 1
            rr, cc = rr + dr, cc + dc
        return n
    left, right = pieces(0, -1), pieces(0, 1)
    up, down = pieces(-1, 0), pieces(1, 0)
    weight = (left * right + 1.0) * (up * down + 1.0)
    for n in (left, right, up, down):
        if n == 2:
            weight *= stump
        elif n == 3:
            weight *= math.sqrt(stump)
    return weight


def _place_runs(rows: int, cols: int, lengths: list[int], rng: random.Random):
    """Edge blocks (and the frame) plus the tajenka runs with their end blocks, or None if the result is not valid."""
    n = len(lengths)
    blocks: set[Coord] = {(0, c) for c in range(cols)} | {(r, 0) for r in range(rows)} | _frame(rows, cols)
    runs: list[list[Coord]] = []
    prev = -1
    for k, length in enumerate(lengths):
        target = round((k + 1) / (n + 1) * rows) + rng.choice((-1, 0, 1))
        lo = max(1, prev + 2)
        hi = rows - 1 - 2 * (n - 1 - k)
        r = min(max(target, lo), hi)
        c0 = rng.randint(1, cols - length)
        runs.append([(r, c0 + i) for i in range(length)])
        if c0 - 1 >= 1:
            blocks.add((r, c0 - 1))
        if c0 + length < cols:
            blocks.add((r, c0 + length))
        prev = r
    tajenka = {cell for run in runs for cell in run}
    for r in range(1, rows):
        for c in range(1, cols):
            if (r, c) not in blocks and not _cell_ok(r, c, blocks):
                return None
    return blocks, runs, tajenka


def _attempt(rows: int, cols: int, lengths: list[int], rng: random.Random, share: float,
             max_len: int, soft_len: int = 8, long_slots: int = 2, stump: float = 0.1) -> Pattern | None:
    """One random pattern: ``share`` is the inner block share to reach; blocks keep being added
    while a run exceeds ``max_len`` or more than ``long_slots`` non-tajenka runs exceed ``soft_len``."""
    placed = None
    for _ in range(_PLACE_TRIES):   # a few run positions are invalid (e.g. a stump next to the top edge)
        placed = _place_runs(rows, cols, lengths, rng)
        if placed is not None:
            break
    if placed is None:
        return None
    blocks, runs, tajenka = placed
    run_set = {tuple(run) for run in runs}
    all_cells = [(r, c) for r in range(1, rows) for c in range(1, cols)]
    nframe = 2 * (rows + cols + 2)
    nedge = rows + cols - 1
    inner_cells = (rows - 1) * (cols - 1)
    while True:
        across, down = _run_lengths(rows, cols, blocks)
        too_long = any(n > max_len for n in across.values()) or any(n > max_len for n in down.values())
        long_runs = sum(1 for d in (ACROSS, DOWN) for run in _runs(rows, cols, blocks, d)
                        if len(run) > soft_len and tuple(run) not in run_set)
        too_many_long = long_runs > long_slots
        reached = (len(blocks) - nframe - nedge) / inner_cells >= share
        if reached and not too_long and not too_many_long:
            break
        cands: list[tuple[list[Coord], float]] = []
        for cell in all_cells:
            if cell in blocks or cell in tajenka:
                continue
            la, ld = across[cell], down[cell]
            if reached and la <= max_len and ld <= max_len and not (too_many_long and (la > soft_len or ld > soft_len)):
                continue   # the share is met: only runs that are still too long get split
            r, c = cell
            added = _block_closure(r, c, blocks, tajenka)
            if added is None:
                continue
            blocks.difference_update(added)
            used_clue_cell = (r, c + 1) in across and (r + 1, c) in down   # starts an across and a down word
            weight = _split_weight(r, c, blocks, stump) * (2.0 if used_clue_cell else 1.0)
            cands.append((added, weight / len(added) ** 2))   # a move that strands neighbours costs more
        while cands:
            pick = rng.choices(range(len(cands)), weights=[w for _, w in cands])[0]
            added = cands[pick][0]
            blocks.update(added)
            if _connected_blocks(rows, cols, blocks):
                break
            blocks.difference_update(added)
            del cands[pick]
        else:
            break   # nothing can be blocked any more
    return Pattern(rows, cols, blocks - _frame(rows, cols), runs)


def difficulty(pattern: Pattern, counts: dict[int, int] | None = None, max_len: int = 8,
               block_share: float | None = None, inner_share: float | None = None) -> float:
    """Estimated difficulty of filling the pattern, lower = easier.

    -log of the expected number of fills: a free cell can hold ~_ALPHABET letters, a slot of n
    cells accepts a random letter string with probability counts[n] / _ALPHABET**n. Slots longer
    than ``max_len`` are penalised, and so is every block above the target share (``inner_share``
    of the inner cells, or the deprecated ``block_share`` of all cells; more blocks always make a
    grid easier, which must not decide the choice). The tajenka cells are fixed, their slots are
    not counted.
    """
    total = 0.0
    if inner_share is not None:
        inner_blocks = sum(1 for r, c in pattern.blocks if r > 0 and c > 0)
        total += _EXCESS_BLOCK * max(0.0, inner_blocks - inner_share * (pattern.rows - 1) * (pattern.cols - 1))
    elif block_share is not None:
        total += _EXCESS_BLOCK * max(0.0, len(pattern.blocks) - block_share * pattern.rows * pattern.cols)
    free = pattern.white() - {cell for run in pattern.tajenka_runs for cell in run}
    total -= len(free) * math.log(_ALPHABET)
    for slot in pattern.slots():
        if slot.tajenka is not None:
            continue
        n = len(slot.cells)
        have = _DEFAULT_COUNT if counts is None else max(1, counts.get(n, 0))
        total += n * math.log(_ALPHABET) - math.log(have)
        total += _LONG_PENALTY * max(0, n - max_len)
    return total


class NoFeasiblePattern(PatternError):
    """Valid patterns exist but none of the candidates passed the ``accept`` test."""


def inner_from_block_share(rows: int, cols: int, block_share: float) -> float:
    """The inner share that stops ``_attempt`` at the same block count as the old all-cell share."""
    return max(0.0, (block_share * rows * cols - (rows + cols - 1)) / ((rows - 1) * (cols - 1)))


def generate(rows: int, cols: int, tajenka_lengths: list[int], *, rng: random.Random,
             block_share: float | None = None, max_len: int = 11, tries: int = 50,
             counts: dict[int, int] | None = None, accept=None,
             inner_share: float | None = None, soft_len: int = 8, long_slots: int = 2,
             stump: float = 0.1) -> Pattern:
    """A random valid pattern; the easiest of ``tries`` candidates by ``difficulty``.

    Shape knobs (slice 4d, defaults = the shape of the Czech puzzle magazines): ``inner_share``
    (default 0.13) = blocks among the inner cells; ``max_len`` the hard cap on a run; at most
    ``long_slots`` non-tajenka runs longer than ``soft_len``; ``stump`` = weight factor of a split
    that leaves a 2-cell piece. ``block_share`` (blocks over all cells) is deprecated: it is
    converted to the inner share that gives the same block count.

    ``counts`` (words per length, from the lexicon) sharpens the difficulty estimate; ``accept``
    (pattern -> bool) drops candidates the caller knows cannot work, e.g. because the tajenka
    letters already starve a slot (``NoFeasiblePattern`` if every candidate is dropped).
    Deterministic for a given ``rng`` state.
    """
    n = len(tajenka_lengths)
    if block_share is not None and inner_share is not None:
        raise PatternError("give inner_share or the deprecated block_share, not both")
    if block_share is not None:
        if not 0 <= block_share < 1:
            raise PatternError(f"block_share {block_share} must be in [0, 1)")
        warnings.warn("block_share is deprecated, use inner_share", DeprecationWarning, stacklevel=2)
        inner_share = inner_from_block_share(rows, cols, block_share) if rows > 1 and cols > 1 else 0.0
    if inner_share is None:
        inner_share = 0.13
    if rows < 2 or cols < 2:
        raise PatternError(f"grid {rows}x{cols} is too small")
    if n == 0:
        raise PatternError("no tajenka run requested")
    if rows < 2 * n:
        raise PatternError(f"{n} tajenka runs on separate, non-adjacent rows need at least {2 * n} rows, got {rows}")
    for length in tajenka_lengths:
        if length < 2:
            raise PatternError(f"a tajenka run needs at least 2 cells, got {length}")
        if length > cols - 1:
            raise PatternError(f"tajenka run of {length} cells does not fit: at most {cols - 1} "
                               f"(column 0 is a block) in {cols} columns")
    if not 0 <= inner_share < 1:
        raise PatternError(f"inner_share {inner_share} must be in [0, 1)")
    if max_len < MIN_LEN or soft_len < MIN_LEN or long_slots < 0 or stump < 0:
        raise PatternError(f"max_len {max_len} / soft_len {soft_len} / long_slots {long_slots} / stump {stump}: bad value")
    best: Pattern | None = None
    best_score = math.inf
    found = 0
    for _ in range(max(1, tries)):
        cand = _attempt(rows, cols, list(tajenka_lengths), rng, inner_share, max_len, soft_len, long_slots, stump)
        if cand is None or cand.is_valid():
            continue
        found += 1
        if accept is not None and not accept(cand):
            continue
        score = difficulty(cand, counts, max_len, inner_share=inner_share)
        if score < best_score:
            best, best_score = cand, score
    if best is None and found:
        raise NoFeasiblePattern(f"none of {found} valid patterns was accepted")
    if best is None:
        raise PatternError("could not place the tajenka runs in a valid pattern; "
                           "try a bigger grid, shorter runs or more tries")
    return best


def block_options(pattern: Pattern, cells: list[Coord], *, cap: float, protected: set[Coord] | None = None,
                  stump: float = 0.1) -> list[tuple[Coord, list[Coord], float]]:
    """The legal repairs of the slot ``cells`` (slice 4d): for every cell of it that is not protected
    and leaves the slot in pieces of 0 or >= 2 cells (a 2-cell slot goes as a whole), the cells its
    ``_block_closure`` adds, when the closure succeeds, the white cells stay connected and the inner
    share after it is <= ``cap``. Returns ``(cell, added, weight)`` with ``_attempt``'s score
    ``_split_weight / len(added)**2`` (even pieces, little collateral damage); the caller chooses."""
    rows, cols = pattern.rows, pattern.cols
    if protected is None:
        protected = {cell for run in pattern.tajenka_runs for cell in run}
    blocks = set(pattern.blocks) | _frame(rows, cols)
    inner_cells = (rows - 1) * (cols - 1)
    inner_now = sum(1 for r, c in pattern.blocks if r > 0 and c > 0)
    n = len(cells)
    out: list[tuple[Coord, list[Coord], float]] = []
    for i, (r, c) in enumerate(cells):
        if (r, c) in protected or (r, c) in blocks:
            continue
        if n == 2 and i == 1:
            continue   # the same move as blocking the first cell (the closure takes both)
        if n != 2 and (i == 1 or n - 1 - i == 1):
            continue   # a 1-cell piece would only cascade to the end-cell move
        weight = _split_weight(r, c, blocks, stump)
        added = _block_closure(r, c, blocks, protected)
        if added is None:
            continue
        ok = _connected_blocks(rows, cols, blocks)
        inner_after = inner_now + sum(1 for ar, ac in added if ar > 0 and ac > 0)
        blocks.difference_update(added)
        if not ok or inner_cells == 0 or inner_after / inner_cells > cap + 1e-9:
            continue
        out.append(((r, c), added, weight / len(added) ** 2))
    return out


def shape_stats(pattern: Pattern, tajenka: set[Coord] | None = None) -> dict[str, object]:
    """Shape numbers of a pattern against the magazine targets (``Source/cuddly-lovelace.md`` E1):
    block shares, word count and lengths, and how the inner blocks sit. ``tajenka`` = the tajenka
    cells (default: the pattern's runs); a slot lying wholly inside them is not a long word."""
    taj = set(tajenka) if tajenka is not None else {cell for run in pattern.tajenka_runs for cell in run}
    slots = pattern.slots()
    lengths = [len(s.cells) for s in slots]
    nwords = len(lengths)
    inner = [(r, c) for r, c in pattern.blocks if r > 0 and c > 0]
    inner_set = set(inner)
    across, down = _run_lengths(pattern.rows, pattern.cols, set(pattern.blocks))
    both = none = diag = orth = 0
    for r, c in inner:
        starts_across = across.get((r, c + 1), 0) >= 2
        starts_down = down.get((r + 1, c), 0) >= 2
        both += starts_across and starts_down
        none += not starts_across and not starts_down
        diag += any((r + dr, c + dc) in inner_set for dr in (-1, 1) for dc in (-1, 1))
        orth += any(nb in inner_set for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)))
    ninner = len(inner)
    interior = (pattern.rows - 1) * (pattern.cols - 1)

    def pct(part: int, whole: int) -> float:
        return 100.0 * part / whole if whole else 0.0

    return {
        "size": f"{pattern.rows}x{pattern.cols}",
        "blocks%": 100.0 * pattern.block_share(),
        "inner%": pct(ninner, interior),
        "words": nwords,
        "mean_len": sum(lengths) / nwords if nwords else 0.0,
        "longest": max(lengths, default=0),
        "2-3cell%": pct(sum(1 for n in lengths if n <= 3), nwords),
        "2cell%": pct(sum(1 for n in lengths if n == 2), nwords),
        "long>8": sum(1 for s in slots if len(s.cells) > 8 and not set(s.cells) <= taj),
        "both%": pct(both, ninner),
        "none%": pct(none, ninner),
        "diag%": pct(diag, ninner),
        "orth%": pct(orth, ninner),
    }
