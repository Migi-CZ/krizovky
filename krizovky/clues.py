"""Clue and theme-word exchange with a language model, through files.

There is no API key on this machine, so the tool writes ``request.json``; the
Claude Code session (or any chat assistant) answers it as ``clues.json``; the
tool validates and applies that. The model only ever writes language - it
never sees or changes the grid (project lesson: a one-shot LLM must not
touch the grid).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from . import alphabet, validate
from .model import Entry, Puzzle

REQUEST_NAME = "request.json"
CLUES_NAME = "clues.json"
FORMAT_VERSION = 1
MUST_CONTAIN_MIN_WORDS = 2

log = logging.getLogger(__name__)


class CluesError(ValueError):
    """clues.json is malformed (the message names the file)."""


# --- request -----------------------------------------------------------------

def missing_clues(p: Puzzle) -> list[Entry]:
    return [e for e in p.entries if e.clue is None or not e.clue.strip()]


def _write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def label_tajenka(p: Puzzle) -> list[str]:
    """Mode swedish: the clue cell of a tajenka entry shows a label ("tajenka" or "2. díl tajenky"),
    not a definition. Sets only missing clues; returns the labels it set."""
    if p.mode != "swedish":
        return []
    runs = p.tajenka_run_cells()
    labels: list[str] = []
    for i, k in sorted(p.tajenka_entries().items()):
        entry = p.entries[i]
        if entry.clue is None or not entry.clue.strip():
            entry.clue = "tajenka" if len(runs) == 1 else f"{k + 1}. díl tajenky"
            labels.append(entry.clue)
    return labels


SWEDISH_INSTRUCTIONS = (
    "Napiš ke každému slovu v items jednu křížovkářskou legendu do políčka švédské křížovky: stručná "
    "definice (ne věta), nejvýše {cap} znaků, česky, v prvním pádě tam, kde to dává smysl. Legenda nesmí "
    "obsahovat žádný tvar odpovědi ani slovo od ní odvozené. Vycházej z gloss, form a flags u položky "
    "(freq je pořadí v seznamu četnosti, čím nižší, tím běžnější slovo, 0 = v seznamu není) a piš jako časopisecké křížovky: zkratku označ "
    "„(zkr.)“ (flag zkr.), množné číslo podle form „(mn. č.)“, dále „zast.“, „kniž.“, „hovor.“, „nář.“ "
    "podle flags, „slovensky“, „domácky“, „SPZ …“ (značka vozidla), „chem. zn.“, „(římsky)“ pro římské "
    "číslo a u cizího slova jeho jazyk (např. „angl.“). Pozice slov v mřížce neřeš, měň jen legendy. "
    "Do pole pomucka dej odpovědi, které luštitel nemusí znát (cizí slova, zkratky, jména), přesně v "
    "podobě, jak se mají vytisknout („anis“, „Denali“, „MTI“). Vrať soubor clues.json ve tvaru uvedeném "
    "ve schema, klíčem v clues je odpověď (answer) velkými písmeny.")


def write_request(p: Puzzle, out_dir: Path, *, theme: str | None = None) -> Path:
    """Write request.json asking for a clue for every entry that has none."""
    if theme is None and isinstance(p.meta.get("theme"), str):
        theme = p.meta["theme"]
    cap = validate.CLUE_MAX.get(p.mode, 70)
    swedish = p.mode == "swedish"
    dictionary = p.meta.get("dictionary") if isinstance(p.meta.get("dictionary"), dict) else {}
    items = []
    for e in missing_clues(p):
        item = {"answer": e.answer, "cells": list(e.cells), "length": len(e.cells),
                "pos": e.pos, "gloss": None, "synonyms": []}
        if swedish:
            row = dictionary.get(e.answer) or {}
            item.update(gloss=row.get("gloss"), form=row.get("form") or "",
                        flags=list(row.get("flags") or []), freq=row.get("freq") or 0)
        items.append(item)
    schema = {"version": FORMAT_VERSION, "clues": {"<ANSWER>": "<clue>"}}
    if swedish:
        schema["pomucka"] = ["<answer>"]
    data = {
        "version": FORMAT_VERSION, "kind": "clues", "language": "cs",
        "theme": theme, "tajenka": p.tajenka, "match": p.match,
        "instructions": SWEDISH_INSTRUCTIONS.format(cap=cap) if swedish else (
            "Napiš ke každému slovu v items jednu křížovkářskou legendu. Styl definice (ne věta), "
            f"nejvýše {cap} znaků, česky, v prvním pádě tam, kde to dává smysl. Legenda nesmí obsahovat "
            "žádný tvar odpovědi ani slovo od ní odvozené. U cizích slov připiš jazyk (např. „angl.“). "
            "Pozice slov v mřížce neřeš, měň jen legendy. Vrať soubor clues.json ve tvaru uvedeném "
            "ve schema, klíčem je odpověď (answer) velkými písmeny."),
        "items": items,
        "schema": schema,
    }
    return _write_json(Path(out_dir) / REQUEST_NAME, data)


def write_theme_request(out_dir: Path, *, theme: str, tajenka: str, count: int, max_len: int,
                        match: str = "strict", ch_one_cell: bool = True) -> Path:
    """Write request.json asking for theme words (plus clues) that carry the tajenka letters."""
    if match not in alphabet.MATCH_MODES:
        raise ValueError(f"unknown match mode {match!r}; use one of {alphabet.MATCH_MODES}")
    if count < 1:
        raise ValueError(f"count must be at least 1, got {count}")
    if not alphabet.MIN_LEN <= max_len <= alphabet.MAX_LEN:
        raise ValueError(f"max_len must be {alphabet.MIN_LEN}–{alphabet.MAX_LEN}, got {max_len}")
    cells = alphabet.flatten(alphabet.tokenize_phrase(tajenka, ch_one_cell=ch_one_cell))  # AlphabetError if bad
    # Distinct cells in order of first appearance; keyed by match mode so that
    # e.g. Ě and E are one need when diacritics do not matter.
    seen: dict[str, None] = {}
    for cell in cells:
        seen.setdefault(alphabet.cell_key(cell, match), None)
    data = {
        "version": FORMAT_VERSION, "kind": "theme_words", "language": "cs",
        "theme": theme, "tajenka": tajenka, "match": match,
        "instructions": (
            f"Navrhni {count} běžných českých podstatných nebo přídavných jmen v prvním pádě, "
            f"každé o 2 až {max_len} buňkách, týkajících se tématu, a ke každému legendu "
            "(definice, nejvýše 70 znaků, bez tvaru odpovědi). Pro každé písmeno v need.must_contain "
            f"navrhni alespoň {MUST_CONTAIN_MIN_WORDS} slova, která ho obsahují. "
            + ("CH se počítá jako jedna buňka. " if ch_one_cell else "CH se počítá jako dvě buňky. ")
            + "Vrať soubor clues.json ve tvaru uvedeném ve schema (klíč theme_words)."),
        "need": {"count": count, "max_len": max_len,
                 "must_contain": [{"cell": c, "min_words": MUST_CONTAIN_MIN_WORDS} for c in seen]},
        "schema": {"version": FORMAT_VERSION, "theme_words": [{"word": "RECYKLACE", "clue": "..."}]},
    }
    return _write_json(Path(out_dir) / REQUEST_NAME, data)


def clear_request(out_dir: Path) -> bool:
    """Remove a clue request once no clue is missing: it would list clues that are already
    answered. A request of another kind (theme words) or an unreadable file is left alone."""
    path = Path(out_dir) / REQUEST_NAME
    try:
        if json.loads(path.read_text(encoding="utf-8")).get("kind") != "clues":
            return False
        path.unlink()
    except (OSError, ValueError, AttributeError):
        return False
    return True


# --- clues.json ----------------------------------------------------------------

def read_clues(out_dir: Path) -> dict:
    """Parse and schema-check clues.json; {} when it does not exist."""
    path = Path(out_dir) / CLUES_NAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CluesError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise CluesError(f"{path.name}: top level must be an object")
    if data.get("version") != FORMAT_VERSION:
        raise CluesError(f"{path.name}: version {data.get('version')!r} not supported "
                         f"(expected {FORMAT_VERSION})")
    if "clues" in data:
        if not isinstance(data["clues"], dict):
            raise CluesError(f"{path.name}: 'clues' must be an object answer -> clue")
        for key, value in data["clues"].items():
            if not isinstance(value, str):
                raise CluesError(f"{path.name}: clue for {key!r} must be a string")
    if "pomucka" in data and not (isinstance(data["pomucka"], list)
                                  and all(isinstance(x, str) for x in data["pomucka"])):
        raise CluesError(f"{path.name}: 'pomucka' must be a list of strings")
    if "theme_words" in data and not isinstance(data["theme_words"], list):
        raise CluesError(f"{path.name}: 'theme_words' must be a list")
    return data


def apply_clues(p: Puzzle, data: dict) -> list[str]:
    """Set entry.clue for every valid clue; return one problem line per bad,
    missing or unmatched clue. Never raises on a bad clue (the owner can then
    fix clues.json and rerun)."""
    problems: list[str] = []
    raw = data.get("clues", {}) if isinstance(data, dict) else {}
    if not isinstance(raw, dict):
        return ["clues.json: 'clues' is not an object answer -> clue"]

    def folded(text: str) -> str:
        return alphabet.strip_diacritics(text)

    exact = {alphabet.normalize(str(k).strip()): v for k, v in raw.items()}
    # Accent-free keys are only safe when diacritics do not distinguish cells.
    loose = {folded(k): v for k, v in exact.items()} if p.match == "none" else {}

    used: set[str] = set()
    for entry in p.entries:
        key = alphabet.normalize(entry.answer)
        if key in exact:
            used.add(key)
            value = exact[key]
        elif p.match == "none" and folded(key) in loose:
            used.add(folded(key))
            value = loose[folded(key)]
        else:
            if entry in missing_clues(p):
                problems.append(f"clue for {entry.answer}: missing in {CLUES_NAME}")
            continue
        if not isinstance(value, str):
            problems.append(f"clue for {entry.answer}: not a string")
            continue
        bad = validate.clue_violations(entry.answer, value, p.mode)
        if bad:
            problems.extend(bad)
            continue
        entry.clue = value.strip()

    answers = {alphabet.normalize(e.answer) for e in p.entries}
    for key in exact:
        if key not in used and not (p.match == "none" and folded(key) in used):
            if key not in answers:
                problems.append(f"{CLUES_NAME}: clue for {key!r} matches no entry")

    items = data.get("pomucka") if isinstance(data, dict) else None
    if isinstance(items, list):
        matched: list[str] = []
        for item in items:
            text = str(item).strip()
            norm = alphabet.normalize(text)
            if norm in answers or (p.match == "none" and folded(norm) in {folded(a) for a in answers}):
                matched.append(text)
            else:
                problems.append(f"pomucka: {text!r} matches no entry")
        if matched:
            p.meta["pomucka"] = matched
        else:
            p.meta.pop("pomucka", None)
    return problems


def theme_words(data: dict) -> list[tuple[str, str | None]]:
    """(word, clue) pairs from data['theme_words']; invalid words are skipped
    with a warning, duplicates keep the first."""
    out: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    items = data.get("theme_words", []) if isinstance(data, dict) else []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict):
            word, clue = item.get("word"), item.get("clue")
        else:
            word, clue = item, None
        if not isinstance(word, str):
            log.warning("theme word skipped: %r is not a word entry", item)
            continue
        try:
            alphabet.tokenize(word)
        except alphabet.AlphabetError as exc:
            log.warning("theme word %s skipped: %s", alphabet.normalize(word.strip()), exc)
            continue
        norm = alphabet.normalize(word.strip()).replace(alphabet.SPLIT_MARK, "")
        if norm in seen:
            continue
        seen.add(norm)
        out.append((norm, clue.strip() if isinstance(clue, str) and clue.strip() else None))
    return out


def fallback_clue(item: dict, mode: str) -> str | None:
    """Offline clue from a dictionary entry: the gloss up to ';' or '(', else the
    first synonym. None when empty or when it breaks the clue rules."""
    answer = str(item.get("answer") or item.get("word") or "")
    text = ""
    gloss = item.get("gloss")
    if isinstance(gloss, str):
        text = re.split(r"[;(]", gloss, maxsplit=1)[0].strip(" \t,:")
    if not text:
        synonyms = item.get("synonyms")
        if isinstance(synonyms, list) and synonyms and isinstance(synonyms[0], str):
            text = synonyms[0].strip()
    if not text or validate.clue_violations(answer, text, mode):
        return None
    return text
