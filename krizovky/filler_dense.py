"""Mode C (swedish): fill a clue-cell pattern densely with dictionary words (CSP search).

``Lexicon`` indexes the word list as one bitset per (position, cell key) and length, so
"which words of length 5 have T in cell 3 and A in cell 1, and are not used yet" is a
couple of integer ANDs. ``fill`` runs one attempt: tajenka runs are written into the grid first,
then the slot with the fewest candidates is filled next (MRV), values are checked against the
crossing slots (forward checking) and tried best-first, depth-first with a node limit.
``repair_fill`` repeats that on one pattern and, when an attempt dies, turns a cell of the
slot that ran out of candidates most often into a clue cell (slice 4d: what a setter does
instead of giving up), until the inner block share reaches ``repair_cap``; after each repair it first
can retry with the words of the dead attempt's deepest point held in the slots the repair left intact
(slice 4f, ``keep``; off by default, it did not help). ``solve`` runs it with fresh randomness and
fresh patterns until the timeout. Every word is used once
(directive §16); the result is a ``Puzzle`` in mode ``swedish`` that ``validate.validate``
must accept.
"""
from __future__ import annotations

import random
import time
import warnings
from collections import Counter
from dataclasses import dataclass, field

from . import alphabet, wordlist
from .model import Entry, Placement, Puzzle
from .pattern_swedish import Coord, NoFeasiblePattern, Pattern, PatternError, block_options, generate, inner_from_block_share

_REGISTER_FLAGS = ("zast.", "kniž.", "básn.", "nář.", "hovor.")
_DENSE = 0.05   # below this share of candidates, sampling by rejection is replaced by enumeration
# Shape ``solve`` asks the generator for when the caller gives no knob: the magazine shape of
# slice 4d (inner_share 0.13, max_len 11, stump 0.1; the slice-4 shape was block_share 0.22,
# max_len 8, stump 1.0). The repair cap depends on the lexicon (4d bench, 20 runs/size, 60 s):
# with names (``Lexicon(names=True)``) cap 0.17 fills 17/20 and 19/20 at inner 16-17 %, mean word
# 4.3-4.4; without names 0.17 fills only 16/20 and 11/20, so 0.20 (20/20, inner 18-19 %).
_SHAPE_DEFAULTS: dict = {"block_share": None, "inner_share": 0.13, "max_len": 11, "stump": 0.1}
_REPAIR_CAP = {"names": 0.17, "no_names": 0.20}


class FillError(ValueError):
    """The tajenka does not match the pattern, or the arguments are unusable."""


def weight(w: wordlist.Word, *, names: bool) -> float:
    """How welcome a dictionary row is as a grid answer; 0 = never used.

    Lemma 1.0 > form row (plural / variant / comparative) 0.5 > ``tvar`` 0.25; doubled when
    the word is in the frequency list; x0.6 for dated / bookish / dialect / colloquial
    words, x0.8 for abbreviations; names (``vl.``) are excluded unless ``names``, then x0.3.
    """
    if "vl." in w.flags and not names:
        return 0.0
    value = 0.25 if "tvar" in w.flags else (0.5 if w.form else 1.0)
    if w.freq > 0:
        value *= 2.0
    if any(f in w.flags for f in _REGISTER_FLAGS):
        value *= 0.6
    if "zkr." in w.flags:
        value *= 0.8
    if "vl." in w.flags:
        value *= 0.3
    return value


def _mask(indices: list[int], size: int) -> int:
    buf = bytearray((size + 7) // 8)
    for i in indices:
        buf[i >> 3] |= 1 << (i & 7)
    return int.from_bytes(buf, "little")


class Lexicon:
    """Per length: words (one per match key, the heaviest row wins), weights and bit masks."""

    def __init__(self, index: wordlist.Index, *, match: str = "strict", names: bool = False):
        if match not in alphabet.MATCH_MODES:
            raise ValueError(f"unknown match mode {match!r}; use one of {alphabet.MATCH_MODES}")
        self.match = match
        self.names = names
        best: dict[tuple[str, ...], tuple[float, wordlist.Word]] = {}
        for word in index.words:
            wt = weight(word, names=names)
            if wt <= 0:
                continue
            key = word.keys(match)
            have = best.get(key)
            if have is None or wt > have[0]:
                best[key] = (wt, word)
        self.words: dict[int, list[wordlist.Word]] = {}
        self.weight: dict[int, list[float]] = {}
        self.keys: dict[int, list[tuple[str, ...]]] = {}
        for key, (wt, word) in best.items():
            n = len(key)
            self.words.setdefault(n, []).append(word)
            self.weight.setdefault(n, []).append(wt)
            self.keys.setdefault(n, []).append(key)
        self.masks: dict[int, dict[tuple[int, str], int]] = {}
        self.full: dict[int, int] = {}
        for n, keys in self.keys.items():
            positions: dict[tuple[int, str], list[int]] = {}
            for i, key in enumerate(keys):
                for pos, cell in enumerate(key):
                    positions.setdefault((pos, cell), []).append(i)
            self.masks[n] = {pk: _mask(ix, len(keys)) for pk, ix in positions.items()}
            self.full[n] = (1 << len(keys)) - 1

    def size(self, length: int) -> int:
        return len(self.words.get(length, ()))

    def candidates(self, length: int, fixed: dict[int, str], used: int) -> int:
        """Bitset of the words of ``length`` cells with the given cells (position -> cell or key)
        that are not in ``used``."""
        result = self.full.get(length, 0)
        masks = self.masks.get(length, {})
        for pos, cell in fixed.items():
            if not result:
                return 0
            result &= masks.get((pos, alphabet.cell_key(cell, self.match)), 0)
        return result & ~used

    def stats(self) -> dict:
        return {
            "total": sum(len(ws) for ws in self.words.values()),
            "by_len": {n: len(ws) for n, ws in sorted(self.words.items())},
            "weight": {n: round(sum(wt), 1) for n, wt in sorted(self.weight.items())},
            "base": {n: sum(1 for w in ws if w.is_base) for n, ws in sorted(self.words.items())},
        }


def default_repair_cap(lexicon: Lexicon) -> float:
    """The repair cap ``solve`` uses when the caller gives none: 0.17 with names, 0.20 without."""
    return _REPAIR_CAP["names"] if lexicon.names else _REPAIR_CAP["no_names"]


@dataclass
class Stats:
    """Effort counters; ``fill`` and ``solve`` add to the object they are given."""
    nodes: int = 0                  # slots chosen for filling (search nodes)
    restarts: int = 0               # fill attempts after the first
    patterns: int = 0               # patterns generated
    seconds: float = 0.0
    dead_ends: Counter = field(default_factory=Counter)   # slot length -> candidate lists that ran empty
    starved: Counter = field(default_factory=Counter)     # length of the slot a rejected candidate pattern starved
    stopped: str = ""               # "", "root", "nodes" or "time": why the last attempt gave up
    repairs: int = 0                # clue cells added by ``repair_fill`` after a dead attempt
    repair_cells: int = 0           # blocks those repairs added (closure included)
    repairs_rejected: int = 0       # repairs dropped by the ``is_valid`` guard (expected 0)
    kept_attempts: int = 0          # attempts after a repair that held the dead attempt's deepest words (4f)
    kept_successes: int = 0         # those of them that filled the grid
    kept_words: int = 0             # words held by those attempts
    kept_dropped: int = 0           # seed words that no longer fit their slot (expected 0)
    kept_root: int = 0              # kept attempts whose held words left an open slot without candidates


@dataclass
class FillResult:
    puzzle: Puzzle
    nodes: int
    restarts: int
    seconds: float
    pattern: Pattern                # the pattern that was filled: after its repairs, if any
    repairs: int = 0


class _Stop(Exception):
    pass


def tajenka_runs(text: str | None) -> list[list[str]]:
    """Cells of every run of a tajenka text ("A B / C": runs separated by "/", spaces inside a run
    removed); the cell order is the one ``validate`` expects."""
    if not text or not text.strip():
        return []
    runs: list[list[str]] = []
    for piece in text.split("/"):
        if not piece.strip():
            continue
        try:
            runs.append(alphabet.flatten(alphabet.tokenize_phrase(piece)))
        except alphabet.AlphabetError as exc:
            raise FillError(f"tajenka {text!r}: {exc}") from exc
    return runs


class _Search:
    def __init__(self, pattern: Pattern, lex: Lexicon, runs: list[list[str]], rng: random.Random, *,
                 node_limit: int, max_branch: int, sample: int,
                 deadline: float | None = None, stats: Stats | None = None,
                 seed: dict[tuple[Coord, ...], int] | None = None):
        self.lex, self.rng = lex, rng
        self.stats = stats = stats if stats is not None else Stats()
        self.max_branch, self.sample, self.deadline = max_branch, sample, deadline
        self.node_cap = stats.nodes + node_limit   # the limit is per attempt, the counter may be shared
        self.slots = [s for s in pattern.slots() if s.tajenka is None]
        self.length = [len(s.cells) for s in self.slots]
        self.cell_slots: dict[Coord, list[tuple[int, int]]] = {}
        for t, s in enumerate(self.slots):
            for pos, cell in enumerate(s.cells):
                self.cell_slots.setdefault(cell, []).append((t, pos))
        self.letters: dict[Coord, str] = {}
        self.dead_by_slot: Counter = Counter()   # slot index -> how often its candidate set ran empty
        self.dead_by_cell: Counter = Counter()   # cell -> how often its letter emptied the crossing slot
        self.used = [0] * (alphabet.MAX_LEN + 2)
        for run, cells in zip(runs, pattern.tajenka_runs):
            keys = [alphabet.cell_key(c, lex.match) for c in run]
            for cell, key in zip(cells, keys):
                self.letters[cell] = key
            if len(keys) < len(self.used):   # the run is an entry: no other slot may repeat its key
                self.used[len(keys)] |= lex.candidates(len(keys), dict(enumerate(keys)), 0)
        self.base: list[int] = []
        for t, s in enumerate(self.slots):
            m = lex.full.get(self.length[t], 0)
            masks = lex.masks.get(self.length[t], {})
            for pos, cell in enumerate(s.cells):
                if cell in self.letters:
                    m &= masks.get((pos, self.letters[cell]), 0)
            self.base.append(m)
        self.word: list[int | None] = [None] * len(self.slots)
        # Deepest point of this search (slice 4f): the assignment with the most words placed, kept
        # when the search unwinds or stops, so a repair can start from it instead of from nothing.
        self.depth = 0
        self.best_depth = 0
        self.best_word: list[int | None] | None = None
        # ``seed``: slot cells -> word index to hold fixed (like tajenka letters) before the search;
        # a seed word that is no longer a candidate of its slot is skipped, not an error.
        self.kept = 0
        if seed and self.starved_slot() is None:   # a root-starved pattern dies anyway; seeding it could
            for t, s in enumerate(self.slots):      # cross a slot length the lexicon has no words for
                idx = seed.get(tuple(s.cells))
                if idx is None:
                    continue
                if (self.base[t] & ~self.used[self.length[t]]) >> idx & 1:
                    self.assign(t, idx)
                    self.kept += 1
                else:
                    stats.kept_dropped += 1

    def starved_slot(self) -> int | None:
        """Index of an open slot that has no candidate before the search starts, else None."""
        for t in range(len(self.slots)):
            if self.word[t] is None and not self.base[t] & ~self.used[self.length[t]]:
                return t
        return None

    def starved(self) -> int | None:
        """Length of a slot that has no candidate before any word is placed, else None."""
        t = self.starved_slot()
        return None if t is None else self.length[t]

    # -- one node --------------------------------------------------------------------
    def solve(self) -> bool:
        rng = self.rng
        chosen = -1
        best_key = None
        for t in range(len(self.slots)):
            if self.word[t] is not None:
                continue
            n = self.length[t]
            count = (self.base[t] & ~self.used[n]).bit_count()
            key = (count, -n, rng.random())
            if best_key is None or key < best_key:
                chosen, best_key = t, key
        if chosen < 0:
            return True
        self.stats.nodes += 1
        if self.stats.nodes > self.node_cap:
            self.stats.stopped = "nodes"
            raise _Stop
        if self.deadline is not None and time.monotonic() > self.deadline:
            self.stats.stopped = "time"
            raise _Stop
        count = best_key[0]
        if count == 0:
            self.stats.dead_ends[self.length[chosen]] += 1
            self.dead_by_slot[chosen] += 1
            return False
        for idx in self.values(chosen, count):
            changed, new_cells = self.assign(chosen, idx)
            if self.solve():
                return True
            self.undo(chosen, idx, changed, new_cells)
        return False

    def values(self, t: int, count: int) -> list[int]:
        """Up to ``max_branch`` words for slot ``t``: a random sample of the candidates, those that
        leave a crossing slot without candidates dropped, the rest ordered by how many words the
        tightest crossing slot keeps (then by weight)."""
        lex, rng, used = self.lex, self.rng, self.used
        n = self.length[t]
        mask = self.base[t] & ~used[n]
        size = lex.size(n)
        if count <= self.sample:
            picks = _bits(mask)
            rng.shuffle(picks)
        elif count >= _DENSE * size:
            raw = mask.to_bytes((size + 7) // 8, "little")
            chosen: set[int] = set()
            for _ in range(self.sample * 60):
                i = rng.randrange(size)
                if raw[i >> 3] >> (i & 7) & 1:
                    chosen.add(i)
                    if len(chosen) == self.sample:
                        break
            picks = sorted(chosen) if len(chosen) == self.sample else rng.sample(_bits(mask), self.sample)
            rng.shuffle(picks)
        else:
            picks = rng.sample(_bits(mask), self.sample)
        slot = self.slots[t]
        free = [(i, cell, [(u, pos) for u, pos in self.cell_slots[cell] if u != t])
                for i, cell in enumerate(slot.cells) if cell not in self.letters]
        keys_of = lex.keys[n]
        weights = lex.weight[n]
        scored: list[tuple[int, float, int]] = []
        for idx in picks:
            keys = keys_of[idx]
            tightest = 1 << 30
            for i, _, crossing in free:
                for u, pos in crossing:
                    m = self.base[u] & lex.masks[self.length[u]].get((pos, keys[i]), 0)
                    taken = used[self.length[u]]
                    if self.length[u] == n:
                        taken |= 1 << idx
                    left = (m & ~taken).bit_count()
                    if left == 0:
                        self.stats.dead_ends[self.length[u]] += 1
                        self.dead_by_slot[u] += 1
                        self.dead_by_cell[slot.cells[i]] += 1
                        tightest = 0
                        break
                    if left < tightest:
                        tightest = left
                if tightest == 0:
                    break
            if tightest:
                scored.append((tightest, weights[idx], idx))
        scored.sort(reverse=True)
        return [idx for _, _, idx in scored[:self.max_branch]]

    def assign(self, t: int, idx: int) -> tuple[list[tuple[int, int]], list[Coord]]:
        lex = self.lex
        n = self.length[t]
        keys = lex.keys[n][idx]
        changed: list[tuple[int, int]] = []
        new_cells: list[Coord] = []
        for i, cell in enumerate(self.slots[t].cells):
            if cell in self.letters:
                continue
            self.letters[cell] = keys[i]
            new_cells.append(cell)
            for u, pos in self.cell_slots[cell]:
                if u != t:
                    changed.append((u, self.base[u]))
                    self.base[u] &= lex.masks[self.length[u]].get((pos, keys[i]), 0)
        self.word[t] = idx
        self.used[n] |= 1 << idx
        self.depth += 1
        if self.depth > self.best_depth:   # a new deepest point: remember the whole assignment
            self.best_depth = self.depth
            self.best_word = self.word[:]
        return changed, new_cells

    def undo(self, t: int, idx: int, changed: list[tuple[int, int]], new_cells: list[Coord]) -> None:
        for u, old in reversed(changed):
            self.base[u] = old
        for cell in new_cells:
            del self.letters[cell]
        self.word[t] = None
        self.used[self.length[t]] &= ~(1 << idx)
        self.depth -= 1


def _bits(mask: int) -> list[int]:
    out: list[int] = []
    while mask:
        low = mask & -mask
        out.append(low.bit_length() - 1)
        mask ^= low
    return out


def _check_args(pattern: Pattern, tajenka: str | None) -> list[list[str]]:
    runs = tajenka_runs(tajenka)
    if [len(r) for r in runs] != [len(r) for r in pattern.tajenka_runs]:
        raise FillError(f"tajenka {tajenka!r} has runs of {[len(r) for r in runs]} cells but the pattern "
                        f"holds runs of {[len(r) for r in pattern.tajenka_runs]}")
    problems = pattern.is_valid()
    if problems:
        raise FillError("invalid pattern: " + "; ".join(problems[:3]))
    return runs


def _one_attempt(pattern: Pattern, lexicon: Lexicon, tajenka: str | None, runs: list[list[str]],
                 rng: random.Random, *, node_limit: int, max_branch: int, sample: int,
                 deadline: float | None, stats: Stats,
                 seed: dict[tuple[Coord, ...], int] | None = None) -> tuple[Puzzle | None, _Search]:
    """One search on the pattern (``seed``: words held fixed, slice 4f); the search object is
    returned for its dead-end counters and its deepest assignment."""
    search = _Search(pattern, lexicon, runs, rng, node_limit=node_limit, max_branch=max_branch,
                     sample=sample, deadline=deadline, stats=stats, seed=seed)
    stats.stopped = ""
    start_nodes = stats.nodes
    starved = search.starved()
    if starved is not None:   # the tajenka letters alone starve a slot: nothing to search
        stats.dead_ends[starved] += 1
        stats.stopped = "root"
        return None, search
    try:
        if not search.solve():
            return None, search
    except _Stop:
        return None, search
    return _build(pattern, lexicon, tajenka, runs, search, stats.nodes - start_nodes), search


def fill(pattern: Pattern, lexicon: Lexicon, tajenka: str | None, *, rng: random.Random,
         node_limit: int = 5000, max_branch: int = 8, sample: int = 40,
         deadline: float | None = None, stats: Stats | None = None) -> Puzzle | None:
    """One fill attempt; ``None`` on a dead end, the node limit or the ``deadline`` (time.monotonic())."""
    runs = _check_args(pattern, tajenka)
    stats = stats if stats is not None else Stats()
    puzzle, _ = _one_attempt(pattern, lexicon, tajenka, runs, rng, node_limit=node_limit,
                             max_branch=max_branch, sample=sample, deadline=deadline, stats=stats)
    return puzzle


def _repair(pattern: Pattern, search: _Search, rng: random.Random, cap: float, stump: float,
            stats: Stats) -> tuple[Pattern, list[Coord]] | None:
    """A clue cell for the slot that ran out of candidates most often (at the root: the starved
    slot): the cell where the across and the down constraints collided most often (its letter
    emptied the crossing slot), then the cell whose crossing slot ran out most often, then the
    most even split with the least collateral blocks, then the rng. None when no slot has a legal
    option (cap, tajenka, connectivity)."""
    dead = search.dead_by_slot
    dead_cell = search.dead_by_cell
    if dead:
        order = sorted(dead, key=lambda t: (-dead[t], -search.length[t], rng.random()))
    else:
        t = search.starved_slot()
        order = [] if t is None else [t]
    protected = {cell for run in pattern.tajenka_runs for cell in run}
    for t in order:
        options = block_options(pattern, search.slots[t].cells, cap=cap, protected=protected, stump=stump)
        if not options:
            continue
        scored = []
        for cell, added, weight in options:
            crossing = max((dead.get(u, 0) for u, _ in search.cell_slots[cell] if u != t), default=0)
            scored.append(((dead_cell.get(cell, 0), crossing, weight, rng.random()), cell, added))
        scored.sort(reverse=True)
        for _, cell, added in scored:
            new = Pattern(pattern.rows, pattern.cols, set(pattern.blocks) | set(added), pattern.tajenka_runs)
            if new.is_valid():   # the closure keeps validity by construction; this is the guard
                stats.repairs_rejected += 1
                continue
            return new, added
    return None


def _seed_from(search: _Search, pattern: Pattern) -> dict[tuple[Coord, ...], int]:
    """The words of the search's deepest assignment whose slot still exists in ``pattern`` (slots
    split by the repair have new cell tuples and drop out by themselves)."""
    if search.best_word is None:
        return {}
    alive = {tuple(s.cells) for s in pattern.slots() if s.tajenka is None}
    return {tuple(search.slots[t].cells): idx for t, idx in enumerate(search.best_word)
            if idx is not None and tuple(search.slots[t].cells) in alive}


def repair_fill(pattern: Pattern, lexicon: Lexicon, tajenka: str | None, *, rng: random.Random,
                node_limit: int = 5000, max_branch: int = 8, sample: int = 40,
                deadline: float | None = None, stats: Stats | None = None,
                repair: bool = True, repair_cap: float | None = None, patterns_per_fill: int = 3,
                stump: float = 0.1, keep: bool = False, keep_min: float = 0.5) -> tuple[Puzzle | None, Pattern]:
    """Fill attempts on one pattern with repairs: after a dead attempt (dead end, node limit or a
    slot starved at the root) a clue cell is added to the failing slot (``_repair``) and the
    search restarts on the repaired pattern, while the inner block share stays <= ``repair_cap``;
    when no repair is possible, up to ``patterns_per_fill`` plain attempts follow (today's restart
    loop). With ``keep`` (slice 4f) the first attempt after a repair holds the words of the dead
    attempt's deepest point in the slots the repair left intact, when that point had at least
    ``keep_min`` of the slots placed; a kept attempt that dies is followed by the fresh attempt, which
    alone decides the next repair. Off by default: the 4f bench (20 runs/size, 60 s) filled 2 of 40
    grids by a kept attempt and left the mean word at 4.3-4.4, because the deepest point is the state
    right before a dead end and one block rarely frees it (``WORKLOG.md`` 2026-10-21).
    Returns the puzzle (or None) and the pattern that was last tried."""
    runs = _check_args(pattern, tajenka)
    if not 0.0 <= keep_min <= 1.0:
        raise FillError(f"keep_min must be between 0 and 1, got {keep_min!r}")
    stats = stats if stats is not None else Stats()
    if repair_cap is None:
        repair_cap = default_repair_cap(lexicon)
    plain = 0
    while deadline is None or time.monotonic() < deadline:
        puzzle, search = _one_attempt(pattern, lexicon, tajenka, runs, random.Random(rng.getrandbits(64)),
                                      node_limit=node_limit, max_branch=max_branch, sample=sample,
                                      deadline=deadline, stats=stats)
        if puzzle is not None:
            return puzzle, pattern
        if stats.stopped == "time":
            return None, pattern
        repaired = _repair(pattern, search, rng, repair_cap, stump, stats) if repair else None
        if repaired is None:
            if stats.stopped == "root":
                return None, pattern   # starved and not repairable: this pattern is dead
            plain += 1
            if plain >= patterns_per_fill:
                return None, pattern
            stats.restarts += 1
            continue
        pattern, added = repaired
        stats.repairs += 1
        stats.repair_cells += len(added)
        stats.restarts += 1
        if keep and search.best_depth >= keep_min * len(search.slots):
            seed = _seed_from(search, pattern)
            if seed:
                stats.kept_attempts += 1
                puzzle, kept = _one_attempt(pattern, lexicon, tajenka, runs, random.Random(rng.getrandbits(64)),
                                            node_limit=node_limit, max_branch=max_branch, sample=sample,
                                            deadline=deadline, stats=stats, seed=seed)
                stats.kept_words += kept.kept
                if stats.stopped == "root":
                    stats.kept_root += 1
                if puzzle is not None:
                    stats.kept_successes += 1
                    return puzzle, pattern
                if stats.stopped == "time":
                    return None, pattern
                stats.restarts += 1   # the fresh attempt that follows a dead kept attempt is a restart too
    return None, pattern


def _build(pattern: Pattern, lex: Lexicon, tajenka: str | None, runs: list[list[str]],
           search: _Search, nodes: int) -> Puzzle:
    entries: list[Entry] = []
    placements: list[Placement] = []
    dictionary: dict[str, dict] = {}
    by_cells = {tuple(s.cells): t for t, s in enumerate(search.slots)}
    for slot in pattern.slots():
        if slot.tajenka is not None:
            cells = runs[slot.tajenka]
            entries.append(Entry(answer="".join(cells), cells=list(cells)))
        else:
            t = by_cells[tuple(slot.cells)]
            word = lex.words[search.length[t]][search.word[t]]
            entry = Entry.from_word(word.word, pos=word.pos)
            entries.append(entry)
            dictionary[entry.answer] = {"gloss": word.gloss, "form": word.form,
                                        "flags": list(word.flags), "freq": word.freq}
        placements.append(Placement(slot.cells[0][0], slot.cells[0][1], slot.direction))
    return Puzzle(
        mode="swedish", width=pattern.cols, height=pattern.rows, match=lex.match,
        entries=entries, placements=placements,
        tajenka=tajenka if runs else None,
        tajenka_cells=[cell for run in pattern.tajenka_runs for cell in run],
        blocks=sorted(pattern.blocks),
        meta={"nodes": nodes, "block_share": round(pattern.block_share(), 4),
              "inner_share": round(pattern.inner_share(), 4), "repairs": search.stats.repairs,
              "kept": search.kept, "dictionary": dictionary},
    )


def solve(rows: int, cols: int, tajenka: str, lexicon: Lexicon, *, rng: random.Random,
          timeout: float = 60.0, pattern_tries: int = 50, node_limit: int = 20000,
          block_share: float | None = None, max_len: int | None = None, max_branch: int = 8, sample: int = 40,
          patterns_per_fill: int = 3, stats: Stats | None = None,
          inner_share: float | None = None, soft_len: int = 8, long_slots: int = 2, stump: float | None = None,
          repair: bool = True, repair_cap: float | None = None,
          keep: bool = False, keep_min: float = 0.5) -> FillResult | None:
    """Fill a fresh ``rows`` x ``cols`` pattern for ``tajenka``: ``repair_fill`` on it (repairs while
    the inner block share stays <= ``repair_cap``, each followed by an attempt that keeps the placed
    words when ``keep``, then ``patterns_per_fill`` plain attempts), a new pattern, ... until it works
    or ``timeout`` seconds pass.

    Shape knobs (``pattern_swedish.generate``): ``inner_share``, ``max_len``, ``soft_len``,
    ``long_slots``, ``stump``; ``block_share`` is deprecated (converted to the inner share with the
    same block count). A knob left None takes ``_SHAPE_DEFAULTS``; ``repair_cap`` left None takes
    ``default_repair_cap`` (0.17 with names, 0.20 without). ``node_limit`` 20 000 per attempt
    (2026-10-21, ``out/bench4f/r2_nodes20k.txt``: a 5 000-node death on 16x12 was often search luck
    that cost a block; 20 000 gives mean word 4.5 there, 16x12 p90 58 s, so callers allow > 60 s).
    Raises ``PatternError`` for a
    tajenka that cannot be placed at all. ``stats`` receives the effort counters whether or not a
    fill was found."""
    if block_share is not None and inner_share is not None:
        raise PatternError("give inner_share or the deprecated block_share, not both")
    if block_share is not None:
        warnings.warn("block_share is deprecated, use inner_share", DeprecationWarning, stacklevel=2)
        inner_share = inner_from_block_share(rows, cols, block_share) if rows > 1 and cols > 1 else 0.0
    elif inner_share is None:
        default_share = _SHAPE_DEFAULTS["block_share"]
        inner_share = (_SHAPE_DEFAULTS["inner_share"] if default_share is None
                       else inner_from_block_share(rows, cols, default_share) if rows > 1 and cols > 1 else 0.0)
    if max_len is None:
        max_len = _SHAPE_DEFAULTS["max_len"]
    if stump is None:
        stump = _SHAPE_DEFAULTS["stump"]
    if repair_cap is None:
        repair_cap = default_repair_cap(lexicon)
    runs = tajenka_runs(tajenka)
    lengths = [len(r) for r in runs]
    counts = {n: lexicon.size(n) for n in range(alphabet.MIN_LEN, alphabet.MAX_LEN + 1)}
    stats = stats if stats is not None else Stats()

    def feasible(candidate: Pattern) -> bool:   # no slot starved by the tajenka letters alone
        probe = _Search(candidate, lexicon, runs, random.Random(0), node_limit=0, max_branch=0, sample=0)
        starved = probe.starved()
        if starved is not None:
            stats.starved[starved] += 1
        return starved is None

    start = time.monotonic()
    deadline = start + timeout
    try:
        while time.monotonic() < deadline:
            try:
                pattern = generate(rows, cols, lengths, rng=rng, inner_share=inner_share, max_len=max_len,
                                   soft_len=soft_len, long_slots=long_slots, stump=stump,
                                   tries=pattern_tries, counts=counts, accept=feasible)
            except NoFeasiblePattern:
                continue
            if stats.patterns:
                stats.restarts += 1   # the first attempt on a new pattern is a restart too
            stats.patterns += 1
            puzzle, pattern = repair_fill(pattern, lexicon, tajenka, rng=rng, node_limit=node_limit,
                                          max_branch=max_branch, sample=sample, deadline=deadline, stats=stats,
                                          repair=repair, repair_cap=repair_cap,
                                          patterns_per_fill=patterns_per_fill, stump=stump,
                                          keep=keep, keep_min=keep_min)
            if puzzle is not None:
                puzzle.meta["restarts"] = stats.restarts
                puzzle.meta["nodes_total"] = stats.nodes
                return FillResult(puzzle, stats.nodes, stats.restarts, time.monotonic() - start, pattern,
                                  stats.repairs)
        return None
    finally:
        stats.seconds += time.monotonic() - start
