"""Build data/words.tsv.gz from the raw dictionary downloads.

    python3 -I scripts/build_wordlist.py --raw RAW_DIR --out data/words.tsv.gz
    python3 -I scripts/build_wordlist.py --wikt FILE.jsonl[.gz] --freq cs_50k.txt --out words.tsv
    ... [--en-wikt kaikki.org-dictionary-Czech.jsonl] [--syn syn2015_lemma_utf8.zip] [--syn-min 20]
    ... [--review data/source_review.tsv] [--export-review GROUPS.tsv] [--blocklist data/blocklist.tsv]

Inputs (untrusted data, only parsed, never executed): the kaikki.org / cs.wiktionary
JSONL dump ``raw-wiktextract-data.jsonl.gz`` and the FrequencyWords list ``cs_50k.txt``
(``word count`` per line, rank = line number). ``krizovky/wordlist.py`` reads the result.
Only basic forms are kept (SČHAK directive §10): 1st case singular or plural, infinitive.
Optional (slice 4e): the Czech entries of the English Wiktionary (``--en-wikt``, words only:
its English glosses and synonyms are never written) and the ČNK SYN2015 lemma list
(``--syn``, .tsv or the .zip holding it): attests rows and adds frequent lemmas.
Slice 4e unit 3b: fixed rules R9–R12 on those two sources and a model review of their riskiest
rows (groups A surnames, B ASCII-only words, C 2–3 cells), read from ``--review FILE`` (a TSV
``word source group verdict note``, verdict keep/drop; a row of a group without a verdict is
dropped); ``--export-review FILE`` lists the rows that reach the review, for whoever writes it.
Slice 7b: leak rules R13–R25 on every source and a hand blocklist (``--blocklist FILE``, a TSV
``word lemma note``; an empty lemma blocks every row of the word).
"""
from __future__ import annotations

import sys
from pathlib import Path

# The script runs under `python3 -I`, which does not add the script folder to sys.path;
# the project root is an explicit, trusted path (the raw data folder never gets onto it).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from krizovky import alphabet  # noqa: E402

import argparse  # noqa: E402
import gzip  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import unicodedata  # noqa: E402
import zipfile  # noqa: E402
from typing import Iterator  # noqa: E402

COLUMNS = ("word", "lemma", "pos", "form", "gloss", "syn", "freq", "flags")
RAW_WIKT_NAME = "raw-wiktextract-data.jsonl.gz"
RAW_FREQ_NAME = "cs_50k.txt"
GLOSS_MAX = 100
SYN_MAX = 3

# "offensive", "slur", "dated", "colloquial": tags of the English Wiktionary (slice 4e); the Czech
# dump carries none of them, so its rows do not change ("Moravia" it does carry: left out).
DROP_SENSE_TAGS = frozenset({"vulgar", "derogatory", "pejorative", "offensive", "slur"})
OBSOLETE_TAGS = frozenset({"obsolete", "archaic", "outdated", "Old-Cezch", "dated"})  # sic: typo is in the data
# Flags set from sense tags: only when EVERY kept sense carries one tag of the group.
SENSE_FLAGS = (
    ("zast.", OBSOLETE_TAGS),
    ("kniž.", frozenset({"literary"})),
    ("básn.", frozenset({"poetic"})),
    ("hovor.", frozenset({"colloquially", "colloquial", "slang", "familiar", "informal"})),
    ("nář.", frozenset({"dialectal", "regional"})),
)
# A row's source when it is not the Czech Wiktionary (slice 4e): lets the bench exclude a source.
SOURCE_FLAGS = {"cs-wikt": "", "en-wikt": "en-wikt", "syn": "syn"}
FLAG_ORDER = ("zkr.", "vl.", "zast.", "kniž.", "básn.", "hovor.", "nář.", "tvar", "en-wikt", "syn")
FORM_TAG_FLAGS = (("obsolete", "zast."),)   # a form's own tags add a flag
# Dialectal variants of a form ("okřáť" under "okřát", Slovak-looking "deň") are not Czech
# entries; dialectal lemmas keep their own entry with the flag `nář.` (owner's gate 2026-10-19).
DIALECT_FORM_TAGS = frozenset({"dialectal", "Moravia", "Silesia", "Slovakia"})
# A non-lemma row carries the lemma's gloss; the magazine marker tells the clue writer
# which form the clue must take ("nápadníci" -> "muž, který… (mn. č.)").
FORM_GLOSS_MARKS = (("comparative", " (2. st.)"), ("superlative", " (3. st.)"))
PLURAL_MARK = " (mn. č.)"
# Wiktionary generates a full declension table for every adjective ("kunoví"); such a form
# is kept only when the frequency list attests it (owner's gate 2026-10-19). The same holds
# for any `alternative` spelling (KOŘAN, ODKAD, UNI; rule R6, slice 4b).
ATTESTED_FORM_POS = frozenset({"adj"})
ATTESTED_FORM_TAG = "alternative"

# SČHAK directive §10: an entry is a noun/adjective/pronoun/numeral in the 1st case
# (singular or plural) or a verb in the infinitive. Only such forms are kept (owner's
# decision 2026-10-19): a form with a `nominative` tag, or a form without any case or
# verb-form tag (alternative spellings, comparatives of adverbs); verbs keep only
# tag-free alternative infinitives.
OBLIQUE_CASES = frozenset({"genitive", "dative", "accusative", "vocative", "locative", "instrumental"})
VERB_FORM_TAGS = frozenset({
    "participle", "transgressive", "indicative", "imperative", "conditional", "subjunctive",
    "first-person", "second-person", "third-person", "present", "past", "future", "active", "passive",
})
TVAR_GLOSS_PREFIX = "nominativ"   # a form-of entry without a lemma stays only as a 1st-case form
# Some inflected forms are lemma entries in kaikki without a form-of tag ("dvěma": gloss
# "instrumentál číslovek dva a dvě"); a gloss that opens with an oblique case or a person
# is a grammar description of a non-basic form, not an entry.
# Cases are also tested behind leading labels ("nim": "(po předložce) dativ…", rule R2), the
# rest only on the raw gloss: "Syn" is "(v křesťanství) druhá osoba Nejsvětější Trojice".
CASE_PREFIXES = (
    "genitiv", "dativ", "akuzativ", "vokativ", "lokál", "instrumentál",
)
CLITIC_PREFIXES = ("příklonný tvar",)   # R3: "ho", "mu", "jej" (clitic accusative/dative)
# R4: short adjective forms ("sláb", "kliden"); "participium" (jmenný tvar slovesa) stays
SHORT_ADJ_GLOSS = ("jmenný tvar",)
SHORT_ADJ_OF = ("adjektiva", "přídavného jména")
LEADING_LABELS = re.compile(r"^(?:\([^()]*\)\s*)+")
NON_BASIC_GLOSS_PREFIXES = CASE_PREFIXES + (
    "první osoba", "druhá osoba", "třetí osoba",
    # participles, imperatives, transgressives and auxiliary forms filed as entries ("neměl", "šil", "hoj", "bych")
    "příčestí", "záporné příčestí", "rozkazovací", "imperativ", "přechodník",
    "jednotné číslo minulého", "množné číslo minulého", "plurál mužského", "plurál příčestí", "singulár příčestí",
    "tvar pomocného", "tvar akuzativu", "tvar genitivu", "tvar dativu", "tvar lokálu", "tvar instrumentálu", "tvar vokativu",
)   # not "množné číslo", "tvar slovesa", "podmiňovací": those glosses belong to the real words plurál, infinitiv, kondicionál

# R8: words whose main use is vulgar; the owner wants none in a puzzle (2026-10-19). The sense tag
# is not enough: kokot, kunda also carry untagged vulgar senses. Words with a common main sense
# (ocas, prkno, čubka, kouřit) are deliberately not listed.
VULGAR_BLOCKLIST = frozenset({"buzna", "buzík", "jebat", "kokot", "kunda", "prdel", "prdelka",
                              "přefiknout", "sračka"})

# The English Wiktionary lists derived words (feminine, diminutive, aspect pair, relational
# adjective) as head forms of a lemma, and table labels ("animate", "cs-ndecl") as forms; only
# real cells of its declension/conjugation tables are forms.
TABLE_FORM_SOURCES = frozenset({"declension", "conjugation", "inflection"})
PSEUDO_FORM_TAGS = frozenset({"table-tags", "inflection-template"})
# SYN2015: a row attested only there gets freq 50 000 + SYN rank, after every cs_50k rank
# (`freq > 0` = attested); a SYN-only lemma becomes a row from SYN_MIN occurrences on.
SYN_OFFSET = 50_000
SYN_MIN = 20
SYN_MAX_BYTES = 64 << 20     # the real list is 3.5 MB; a bigger zip member is not that list

DROP_RULES = ("empty-gloss", "non-basic-gloss", "case-label", "clitic", "short-adj",
              "vulgar-obsolete", "vulgar-unattested", "vulgar-blocked", "alternative-unattested",
              "known-word", "wikt-rejected",                    # en-wikt and syn
              "non-table-form", "name-form", "archaic-infinitive", "surname",   # en-wikt (R9, R10, R11)
              "duplicate", "capitalised", "rare", "not-a-word", "possessive",   # syn (R12 last)
              "non-infinitive", "bad-initial", "name-no-gloss", "insult", "name-plural",   # slice 7b
              "unattested-abbrev", "nonstandard-form", "name-possessive", "dialect", "obscure-surname",
              "colloquial-name", "unattested-slang", "blocked")

# Slice 4e unit 3b (plan `Source/4e-dictionary-2.md` §G). R11: a surname of the English Wiktionary
# stays only with this many SYN2015 occurrences of the capitalised lemma, and a `keep` review.
SURNAME_MIN = 100
POSSESSIVE_SUFFIX = "ův"      # R12: komárkův, a name possessive the SYN lemmatiser lists as a lemma
SURNAME_RE = re.compile(r"\bsurname\b", re.IGNORECASE)   # filter only; the English text is never written
REVIEW_SOURCES = ("en-wikt", "syn")
REVIEW_GROUPS = ("A", "B", "C")       # A surnames, B ASCII-only words, C 2–3 cells (checked in that order: C before B)
REVIEW_VERDICTS = ("keep", "drop")
REVIEW_HEADER = ("word", "source", "group", "verdict", "note")

# Slice 7b (plan `Source/7b-dictionary-cleanup.md`): leak classes the generated grids showed.
INFINITIVE_RE = re.compile(r"(?:t|ti|ci)$")     # R13: pudeme, řek, poď are filed as verbs, not infinitives
ARCHAIC_INF_GLOSS = "tvar infinitivu"           # R14: "zastaralý a knižní tvar infinitivu slovesa lát"
BAD_INITIALS = frozenset("ěůý")                 # R15: no Czech word starts with them (SYN artefact "ěstí")
# R17: the gloss names an insult ("vulgární nadávka", "potupné označení člověka"); "nadávka" itself
# ("hrubé, urážlivé… oslovení") and words merely labelled "(hanlivě)" stay.
INSULT_RE = re.compile(r"^(?:vulgární )?nadávka|; nadávka|^(?:potupné|hanlivé|urážlivé) označení")
# R16 (owner's gate 1, 2026-10-21): only person names go (Svata, Otík); places, gods and historical
# figures stay (Kigali, Hermes, Jericho). Read from the English glosses, which are never written.
PERSON_NAME_RE = re.compile(r"given name|diminutive|nickname|pet form|hypocoristic|surname|patronymic|endearing",
                            re.IGNORECASE)
NAME_GLOSS_RE = re.compile(r"jméno|příjmení")   # R18: plurals of given names and surnames (Zity, Anny)
# R18 also: a nickname whose gloss is only the full name(s) ("Ivča": "Ivana"; "Mirek": "Miroslav, Jaromír")
NAME_ONLY_GLOSS_RE = re.compile(r"^[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][^\s;,]*(?:[;,] [A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][^\s;,]*)*$")
ABBREV_MIN_CELLS = 4                            # R19: an abbreviation this long needs a frequency-list attestation
NONSTANDARD_RAW_TAGS = ("v obecném jazyce", "lidově")   # R20: muj, kterej, leto (raw tags of a form)
# R23 (owner, 2026-10-21): a Czech-Wiktionary surname row ("české mužské příjmení") stays only when SYN2015
# attests the name as often as R11 asks of an English-Wiktionary surname (Baťa, Janáček stay; Terynek goes).
# R22 also: a dialect label in the gloss without the nář. flag ("(nářečně) onen", "(oblastně, brněnský hantec)");
# "(v moravské kuchyni) vdolek" is standard Czech and stays.
DIALECT_LABEL_RE = re.compile(r"nářečn|oblastn|moravsky|ve Slezsku|na Moravě")
SURNAME_GLOSS_RE = re.compile(r"příjmení")
NOT_SURNAME_GLOSS_RE = re.compile(r"jméno|přezdívk")     # "mužské křestní jméno (a příjmení)", "přezdívka … diktátora"
BLOCKLIST_HEADER = ("word", "lemma", "note")

# A row: (cells, word, lemma, pos, form, gloss, syn, freq, flags)
Row = tuple[int, str, str, str, str, str, str, int, str]


class BuildError(Exception):
    """Bad input or arguments; reported on stderr, exit code 1."""


# --- reading ------------------------------------------------------------------
def open_text(path: Path):
    try:
        if path.suffix == ".gz":
            return gzip.open(path, "rt", encoding="utf-8")
        return open(path, "rt", encoding="utf-8")
    except OSError as exc:
        raise BuildError(f"cannot open {path}: {exc.strerror or exc}")


def iter_czech_entries(path: Path) -> Iterator[dict]:
    """Yield the ``lang_code == "cs"`` entries of a JSONL dump; streams, one line at a time."""
    with open_text(path) as fh:
        try:
            for number, line in enumerate(fh, 1):
                if '"cs"' not in line:      # cheap prefilter: a Czech entry contains the JSON string "cs"
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise BuildError(f"{path}:{number}: not valid JSON ({exc.msg})")
                if isinstance(entry, dict) and entry.get("lang_code") == "cs":
                    yield entry
        except (OSError, EOFError, UnicodeDecodeError) as exc:  # gzip.BadGzipFile is an OSError
            raise BuildError(f"cannot read {path}: {exc}")


def read_freq(path: Path) -> dict[str, int]:
    """Lower-cased word -> rank (1-based line number); first occurrence wins, blank lines skipped."""
    ranks: dict[str, int] = {}
    with open_text(path) as fh:
        try:
            for number, line in enumerate(fh, 1):
                parts = line.split()
                if parts:
                    ranks.setdefault(unicodedata.normalize("NFC", parts[0]).lower(), number)
        except (OSError, EOFError, UnicodeDecodeError) as exc:
            raise BuildError(f"cannot read {path}: {exc}")
    return ranks


def read_syn(path: Path) -> list[tuple[str, int, int]]:
    """(lemma, rank, frequency) per line of the ČNK SYN2015 lemma list; rank = line number.

    Tab-separated, lemma in column 2, frequency in column 3; the list is sorted by column 3.
    Column 1 is filled on a few thousand lines only, so it is not the rank. A .zip must hold
    exactly one file, the list itself.
    """
    try:
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as zf:
                members = [i for i in zf.infolist() if not i.is_dir()]
                if len(members) != 1:
                    raise BuildError(f"{path}: expected one file inside, found {len(members)}")
                if members[0].file_size > SYN_MAX_BYTES:
                    raise BuildError(f"{path}: {members[0].filename} is {members[0].file_size} bytes, too big")
                lines = zf.read(members[0]).decode("utf-8").split("\n")
        else:
            with open_text(path) as fh:
                lines = fh.read().split("\n")
    except (OSError, EOFError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
        raise BuildError(f"cannot read {path}: {exc}")
    out: list[tuple[str, int, int]] = []
    for number, line in enumerate(lines, 1):
        cols = line.rstrip("\r").split("\t")
        if cols == [""]:
            continue
        try:
            count = int(cols[2])
        except (IndexError, ValueError):
            raise BuildError(f"{path}:{number}: expected 'rank<TAB>lemma<TAB>frequency…'")
        out.append((nfc(cols[1].strip()), number, count))
    return out


def read_review(path: Path) -> dict[tuple[str, str], tuple[str, str]]:
    """(word, source) -> (verdict, note) from the review file; every malformed line is an error."""
    with open_text(path) as fh:
        try:
            lines = fh.read().split("\n")
        except (OSError, EOFError, UnicodeDecodeError) as exc:
            raise BuildError(f"cannot read {path}: {exc}")
    if tuple(lines[0].rstrip("\r").split("\t")) != REVIEW_HEADER:
        raise BuildError(f"{path}:1: header must be {' '.join(REVIEW_HEADER)} (tab-separated)")
    review: dict[tuple[str, str], tuple[str, str]] = {}
    for number, line in enumerate(lines[1:], 2):
        cols = line.rstrip("\r").split("\t")
        if cols == [""]:
            continue
        if len(cols) != len(REVIEW_HEADER):
            raise BuildError(f"{path}:{number}: expected {len(REVIEW_HEADER)} columns, got {len(cols)}")
        word, source, group, verdict, note = cols
        for value, allowed, what in ((source, REVIEW_SOURCES, "source"), (group, REVIEW_GROUPS, "group"),
                                     (verdict, REVIEW_VERDICTS, "verdict")):
            if value not in allowed:
                raise BuildError(f"{path}:{number}: {what} must be one of {' '.join(allowed)}, got {value!r}")
        key = (nfc(word.strip()), source)
        if key in review:
            raise BuildError(f"{path}:{number}: {key[0]} ({source}) is listed twice")
        review[key] = (verdict, note.strip())
    return review


def read_blocklist(path: Path) -> set[tuple[str, str]]:
    """(word, lemma) pairs from the hand blocklist; lemma "" blocks every row of the word."""
    with open_text(path) as fh:
        try:
            lines = fh.read().split("\n")
        except (OSError, EOFError, UnicodeDecodeError) as exc:
            raise BuildError(f"cannot read {path}: {exc}")
    if tuple(lines[0].rstrip("\r").split("\t")) != BLOCKLIST_HEADER:
        raise BuildError(f"{path}:1: header must be {' '.join(BLOCKLIST_HEADER)} (tab-separated)")
    blocked: set[tuple[str, str]] = set()
    for number, line in enumerate(lines[1:], 2):
        cols = line.rstrip("\r").split("\t")
        if cols == [""]:
            continue
        if len(cols) != len(BLOCKLIST_HEADER):
            raise BuildError(f"{path}:{number}: expected {len(BLOCKLIST_HEADER)} columns, got {len(cols)}")
        key = (nfc(cols[0].strip()), nfc(cols[1].strip()))
        if not key[0]:
            raise BuildError(f"{path}:{number}: empty word")
        if key in blocked:
            raise BuildError(f"{path}:{number}: {key[0]} ({key[1] or 'every lemma'}) is listed twice")
        blocked.add(key)
    return blocked


# --- entry analysis -----------------------------------------------------------
def clean(text: object) -> str:
    """One line, no tabs: the TSV has no quoting."""
    return " ".join(str(text).split())


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def str_list(value: object) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def senses_of(entry: dict) -> list[dict]:
    senses = entry.get("senses")
    return [s for s in senses if isinstance(s, dict)] if isinstance(senses, list) else []


def is_form_of(entry: dict) -> bool:
    senses = senses_of(entry)
    return bool(senses) and all("form-of" in str_list(s.get("tags")) for s in senses)


def form_of_words(entry: dict) -> list[str]:
    out: list[str] = []
    for sense in senses_of(entry):
        for item in sense.get("form_of") or []:
            if isinstance(item, dict) and isinstance(item.get("word"), str):
                out.append(nfc(item["word"].strip()))
    return out


def kept_senses(entry: dict) -> tuple[list[dict], bool]:
    """Senses without a vulgar/derogatory tag, and whether a `vulgar` sense was dropped."""
    senses = senses_of(entry)
    kept = [s for s in senses if not DROP_SENSE_TAGS & set(str_list(s.get("tags")))]
    vulgar = any("vulgar" in str_list(s.get("tags")) for s in senses)
    return kept, vulgar


def strip_labels(gloss: str) -> str:
    """The gloss without its leading "(…)" label groups."""
    return LEADING_LABELS.sub("", gloss)


def non_basic_rule(gloss: str) -> str | None:
    """Name of the rule by which a lemma gloss describes a non-basic form, or None."""
    raw = gloss.lower()
    bare = strip_labels(raw)
    if bare.startswith(CLITIC_PREFIXES):
        return "clitic"
    if raw.startswith(NON_BASIC_GLOSS_PREFIXES):
        return "non-basic-gloss"
    if bare.startswith(CASE_PREFIXES):
        return "case-label"
    if bare.startswith(SHORT_ADJ_GLOSS) and any(of in bare for of in SHORT_ADJ_OF):
        return "short-adj"
    return None


def is_surname_entry(entry: dict, senses: list[dict]) -> bool:
    """R11: a name entry in which every sense says "surname" (a given name too -> not a surname)."""
    return entry.get("pos") == "name" and bool(senses) and all(
        SURNAME_RE.search(" ".join(str_list(s.get("glosses")))) for s in senses)


def is_person_name(entry: dict, senses: list[dict]) -> bool:
    """R16: a name entry in which every sense names a person ("a male given name", "a diminutive of …")."""
    return entry.get("pos") == "name" and bool(senses) and all(
        PERSON_NAME_RE.search(" ".join(str_list(s.get("glosses")))) for s in senses)


def review_group(cells: int, word: str, form: str, flags: set[str], surname: bool) -> str:
    """The review group of a new row ("" = not reviewed): A surnames, C every word of 2–3 cells, B the
    other ASCII-only words; longer form rows follow their lemma, other names are not reviewed."""
    if surname:
        return "A"
    if cells <= 3:
        return "C"
    if form or "vl." in flags:
        return ""
    return "B" if word.isascii() else ""


def pick_gloss(senses: list[dict]) -> str:
    for sense in senses:
        if "no-gloss" in str_list(sense.get("tags")):
            continue
        for gloss in str_list(sense.get("glosses")):
            if clean(gloss):
                return clean(gloss)[:GLOSS_MAX]
    return ""


def pick_syn(entry: dict) -> str:
    words: list[str] = []
    for item in entry.get("synonyms") or []:
        if isinstance(item, dict) and isinstance(item.get("word"), str) and clean(item["word"]):
            words.append(clean(item["word"]).replace(";", ","))   # ";" separates the synonyms
        if len(words) == SYN_MAX:
            break
    return ";".join(words)


def entry_flags(entry: dict, senses: list[dict]) -> set[str]:
    flags: set[str] = set()
    if entry.get("pos") in ("abbrev", "symbol"):   # R7: SPZ codes, units, chemical symbols
        flags.add("zkr.")
    if entry.get("pos") == "name" or "vlastní" in str_list(entry.get("raw_tags")):
        flags.add("vl.")
    tag_sets = [set(str_list(s.get("tags"))) for s in senses]
    for flag, group in SENSE_FLAGS:
        if tag_sets and all(tags & group for tags in tag_sets):
            flags.add(flag)
    return flags


def cell_count(word: str) -> int | None:
    """Number of cells, or None when the word cannot be a crossword entry."""
    try:
        cells = alphabet.tokenize(word)
    except alphabet.AlphabetError:
        return None
    if "".join(cells) != alphabet.normalize(word):   # tokenize silently drops "|"
        return None
    return len(cells) if alphabet.MIN_LEN <= len(cells) <= alphabet.MAX_LEN else None


def is_basic_form(pos: str, tags: set[str]) -> bool:
    """Directive §10: 1st case (any number) for declined words, infinitive for verbs."""
    if tags & DIALECT_FORM_TAGS:
        return False
    if pos == "verb":
        return not tags & (OBLIQUE_CASES | VERB_FORM_TAGS | {"nominative"})
    return "nominative" in tags or not tags & (OBLIQUE_CASES | VERB_FORM_TAGS)


def form_gloss(gloss: str, tags: set[str]) -> str:
    """The lemma's gloss plus the marker of the form (plural only, comparison)."""
    if "plural" in tags and "singular" not in tags:
        gloss += PLURAL_MARK
    for tag, mark in FORM_GLOSS_MARKS:
        if tag in tags:
            gloss += mark
    return gloss


def merged_forms(entry: dict, word: str, *, tables_only: bool = False,
                 skipped: list[str] | None = None,
                 nonstandard: set[str] | None = None) -> dict[str, set[str]]:
    """Distinct forms (not the lemma itself) -> union of their tags.

    ``tables_only`` keeps only cells of the inflection tables (English Wiktionary); the
    forms left out are appended to ``skipped``. ``nonstandard`` receives the forms whose
    every occurrence carries a Common-Czech raw tag (R20: "muj" under "můj").
    """
    forms: dict[str, set[str]] = {}
    standard: set[str] = set()
    for item in entry.get("forms") or []:
        if not isinstance(item, dict) or not isinstance(item.get("form"), str):
            continue
        text = nfc(item["form"].strip())
        if not text or text == word:
            continue
        tags = {clean(t) for t in str_list(item.get("tags")) if clean(t)}
        if tables_only and (item.get("source") not in TABLE_FORM_SOURCES or tags & PSEUDO_FORM_TAGS):
            if skipped is not None:
                skipped.append(text)
            continue
        forms.setdefault(text, set()).update(tags)
        raw = " ".join(str_list(item.get("raw_tags")))
        if not any(mark in raw for mark in NONSTANDARD_RAW_TAGS):
            standard.add(text)
    if nonstandard is not None:
        nonstandard.update(f for f in forms if f not in standard)
    return forms


# --- build --------------------------------------------------------------------
class Builder:
    def __init__(self, ranks: dict[str, int], syn: list[tuple[str, int, int]] = (),
                 review: dict[tuple[str, str], tuple[str, str]] | None = None,
                 blocklist: set[tuple[str, str]] | None = None):
        self.ranks = ranks
        self.blocklist = blocklist            # None = no --blocklist
        self.blocklist_used: set[tuple[str, str]] = set()
        self.cleaned: set[str] = set()        # normalised words a slice-7b rule dropped (never brought back)
        self.cleaned_lemmas: dict[str, str] = {}   # entry dropped by R14/R17 -> rule; its forms go in every source
        # lower-case SYN lemma -> rank; capitalised lemmas are names and attest nothing
        self.syn_ranks: dict[str, int] = {}
        self.syn_counts: dict[str, int] = {}      # lemma as written -> occurrences (R11 reads the surnames)
        for lemma, rank, count in syn:
            self.syn_counts[lemma] = self.syn_counts.get(lemma, 0) + count
            if lemma == lemma.lower():
                self.syn_ranks.setdefault(lemma, rank)
        self.review = review                       # None = the review step is off
        self.review_members: list[tuple[str, str, str]] = []   # (word, source, group) of every row that reaches it
        self.review_counts: dict[tuple[str, str], dict[str, int]] = {}
        self.review_used: set[tuple[str, str]] = set()
        self.lemmas: set[str] = set()
        self.seen: set[tuple[str, str, str]] = set()
        self.rows: list[Row] = []
        self.source = "cs-wikt"
        self.dropped: dict[str, list[str]] = {rule: [] for rule in DROP_RULES}   # evidence per rule
        self.dropped_by_source = {self.source: self.dropped}
        self.known: set[str] = set()          # normalised words of the earlier sources' rows
        self.entry_words: set[str] = set()    # normalised words of every Czech lemma entry seen
        self.rejected: set[str] = set()       # lemma entries of earlier sources that gave no row
        self.vulgar_kept: list[str] = []      # vulgar sense dropped, entry kept: the owner's gate list

    def begin_source(self, name: str) -> None:
        """Rows from now on come from ``name``; a word of an earlier source's row wins over them."""
        self.source = name
        self.dropped = self.dropped_by_source[name] = {rule: [] for rule in DROP_RULES}
        self.known = {alphabet.normalize(r[1]) for r in self.rows}
        self.rejected = (self.entry_words | self.cleaned) - self.known

    def freq_of(self, word: str) -> int:
        low = word.lower()
        if low in self.ranks:
            return self.ranks[low]
        return SYN_OFFSET + self.syn_ranks[low] if low in self.syn_ranks else 0

    def collect_lemmas(self, entries: Iterator[dict]) -> None:
        """Pass 1: the lemma index = words of Czech entries that are not form-of entries."""
        for entry in entries:
            if isinstance(entry.get("word"), str) and not is_form_of(entry):
                self.lemmas.add(nfc(entry["word"].strip()))

    def source_rule(self, word: str, form: str, flags: set[str], surname: bool) -> str:
        """Name of the fixed rule (R9–R12) that drops a new-source row, or ""."""
        if self.source == "en-wikt":
            if form and "vl." in flags:
                return "name-form"                          # R9: Fučíkové
            if "infinitive" in form.split():
                return "archaic-infinitive"                 # R10: zešíleti
            if surname and self.syn_counts.get(word, 0) < SURNAME_MIN:
                return "surname"                            # R11, the review keeps the rest
        elif self.source == "syn" and word.endswith(POSSESSIVE_SUFFIX):
            return "possessive"                             # R12
        return ""

    def cleanup_rule(self, n: int, word: str, lemma: str, pos: str, form: str, flags: set[str],
                     gloss: str = "") -> str:
        """Name of the slice-7b rule that drops a row of any source, or ""."""
        if lemma in self.cleaned_lemmas:
            return self.cleaned_lemmas[lemma]           # en-wikt forms of an insult (děvky, hakeni)
        if self.blocklist is not None:
            for key in ((word, lemma), (word, "")):
                if key in self.blocklist:
                    self.blocklist_used.add(key)
                    return "blocked"
        if pos == "verb" and (not form or "alternative" in form.split()) \
                and not INFINITIVE_RE.search(word.lower()):
            return "non-infinitive"                     # R13
        if word[:1].lower() in BAD_INITIALS:
            return "bad-initial"                        # R15
        if "zkr." in flags and n >= ABBREV_MIN_CELLS and self.freq_of(word) == 0:
            return "unattested-abbrev"                  # R19
        if pos == "adj" and word[:1].isupper():
            return "name-possessive"                    # R21: Eliin, Janův, Baťovi
        labels = LEADING_LABELS.match(gloss)
        if "nář." in flags or (labels and DIALECT_LABEL_RE.search(labels.group(0))):
            return "dialect"                            # R22 (owner, 2026-10-21): starej, vaš, ešče, ščur
        if self.source == "cs-wikt" and "vl." in flags and SURNAME_GLOSS_RE.search(gloss) \
                and not NOT_SURNAME_GLOSS_RE.search(gloss) and self.syn_counts.get(lemma, 0) < SURNAME_MIN:
            return "obscure-surname"                    # R23: Terynek, Lednová, Zíma
        if "vl." in flags and "hovor." in flags:
            return "colloquial-name"                    # R24 (sample, 2026-10-21): Stoun, Valmez, Pánbíček
        if self.source == "en-wikt" and "hovor." in flags and self.freq_of(word) == 0:
            # R25: slang with no Czech gloss and no attestation leaves the clue writer nothing (kasr, obyč, žgrt)
            return "unattested-slang"
        return ""

    def drop_clean(self, rule: str, word: str) -> None:
        self.dropped[rule].append(word)
        if not word[:1].isupper():
            # names and abbreviations never come back anyway (R9, R11, R16, R19, R21 apply to every source);
            # their upper-case key would also block a common word ("Čtvrtek" the surname vs "čtvrtek")
            self.cleaned.add(alphabet.normalize(word))

    def review_keeps(self, word: str, group: str) -> bool:
        """Record a row of a review group and return whether it stays (always, without a review file)."""
        self.review_members.append((word, self.source, group))
        if self.review is None:
            return True
        counts = self.review_counts.setdefault((self.source, group), {"keep": 0, "drop": 0, "missing": 0})
        key = (word, self.source)
        if key not in self.review:
            counts["missing"] += 1        # no verdict: dropped, like a "drop"
            return False
        self.review_used.add(key)
        verdict = self.review[key][0]
        counts[verdict] += 1
        return verdict == "keep"

    def add_row(self, word: str, lemma: str, pos: str, form: str, gloss: str, syn: str,
                flags: set[str], surname: bool = False, person: bool = False) -> bool:
        n = cell_count(word)
        key = (word, lemma, pos)
        if n is None:
            return False
        if self.source != "cs-wikt":
            if alphabet.normalize(word) in self.known:   # today's row wins, with its Czech gloss
                self.dropped["known-word"].append(word)
                return False
            if alphabet.normalize(word) in self.rejected:   # a rule dropped it there (mrdat, kurva)
                self.dropped["wikt-rejected"].append(word)
                return False
            gloss, syn = "", ""                          # no English text in the word list
            flags = flags | {SOURCE_FLAGS[self.source]}
        if word.lower() in VULGAR_BLOCKLIST:    # R8 also for a form row of another lemma (prdelka)
            return False
        if key in self.seen:
            return False
        if self.source != "cs-wikt":
            rule = self.source_rule(word, form, flags, surname)
            if rule:
                self.dropped[rule].append(word)
                return False
            group = review_group(n, word, form, flags, surname)
            if not group and person:
                self.drop_clean("name-no-gloss", word)   # R16: Svata, Otík (unreviewed person names, no gloss)
                return False
            if group and not self.review_keeps(word, group):
                return False
        rule = self.cleanup_rule(n, word, lemma, pos, form, flags, gloss)
        if rule:
            self.drop_clean(rule, word)
            if rule in ("colloquial-name", "unattested-slang"):
                self.seen.add(key)     # these rules read the tags: a second entry without them (grán, felák) stays out
            return False
        self.seen.add(key)
        flag_text = ",".join(f for f in FLAG_ORDER if f in flags)
        self.rows.append((n, word, lemma, pos, form, gloss, syn, self.freq_of(word), flag_text))
        return True

    def add_entry(self, entry: dict) -> None:
        """Pass 2: the rows of one Czech entry."""
        if not isinstance(entry.get("word"), str):
            return
        word = nfc(entry["word"].strip())
        pos = clean(entry.get("pos") or "")
        if not is_form_of(entry):
            self.entry_words.add(alphabet.normalize(word))
        if word.lower() in VULGAR_BLOCKLIST:
            self.dropped["vulgar-blocked"].append(word)
            return
        senses, vulgar = kept_senses(entry)
        if not senses:                       # every sense vulgar/derogatory (or no senses at all)
            return
        if vulgar:
            # R5: a word with a vulgar sense stays only when its kept senses are current and the
            # frequency list attests it ("pták" stays; "mrdat" = only an obsolete sense, goes)
            if all(OBSOLETE_TAGS & set(str_list(s.get("tags"))) for s in senses):
                self.dropped["vulgar-obsolete"].append(word)
                return
            if word.lower() not in self.ranks:
                self.dropped["vulgar-unattested"].append(word)
                return
        gloss, syn, flags = pick_gloss(senses), pick_syn(entry), entry_flags(entry, senses)
        surname = self.source == "en-wikt" and is_surname_entry(entry, senses)
        person = self.source == "en-wikt" and is_person_name(entry, senses)
        if is_form_of(entry):
            lemmas = form_of_words(entry)
            if any(w in self.lemmas for w in lemmas):
                return                       # the lemma's own `forms` already carry this form
            if not gloss.lower().startswith(TVAR_GLOSS_PREFIX):
                return                       # an oblique case or a verb form: not an entry (§10)
            self.add_row(word, clean(lemmas[0]) if lemmas else word, pos, "", gloss, syn, flags | {"tvar"})
            return
        rule = non_basic_rule(gloss)
        if rule:                             # a declined/conjugated form filed as its own entry
            self.dropped[rule].append(word)
            return
        if not gloss:
            # R1: no clue can be written; checked per entry, because form rows would
            # otherwise survive with only a marker (" (mn. č.)") as their gloss
            if cell_count(word) is not None:
                self.dropped["empty-gloss"].append(word)
            return
        if pos == "verb" and word.endswith("ti") and (ARCHAIC_INF_GLOSS in gloss or word[:-1] in self.lemmas):
            self.drop_clean("archaic-infinitive", word)    # R14: odezírati, láti (the -t verb is the entry)
            self.cleaned_lemmas[word] = "archaic-infinitive"
            return
        if INSULT_RE.search(strip_labels(gloss).lower()):
            self.drop_clean("insult", word)                # R17: haken, grázl (with their forms)
            self.cleaned_lemmas[word] = "insult"
            return
        if self.add_row(word, word, pos, "", gloss, syn, flags, surname, person) and vulgar:
            self.vulgar_kept.append(word)
        nonstandard: set[str] = set()
        forms = merged_forms(entry, word, tables_only=self.source == "en-wikt",
                             skipped=self.dropped["non-table-form"], nonstandard=nonstandard)
        for form, tags in sorted(forms.items()):
            if not is_basic_form(pos, tags):
                continue
            # R20 and R18 depend on this entry's tags; the key counts as seen, so a duplicate entry
            # cannot add it back (the second "Maria" entry would re-add "Marie")
            if form in nonstandard:
                self.drop_clean("nonstandard-form", form)   # R20
                self.seen.add((form, word, pos))
                continue
            if "vl." in flags and "plural" in tags and (NAME_GLOSS_RE.search(gloss) or NAME_ONLY_GLOSS_RE.match(gloss)):
                self.drop_clean("name-plural", form)        # R18: Zity, Anny
                self.seen.add((form, word, pos))
                continue
            if pos in ATTESTED_FORM_POS and form.lower() not in self.ranks:
                continue
            if ATTESTED_FORM_TAG in tags and form.lower() not in self.ranks:
                self.dropped["alternative-unattested"].append(form)
                continue
            extra = {flag for tag, flag in FORM_TAG_FLAGS if tag in tags}
            self.add_row(form, word, pos, " ".join(sorted(tags)), form_gloss(gloss, tags), syn, flags | extra)

    def add_syn(self, syn: list[tuple[str, int, int]], syn_min: int) -> None:
        """SYN2015 lemmas that neither Wiktionary has, as rows without part of speech or gloss.

        A lemma a Wiktionary rule rejected (vulgar, empty gloss, a form filed as an entry) is
        not brought back (``add_row``).
        """
        self.begin_source("syn")
        done: set[str] = set()
        for lemma, _, count in syn:
            if lemma in done:
                rule = "duplicate"
            elif lemma != lemma.lower():
                rule = "capitalised"          # a name; names come from the Wiktionaries
            elif count < syn_min:
                rule = "rare"
            elif cell_count(lemma) is None:
                rule = "not-a-word"
            else:
                rule = ""
            done.add(lemma)
            if rule:
                self.dropped[rule].append(lemma)
            else:
                self.add_row(lemma, lemma, "", "", "", "", set())


# --- output and statistics ----------------------------------------------------
def write_rows(out, rows: list[Row]) -> None:
    out.write("\t".join(COLUMNS) + "\n")
    for r in rows:
        out.write("\t".join((r[1], r[2], r[3], r[4], r[5], r[6], str(r[7]), r[8])) + "\n")


def write_output(path: Path, rows: list[Row]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".gz":
            # mtime 0 and no stored name: the same input gives the same bytes
            with open(path, "wb") as raw, \
                    gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz, \
                    io.TextIOWrapper(gz, encoding="utf-8", newline="\n") as out:
                write_rows(out, rows)
        else:
            with open(path, "w", encoding="utf-8", newline="\n") as out:
                write_rows(out, rows)
    except OSError as exc:
        raise BuildError(f"cannot write {path}: {exc.strerror or exc}")


def write_review_groups(path: Path, members: list[tuple[str, str, str]]) -> None:
    """The words that reach the review: word, source, group, once each (sorted by group, source, word)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as out:
            out.write("word\tsource\tgroup\n")
            for word, source, group in sorted(set(members), key=lambda m: (m[2], m[1], m[0])):
                out.write(f"{word}\t{source}\t{group}\n")
    except OSError as exc:
        raise BuildError(f"cannot write {path}: {exc.strerror or exc}")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def print_stats(rows: list[Row], inputs: list[Path], out_path: Path, builder: Builder) -> None:
    by_pos: dict[str, int] = {}
    by_flag = dict.fromkeys(FLAG_ORDER, 0)
    for r in rows:
        by_pos[r[3]] = by_pos.get(r[3], 0) + 1
        for flag in filter(None, r[8].split(",")):
            by_flag[flag] += 1
    print(f"total: {len(rows)}")
    print(f"base: {sum(1 for r in rows if r[4] == '')}")
    for n in range(alphabet.MIN_LEN, alphabet.MAX_LEN + 1):
        print(f"len {n}: {sum(1 for r in rows if r[0] == n)}")
    for pos, n in sorted(by_pos.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"pos {pos or '(none)'}: {n}")
    for flag, n in by_flag.items():
        print(f"flag {flag}: {n}")
    for rule, words in builder.dropped_by_source["cs-wikt"].items():
        print(f"dropped {rule}: {len(words)}")
    for source, dropped in builder.dropped_by_source.items():
        if source != "cs-wikt":
            for rule, words in dropped.items():
                if words:
                    print(f"{source} dropped {rule}: {len(words)}")
    for (source, group), counts in sorted(builder.review_counts.items()):
        print(f"review {source} {group}: keep {counts['keep']} drop {counts['drop']} missing {counts['missing']}")
    if builder.review is not None:
        print(f"review unused: {len(builder.review) - len(builder.review_used)}")
    if builder.blocklist is not None:
        print(f"blocklist unused: {len(builder.blocklist - builder.blocklist_used)}")

    def source_of(r: Row) -> str:
        return next((s for s, f in SOURCE_FLAGS.items() if f and f in r[8].split(",")), "cs-wikt")
    for source in SOURCE_FLAGS:
        print(f"source {source}: {sum(1 for r in rows if source_of(r) == source)}")
    print(f"attested-by-syn: {sum(1 for r in rows if r[7] > SYN_OFFSET and source_of(r) != 'syn')}")
    for n in range(alphabet.MIN_LEN, alphabet.MAX_LEN + 1):
        here = [r for r in rows if r[0] == n]
        mix = " ".join(f"{s} {sum(1 for r in here if source_of(r) == s)}" for s in SOURCE_FLAGS)
        print(f"len {n} sources: {mix} freq>0 {sum(1 for r in here if r[7] > 0)}")
    kept = sorted(set(builder.vulgar_kept))
    print(f"vulgar-kept: {len(kept)} {' '.join(kept)}".rstrip())
    for path in inputs:
        print(f"sha256 {sha256_of(path)} {path}")
    print(f"output: {out_path} {out_path.stat().st_size} bytes")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--raw", help=f"folder with {RAW_WIKT_NAME} and {RAW_FREQ_NAME}")
    parser.add_argument("--wikt", help="wiktextract JSONL dump (.jsonl or .jsonl.gz)")
    parser.add_argument("--freq", help="frequency list, lines 'word count'")
    parser.add_argument("--en-wikt", help="Czech entries of the English Wiktionary (kaikki.org JSONL); words only")
    parser.add_argument("--syn", help="ČNK SYN2015 lemma list (.tsv, or the .zip holding it)")
    parser.add_argument("--syn-min", type=int, default=SYN_MIN,
                        help=f"SYN frequency from which a lemma missing elsewhere becomes a row (default {SYN_MIN})")
    parser.add_argument("--review", help="review verdicts of the new rows (TSV: word source group verdict note)")
    parser.add_argument("--export-review", help="write the rows that reach the review (word source group) to FILE")
    parser.add_argument("--blocklist", help="hand blocklist (TSV: word lemma note; empty lemma = every row of the word)")
    parser.add_argument("--out", required=True, help="output; gzip when it ends with .gz")
    args = parser.parse_args(argv)
    try:
        if args.raw and (args.wikt or args.freq):
            raise BuildError("use either --raw DIR or --wikt FILE --freq FILE, not both")
        if args.raw:
            raw = Path(args.raw).expanduser()
            if not raw.is_dir():
                raise BuildError(f"raw folder not found: {raw}")
            wikt, freq = raw / RAW_WIKT_NAME, raw / RAW_FREQ_NAME
        elif args.wikt and args.freq:
            wikt, freq = Path(args.wikt).expanduser(), Path(args.freq).expanduser()
        else:
            raise BuildError("give --raw DIR, or both --wikt FILE and --freq FILE")
        en_wikt = Path(args.en_wikt).expanduser() if args.en_wikt else None
        syn_path = Path(args.syn).expanduser() if args.syn else None
        review_path = Path(args.review).expanduser() if args.review else None
        block_path = Path(args.blocklist).expanduser() if args.blocklist else None
        inputs = [p for p in (wikt, freq, en_wikt, syn_path, review_path, block_path) if p is not None]
        for path in inputs:
            if not path.is_file():
                raise BuildError(f"input not found: {path}")
        if args.syn_min < 1:
            raise BuildError(f"--syn-min must be at least 1, got {args.syn_min}")
        out_path = Path(args.out).expanduser()

        syn = read_syn(syn_path) if syn_path else []
        builder = Builder(read_freq(freq), syn, read_review(review_path) if review_path else None,
                          read_blocklist(block_path) if block_path else None)
        builder.collect_lemmas(iter_czech_entries(wikt))          # pass 1
        for entry in iter_czech_entries(wikt):                    # pass 2
            builder.add_entry(entry)
        if en_wikt:
            # its lemmas join the index only now: a Czech form-of row must not depend on them
            builder.begin_source("en-wikt")
            builder.collect_lemmas(iter_czech_entries(en_wikt))
            for entry in iter_czech_entries(en_wikt):
                builder.add_entry(entry)
        if syn:
            builder.add_syn(syn, args.syn_min)
        rows = sorted(builder.rows, key=lambda r: r[:4])
        write_output(out_path, rows)
        if args.export_review:
            write_review_groups(Path(args.export_review).expanduser(), builder.review_members)
        print_stats(rows, inputs, out_path, builder)
    except BuildError as exc:
        print(f"build_wordlist: error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
