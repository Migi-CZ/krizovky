"""Czech word list for the filler: ``data/words.tsv.gz`` and an index by length.

The file is built by ``scripts/build_wordlist.py`` (UTF-8 TSV with a header, gzip or
plain). ``load`` reads it (plus ``extra_words.tsv`` next to it, same columns) and
``Index.find`` answers "which words of length N have letter E in cell 3".
"""
from __future__ import annotations

import gzip
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import alphabet

COLUMNS = ("word", "lemma", "pos", "form", "gloss", "syn", "freq", "flags")
DATA = Path(__file__).resolve().parent.parent / "data" / "words.tsv.gz"
EXTRA_NAME = "extra_words.tsv"
FLAGS = ("zkr.", "vl.", "zast.", "kniž.", "básn.", "hovor.", "nář.", "tvar", "en-wikt", "syn")
BUILD_HINT = ("python3 -I scripts/build_wordlist.py --raw RAW_DIR"
              " --en-wikt RAW_DIR/kaikki.org-dictionary-Czech.jsonl"
              " --syn RAW_DIR/syn2015_lemma_utf8.zip --out data/words.tsv.gz")


class WordlistError(Exception):
    """The word list is missing or malformed, or a query is invalid."""


@dataclass(frozen=True)
class Word:
    word: str
    cells: tuple[str, ...]
    lemma: str
    pos: str
    form: str      # form tags, space separated; "" = base form
    gloss: str
    syn: str       # up to 3 synonyms separated by ";"
    freq: int      # rank in the frequency list (1 = most frequent), 0 = absent
    flags: tuple[str, ...]

    def keys(self, match: str = "strict") -> tuple[str, ...]:
        return alphabet.word_key(list(self.cells), match)

    @property
    def is_base(self) -> bool:
        return self.form == "" and "tvar" not in self.flags

    def __len__(self) -> int:
        return len(self.cells)


# --- patterns -------------------------------------------------------------------
def _pattern_cells(text: str) -> list[str | None]:
    """Cells of a pattern; None = any cell. ``.`` and ``?`` are wildcards, ``CH`` is one cell."""
    src = alphabet.normalize(text.strip())
    if not src:
        raise WordlistError("empty pattern")
    cells: list[str | None] = []
    i = 0
    while i < len(src):
        ch = src[i]
        if ch == alphabet.SPLIT_MARK:
            i += 1
        elif ch in ".?":
            cells.append(None)
            i += 1
        elif ch not in alphabet.LETTERS:
            raise WordlistError(f"pattern {text!r}: character {ch!r} is not a letter, '.' or '?'")
        elif ch == "C" and src[i + 1:i + 2] == "H":
            cells.append("CH")
            i += 2
        else:
            cells.append(ch)
            i += 1
    if not cells:
        raise WordlistError("empty pattern")
    return cells


def parse_pattern(text: str) -> dict[int, str]:
    """``"..CH."`` -> ``{2: "CH"}``: 0-based cell index -> required cell (wildcards left out)."""
    return {i: c for i, c in enumerate(_pattern_cells(text)) if c is not None}


def pattern_length(text: str) -> int:
    """Number of cells of a pattern (``CH`` counts once)."""
    return len(_pattern_cells(text))


# --- index ------------------------------------------------------------------------
class Index:
    """Words in file order, grouped by cell count."""

    def __init__(self, words: list[Word]):
        self.words = words
        self._by_len: dict[int, list[Word]] = {}
        for w in words:
            self._by_len.setdefault(len(w), []).append(w)
        self._keys: dict[tuple[int, str], list[tuple[str, ...]]] = {}

    def __len__(self) -> int:
        return len(self.words)

    def by_len(self, length: int) -> list[Word]:
        return self._by_len.get(length, [])

    def _bucket_keys(self, length: int, match: str) -> list[tuple[str, ...]]:
        cached = self._keys.get((length, match))
        if cached is None:
            cached = self._keys[(length, match)] = [w.keys(match) for w in self.by_len(length)]
        return cached

    def find(self, length: int | None = None, pattern: str | dict[int, str] | None = None, *,
             match: str = "strict", pos: str | None = None) -> list[Word]:
        """Words of ``length`` cells whose cells fit ``pattern`` (``"..E.."`` or ``{2: "E"}``).

        A string pattern fixes the length itself (a different explicit ``length`` is an
        error). Constraint and word cells are compared as match keys (``match``).
        """
        if match not in alphabet.MATCH_MODES:
            raise WordlistError(f"unknown match mode {match!r}; use one of {alphabet.MATCH_MODES}")
        if isinstance(pattern, str):
            plen = pattern_length(pattern)
            if length is not None and length != plen:
                raise WordlistError(f"pattern {pattern!r} has {plen} cells but length {length} was asked")
            length, constraints = plen, parse_pattern(pattern)
        else:
            constraints = {}
            for idx, cell in (pattern or {}).items():
                try:
                    cells = alphabet.tokenize(cell)
                except alphabet.AlphabetError as exc:
                    raise WordlistError(f"pattern cell {cell!r}: {exc}")
                if len(cells) != 1 or not isinstance(idx, int) or idx < 0 or (length is not None and idx >= length):
                    raise WordlistError(f"bad pattern entry {idx!r}: {cell!r} (index inside the length, one cell)")
                constraints[idx] = cells[0]
        wanted = [(i, alphabet.cell_key(c, match)) for i, c in sorted(constraints.items())]
        lengths = [length] if length is not None else sorted(self._by_len)
        found: list[Word] = []
        for n in lengths:
            if wanted and wanted[-1][0] >= n:
                continue
            for w, key in zip(self.by_len(n), self._bucket_keys(n, match)):
                if pos is not None and w.pos != pos:
                    continue
                if all(key[i] == k for i, k in wanted):
                    found.append(w)
        if length is None:   # several buckets: keep the order of loading
            order = {id(w): n for n, w in enumerate(self.words)}
            found.sort(key=lambda w: order[id(w)])
        return found

    def stats(self) -> dict:
        by_pos: dict[str, int] = {}
        for w in self.words:
            by_pos[w.pos] = by_pos.get(w.pos, 0) + 1
        return {
            "total": len(self.words),
            "base": sum(1 for w in self.words if w.is_base),
            "by_len": {n: len(ws) for n, ws in sorted(self._by_len.items())},
            "by_pos": by_pos,
        }


# --- loading ----------------------------------------------------------------------
def _read_file(path: Path, *, min_len: int, max_len: int) -> list[tuple[tuple[str, str, str], Word]]:
    """All rows of one TSV file within the length window, with their (word, lemma, pos) key."""
    rows: list[tuple[tuple[str, str, str], Word]] = []
    try:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8", newline="") as fh:
            header = fh.readline().rstrip("\r\n")
            if tuple(header.split("\t")) != COLUMNS:
                raise WordlistError(
                    f"{path}: bad header {header!r}; expected {chr(9).join(COLUMNS)!r}. Rebuild: {BUILD_HINT}")
            for number, line in enumerate(fh, 2):
                line = line.rstrip("\r\n")
                if not line:
                    continue
                cols = line.split("\t")
                if len(cols) != len(COLUMNS):
                    raise WordlistError(f"{path}:{number}: expected {len(COLUMNS)} columns, got {len(cols)}")
                word, lemma, pos, form, gloss, syn, freq, flags = cols
                try:
                    cells = alphabet.tokenize(word)
                    if "".join(cells) != alphabet.normalize(word):
                        raise alphabet.AlphabetError(f"{word!r}: not a plain word")
                except alphabet.AlphabetError as exc:
                    raise WordlistError(f"{path}:{number}: {exc}")
                try:
                    rank = int(freq)
                except ValueError:
                    raise WordlistError(f"{path}:{number}: freq {freq!r} is not an integer")
                flag_tuple = tuple(f for f in flags.split(",") if f)
                bad = [f for f in flag_tuple if f not in FLAGS]
                if bad:
                    raise WordlistError(f"{path}:{number}: unknown flag {bad[0]!r}; known: {', '.join(FLAGS)}")
                if min_len <= len(cells) <= max_len:
                    rows.append(((word, lemma, pos),
                                 Word(word, tuple(cells), lemma, pos, form, gloss, syn, rank, flag_tuple)))
    except FileNotFoundError:
        raise WordlistError(f"word list not found: {path}; build it with: {BUILD_HINT}")
    except (OSError, EOFError, UnicodeDecodeError) as exc:   # gzip.BadGzipFile is an OSError
        raise WordlistError(f"cannot read {path}: {exc}")
    return rows


def load(path: Path | str = DATA, *, min_len: int = alphabet.MIN_LEN, max_len: int = alphabet.MAX_LEN,
         base_only: bool = False, exclude_flags: Iterable[str] = (), extra: bool = True) -> Index:
    """Read the word list. ``base_only`` drops inflected forms and "tvar" rows;
    ``exclude_flags`` drops rows with any of the flags. ``extra_words.tsv`` next to the
    file is appended (rows whose (word, lemma, pos) is already in the main file are ignored).
    """
    path = Path(path)
    excluded = frozenset(exclude_flags)
    unknown = excluded - set(FLAGS)
    if unknown:
        raise WordlistError(f"unknown flag {sorted(unknown)[0]!r}; known: {', '.join(FLAGS)}")
    if min_len > max_len:
        raise WordlistError(f"min_len {min_len} is greater than max_len {max_len}")

    def keep(w: Word) -> bool:
        return not (base_only and not w.is_base) and not excluded.intersection(w.flags)

    main = _read_file(path, min_len=min_len, max_len=max_len)
    words = [w for _, w in main if keep(w)]
    extra_path = path.parent / EXTRA_NAME
    if extra and extra_path.is_file():
        seen = {key for key, _ in main}   # includes rows filtered out: the main file owns the key
        for key, w in _read_file(extra_path, min_len=min_len, max_len=max_len):
            if key not in seen and keep(w):
                seen.add(key)
                words.append(w)
    return Index(words)
