"""Mode B (web): a freeform word-web crossword, words crossing each other.

Greedy construction with random restarts: the longest word goes through the
centre, then every other word takes the legal position with the most crossings.
The best of several attempts wins. The tajenka is spread over numbered cells
of the finished web; words that did not fit go to ``Puzzle.dropped``.
"""
from __future__ import annotations

import random
from collections import Counter

from . import alphabet, grid
from .model import ACROSS, DOWN, Entry, Placement, Puzzle

Coord = tuple[int, int]
_STEP = {ACROSS: (0, 1), DOWN: (1, 0)}
_PERP = {ACROSS: (1, 0), DOWN: (0, 1)}
_PASSES = 2


class PlacementError(ValueError):
    """The words cannot form a web that holds the tajenka."""


class _Web:
    """One partially built grid. ``by_key`` finds crossing cells without
    scanning the whole grid."""

    def __init__(self, rows: int, cols: int) -> None:
        self.rows, self.cols = rows, cols
        self.cells: dict[Coord, str] = {}
        self.dirs: dict[Coord, set[str]] = {}
        self.by_key: dict[str, list[Coord]] = {}
        self.placements: list[tuple[int, Placement]] = []
        self.lengths: list[int] = []  # lengths[n] belongs to placements[n]

    def fits(self, keys: tuple[str, ...], r: int, c: int, direction: str) -> int:
        """Number of crossings if the word can stand here, else -1."""
        dr, dc = _STEP[direction]
        pr, pc = _PERP[direction]
        n = len(keys)
        end_r, end_c = r + dr * n, c + dc * n  # first cell after the word
        if not (0 <= r < self.rows and 0 <= c < self.cols
                and 0 <= end_r - dr < self.rows and 0 <= end_c - dc < self.cols):
            return -1
        # a word must not touch another one head to tail (PES + EK -> PESEK)
        if (r - dr, c - dc) in self.cells or (end_r, end_c) in self.cells:
            return -1
        crossings = 0
        for i, key in enumerate(keys):
            cell = (r + dr * i, c + dc * i)
            have = self.cells.get(cell)
            if have is None:
                # an empty cell next to a filled one would form an unintended run
                if (cell[0] + pr, cell[1] + pc) in self.cells or (cell[0] - pr, cell[1] - pc) in self.cells:
                    return -1
            elif have != key or direction in self.dirs[cell]:
                # only a perpendicular entry may be crossed; a same-direction
                # entry here would be extended or overlapped
                return -1
            else:
                crossings += 1
        return crossings if crossings else -1

    def put(self, index: int, keys: tuple[str, ...], r: int, c: int, direction: str) -> None:
        dr, dc = _STEP[direction]
        for i, key in enumerate(keys):
            cell = (r + dr * i, c + dc * i)
            if cell not in self.cells:
                self.cells[cell] = key
                self.by_key.setdefault(key, []).append(cell)
            self.dirs.setdefault(cell, set()).add(direction)
        self.placements.append((index, Placement(r, c, direction)))
        self.lengths.append(len(keys))

    def best_position(self, keys: tuple[str, ...], rng: random.Random) -> tuple[int, int, str] | None:
        """The legal position with the most crossings; ties are broken by rng."""
        best: list[tuple[int, int, str]] = []
        best_score = 0
        seen: set[tuple[int, int, str]] = set()
        for i, key in enumerate(keys):
            for cr, cc in self.by_key.get(key, ()):
                for direction, (dr, dc) in _STEP.items():
                    pos = (cr - dr * i, cc - dc * i, direction)
                    if pos in seen:
                        continue
                    seen.add(pos)
                    score = self.fits(keys, *pos)
                    if score > best_score:
                        best, best_score = [pos], score
                    elif score == best_score and score > 0:
                        best.append(pos)
        return rng.choice(best) if best else None

    def crossings(self) -> int:
        return sum(1 for d in self.dirs.values() if len(d) > 1)

    def area(self) -> int:
        rs = [r for r, _ in self.cells]
        cs = [c for _, c in self.cells]
        return (max(rs) - min(rs) + 1) * (max(cs) - min(cs) + 1)


def _attempt(keys: dict[int, tuple[str, ...]], cands: list[int], rows: int, cols: int,
             rng: random.Random) -> _Web:
    web = _Web(rows, cols)
    order = sorted(cands, key=lambda i: -len(keys[i]) + rng.uniform(0, 3))
    first = order[0]
    n = len(keys[first])
    direction = ACROSS if rng.random() < 0.5 else DOWN
    if (direction == ACROSS and n > cols) or (direction == DOWN and n > rows):
        direction = DOWN if direction == ACROSS else ACROSS
    if direction == ACROSS:
        web.put(first, keys[first], (rows - 1) // 2, (cols - n) // 2, ACROSS)
    else:
        web.put(first, keys[first], (rows - n) // 2, (cols - 1) // 2, DOWN)
    pending = order[1:]
    for _ in range(_PASSES):
        rest = []
        for i in pending:
            pos = web.best_position(keys[i], rng)
            if pos is None:
                rest.append(i)
            else:
                web.put(i, keys[i], *pos)
        pending = rest
    return web


def _missing(tajenka_keys: list[str], have: Counter) -> list[str]:
    """Tajenka keys the cells cannot supply, once each, in tajenka order."""
    need = Counter(tajenka_keys)
    out: list[str] = []
    for key in tajenka_keys:
        if need[key] > have[key] and key not in out:
            out.append(key)
    return out


def _tajenka_cells(web: _Web, tajenka_keys: list[str], rng: random.Random) -> list[Coord]:
    """One distinct cell per tajenka letter. Cells with the same key are
    interchangeable, so a count check is enough for coverage; here we only
    choose, preferring words that carry no tajenka letter yet so the phrase is
    not readable from a single word."""
    owners: dict[Coord, list[int]] = {}
    for n, (_, pl) in enumerate(web.placements):
        for cell in pl.coords(web.lengths[n]):
            owners.setdefault(cell, []).append(n)
    has_letter: set[int] = set()
    free = {key: list(cells) for key, cells in web.by_key.items()}
    chosen: list[Coord] = []
    for key in tajenka_keys:
        options = free[key]
        fresh = [cell for cell in options if any(n not in has_letter for n in owners[cell])]
        cell = rng.choice(fresh or options)
        options.remove(cell)
        has_letter.update(owners[cell])
        chosen.append(cell)
    return chosen


def place(entries: list[Entry], tajenka: str, *, rows: int = 11, cols: int = 11,
          match: str = "strict", ch_one_cell: bool = True,
          rng: random.Random | None = None, tries: int = 20) -> Puzzle:
    if match not in alphabet.MATCH_MODES:
        raise PlacementError(f"unknown match mode {match!r}; use one of {alphabet.MATCH_MODES}")
    for name, size in (("rows", rows), ("cols", cols)):
        if size < alphabet.MIN_LEN:
            raise PlacementError(f"{name} {size} is too small (min {alphabet.MIN_LEN})")
    if tries < 1:
        raise PlacementError(f"tries must be at least 1, got {tries}")
    if not entries:
        raise PlacementError("no words to place")
    rng = rng or random.Random(0)

    phrase = alphabet.tokenize_phrase(tajenka, ch_one_cell=ch_one_cell)
    tajenka_keys = [alphabet.cell_key(c, match) for c in alphabet.flatten(phrase)]

    # Candidates: length rules, one entry per key (first wins) and never a word
    # of the tajenka itself (it would give the secret away).
    seen: set[tuple[str, ...]] = {alphabet.word_key(w, match) for w in phrase}
    cands: list[int] = []
    longest = max(rows, cols)
    for i, e in enumerate(entries):
        k = e.keys(match)
        if alphabet.MIN_LEN <= len(e) <= min(alphabet.MAX_LEN, longest) and k not in seen:
            seen.add(k)
            cands.append(i)
    cand_set = set(cands)
    unused = [e.answer for i, e in enumerate(entries) if i not in cand_set]

    missing = _missing(tajenka_keys, Counter(k for i in cands for k in entries[i].keys(match)))
    if missing:
        raise PlacementError("no usable word for tajenka letters: " + ", ".join(missing))
    if len(cands) < 2:
        raise PlacementError("fewer than 2 usable words; a web needs at least 2 crossing words")

    keys = {i: entries[i].keys(match) for i in cands}
    best: _Web | None = None
    best_score: tuple | None = None
    for _ in range(tries):
        web = _attempt(keys, cands, rows, cols, rng)
        covered = not _missing(tajenka_keys, Counter(web.cells.values()))
        score = (covered, len(web.placements), web.crossings(), -web.area())
        if best_score is None or score > best_score:
            best, best_score = web, score
    assert best is not None

    if len(best.placements) < 2:
        raise PlacementError("fewer than 2 words could be placed; the words share no letters "
                             "in a usable way, add more words or a bigger --size")
    lost = _missing(tajenka_keys, Counter(best.cells.values()))
    if lost:
        raise PlacementError("tajenka letters not placed in the grid: " + ", ".join(lost)
                             + "; add words with these letters or a bigger --size")

    placed_idx = [i for i, _ in best.placements]
    placed = set(placed_idx)
    puzzle = Puzzle(
        mode="web", width=cols, height=rows, match=match, ch_one_cell=ch_one_cell,
        entries=[entries[i] for i in placed_idx], placements=[pl for _, pl in best.placements],
        tajenka=tajenka, tajenka_cells=_tajenka_cells(best, tajenka_keys, rng),
        dropped=[entries[i].answer for i in cands if i not in placed],
        meta={"unused": unused, "crossings": best.crossings(), "tries": tries},
    )
    puzzle = grid.trim(puzzle)
    grid.number_entries(puzzle)
    return puzzle
