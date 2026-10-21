# Křížovky — build and operation notes

Technical description for anyone who wants to change, rebuild or extend the generator.
For users: `README.md` (Czech) or `README.en.md` (English).

## 0) Metadata
- **Name:** Křížovky (Czech crossword generator)
- **Version:** 0.1.0 (`krizovky/__init__.py`); this copy: 2026-10-21
- **Author:** Michal Stasiak
- **Status:** active, hobby project
- **Licences:** code MIT (`LICENSE`); dictionary CC BY-SA 4.0 (`data/LICENSES.md`)

---

## 1) Purpose and scope
**Purpose**
- Build a Czech crossword for print from the command line: mainly the *švédská křížovka*
  (Swedish style as in Czech puzzle magazines: clues inside the grid cells, dense fill, a tajenka
  in 1–3 shaded rows), plus two simpler modes (column puzzle, numbered word-web).

**Out of scope**
- Writing the clues: the tool asks for them through `request.json`; a person or a language
  model writes `clues.json`.
- Languages other than Czech: the dictionary and the alphabet rules are Czech.
- A web app, online dictionaries, an API key (none is needed).

**Manual steps**
- Writing or checking the clues; printing.

---

## 2) Architecture overview
- **Entry point:** `python3 -m krizovky <command>` (`krizovky/cli.py`), run from the repository folder.
- **Source of truth:** the dictionary `data/words.tsv.gz` + `data/extra_words.tsv`; for one puzzle,
  its `puzzle.json`.
- **Output:** one folder per puzzle (`--out DIR`): `puzzle.json`, `puzzle.svg`, `solution.svg`,
  `solution.md`, `request.json` while clues are missing, PDFs with `--pdf`.
- **Run time:** a Swedish 16×12 fill takes seconds to about a minute (limit `--timeout`, default 180 s).

> A pure-Python CLI turns a size and a tajenka into a filled grid from a local dictionary, asks for
> clues through a JSON file round trip and renders A4 SVG, with LibreOffice converting it to PDF.

---

## 3) Components and dependencies
### Code (`krizovky/`)
| Module | Role |
|---|---|
| `cli.py` | commands `generate`, `clues`, `render`, `validate`, `words`; exit codes |
| `alphabet.py` | Czech cells (`CH` = one cell), normalisation, match keys |
| `wordlist.py` | loads `data/words.tsv.gz` + `data/extra_words.tsv`, index by length |
| `pattern_swedish.py` | mode C: clue-cell layout of the grid, shape knobs, `shape_stats` |
| `filler_dense.py` | mode C: CSP fill from the dictionary, pattern repair when a fill dies |
| `placer_column.py`, `placer_freeform.py`, `grid.py` | modes A and B |
| `clues.py` | `request.json` / `clues.json` exchange |
| `model.py` | Entry, Placement, Puzzle and `puzzle.json` |
| `render_svg.py`, `render_swedish.py` | A4 SVG of the puzzle and the solution, `solution.md` |
| `render_pdf.py` | SVG → PDF through headless LibreOffice |
| `validate.py` | crossword rules (SČHAK directive) and the Swedish rules |

### Scripts (`scripts/`)
- `build_wordlist.py` — builds the dictionary from the raw downloads.
- `inspect_sources.py` — read-only comparison of the raw sources with the current dictionary.
- `bench_fill.py` — benchmark of the dense filler.
- `grid_stats.py` — shape numbers of hand-transcribed grids.

### External dependencies
- Python 3.10 or newer, standard library only (the filler uses `int.bit_count()`, new in 3.10;
  tested on 3.14 under Linux).
- LibreOffice (`soffice` or `libreoffice` on `PATH`) for `--pdf` only. The SVGs embed no fonts
  (`font-family` DejaVu Sans, Noto Sans, Arial, sans-serif); clue text is sized for DejaVu Sans.

---

## 4) Configuration and parameters
```
python3 -m krizovky generate --mode column|web|swedish --tajenka TEXT [--words FILE] [--theme T]
                             [--width 11] [--size 11|11x15] [--tries 20]
                             [--timeout 180] [--no-names] [--header TEXT] [--data FILE]   # swedish
                             [--match strict|length|none] [--no-ch] [--seed N] [--title T] [--pdf] --out DIR
python3 -m krizovky clues DIR [--pdf]        # apply clues.json, re-render
python3 -m krizovky render DIR [--pdf]       # SVG (+PDF) + solution.md
python3 -m krizovky validate DIR|puzzle.json
python3 -m krizovky words [--len N] [--pattern ..E..] [--contains E@3] [--pos noun] [--base]
                          [--exclude FLAG] [--match m] [--random N] [--limit 20] [--data FILE]
python3 -m unittest discover -s tests        # tests
```

The default `--mode` is `column`; pass `--mode swedish` for the magazine crossword.

### Mode C — švédská křížovka (clues in the cells)
```bash
python3 -m krizovky generate --mode swedish --size 11x12 --tajenka "RÁNO / MOUDŘEJŠÍ / VEČERA" \
    --title "…" --header "…" --out out/svedska
```

Words come from the dictionary (`data/words.tsv.gz`, §5), not from `--words` (refused,
exit 1). The `--tajenka` is written as runs separated by `/`; each run is one shaded row of the
grid with its own label (`1. díl tajenky`, `2. díl tajenky`, …; one run is labelled `tajenka`).
`--size` is rows × columns. The filler (`krizovky/filler_dense.py`) builds a clue-cell pattern and
fills it, repairing the pattern when a fill dies. On success it prints one line, e.g.
`filled 16x12 in 7.0 s: 63 words, 7 repairs, inner blocks 17 %`; if no fill is found within the
time limit it exits 2 with `no fill of 11x12 for this tajenka within 180 s; try --timeout, a bigger
grid or shorter runs`. The magazine sizes are `--size 11x12` and `--size 16x12`; a fill takes
seconds to about a minute, rarely longer (`--timeout`, default 180 s; the search budget is 20 000
nodes per attempt).

Options (besides `--size`, `--seed`, `--match`, `--theme`, `--title`, `--pdf`, `--out`):

- `--timeout SECONDS` — time limit for the fill (default 180).
- `--no-names` — leave proper names (`vl.` rows) out of the dictionary (names are used by default).
- `--header TEXT` — text block printed above the grid (default: `--theme`; none: the grid moves up).
- `--data FILE` — other word list (default `data/words.tsv.gz`).
- `--no-ch` is refused: the filler always treats CH as one cell.

### Mode A — doplňovačka with the tajenka in a column
```bash
python3 -m krizovky generate --mode column --tajenka "DEN ZEMĚ" --words examples/den_zeme.txt \
    --theme "Den Země" --title "Den Země" --pdf --out out/denzeme
```

### Mode B — křížovka with numbered clues (word-web)
```bash
python3 -m krizovky generate --mode web --size 11 --words examples/20words.txt \
    --tajenka SVOBODA --title Svoboda --pdf --out out/svoboda
```

Words are woven into a free grid of at most `--size` cells (`N` or `RxC`); every word
crosses another one, clues are numbered Vodorovně / Svisle, and the tajenka is spread
over cells numbered 1..k with answer boxes under the grid. Words that do not fit are
printed as `dropped (n): …` (and listed in `solution.md`); words excluded before the
search (longer than the grid, duplicates, the tajenka itself) as `unused (n): …`.
`--tries` sets the number of random restarts (default 20); `--seed` changes the layout.
Capacity with words of 5–8 letters: about 10 words at `--size 11`, 13 at 13, 17 at 15;
give more words than that and let the tool drop the rest.
It fails (exit 2) only when fewer than 2 words can be placed or the tajenka letters are
not in the grid.

### Alphabet
`CH` is one cell (`--no-ch` splits it; `c|h` in a word forces a split).
Diacritics are kept (`--match strict`); `--match length` merges long/short vowels,
`--match none` ignores diacritics.

---

## 5) Data model
**Dictionary row** (`data/words.tsv.gz`, 111 587 rows; `data/extra_words.tsv`, same columns, no gzip)
- Key: `(word, lemma, pos)`.
- Columns: `word lemma pos form gloss syn freq flags`.
- `form` is empty for the lemma itself, otherwise the tags of the kept form (`nominative plural`,
  `alternative`, `comparative`), which the clue must mirror: the gloss of such a row ends with the
  magazine marker `(mn. č.)`, `(2. st.)` or `(3. st.)`.
- `freq` = rank in the frequency list, 0 = absent.
- `flags` use the magazine markers `zkr.` `vl.` `zast.` `kniž.` `básn.` `hovor.` `nář.` and `tvar`
  (a 1st-case form whose lemma is missing; `symbol` rows such as SPZ codes and units also get
  `zkr.`), plus the source flags `en-wikt` and `syn`.

**Word list for modes A and B:** one word per line, optional `TAB` + clue, `#` comments
(`examples/den_zeme.txt`).

**Puzzle** (`puzzle.json`, `krizovky/model.py`): mode, width, height, match, entries (answer, cells,
clue), placements, tajenka cells, blocks, dropped words, meta (seed, timings, the dictionary rows
of the answers).

**Clue round trip**
- `request.json`: `kind`, `instructions` (in Czech, for the clue writer), `items` with `answer`,
  `cells`, `length`, `pos`, `gloss`, `synonyms`, `form`, `flags`, `freq`, and a `schema`.
- `clues.json`: `{"version": 1, "clues": {"ANSWER": "clue", …}, "pomucka": ["anis", …]}`;
  a clue has at most 28 characters in mode C and may not contain the answer stem.

---

## 6) Data mapping (sources → dictionary)
| Source | Transformation | Target | Notes |
|---|---|---|---|
| Czech Wiktionary extract (kaikki.org) | basic forms only, leak rules R1–R25 | rows with gloss | CC BY-SA 4.0 |
| English Wiktionary, Czech entries (kaikki.org) | words, part of speech, 1st-case cells of inflection tables; no English text | rows flagged `en-wikt` | CC BY-SA 4.0 |
| hermitdave `cs_50k.txt` | rank | `freq` | MIT |
| ČNK SYN2015 lemma list | attests rows (`freq` = 50 000 + SYN rank when `cs_50k.txt` lacks the word); adds lower-case lemmas with ≥ `--syn-min` (20) occurrences | `freq`, rows flagged `syn` | CC BY 4.0 |
| `data/source_review.tsv` | model review verdicts per word group | keep / drop | `--review` |
| `data/blocklist.tsv` | hand verdicts per word (§ Blocklist below) | drop | `--blocklist`, MIT |
| `data/extra_words.tsv` | merged on every load; a row whose `(word, lemma, pos)` exists is ignored | crossword-ese | hand-written |

Licences, checksums and attribution: `data/LICENSES.md`.

**Basic forms only**, as the SČHAK directive §10 requires: nouns, adjectives, pronouns and
numerals in the 1st case singular or plural, verbs in the infinitive. Dialectal variants of a
form are dropped, and a form of an adjective is kept only when the frequency list attests it
(Wiktionary generates full tables).

**Leak rules:** an entry without a gloss is dropped, as are entries whose gloss names a case
behind a label (`(po předložce) dativ…`), clitic forms (`příklonný tvar`), short adjective forms
(`jmenný tvar přídavného jména`), entries that lost a vulgar sense and are only obsolete or absent
from the frequency list, and `alternative` spellings the frequency list does not attest. The build
prints one `dropped <rule>: <n>` line per rule and a `vulgar-kept:` list of words that keep a
non-vulgar sense, for a human check. A word already in the Czech Wiktionary keeps its row, and a
word a rule dropped there is not brought back. `--exclude-flags en-wikt` / `syn` measures what a
source adds.

**Cleanup rules R9–R25** (rule names as in `DROP_RULES` of `scripts/build_wordlist.py`; R9–R12 are
the filters on the two extra sources, R13–R25 were added in slice 7b and run on every source). A
word a 7b rule dropped is never brought back by a later source.

| Rule | Drops |
|---|---|
| R13 `non-infinitive` | verb row whose form is empty or `alternative` and whose word does not end in `t`, `ti`, `ci` |
| R14 `archaic-infinitive` | verb lemma ending in `ti` that has a `-t` twin or is glossed as an infinitive form (ODEZÍRATI) |
| R15 `bad-initial` | word starting with `ě`, `ů`, `ý` |
| R16 `name-no-gloss` | en-wikt row without a review group whose every English sense names a person (given name, diminutive, nickname, surname) |
| R17 `insult` | entry glossed as an insult (`nadávka`, `hanlivé označení`), with its forms, in every source |
| R18 `name-plural` | plural of a `vl.` name or nickname (Zity, Ály, Pepové) |
| R19 `unattested-abbrev` | `zkr.` row of 4 or more cells absent from the frequency list (known abbreviations come back through `extra_words.tsv`) |
| R20 `nonstandard-form` | form tagged `v obecném jazyce` / `lidově` |
| R21 `name-possessive` | capitalised adjective row (Eliin, Janův) |
| R22 `dialect` | every `nář.` row and rows whose gloss carries a dialect label (replaces the 2026-10-19 rule that dialectal lemmas stay) |
| R23 `obscure-surname` | cs-wikt `vl.` surname with fewer than 100 SYN2015 occurrences |
| R24 `colloquial-name` | `vl.` row that is also `hovor.` (Budějky, Pánbíček) |
| R25 `unattested-slang` | en-wikt `hovor.` row absent from the frequency list (kasr, obyč) |

Famous persons and known abbreviations that R19 or R23 dropped are written back by hand into
`data/extra_words.tsv`, with glosses written for this project (no Wiktionary text, the file is MIT).

**Blocklist** (`data/blocklist.tsv`, TSV `word lemma note`; an empty `lemma` blocks every row of
the word; 376 entries). The classes: vulgar and crude words, insults and slurs, explicit sexual terms,
Common-Czech spellings that have a standard twin (sejr, bejt, mlíko, von), and single leaks the rules
miss (SYN artefacts, table artefacts). The content bar is that of a company crossword: no sexual
terms, insults, vulgar words or unlabelled Common Czech (owner, 2026-10-21). Words with a neutral
sense (gay, lesba, kondom, sexualita, erotika, SEX), famous persons and words labelled `hovor.` stay.
To lift a class, delete its lines and rebuild; the build prints `blocklist unused: n` for lines that
no longer match a row.

**Crossword-ese** the Wiktionary lacks grows by hand in `data/extra_words.tsv`: former district SPZ
codes and 2-letter chemical symbols (`symbol`, `zkr.`), Roman numerals (`num`, gloss `římsky 4`),
solmization syllables and Greek letters, short foreign words (`cizí`, gloss `anglicky ano`),
interjections, nicknames (`name`, `vl.`) and short rivers, towns and hills (`vl.`).

**Rebuild** from the raw downloads (not in the repository; URLs in `data/LICENSES.md`), parsed with
`python3 -I` because they are untrusted data; `RAW_DIR` is the folder holding them:

```bash
python3 -I scripts/build_wordlist.py --raw RAW_DIR \
    --en-wikt RAW_DIR/kaikki.org-dictionary-Czech.jsonl \
    --syn RAW_DIR/syn2015_lemma_utf8.zip --review data/source_review.tsv \
    --blocklist data/blocklist.tsv --out data/words.tsv.gz
```

The build is deterministic: two runs give a byte-identical file, 111 587 rows, sha256
`071c10ba8112ce56502fffe0775b66eb3563bec4aa40ce2e5a0ad767cfb88624`. After a rebuild the sample grid
changes: rerun the README command, write the clues again and redo the PDFs.

**Look up words:**
```bash
python3 -m krizovky words --len 7 --contains E@3          # 7 cells, E in cell 3 (first 20)
python3 -m krizovky words --pattern "..CH." --match none  # pattern, CH = one cell
python3 -m krizovky words --len 3 --base --limit 0        # all 3-cell lemmas (no plurals, no variants)
python3 -m krizovky words --random 50 --exclude tvar      # sample for a quick look
```

Output rows are `word pos form flags gloss`; the match count goes to stderr.

---

## 7) Processing logic (mode C)
1. **Input:** size, tajenka runs, options (`cli.py`).
2. **Load the dictionary:** `wordlist.py` reads both files; `--no-names` drops `vl.` rows.
3. **Pattern:** `pattern_swedish.py` lays out clue cells: row 0 and column 0 are clue cells, every
   white cell is in an across and a down word, the tajenka runs go across. Shape knobs follow the
   magazine shape (`--inner-share 0.13` = blocks among the inner cells, `--max-len 11`, at most
   `--long-slots 2` words longer than `--soft-len 8`, `--stump 0.1` against 2–3-cell stumps).
4. **Fill:** `filler_dense.py` searches word by word. When an attempt dies, it repairs the pattern
   like a setter would: the cell where the across and the down word collided most often becomes a
   clue cell, and the search restarts on the repaired pattern, until the inner share would pass the
   repair cap (0.17 with names, 0.20 without).
5. **Validate:** `validate.py` checks the generated puzzle (a failure here is a bug, exit 2).
6. **Write:** `puzzle.json`, SVGs, `solution.md`; `request.json` and exit 3 when clues are missing.
7. **Clues:** `clues DIR` reads `clues.json`, checks each clue, re-renders (and converts with `--pdf`).
   While clues are missing `request.json` is rewritten with the missing ones only; when none is missing it is
   deleted (a request of another kind, theme words, stays).

**Clue round trip in mode C:** `request.json` gives every item the answer plus `gloss`, `form`,
`flags` and `freq` from the dictionary; the tajenka entries are not asked for (their label is the
clue). `"clues"` maps each answer to a clue of at most 28 characters in magazine style (`zkr.`,
`(mn. č.)`, `zast.`, …), and the optional `"pomucka"` lists the answers a solver cannot know,
printed as given (`"pomucka": ["anis", "Denali", "MTI"]`). In modes A and B, `--theme` without
`--words` writes a `theme_words` request instead; `clues.json` with `theme_words` is picked up by
the next `generate` run.

**The sheet:** clue text inside the cells in upper case, no arrows; a clue applies to the word
starting right of it (across) or below it (down). A split cell has a line across the middle: the
upper half is the across clue, the lower half the down clue. Dead cells are white with a black
disc ●. The tajenka runs are grey and each is labelled in the clue cell before it. Under the grid
come the `Pomůcka:` line (when `clues.json` names any) and the answer boxes for the tajenka.
`solution.svg` fills the letters and `solution.md` lists the answers by position.
`python3 -m krizovky validate DIR` also checks the Swedish rules (every cell a letter or a block,
every letter in an across and a down word, every word has its clue cell, every tajenka run is a
whole word).

---

## 9) Error handling
| Exit code | Meaning | Typical cause |
|---|---|---|
| 0 | ok | — |
| 1 | bad input | `--words` in mode C, empty or broken word list, unreadable `puzzle.json`, missing LibreOffice for `--pdf` |
| 2 | placement failed | no fill within `--timeout`; in mode B fewer than 2 words placed; `validate` found violations; also a command-line syntax error (argparse prints `usage:` and exits 2) |
| 3 | clues missing | `request.json` written; fill `clues.json` and run `clues` |

Errors print one `error: …` line, no traceback. A clue that contains the answer stem is not applied: `clues` prints a `WARNING: clue for …` line and keeps the entry's previous clue, or leaves it missing (exit 3). A missing LibreOffice gives
`LibreOffice (soffice) not found on PATH; install it or skip the PDF step`.

---

## 12) Tests and benchmark
```bash
python3 -m unittest discover -s tests        # 417 tests; PdfTests need LibreOffice
python3 scripts/bench_fill.py --runs 20                                        # 11x12 + 16x12: success, shape, word quality
python3 scripts/bench_fill.py --sizes 11x12 --runs 5 --show --save out/bench   # print a grid, keep puzzle.json
python3 -m krizovky validate out/bench/11x12_s0
```

The benchmark options: `--match`, `--names` (admit `vl.`), `--exclude-flags FLAG …` (leave out rows
with these flags, e.g. `zkr.`), `--timeout`, `--jobs`, search limits (`--node-limit`, `--max-branch`,
`--sample`, `--patterns-per-fill`), `--repair-cap`, `--no-repair` (fixed-pattern loop);
`--block-share` is deprecated. The shape table compares the filled patterns with the magazine
targets (blocks ≤ 27 %, mean word ≥ 4.5, 2–3-cell words ≤ 38 %); `--magazine FILE …` adds rows for
hand-transcribed grids.

Grid transcription format for `grid_stats.py` and `--magazine`: one line per row, `#` = clue or
black cell, `.` = letter, `=` = tajenka letter; `python3 scripts/grid_stats.py GRID.txt …` prints
block shares, word lengths and how the clue cells sit (`pattern_swedish.shape_stats`).

Last benchmark (20 runs per size, `--names --node-limit 20000 --timeout 120`, dictionary of 111 587
rows): 20/20 fills on 11×12 and 19/20 on 16×12 (one run out of time at 120 s), 0 validate failures,
mean word length 4.3 / 4.4, median 20.9 / 16.1 s, 90th percentile 69.0 / 39.4 s. The cleanup removed
short words, so fills take longer than before it (4.6 / 13.9 s median); the CLI limit is therefore
`--timeout 180`.

---

## 13) Operational notes and known limits
- Odd words can still get into a grid: rare words with a gloss (AAK, KUTIN), rare names, leftovers
  of the `syn` and `en-wikt` sources the rules do not catch. Check every answer and clue before
  printing; `--seed N` gives another grid; add a word you do not want to `data/blocklist.tsv` and
  rebuild.
- A long word in a clue is cut between syllables by a rule of thumb (`render_swedish.syllable_breaks`, no
  dictionary); foreign words and compounds can be cut in the wrong place (PŘEDV-STUP-NÍ).
- The tajenka rows are partial rows and the clue cells are scattered; magazines use full-width
  tajenka rows and a diagonal staircase of split cells.
- 11×12 grids reach a mean word length of 4.4 (magazine target 4.5).
- `--pdf` starts LibreOffice; close open LibreOffice windows first, or convert the SVG yourself.
- Do not edit `data/words.tsv.gz` by hand; add words to `data/extra_words.tsv` or rebuild.

---

## 14) Change log
| Date | Version | Change | Author |
|---|---|---|---|
| 2026-10-21 | 0.1.0 | first shared copy | Michal Stasiak |
