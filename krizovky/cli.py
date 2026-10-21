"""Command line: generate / clues / render / validate / words.

Modes: column (tajenka in a column), web (numbered word-web), swedish (clues in the cells,
words drawn from the dictionary: ``generate --mode swedish --size 11x12 --tajenka "A / B"``).

Exit codes: 0 ok · 1 bad input · 2 placement failed · 3 clues missing
(request.json written, fill clues.json and run ``clues``).
"""
from __future__ import annotations

import argparse
import logging
import random
import sys
from pathlib import Path

from . import (alphabet, clues, filler_dense, pattern_swedish, placer_column, placer_freeform, render_pdf,
               render_svg, validate, wordlist)
from .model import Entry, ModelError, Puzzle

EXIT_OK, EXIT_INPUT, EXIT_PLACEMENT, EXIT_CLUES = 0, 1, 2, 3
PUZZLE_NAME = "puzzle.json"
log = logging.getLogger("krizovky")


class CliError(Exception):
    def __init__(self, message: str, code: int = EXIT_INPUT):
        super().__init__(message)
        self.code = code


# --- input ------------------------------------------------------------------
def read_words_file(path: Path) -> list[tuple[str, str | None]]:
    """One word per line, optional TAB + clue, ``#`` comments."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CliError(f"cannot read word list {path}: {exc}")
    out: list[tuple[str, str | None]] = []
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        word, _, clue = line.partition("\t")
        word = word.strip()
        try:
            alphabet.tokenize(word)
        except alphabet.AlphabetError as exc:
            raise CliError(f"{path}:{n}: {exc}")
        out.append((word, clue.strip() or None))
    return out


def parse_size(text: str) -> tuple[int, int]:
    """``N`` (square) or ``RxC`` (rows x columns) -> (rows, cols)."""
    parts = text.lower().replace("×", "x").split("x")
    try:
        nums = [int(x) for x in parts]
    except ValueError:
        nums = []
    if len(nums) == 1:
        nums = nums * 2
    if len(nums) != 2 or min(nums) < alphabet.MIN_LEN:
        raise CliError(f"--size {text!r}: use N or RxC with values >= {alphabet.MIN_LEN}")
    return nums[0], nums[1]


def collect_entries(args: argparse.Namespace, out_dir: Path) -> list[Entry]:
    pairs: list[tuple[str, str | None]] = []
    if args.words:
        pairs += read_words_file(Path(args.words))
    data = clues.read_clues(out_dir)
    pairs += clues.theme_words(data)  # words proposed by the assistant for --theme
    seen: set[str] = set()
    entries: list[Entry] = []
    for word, clue in pairs:
        entry = Entry.from_word(word, ch_one_cell=not args.no_ch, clue=clue)
        if entry.answer in seen:
            continue
        seen.add(entry.answer)
        entries.append(entry)
    return entries


# --- commands ---------------------------------------------------------------
def cmd_generate(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not args.tajenka or not args.tajenka.strip():
        raise CliError("--tajenka is required (keyword or quote); every crossword has one (SČHAK §61)")
    try:
        alphabet.tokenize_phrase(args.tajenka, ch_one_cell=not args.no_ch)
    except alphabet.AlphabetError as exc:
        raise CliError(f"tajenka: {exc}")
    if args.mode == "swedish":
        return finish(generate_swedish(args), out_dir, args)
    size = parse_size(args.size) if args.mode == "web" else None

    entries = collect_entries(args, out_dir)
    if not entries:
        if args.theme:
            cells = alphabet.flatten(alphabet.tokenize_phrase(args.tajenka, ch_one_cell=not args.no_ch))
            path = clues.write_theme_request(
                out_dir, theme=args.theme, tajenka=args.tajenka, count=max(12, 2 * len(cells)),
                max_len=args.width, match=args.match, ch_one_cell=not args.no_ch)
            print(f"No words yet. Fill {path.parent / clues.CLUES_NAME} from {path} and run generate again.")
            return EXIT_CLUES
        raise CliError("no words: give --words FILE, or --theme to request theme words")

    try:
        if args.mode == "web":
            puzzle = placer_freeform.place(
                entries, args.tajenka, rows=size[0], cols=size[1], match=args.match,
                ch_one_cell=not args.no_ch, rng=random.Random(args.seed), tries=args.tries)
        else:
            puzzle = placer_column.place(
                entries, args.tajenka, width=args.width, match=args.match,
                ch_one_cell=not args.no_ch, rng=random.Random(args.seed))
    except (placer_column.PlacementError, placer_freeform.PlacementError) as exc:
        raise CliError(f"cannot place the words: {exc}", EXIT_PLACEMENT)
    if args.theme:
        puzzle.meta["theme"] = args.theme
    puzzle.meta["seed"] = args.seed
    # Say which words did not make it (spec §3): dropped = did not fit the web,
    # unused = excluded before the search (too long, duplicate, the tajenka itself).
    if puzzle.dropped:
        print(f"dropped ({len(puzzle.dropped)}): {', '.join(puzzle.dropped)}")
    if puzzle.meta.get("unused"):
        print(f"unused ({len(puzzle.meta['unused'])}): {', '.join(puzzle.meta['unused'])}")
    return finish(puzzle, out_dir, args)


def generate_swedish(args: argparse.Namespace) -> Puzzle:
    """Mode swedish: fill a clue-cell grid from the dictionary (``filler_dense``)."""
    if args.words:
        raise CliError("mode swedish draws words from the dictionary; --words is not used")
    if args.no_ch:
        raise CliError("mode swedish always treats CH as one cell; drop --no-ch")
    rows, cols = parse_size(args.size)
    try:
        if not filler_dense.tajenka_runs(args.tajenka):
            raise CliError("--tajenka has no letters; give runs separated by '/', e.g. \"RÁNO / VEČERA\"")
    except filler_dense.FillError as exc:
        raise CliError(str(exc))
    names = not args.no_names
    # "vl." rows are left out at load time when names are off (the bench does the same).
    try:
        index = wordlist.load(args.data, exclude_flags=() if names else ("vl.",))
    except wordlist.WordlistError as exc:
        raise CliError(str(exc))
    lexicon = filler_dense.Lexicon(index, match=args.match, names=names)
    try:
        result = filler_dense.solve(rows, cols, args.tajenka, lexicon, rng=random.Random(args.seed),
                                    timeout=args.timeout)
    except (pattern_swedish.PatternError, filler_dense.FillError) as exc:
        raise CliError(str(exc))
    if result is None:
        raise CliError(f"no fill of {rows}x{cols} for this tajenka within {args.timeout:g} s; "
                       "try --timeout, a bigger grid or shorter runs", EXIT_PLACEMENT)
    puzzle = result.puzzle
    puzzle.meta.update(seed=args.seed, names=names, timeout=args.timeout)
    if args.theme:
        puzzle.meta["theme"] = args.theme
    if args.header:
        puzzle.meta["header"] = args.header
    print(f"filled {rows}x{cols} in {result.seconds:.1f} s: {len(puzzle.entries)} words, "
          f"{result.repairs} repairs, inner blocks {100 * puzzle.meta.get('inner_share', 0):.0f} %")
    return puzzle


def finish(puzzle: Puzzle, out_dir: Path, args: argparse.Namespace) -> int:
    """Apply clues.json, write puzzle.json + renders, report what is missing."""
    if puzzle.mode == "swedish":
        clues.label_tajenka(puzzle)   # the label sits in the clue cell before the run; never asked of the clue writer
    data = clues.read_clues(out_dir)
    problems = clues.apply_clues(puzzle, data)
    for line in problems:
        # without a clues.json every clue is missing: the summary line below says so once
        if data or not line.endswith(f"missing in {clues.CLUES_NAME}"):
            log.warning("%s", line)
    violations = validate.validate(puzzle)
    if violations:
        raise CliError("generated puzzle is invalid (bug):\n  " + "\n  ".join(violations), EXIT_PLACEMENT)
    if getattr(args, "title", None):
        puzzle.meta["title"] = args.title   # so that `clues` / `render` reruns keep it
    puzzle.save(out_dir / PUZZLE_NAME)
    paths = render_svg.write_all(puzzle, out_dir, title=puzzle.meta.get("title"))
    if getattr(args, "pdf", False):
        for key in ("puzzle_svg", "solution_svg"):
            paths[key.replace("svg", "pdf")] = render_pdf.to_pdf(paths[key], out_dir)
    for name, path in paths.items():
        print(f"{name}: {path}")
    missing = clues.missing_clues(puzzle)
    if missing:
        req = clues.write_request(puzzle, out_dir, theme=puzzle.meta.get("theme"))
        print(f"{len(missing)} clue(s) missing: {', '.join(e.answer for e in missing)}")
        print(f"Fill {out_dir / clues.CLUES_NAME} from {req} and run: python3 -m krizovky clues {out_dir}")
        return EXIT_CLUES
    clues.clear_request(out_dir)
    return EXIT_OK


def load_puzzle(target: str) -> tuple[Puzzle, Path]:
    path = Path(target)
    if path.is_dir():
        path = path / PUZZLE_NAME
    try:
        return Puzzle.load(path), path.parent
    except ModelError as exc:
        raise CliError(str(exc))


def cmd_clues(args: argparse.Namespace) -> int:
    puzzle, out_dir = load_puzzle(args.target)
    return finish(puzzle, out_dir, args)


def cmd_render(args: argparse.Namespace) -> int:
    puzzle, out_dir = load_puzzle(args.target)
    paths = render_svg.write_all(puzzle, out_dir, title=args.title or puzzle.meta.get("title"))
    if args.pdf:
        for key in ("puzzle_svg", "solution_svg"):
            paths[key.replace("svg", "pdf")] = render_pdf.to_pdf(paths[key], out_dir)
    for name, path in paths.items():
        print(f"{name}: {path}")
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    puzzle, _ = load_puzzle(args.target)
    violations = validate.validate(puzzle)
    if violations:
        print("\n".join(violations))
        return EXIT_PLACEMENT
    print(f"OK: {len(puzzle.entries)} entries, {puzzle.width}x{puzzle.height}, mode {puzzle.mode}")
    return EXIT_OK


def parse_contains(items: list[str]) -> dict[int, str]:
    """``E@3`` -> {2: "E"}: letter at a 1-based cell position (as a solver counts)."""
    out: dict[int, str] = {}
    for item in items:
        letter, sep, pos_text = item.partition("@")
        try:
            cells = alphabet.tokenize(letter)
        except alphabet.AlphabetError as exc:
            raise CliError(f"--contains {item!r}: {exc}")
        if not sep or len(cells) != 1 or not pos_text.isdigit() or int(pos_text) < 1:
            raise CliError(f"--contains {item!r}: use LETTER@POSITION, e.g. E@3 or CH@1")
        out[int(pos_text) - 1] = cells[0]
    return out


def cmd_words(args: argparse.Namespace) -> int:
    """List dictionary words by length and letter pattern (slice 3 word list)."""
    if args.pattern and args.contains:
        raise CliError("use --pattern or --contains, not both")
    pattern: str | dict[int, str] | None = args.pattern or None
    if args.contains:
        if args.len is None:
            raise CliError("--contains needs --len N")
        pattern = parse_contains(args.contains)
        if max(pattern) >= args.len:
            raise CliError(f"--contains position beyond --len {args.len}")
    try:
        index = wordlist.load(args.data, base_only=args.base, exclude_flags=args.exclude or ())
        found = index.find(args.len, pattern, match=args.match, pos=args.pos)
    except wordlist.WordlistError as exc:
        raise CliError(str(exc))
    if args.random:
        rows = random.Random(args.seed).sample(found, min(args.random, len(found)))
    elif args.limit > 0:
        rows = found[:args.limit]
    else:
        rows = found
    for w in rows:
        print("\t".join((w.word, w.pos, w.form, ",".join(w.flags), w.gloss)))
    print(f"{len(found)} word(s) match; showing {len(rows)}", file=sys.stderr)
    return EXIT_OK


# --- parser -----------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="krizovky", description="Czech crossword generator")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="build a puzzle")
    g.add_argument("--mode", choices=["column", "web", "swedish"], default="column")
    g.add_argument("--tajenka", required=True, help="hidden phrase: keyword or quote")
    g.add_argument("--words", help="word list file: word[TAB clue] per line")
    g.add_argument("--theme", help="theme; without --words a theme-words request is written")
    g.add_argument("--width", type=int, default=11, help="mode column: max grid width in cells (default 11)")
    g.add_argument("--size", default="11", help="modes web and swedish: grid size N or RxC in cells (default 11)")
    g.add_argument("--tries", type=int, default=20, help="mode web: random restarts (default 20)")
    g.add_argument("--timeout", type=float, default=180, help="mode swedish: seconds for the fill (default 180)")
    g.add_argument("--no-names", action="store_true", help="mode swedish: leave proper names (vl.) out of the dictionary")
    g.add_argument("--header", help="mode swedish: text block printed above the grid (default: --theme)")
    g.add_argument("--data", default=str(wordlist.DATA), help="mode swedish: word list (default data/words.tsv.gz)")
    g.add_argument("--match", choices=alphabet.MATCH_MODES, default="strict")
    g.add_argument("--no-ch", action="store_true", help="treat CH as two cells")
    g.add_argument("--seed", type=int, default=0)
    g.add_argument("--title", help="title printed on the puzzle (never the tajenka)")
    g.add_argument("--pdf", action="store_true", help="also convert to PDF via soffice")
    g.add_argument("--out", required=True, help="output folder")
    g.set_defaults(func=cmd_generate)

    c = sub.add_parser("clues", help="apply clues.json to an existing puzzle and re-render")
    c.add_argument("target", help="output folder or puzzle.json")
    c.add_argument("--title")
    c.add_argument("--pdf", action="store_true")
    c.set_defaults(func=cmd_clues)

    r = sub.add_parser("render", help="write SVG (+PDF) and solution.md")
    r.add_argument("target")
    r.add_argument("--title")
    r.add_argument("--pdf", action="store_true")
    r.set_defaults(func=cmd_render)

    v = sub.add_parser("validate", help="check a puzzle.json")
    v.add_argument("target")
    v.set_defaults(func=cmd_validate)

    w = sub.add_parser("words", help="list dictionary words by length and letter pattern")
    w.add_argument("--len", type=int, help="number of cells (CH is one cell)")
    w.add_argument("--pattern", help="cell pattern, '.' = any, e.g. ..E..")
    w.add_argument("--contains", action="append", metavar="L@N",
                   help="letter at 1-based cell position, e.g. E@3; repeatable")
    w.add_argument("--pos", help="part of speech from the list: noun, adj, verb, abbrev ...")
    w.add_argument("--base", action="store_true", help="base forms only (no inflected forms)")
    w.add_argument("--exclude", action="append", metavar="FLAG",
                   help="drop words with this flag (zkr. vl. zast. kniž. básn. hovor. nář. tvar); repeatable")
    w.add_argument("--match", choices=alphabet.MATCH_MODES, default="strict")
    w.add_argument("--random", type=int, metavar="N", help="N random matches instead of the first --limit")
    w.add_argument("--limit", type=int, default=20, help="rows to print (default 20, 0 = all)")
    w.add_argument("--seed", type=int, default=0)
    w.add_argument("--data", default=str(wordlist.DATA), help="word list file (default data/words.tsv.gz)")
    w.set_defaults(func=cmd_words)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s")
    try:
        return args.func(args)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    except (alphabet.AlphabetError, ModelError, clues.CluesError,
            render_svg.RenderError, render_pdf.PdfError, wordlist.WordlistError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INPUT
