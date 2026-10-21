"""Czech crossword alphabet: cells, normalisation and match keys.

A cell is a string: one letter, or the digraph ``CH`` (the SČHAK directive
§27–34 allows a letter cluster in one cell). Words are compared through
*match keys* so the owner can choose whether diacritics or vowel length
matter (``--match strict|length|none``). The grid stores keys, so what the
solver sees is exactly what is compared.
"""
from __future__ import annotations

import unicodedata

MATCH_MODES = ("strict", "length", "none")
MIN_LEN = 2  # directive §17: an entry occupies at least two cells
MAX_LEN = 15

_BASE = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_DIACRITIC = "ÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ"
LETTERS = frozenset(_BASE + _DIACRITIC)
CELLS = LETTERS | {"CH"}

# "length" mode: long and short vowels share a cell key; Ě and consonants stay.
_LENGTH_MAP = str.maketrans("ÁÉÍÓÚŮÝ", "AEIOUUY")

# Written between C and H in the input ("c|hata") to keep them in two cells,
# for the rare C-H across a morpheme boundary.
SPLIT_MARK = "|"

_PUNCT = frozenset(".,;:!?-–—\"'„“”‚‘’()[]…/")


class AlphabetError(ValueError):
    """Input is not a Czech word the grid can hold."""


def normalize(text: str) -> str:
    """NFC + upper case, so composed and decomposed input compare equal."""
    return unicodedata.normalize("NFC", text).upper()


def tokenize(word: str, *, ch_one_cell: bool = True) -> list[str]:
    """Split one word into cells. Raises AlphabetError on anything but letters."""
    text = normalize(word.strip())
    if not text or text == SPLIT_MARK:
        raise AlphabetError("empty word")
    cells: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == SPLIT_MARK:
            i += 1
            continue
        if ch not in LETTERS:
            raise AlphabetError(f"{word!r}: character {ch!r} is not a Czech letter")
        if ch_one_cell and ch == "C" and i + 1 < len(text) and text[i + 1] == "H":
            cells.append("CH")
            i += 2
            continue
        cells.append(ch)
        i += 1
    if not cells:
        raise AlphabetError("empty word")
    return cells


def tokenize_phrase(text: str, *, ch_one_cell: bool = True) -> list[list[str]]:
    """Split a tajenka (keyword or quote) into words of cells; punctuation is
    dropped (directive §67 allows omitting it)."""
    words: list[list[str]] = []
    for raw in normalize(text).split():
        cleaned = "".join(c for c in raw if c not in _PUNCT)
        if cleaned:
            words.append(tokenize(cleaned, ch_one_cell=ch_one_cell))
    if not words:
        raise AlphabetError("tajenka has no letters")
    return words


def flatten(words: list[list[str]]) -> list[str]:
    return [cell for word in words for cell in word]


def check_length(cells: list[str], what: str = "word") -> None:
    if not MIN_LEN <= len(cells) <= MAX_LEN:
        raise AlphabetError(
            f"{what} {''.join(cells)!r} has {len(cells)} cells; allowed {MIN_LEN}–{MAX_LEN}"
        )


def strip_diacritics(text: str) -> str:
    """ASCII-fold a text (for clue/answer comparisons), keeping case."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def cell_key(cell: str, match: str = "strict") -> str:
    if match not in MATCH_MODES:
        raise ValueError(f"unknown match mode {match!r}; use one of {MATCH_MODES}")
    if match == "strict":
        return cell
    if match == "length":
        return cell.translate(_LENGTH_MAP)
    return strip_diacritics(cell)


def word_key(cells: list[str], match: str = "strict") -> tuple[str, ...]:
    return tuple(cell_key(c, match) for c in cells)
