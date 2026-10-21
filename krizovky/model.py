"""Data model: Entry, Placement, Puzzle and their JSON form (puzzle.json)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import alphabet

FORMAT_VERSION = 1
MODES = ("column", "web", "swedish")
ACROSS = "across"
DOWN = "down"
DIRECTIONS = (ACROSS, DOWN)


class ModelError(ValueError):
    """puzzle.json or an in-memory puzzle is malformed."""


@dataclass(eq=True)
class Entry:
    answer: str                 # normalised answer text, e.g. "ŘEŘICHA"
    cells: list[str]            # strict cells, e.g. ["Ř","E","Ř","I","CH","A"]
    clue: str | None = None
    pos: str | None = None      # part of speech, free text ("noun")

    @classmethod
    def from_word(cls, word: str, *, ch_one_cell: bool = True,
                  clue: str | None = None, pos: str | None = None) -> "Entry":
        cells = alphabet.tokenize(word, ch_one_cell=ch_one_cell)
        answer = alphabet.normalize(word.strip()).replace(alphabet.SPLIT_MARK, "")
        return cls(answer=answer, cells=cells, clue=clue, pos=pos)

    def keys(self, match: str = "strict") -> tuple[str, ...]:
        return alphabet.word_key(self.cells, match)

    def __len__(self) -> int:
        return len(self.cells)


@dataclass(eq=True)
class Placement:
    row: int
    col: int
    direction: str              # ACROSS or DOWN
    number: int | None = None   # clue number (mode web), assigned by grid.number_entries

    def coords(self, length: int) -> list[tuple[int, int]]:
        if self.direction == ACROSS:
            return [(self.row, self.col + i) for i in range(length)]
        if self.direction == DOWN:
            return [(self.row + i, self.col) for i in range(length)]
        raise ModelError(f"unknown direction {self.direction!r}")


@dataclass(eq=True)
class Puzzle:
    mode: str
    width: int
    height: int
    match: str = "strict"
    ch_one_cell: bool = True
    entries: list[Entry] = field(default_factory=list)
    placements: list[Placement] = field(default_factory=list)   # placements[i] belongs to entries[i]
    tajenka: str | None = None                                   # original text, e.g. "Den Země"
    tajenka_cells: list[tuple[int, int]] = field(default_factory=list)  # reading order
    blocks: list[tuple[int, int]] = field(default_factory=list)  # black / clue cells (mode swedish)
    dropped: list[str] = field(default_factory=list)             # words that could not be placed
    meta: dict = field(default_factory=dict)                     # theme, seed, generator notes

    # --- derived -----------------------------------------------------------
    def grid(self) -> list[list[str | None]]:
        """Cell keys written in placement order; None = empty. Out-of-bounds
        cells are skipped here and reported by validate."""
        g: list[list[str | None]] = [[None] * self.width for _ in range(self.height)]
        for entry, placement in zip(self.entries, self.placements):
            for (r, c), key in zip(placement.coords(len(entry)), entry.keys(self.match)):
                if 0 <= r < self.height and 0 <= c < self.width:
                    g[r][c] = key
        return g

    def tajenka_words(self) -> list[list[str]]:
        if not self.tajenka:
            return []
        return alphabet.tokenize_phrase(self.tajenka, ch_one_cell=self.ch_one_cell)

    def tajenka_keys(self) -> tuple[str, ...]:
        return alphabet.word_key(alphabet.flatten(self.tajenka_words()), self.match)

    def tajenka_run_cells(self) -> list[list[tuple[int, int]]]:
        """``tajenka_cells`` split into the runs of the "/"-separated tajenka pieces (mode swedish:
        one run per answer box). Any mismatch falls back to one run of all cells."""
        if not self.tajenka or not self.tajenka_cells:
            return []
        cells = [tuple(x) for x in self.tajenka_cells]
        try:
            sizes = [len(alphabet.flatten(alphabet.tokenize_phrase(piece, ch_one_cell=self.ch_one_cell)))
                     for piece in self.tajenka.split("/") if piece.strip()]
        except alphabet.AlphabetError:
            return [cells]
        if len(sizes) < 2 or sum(sizes) != len(cells):
            return [cells]
        runs, start = [], 0
        for n in sizes:
            runs.append(cells[start:start + n])
            start += n
        return runs

    def tajenka_entries(self) -> dict[int, int]:
        """entry index -> tajenka run index, for the entries whose cells are exactly a run."""
        by_cells = {tuple(run): k for k, run in enumerate(self.tajenka_run_cells())}
        out: dict[int, int] = {}
        for i, (entry, pl) in enumerate(zip(self.entries, self.placements)):
            k = by_cells.get(tuple(pl.coords(len(entry))))
            if k is not None:
                out[i] = k
        return out

    # --- persistence -------------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["version"] = FORMAT_VERSION
        d["tajenka_cells"] = [list(x) for x in self.tajenka_cells]
        d["blocks"] = [list(x) for x in self.blocks]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Puzzle":
        if not isinstance(d, dict) or d.get("version") != FORMAT_VERSION:
            raise ModelError(f"puzzle.json version {d.get('version') if isinstance(d, dict) else '?'} "
                             f"not supported (expected {FORMAT_VERSION})")
        try:
            entries = [Entry(**e) for e in d["entries"]]
            placements = [Placement(**p) for p in d["placements"]]
            return cls(
                mode=d["mode"], width=int(d["width"]), height=int(d["height"]),
                match=d.get("match", "strict"), ch_one_cell=bool(d.get("ch_one_cell", True)),
                entries=entries, placements=placements,
                tajenka=d.get("tajenka"),
                tajenka_cells=[tuple(x) for x in d.get("tajenka_cells", [])],
                blocks=[tuple(x) for x in d.get("blocks", [])],
                dropped=list(d.get("dropped", [])), meta=dict(d.get("meta", {})),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelError(f"malformed puzzle.json: {exc}") from exc

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Puzzle":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelError(f"cannot read {path}: {exc}") from exc
        return cls.from_dict(raw)
