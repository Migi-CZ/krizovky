"""Read-only inspection of the slice 4e sources against today's word list (unit 1).

    python3 -I scripts/inspect_sources.py --raw RAW_DIR

S1 = ``kaikki.org-dictionary-Czech.jsonl`` (English Wiktionary, Czech entries),
S2 = ``syn2015_lemma_utf8.tsv`` (ČNK SYN2015 lemma list). The raw files are only parsed;
nothing in the raw folder is imported or executed. Prints format checks and the
per-length tables of words that would be new.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from krizovky import alphabet  # noqa: E402
import build_wordlist as bw  # noqa: E402

import argparse  # noqa: E402
import collections  # noqa: E402
import gzip  # noqa: E402
import json  # noqa: E402

S1_NAME = "kaikki.org-dictionary-Czech.jsonl"
S2_NAME = "syn2015_lemma_utf8.tsv"
LENGTHS = range(4, 9)
PSEUDO_FORM_TAGS = frozenset({"table-tags", "inflection-template", "class"})


def key(word: str) -> str:
    return alphabet.normalize(word)


def read_words(path: Path) -> list[tuple[str, str, str, str, int, str]]:
    """(word, lemma, pos, form, freq, flags) of the main word list."""
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        fh.readline()
        for line in fh:
            c = line.rstrip("\n").split("\t")
            rows.append((c[0], c[1], c[2], c[3], int(c[6]), c[7]))
    return rows


def ncells(word: str) -> int:
    return len(alphabet.tokenize(word))


def table(title: str, columns: list[str], data: dict[int, list[object]]) -> None:
    print(f"\n{title}")
    print("| len | " + " | ".join(columns) + " |")
    print("|---" * (len(columns) + 1) + "|")
    for n in LENGTHS:
        print(f"| {n} | " + " | ".join(str(v) for v in data[n]) + " |")


def inspect_s1(raw: Path, existing: set[str]) -> dict[int, set[str]]:
    path = raw / S1_NAME
    lang, pos, sense_tags, form_tags = (collections.Counter() for _ in range(4))
    lines = 0
    with open(path, encoding="utf-8") as fh:
        for lines, line in enumerate(fh, 1):
            e = json.loads(line)
            lang[e.get("lang_code")] += 1
            pos[e.get("pos")] += 1
            for s in bw.senses_of(e):
                sense_tags.update(bw.str_list(s.get("tags")))
            for f in e.get("forms") or []:
                if isinstance(f, dict):
                    form_tags.update(bw.str_list(f.get("tags")))
    print(f"S1 {path.name}: {lines} lines, lang_code {dict(lang)}")
    print("S1 pos: " + ", ".join(f"{p} {n}" for p, n in pos.most_common()))
    known = set().union(bw.DROP_SENSE_TAGS, bw.OBSOLETE_TAGS, *(g for _, g in bw.SENSE_FLAGS))
    print("S1 sense tags covered by the build tables: "
          + ", ".join(f"{t} {sense_tags[t]}" for t in sorted(known) if sense_tags[t]))
    register = ("colloquial", "offensive", "slur", "humorous", "nonstandard", "rare", "dated", "historical",
                "Common-Czech", "Bohemia", "Moravia", "Silesia", "proscribed", "misspelling", "euphemistic")
    print("S1 register tags NOT in the tables: " + ", ".join(f"{t} {sense_tags[t]}" for t in register if sense_tags[t]))
    print("S1 form tags (top 40): " + ", ".join(f"{t} {n}" for t, n in form_tags.most_common(40)))

    # Simulate today's rules on S1 alone; the lemma index spans both Wiktionaries.
    ranks = bw.read_freq(raw / bw.RAW_FREQ_NAME)
    builder = bw.Builder(ranks)
    builder.collect_lemmas(bw.iter_czech_entries(raw / bw.RAW_WIKT_NAME))
    builder.collect_lemmas(bw.iter_czech_entries(path))
    for entry in bw.iter_czech_entries(path):
        builder.add_entry(entry)
    print(f"S1 rows under today's rules: {len(builder.rows)}; dropped "
          + ", ".join(f"{r} {len(w)}" for r, w in builder.dropped.items() if w))

    kinds = ("lemma", "lemma vl.", "form: pseudo", "form: no case tag", "form: nominative/infinitive")
    new: dict[str, dict[int, set[str]]] = {k: collections.defaultdict(set) for k in kinds}
    examples: dict[str, list[str]] = collections.defaultdict(list)
    for r in builder.rows:
        n, word, form, flags = r[0], r[1], r[4], r[8]
        if n not in LENGTHS or key(word) in existing:
            continue
        tags = set(form.split())
        if not form:
            kind = "lemma vl." if "vl." in flags else "lemma"
        elif tags & PSEUDO_FORM_TAGS:
            kind = "form: pseudo"
        elif tags & {"nominative", "infinitive"}:
            kind = "form: nominative/infinitive"
        else:
            kind = "form: no case tag"
        new[kind][n].add(key(word))
        if len(examples[kind]) < 12:
            examples[kind].append(f"{word}<{r[2]}>[{form}]" if form else word)
    table("S1: new distinct words (not in data/words.tsv.gz) by kind", list(kinds),
          {n: [len(new[k][n]) for k in kinds] for n in LENGTHS})
    for k in kinds:
        print(f"  e.g. {k}: {' '.join(examples[k])}")
    no_case_tags = collections.Counter()
    for r in builder.rows:
        tags = set(r[4].split())
        if r[4] and not tags & (PSEUDO_FORM_TAGS | {"nominative", "infinitive"}):
            no_case_tags[r[4]] += 1
    print("S1 'no case tag' form tag sets (top 15): " + ", ".join(f"[{t}] {n}" for t, n in no_case_tags.most_common(15)))
    return new


def inspect_s2(raw: Path, rows, existing: set[str], s1: dict[str, dict[int, set[str]]], syn_min: int) -> None:
    path = raw / S2_NAME
    widths, col8 = collections.Counter(), collections.Counter()
    lemmas: list[tuple[int, str, int, int]] = []    # line number = rank, lemma, col3, col4
    col1_filled = col4_sum = 0
    with open(path, encoding="utf-8") as fh:
        for number, line in enumerate(fh, 1):
            c = line.rstrip("\n").split("\t")
            widths[len(c)] += 1
            col8[c[7] if len(c) > 7 else None] += 1
            col1_filled += c[0] != ""
            col4_sum += int(c[3]) == int(c[4]) + int(c[5]) + int(c[6])
            lemmas.append((number, c[1], int(c[2]), int(c[3])))
    sorted_c3 = all(a[2] >= b[2] for a, b in zip(lemmas, lemmas[1:]))
    sorted_c4 = all(a[3] >= b[3] for a, b in zip(lemmas, lemmas[1:]))
    print(f"\nS2 {path.name}: {len(lemmas)} lines, columns {dict(widths)}, col8 {dict(col8)}")
    print(f"S2 col1 filled on {col1_filled} lines (sparse: not the line rank); sorted by col3: {sorted_c3}, "
          f"by col4: {sorted_c4}; col4 = col5+col6+col7 on {col4_sum} lines; "
          f"min col3 {min(l[2] for l in lemmas)}, min col4 {min(l[3] for l in lemmas)}")
    print("S2 head: " + "; ".join(f"{r} {l} {a} {b}" for r, l, a, b in lemmas[:5]))

    capital = sum(1 for _, l, *_ in lemmas if l[:1].isupper())
    letters = [(r, l, f) for r, l, f, _ in lemmas if bw.cell_count(l) is not None]
    print(f"S2 capitalised: {capital} ({100 * capital / len(lemmas):.1f} %); Czech letters only, 2–15 cells: "
          f"{len(letters)}; of them lowercase: {sum(1 for _, l, _ in letters if l == l.lower())}")

    lower_syn: dict[str, tuple[int, int]] = {}
    for r, l, f in letters:
        if l == l.lower():
            lower_syn.setdefault(key(l), (r, f))
    s1_new = {n: s1["lemma"][n] | s1["lemma vl."][n] | s1["form: nominative/infinitive"][n] for n in LENGTHS}
    any_syn = {key(l) for _, l, _ in letters}
    kinds = ("lemma", "lemma vl.", "form: nominative/infinitive", "form: no case tag")
    table("S1 new words attested in S2 (any case, any frequency): attested / new",
          list(kinds), {n: [f"{len(s1[k][n] & any_syn)} / {len(s1[k][n])}" for k in kinds] for n in LENGTHS})
    thresholds = (10, syn_min, 50, 100)
    data = {}
    examples: list[str] = []
    for n in LENGTHS:
        new_at = []
        for t in thresholds:
            new_at.append(len({k for k, (r, f) in lower_syn.items()
                               if f >= t and k not in existing and ncells(k) == n}))
        both = {k for k, (r, f) in lower_syn.items() if f >= syn_min and k not in existing and ncells(k) == n}
        new_at.append(len(both - s1_new[n]))
        data[n] = new_at
    table("S2: new lowercase lemmas (not in data/words.tsv.gz) by SYN frequency floor (col3)",
          [f"≥ {t}" for t in thresholds] + [f"≥ {syn_min} and not new from S1"], data)
    for k, (r, f) in lower_syn.items():
        if f >= syn_min and k not in existing and 4 <= ncells(k) <= 8 and r % 97 == 0 and len(examples) < 25:
            examples.append(f"{k.lower()}({f})")
    print("  e.g. " + " ".join(examples))

    att = {}
    for n in LENGTHS:
        here = [r for r in rows if ncells(r[0]) == n]
        zero = [r for r in here if r[4] == 0]
        gained = [r for r in zero if key(r[0]) in lower_syn]
        att[n] = [len(here), sum(1 for r in here if r[4] > 0), len(gained),
                  f"{100 * (len(here) - len(zero) + len(gained)) / len(here):.0f} %"]
    table("S2 as attestation of today's rows (freq 0 -> 50 000 + SYN rank)",
          ["rows", "freq>0 today", "freq 0 but in SYN (lowercase)", "freq>0 share after"], att)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--raw", required=True, help="folder with the raw downloads")
    parser.add_argument("--words", default=str(ROOT / "data" / "words.tsv.gz"))
    parser.add_argument("--syn-min", type=int, default=20)
    args = parser.parse_args()
    raw = Path(args.raw).expanduser()
    rows = read_words(Path(args.words))
    existing = {key(r[0]) for r in rows}
    base = {}
    for n in LENGTHS:
        here = [r for r in rows if ncells(r[0]) == n]
        base[n] = [len(here), len({key(r[0]) for r in here}), sum(1 for r in here if "vl." in r[5].split(",")),
                   sum(1 for r in here if r[4] > 0)]
    table(f"today: {Path(args.words).name}, {len(rows)} rows", ["rows", "distinct words", "vl.", "freq>0"], base)
    s1 = inspect_s1(raw, existing)
    inspect_s2(raw, rows, existing, s1, args.syn_min)
    return 0


if __name__ == "__main__":
    sys.exit(main())
