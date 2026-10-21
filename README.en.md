# Křížovky – a Czech Swedish-style crossword generator

[Česká verze](README.md)

The program builds a Czech **švédská křížovka**, the Swedish-style crossword of Czech puzzle magazines: the clues sit inside the grid cells, the words fill the whole grid and a hidden phrase (the *tajenka*) runs through one to three shaded rows. You give the grid size, the tajenka and a title. The program fills the grid from its own dictionary of more than 110,000 Czech words and lists the words that need clues. Once the clues are in, it renders a printable sheet (SVG and PDF) and the solution.

**The tool is Czech only.** The dictionary is built from Czech sources (Czech Wiktionary, the Czech entries of the English Wiktionary, Czech frequency lists), the alphabet rules are Czech (`CH` is one cell, diacritics count), and the clue instructions in `request.json` ask for Czech clues. An English version would need an English word database in the same format (`data/words.tsv.gz`, described in [DEVELOPMENT.md](DEVELOPMENT.md)), English clue instructions and a check of the alphabet rules.

A finished sample is in [`examples/eko_krizovka/`](examples/eko_krizovka/): the [puzzle](examples/eko_krizovka/puzzle.pdf) and the [solution](examples/eko_krizovka/solution.pdf). The tajenka is SLAVÍME / DEN / ZEMĚ ("we celebrate Earth Day"); the grid has 16 rows and 12 columns.

## Quick start with an AI agent (recommended)

The program builds the grid itself, but the clues are written by a person or a language model. You do the least work if you hand both to an AI agent that can run commands in a terminal, for example Claude Code. The agent runs the program, writes the clues, checks the puzzle and produces the files for printing. You supply the topic and the tajenka.

1. You need Python 3.10 or newer and an AI agent with terminal access.
2. Unpack the `krizovky` folder and start the agent in it (for Claude Code, run `claude`).
3. Paste a request, adapted to your topic. Split the tajenka into parts with slashes; each part needs 2 to 11 letters (for the 16x12 size):

```text
Make a Swedish crossword. Follow README.en.md, section "Manual steps".
Topic: environmental protection. Tajenka: SLAVÍME / DEN / ZEMĚ. Size: 16x12.
1. Generate the grid and read the words in request.json. If a word does not suit a
   crossword for a wider audience (vulgar, dialect, too specialised or obsolete),
   generate the grid again with a different --seed.
   Try at most three times, then take the best grid.
2. Write the clues in Czech into clues.json, following the instructions in request.json.
3. Run clues and validate. If either reports an error or a warning, fix the clues.
4. Create the PDF if LibreOffice is available; otherwise keep the SVG.
At the end, list the clues you are unsure about and the words that belong in the pomucka.
```

4. Find the finished files in `out/`. Read every word and clue before printing.

Tested with Claude. Not tried with other models; any model that writes good Czech should work.

**Who does what.** The agent runs the commands, writes the clues and watches for errors. You choose the topic and the tajenka and decide what gets printed. In the sample puzzle a model wrote the clues, and the author rewrote six of 65 by hand.

**Without an agent, in a normal chat.** Generate the grid as in "Manual steps" (step 1). Then upload `request.json` to the chat and write: "Write clues.json following the instructions in the file. Return only the contents of the file." The instructions for the model (in Czech) and the required format are inside `request.json`. Save the answer as `clues.json` in the same folder and continue with step 3.

**Getting good clues**

- Words first, clues second. A word that does not suit is fixed faster by another `--seed` than by a clue that works around it.
- The program checks the clue length (at most 28 characters) and that the clue does not contain the word's stem. Whether a clue is clear and fitting only a person can judge.
- Words a solver cannot be expected to know belong in `pomucka`. They are printed as you write them, capital or lower case.
- `request.json` gives each word its dictionary meaning (`gloss`) and markers (`flags`). A few words have no meaning at all, because they come only from the frequency list; their clues rest on the model's own knowledge, so check them.

## Requirements

- **Python 3.10 or newer**, standard library only. Check with `python3 --version`. Tested on Python 3.14 under Linux.
- **LibreOffice**, only for PDF output. The program starts it on its own (`soffice`). Without LibreOffice you get SVG files, which you can open and print from a web browser.
- **Clues** are written by a person or by a language model such as Claude. The program does not invent clues and needs no API key and no internet connection.

## Installation

Download the `krizovky` folder (on GitHub **Code → Download ZIP**, or the zip you were given) and unpack it. Run all commands below in a terminal opened in that folder.

## Manual steps

The same steps the agent takes in the quick start. Use them if you prefer to type the commands yourself.

### 1. Generate the grid

```bash
python3 -m krizovky generate --mode swedish --size 16x12 --tajenka "SLAVÍME / DEN / ZEMĚ" \
    --title "Eko křížovka" --theme "Ochrana životního prostředí" --seed 2 --out out/den_zeme
```

- `--size 16x12` is the grid size: 16 rows, 12 columns.
- `--tajenka` is the phrase the solver uncovers. A slash `/` splits it into parts; each part gets its own shaded row. A part needs at least 2 letters and at most one fewer than the grid has columns (11 for 12 columns). Spaces inside a part are dropped, so `V ZAHRADĚ` is printed as VZAHRADĚ.
- `--title` is printed above the puzzle, `--theme` above the grid.
- `--seed 2` picks a variant; another number gives another grid.
- `--out out/den_zeme` is the output folder.

The fill takes a few seconds to about a minute. The output looks like this (word list shortened):

```
filled 16x12 in 4.8 s: 68 words, 3 repairs, inner blocks 17 %
puzzle_svg: out/den_zeme/puzzle.svg
solution_svg: out/den_zeme/solution.svg
solution_md: out/den_zeme/solution.md
65 clue(s) missing: PRSK, OSTROV, ROVY, SKELNÝ, PUB, TET, HALT, CO, BLÁ, … , RYSI, ONAK
Fill out/den_zeme/clues.json from out/den_zeme/request.json and run: python3 -m krizovky clues out/den_zeme
```

The program exits with code 3 because the clues are missing; at this point that is expected. The folder now holds `request.json` with the list of words, each with its dictionary meaning and markers such as "abbreviation" or "obsolete" to help with the clue.

### 2. Write the clues (`clues.json`)

The clues go into `clues.json` in the same folder, in one of two ways:

- **Let a language model write them.** Send it `request.json` and ask for `clues.json`. The clue-writing instructions (in Czech) and the file format are inside `request.json`. Save the answer as `out/den_zeme/clues.json`.
- **Write them by hand** in any text editor.

The file looks like this (start of the sample):

```json
{
 "version": 1,
 "clues": {
  "PRSK": "Citoslovce syčení kočky",
  "OSTROV": "Země obklopená vodou",
  "ROVY": "Hroby (kniž.)"
 },
 "pomucka": ["ÍHÁ", "OBMÝTNÍ", "OTKA", "PE", "SOC", "TET"]
}
```

- In `clues`, the word from the grid in capitals maps to its clue. A clue has at most 28 characters and must not contain the word or its stem.
- `pomucka` lists words a solver cannot be expected to know. They are printed under the grid in the "Pomůcka:" line exactly as written. The line is optional.

The full `clues.json` of the sample is [`examples/eko_krizovka/clues.json`](examples/eko_krizovka/clues.json).

### 3. Put the clues into the puzzle

```bash
python3 -m krizovky clues out/den_zeme
```

```
puzzle_svg: out/den_zeme/puzzle.svg
solution_svg: out/den_zeme/solution.svg
solution_md: out/den_zeme/solution.md
```

The program checks the clues and renders the sheet again. When a clue is missing or contains the word's stem, it prints a `WARNING: …` line and exits with code 3; fix the clue and run the command again.

To check the whole puzzle (every cell belongs to an across and a down word, every word has a clue, the tajenka fits):

```bash
python3 -m krizovky validate out/den_zeme
```

```
OK: 68 entries, 12x16, mode swedish
```

This line gives the size the other way round, as width × height (12 columns × 16 rows).

### 4. PDF for printing

Add `--pdf`:

```bash
python3 -m krizovky clues out/den_zeme --pdf
```

The folder gets `puzzle.pdf` (the puzzle) and `solution.pdf` (the solution). Without LibreOffice, open `puzzle.svg` in a browser and print it on A4. The solution is also in the text file `solution.md`.

## Common options

| Option | What it does |
|---|---|
| `--size 11x12` | grid size, rows × columns; the magazine sizes are 11x12 and 16x12 |
| `--tajenka "A / B / C"` | the hidden phrase; parts (1–3 in magazines) separated by slashes |
| `--title "…"` | title above the puzzle |
| `--theme "…"` | theme; printed above the grid and passed to the clue writer |
| `--header "…"` | a different text above the grid than the theme |
| `--seed 1` | another grid variant for the same input |
| `--timeout 300` | how many seconds the search may take (default 180) |
| `--no-names` | no proper names (towns, rivers, people) |
| `--pdf` | also write PDF (needs LibreOffice) |
| `--out folder` | where to write the results |

Two simpler puzzle types (a column puzzle with the tajenka in a column, and a crossword with numbered clues) and every option are described in [DEVELOPMENT.md](DEVELOPMENT.md).

## When the program stops with an error

Right after a command, `echo $?` shows the exit code.

- **Code 3 – clues missing.** Not an error: fill `clues.json` (step 2) and run `clues`.
- **Code 2 – the grid could not be filled.** For example:
  ```
  error: no fill of 11x12 for this tajenka within 1 s; try --timeout, a bigger grid or shorter runs
  ```
  Give it more time (`--timeout 300`), try another `--seed`, a bigger grid or shorter tajenka parts. A typo in an option also gives code 2; the program then prints a `usage: …` line and what is wrong below it.
- **Code 1 – bad input.** The program prints an `error: …` line, for example:
  ```
  error: mode swedish draws words from the dictionary; --words is not used
  ```
  You get the same code when a tajenka part has only one letter (`error: a tajenka run needs at least 2 cells, got 1`) or is longer than the grid can hold. Change the tajenka. Code 1 also comes with `--pdf` when LibreOffice is missing or cannot start (`error: soffice exited with 1: …`). The SVG files stay in the folder; open them in a browser.

## How to read the sheet

- **A clue in a cell** belongs to the word starting right next to it (across) or right below it (down). There are no arrows.
- **A split cell** has a horizontal line across the middle: the upper clue belongs to the word on the right, the lower one to the word below.
- **Grey rows** are the parts of the tajenka. The cell before each carries the label "1. díl tajenky", "2. díl tajenky" and so on, or just "tajenka" for a single part. Under the grid are boxes for writing the tajenka.
- **A black disc ●** marks a cell with neither a letter nor a clue.
- **Pomůcka:** under the grid lists words a solver may not know.

## Check before printing

- The dictionary is built by machine. Dialect forms, obscure names, slang without an explanation, insults and vulgar words have been taken out, but a rare or old-fashioned word still gets into the grid now and then (SOC or MANĚ in the sample). Go through every word and clue before printing; if you dislike a word, generate again with another `--seed`. A grid usually holds some abbreviations and names; that is normal in magazines, and the clue marks an abbreviation with (zkr.).
- Long words in clues are cut between syllables, but by a simple rule without a dictionary (CITOSLOV-CE). Foreign words and compounds can be cut in the wrong place.
- The tajenka parts do not span the whole row, and the clue cells are spread more loosely than in magazines.
- Clues written by a language model can be wrong. Check them.

## Author and licences

Author: Michal Stasiak, 2026.

- The program is under the MIT License ([LICENSE](LICENSE)): you may use, change and share it freely as long as you keep the author notice and the licence text.
- The dictionary `data/words.tsv.gz` and the sample puzzle derive from Wikislovník and Wiktionary and are therefore under CC BY-SA 4.0. When you share them, credit the sources and keep the same licence. Sources, licences and the required attribution are in [data/LICENSES.md](data/LICENSES.md).
- The generated files `puzzle.json` and `request.json` quote Wiktionary glosses verbatim. If you publish or pass them on, they are under CC BY-SA 4.0: credit the source and keep the licence. A printed puzzle (SVG or PDF) with clues in your own words is yours; the dictionary licence does not apply to it.
