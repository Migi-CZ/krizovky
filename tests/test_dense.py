"""Slice 4: Swedish clue-cell pattern generator, dense CSP filler and its lexicon.

Small dictionaries are written as TSV files into a temporary folder (header =
``wordlist.COLUMNS``) and loaded with ``extra=False``; nothing here touches the real
word list except the two guard tests at the end.
"""
import math
import random
import warnings
import tempfile
import time
import unittest
from pathlib import Path

from krizovky import alphabet, validate, wordlist
from krizovky.filler_dense import FillError, Lexicon, Stats, _Search, default_repair_cap, fill, repair_fill, solve, tajenka_runs, weight
from krizovky.model import ACROSS, DOWN
from krizovky.pattern_swedish import Pattern, PatternError, _split_weight, block_options, generate, shape_stats

SIZES = [(11, 11, [7]), (11, 11, [10, 8]), (11, 16, [4, 9, 6]), (12, 17, [10, 8]), (12, 17, [7])]


# --- tiny dictionaries ------------------------------------------------------------
def load_rows(rows):
    """rows: iterable of (word, form, freq, flags) -> wordlist.Index (no extra_words)."""
    lines = ["\t".join(wordlist.COLUMNS)]
    for word, form, freq, flags in rows:
        lines.append("\t".join((word, word.lower(), "noun", form, "gloss of " + word, "", str(freq), flags)))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "words.tsv"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return wordlist.load(path, extra=False)


def lexicon(words, **kw):
    return Lexicon(load_rows([(w, "", 0, "") for w in words]), **kw)


def border_pattern(rows, cols, tajenka_runs=(), extra_blocks=()):
    blocks = {(0, c) for c in range(cols)} | {(r, 0) for r in range(rows)} | set(extra_blocks)
    return Pattern(rows, cols, blocks, [list(run) for run in tajenka_runs])


def runs_of(pattern, direction):
    return [s.cells for s in pattern.slots() if s.direction == direction]


# Hand-checked 4x4 interior (rows 1-4, cols 1-4) of a 5x5 grid; the letters A..P are just
# distinct cells, so the 8 lines are 8 different "words":
#   row 1: A B C D      columns: AEIM  BFJN  CGKO  DHLP
#   row 2: E F G H  <- the tajenka run
#   row 3: I J K L
#   row 4: M N O P
SQUARE = ["ABCD", "IJKL", "MNOP", "AEIM", "BFJN", "CGKO", "DHLP"]
SQUARE_RUN = [(2, 1), (2, 2), (2, 3), (2, 4)]


def square_pattern():
    return border_pattern(5, 5, [SQUARE_RUN])


def binary_words(n=4):
    return ["".join("AB"[(i >> j) & 1] for j in range(n)) for i in range(2 ** n)]


# --- pattern ----------------------------------------------------------------------
class PatternTests(unittest.TestCase):
    def patterns(self):
        for rows, cols, lengths in SIZES:
            for seed in range(4):
                yield rows, cols, lengths, generate(rows, cols, lengths, rng=random.Random(seed), tries=10)

    def test_edges_are_blocked(self):
        for rows, cols, _, p in self.patterns():
            self.assertTrue(all((0, c) in p.blocks for c in range(cols)))
            self.assertTrue(all((r, 0) in p.blocks for r in range(rows)))

    def test_valid_and_no_one_cell_run_in_either_direction(self):
        for rows, cols, _, p in self.patterns():
            self.assertEqual(p.is_valid(), [], (rows, cols))
            across = {c for s in p.slots() if s.direction == ACROSS for c in s.cells}
            down = {c for s in p.slots() if s.direction == DOWN for c in s.cells}
            self.assertEqual(across, p.white())   # every white cell is in an across word ...
            self.assertEqual(down, p.white())     # ... and in a down word
            self.assertTrue(all(len(s.cells) >= 2 for s in p.slots()))

    def test_inner_share_reached_and_length_caps_met(self):
        # slice 4d defaults: inner share >= 0.13, no run > 11, at most 2 non-tajenka runs > 8
        for rows, cols, _, p in self.patterns():
            lengths = [len(s.cells) for s in p.slots() if s.tajenka is None]
            self.assertGreaterEqual(p.inner_share(), 0.13, (rows, cols))
            self.assertLessEqual(p.inner_share(), 0.22, (rows, cols))
            self.assertLessEqual(max(lengths), 11, (rows, cols))
            self.assertLessEqual(sum(1 for n in lengths if n > 8), 2, (rows, cols, sorted(lengths)))

    def test_magazine_sizes_get_the_magazine_shape(self):
        # E2 last row of Source/cuddly-lovelace.md: inner ~13 %, mean >= 4.5, <= 2 long words
        for rows, cols, lengths in ((11, 12, [9, 11]), (16, 12, [11, 11]), (11, 12, [11, 9])):
            inner, mean, short = [], [], []
            for seed in range(6):
                p = generate(rows, cols, lengths, rng=random.Random(seed), tries=20)
                self.assertEqual(p.is_valid(), [])
                st = shape_stats(p)
                inner.append(st["inner%"])
                mean.append(st["mean_len"])
                short.append(st["2-3cell%"])
                self.assertLessEqual(st["long>8"], 2, (rows, cols, seed))
                self.assertLessEqual(st["longest"], 11)
            self.assertLess(sum(inner) / len(inner), 16.5, (rows, cols, inner))   # 16x12 lands at ~15 %: the 15-cell columns force blocks
            self.assertGreater(sum(mean) / len(mean), 4.4, (rows, cols, mean))
            self.assertLess(sum(short) / len(short), 38.0, (rows, cols, short))

    def test_max_len_knob_is_met(self):
        for seed in range(5):
            p = generate(11, 11, [7], rng=random.Random(seed), tries=10, max_len=8)
            self.assertLessEqual(max(len(s.cells) for s in p.slots() if s.tajenka is None), 8)

    def test_block_share_is_deprecated_and_converted_to_inner_share(self):
        rows, cols = 11, 12
        inner = (0.22 * rows * cols - (rows + cols - 1)) / ((rows - 1) * (cols - 1))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            a = generate(rows, cols, [9], rng=random.Random(3), tries=5, block_share=0.22, max_len=8)
        self.assertTrue(any(w.category is DeprecationWarning for w in caught))
        b = generate(rows, cols, [9], rng=random.Random(3), tries=5, inner_share=inner, max_len=8)
        self.assertEqual(a, b)
        with self.assertRaises(PatternError):
            generate(rows, cols, [9], rng=random.Random(0), tries=2, block_share=0.22, inner_share=0.13)
        with self.assertRaises(PatternError):
            generate(rows, cols, [9], rng=random.Random(0), tries=2, inner_share=1.0)

    def test_stump_penalty_in_split_weight(self):
        # row 1 of a 1x7 interior: blocking column 3 leaves 2 + 3 cells -> one 2-cell stump
        blocks = {(0, c) for c in range(-1, 9)} | {(2, c) for c in range(-1, 9)} | {(1, -1), (1, 8), (1, 0), (1, 7)}
        plain = _split_weight(1, 3, blocks, stump=1.0)
        self.assertAlmostEqual(plain, 7.0)                                       # (2*3+1)*(0*0+1)
        # 2 + 3: a 2-cell piece (x stump) and a 3-cell piece (x sqrt(stump))
        self.assertAlmostEqual(_split_weight(1, 3, blocks, stump=0.1), 0.1 * math.sqrt(0.1) * plain)
        self.assertAlmostEqual(_split_weight(1, 4, blocks, stump=0.1), 0.1 * math.sqrt(0.1) * plain)   # 3 + 2
        # a 1x8 interior: blocking column 4 leaves 3 + 4 -> one 3-cell piece only
        wide = {(0, c) for c in range(-1, 10)} | {(2, c) for c in range(-1, 10)} | {(1, -1), (1, 9), (1, 0)}
        self.assertAlmostEqual(_split_weight(1, 4, wide, stump=1.0), 13.0)              # (3*4+1)
        self.assertAlmostEqual(_split_weight(1, 4, wide, stump=0.1), math.sqrt(0.1) * 13.0)
        self.assertAlmostEqual(_split_weight(1, 5, wide, stump=0.1), math.sqrt(0.1) * 13.0)   # 4 + 3
        self.assertAlmostEqual(_split_weight(1, 2, wide, stump=0.1), 7.0)               # 1 + 6: no 2- or 3-cell piece

    def test_inner_share_of_hand_built_patterns(self):
        self.assertEqual(square_pattern().inner_share(), 0.0)
        self.assertAlmostEqual(border_pattern(5, 5, extra_blocks=[(2, 2)]).inner_share(), 1 / 16)
        self.assertAlmostEqual(square_pattern().block_share(), 9 / 25)

    @unittest.skipUnless((Path(__file__).resolve().parent.parent / "examples" / "magazine" / "ex1.txt").exists(),
                         "magazine transcription is not part of the shared copy")
    def test_shape_stats_of_magazine_example_1(self):
        # reference numbers: Source/cuddly-lovelace.md E1 (ex1, 11x12)
        path = Path(__file__).resolve().parent.parent / "examples" / "magazine" / "ex1.txt"
        rows = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("# ")]
        blocks = {(r, c) for r, line in enumerate(rows) for c, ch in enumerate(line) if ch == "#"}
        tajenka = {(r, c) for r, line in enumerate(rows) for c, ch in enumerate(line) if ch == "="}
        st = shape_stats(Pattern(len(rows), len(rows[0]), blocks), tajenka)
        self.assertEqual(st["size"], "11x12")
        self.assertAlmostEqual(st["inner%"], 100 * 14 / 110)
        self.assertAlmostEqual(st["blocks%"], 100 * 36 / 132)                     # 22 edge + 14 inner
        self.assertEqual(st["words"], 41)
        self.assertAlmostEqual(st["mean_len"], 4.68, places=2)
        self.assertAlmostEqual(st["2-3cell%"], 29.3, places=1)
        self.assertAlmostEqual(st["2cell%"], 12.2, places=1)
        self.assertEqual(st["longest"], 11)
        self.assertEqual(st["long>8"], 1)
        self.assertAlmostEqual(st["both%"], 100 * 8 / 14)
        self.assertAlmostEqual(st["none%"], 0.0)
        self.assertAlmostEqual(st["diag%"], 100 * 6 / 14)
        self.assertAlmostEqual(st["orth%"], 100 * 8 / 14)

    def test_shape_stats_of_the_square(self):
        st = shape_stats(square_pattern())
        self.assertEqual((st["words"], st["mean_len"], st["longest"], st["long>8"]), (8, 4.0, 4, 0))
        self.assertEqual((st["inner%"], st["both%"], st["diag%"]), (0.0, 0.0, 0.0))

    def test_tajenka_runs_are_intact_blocked_and_on_distinct_rows(self):
        for rows, cols, lengths, p in self.patterns():
            self.assertEqual([len(run) for run in p.tajenka_runs], lengths)
            rs = [run[0][0] for run in p.tajenka_runs]
            self.assertEqual(rs, sorted(rs))
            self.assertTrue(all(b - a >= 2 for a, b in zip(rs, rs[1:])), rs)   # not adjacent rows
            across = set(map(tuple, runs_of(p, ACROSS)))
            for run in p.tajenka_runs:
                self.assertEqual(len({r for r, _ in run}), 1)
                self.assertEqual([c for _, c in run], list(range(run[0][1], run[0][1] + len(run))))
                self.assertIn(tuple(run), across)    # a maximal run: block before it, block after or edge
                self.assertIn((run[0][0], run[0][1] - 1), p.blocks)
                last = run[-1][1]
                self.assertTrue(last == cols - 1 or (run[0][0], last + 1) in p.blocks)
                for r, c in run:
                    self.assertNotIn((r, c), p.blocks)

    def test_slots_carry_the_tajenka_index(self):
        p = generate(11, 11, [4, 9, 6], rng=random.Random(1), tries=5)
        tagged = {s.tajenka: s.cells for s in p.slots() if s.tajenka is not None}
        self.assertEqual(tagged, {k: run for k, run in enumerate(p.tajenka_runs)})
        self.assertTrue(all(s.direction == ACROSS for s in p.slots() if s.tajenka is not None))

    def test_same_seed_same_pattern(self):
        a = generate(11, 16, [10, 8], rng=random.Random(5), tries=8)
        b = generate(11, 16, [10, 8], rng=random.Random(5), tries=8)
        self.assertEqual(a, b)
        c = generate(11, 16, [10, 8], rng=random.Random(6), tries=8)
        self.assertNotEqual(a.blocks, c.blocks)

    def test_scoring_counts_prefer_a_different_pattern_but_stay_valid(self):
        counts = {n: 100 * n for n in range(2, 16)}
        p = generate(11, 11, [7], rng=random.Random(2), tries=10, counts=counts)
        self.assertEqual(p.is_valid(), [])

    def test_too_long_tajenka_is_a_pattern_error(self):
        with self.assertRaises(PatternError) as ctx:
            generate(11, 11, [11], rng=random.Random(0))
        self.assertIn("10", str(ctx.exception))   # the maximum length is named
        self.assertEqual(len(generate(11, 11, [10], rng=random.Random(0), tries=5).tajenka_runs[0]), 10)

    def test_degenerate_input_is_a_pattern_error(self):
        for args in ((11, 11, [1]), (11, 11, []), (5, 11, [4, 4, 4]), (1, 5, [2])):
            with self.assertRaises(PatternError, msg=str(args)):
                generate(*args, rng=random.Random(0), tries=3)

    def test_is_valid_reports_violations(self):
        ok = square_pattern()
        self.assertEqual(ok.is_valid(), [])
        # a block inside the interior leaves a 1-cell run
        bad = border_pattern(5, 5, [SQUARE_RUN], extra_blocks=[(1, 2)])
        self.assertTrue(bad.is_valid())
        # an edge cell that is not a block
        loose = Pattern(5, 5, set(ok.blocks) - {(0, 2)}, ok.tajenka_runs)
        self.assertTrue(loose.is_valid())
        # a tajenka run that is not a maximal run
        cut = Pattern(5, 5, set(ok.blocks), [SQUARE_RUN[:3]])
        self.assertTrue(cut.is_valid())
        # white cells that fall apart (two 2x2 islands joined by nothing)
        split = border_pattern(5, 6, extra_blocks=[(r, 3) for r in range(1, 5)])
        self.assertTrue(any("connected" in v for v in split.is_valid()))

    def test_slots_of_a_hand_built_pattern(self):
        p = square_pattern()
        slots = p.slots()
        self.assertEqual(len(slots), 8)
        self.assertEqual(sum(1 for s in slots if s.direction == ACROSS), 4)
        self.assertEqual(sum(1 for s in slots if s.tajenka is not None), 1)
        self.assertEqual(len(p.white()), 16)
        self.assertAlmostEqual(p.block_share(), 9 / 25)

    def test_generation_is_fast_enough(self):
        start = time.perf_counter()
        generate(12, 17, [4, 9, 6], rng=random.Random(0), tries=50)
        self.assertLess(time.perf_counter() - start, 5.0)


# --- lexicon ----------------------------------------------------------------------
def w(word="stůl", form="", freq=0, flags=()):
    return wordlist.Word(word, tuple(alphabet.tokenize(word)), word, "noun", form, "", "", freq, tuple(flags))


class WeightTests(unittest.TestCase):
    def test_lemma_over_form_over_tvar(self):
        self.assertGreater(weight(w(), names=False), weight(w(form="pl"), names=False))
        self.assertGreater(weight(w(form="pl"), names=False), weight(w(flags=("tvar",)), names=False))
        self.assertGreater(weight(w(flags=("tvar",)), names=False), 0)

    def test_frequency_doubles(self):
        self.assertAlmostEqual(weight(w(freq=12), names=False), 2 * weight(w(freq=0), names=False))

    def test_names_excluded_unless_asked(self):
        self.assertEqual(weight(w("Ohře", flags=("vl.",)), names=False), 0)
        low = weight(w("Ohře", flags=("vl.",)), names=True)
        self.assertGreater(low, 0)
        self.assertLess(low, weight(w("Ohře"), names=True))

    def test_register_flags_lower_the_weight(self):
        base = weight(w(), names=False)
        for flag in ("zast.", "kniž.", "básn.", "nář.", "hovor."):
            self.assertLess(weight(w(flags=(flag,)), names=False), base, flag)
        self.assertLess(weight(w(flags=("zkr.",)), names=False), base)
        self.assertGreater(weight(w(flags=("zkr.",)), names=False), weight(w(flags=("zast.",)), names=False))


class LexiconTests(unittest.TestCase):
    WORDS = ["pes", "les", "nos", "kos", "kolo", "kost", "sůl", "chata", "ucho", "ch"]

    def test_candidates_agree_with_index_find(self):
        index = load_rows([(x, "", 0, "") for x in self.WORDS])
        lex = Lexicon(index)
        for length, fixed in ((3, {}), (3, {1: "E"}), (3, {0: "K", 2: "S"}), (4, {0: "K"}), (4, {3: "O"}),
                              (4, {0: "CH"}), (3, {1: "CH"}), (4, {2: "T", 0: "CH"}), (3, {0: "X"})):
            expected = {w_.word for w_ in index.find(length, fixed)}
            mask = lex.candidates(length, fixed, 0)
            got = {lex.words[length][i].word for i in range(len(lex.words[length])) if mask >> i & 1}
            self.assertEqual(got, expected, (length, fixed))

    def test_used_mask_removes_words(self):
        lex = lexicon(self.WORDS)
        every = lex.candidates(3, {}, 0)
        first = every & -every
        self.assertEqual(lex.candidates(3, {}, first), every ^ first)
        self.assertEqual(lex.candidates(9, {}, 0), 0)      # no such bucket

    def test_duplicate_keys_collapse_to_the_heaviest_row(self):
        index = load_rows([("po", "", 0, ""), ("po", "", 5, ""), ("Po", "pl", 0, ""), ("pod", "", 0, "")])
        lex = Lexicon(index)
        self.assertEqual(len(lex.words[2]), 1)
        self.assertEqual(lex.words[2][0].freq, 5)
        self.assertEqual(lex.weight[2][0], weight(lex.words[2][0], names=False))
        self.assertEqual(lex.candidates(2, {}, 0).bit_count(), 1)

    def test_names_are_left_out_unless_asked(self):
        index = load_rows([("pes", "", 0, ""), ("Ohře", "", 0, "vl."), ("Ostrava", "", 0, "vl.")])
        self.assertEqual([x.word for x in Lexicon(index).words[3]], ["pes"])
        self.assertEqual(Lexicon(index).words.get(4, []), [])
        self.assertEqual(len(Lexicon(index, names=True).words[4]), 1)

    def test_match_modes_merge_keys(self):
        index = load_rows([("pes", "", 0, ""), ("péš", "", 0, "")])
        self.assertEqual(len(Lexicon(index).words[3]), 2)
        self.assertEqual(len(Lexicon(index, match="none").words[3]), 1)
        lex = Lexicon(index, match="none")
        self.assertEqual(lex.candidates(3, {1: "E"}, 0).bit_count(), 1)

    def test_stats_counts_per_length(self):
        stats = lexicon(self.WORDS).stats()
        # 3 cells: pes les nos kos sůl ucho (U-CH-O); 4 cells: kolo kost chata (CH-A-T-A); "ch" is 1 cell
        self.assertEqual(stats["by_len"], {3: 6, 4: 3})
        self.assertEqual(stats["total"], 9)

    def test_bad_match_mode(self):
        with self.assertRaises(ValueError):
            Lexicon(load_rows([("pes", "", 0, "")]), match="loose")


# --- fill -------------------------------------------------------------------------
class FillTests(unittest.TestCase):
    def test_hand_made_square_fills_and_validates(self):
        lex = lexicon(SQUARE + ["ABCE", "AEIN", "BFJO", "KLMN", "EFGH"])
        pattern = square_pattern()
        puzzle = fill(pattern, lex, "EFGH", rng=random.Random(0))
        self.assertIsNotNone(puzzle)
        self.assertEqual(validate.validate(puzzle), [])
        self.assertEqual(puzzle.mode, "swedish")
        self.assertEqual((puzzle.height, puzzle.width), (5, 5))
        self.assertEqual(sorted(puzzle.blocks), sorted(pattern.blocks))
        answers = [e.answer for e in puzzle.entries]
        self.assertEqual(sorted(answers), sorted(SQUARE + ["EFGH"]))
        self.assertEqual(len(set(answers)), len(answers))            # every key once
        g = puzzle.grid()
        self.assertEqual("".join(g[r][c] for r, c in puzzle.tajenka_cells), "EFGH")
        self.assertEqual(puzzle.tajenka_cells, SQUARE_RUN)
        self.assertEqual(puzzle.tajenka, "EFGH")

    def test_meta_holds_nodes_and_dictionary_rows(self):
        index = load_rows([(x, "", 7 if x == "ABCD" else 0, "") for x in SQUARE])
        puzzle = fill(square_pattern(), Lexicon(index), "EFGH", rng=random.Random(1))
        self.assertGreaterEqual(puzzle.meta["nodes"], 7)
        self.assertAlmostEqual(puzzle.meta["block_share"], 9 / 25)
        self.assertEqual(set(puzzle.meta["dictionary"]), set(SQUARE))
        self.assertEqual(puzzle.meta["dictionary"]["ABCD"]["freq"], 7)
        self.assertEqual(set(puzzle.meta["dictionary"]["ABCD"]), {"gloss", "form", "flags", "freq"})

    def test_tajenka_run_may_also_be_a_dictionary_word(self):
        lex = lexicon(SQUARE + ["EFGH"])
        puzzle = fill(square_pattern(), lex, "EFGH", rng=random.Random(2))
        self.assertEqual(validate.validate(puzzle), [])
        self.assertEqual([e.answer for e in puzzle.entries].count("EFGH"), 1)

    def test_a_tajenka_run_key_is_not_reused_by_another_slot(self):
        # 3x3 grid, interior 2x2: across AB / AB, down AA / BB. The tajenka run is row 1 = AB,
        # so the second across word would have to be AB again -> no fill.
        pattern = border_pattern(3, 3, [[(1, 1), (1, 2)]])
        self.assertIsNone(fill(pattern, lexicon(["AB", "AA", "BB"]), "AB", rng=random.Random(0)))

    def test_a_word_is_never_used_twice(self):
        # interior 2x2 needs AB twice (across), the dictionary has it once
        pattern = border_pattern(3, 3)
        self.assertIsNone(fill(pattern, lexicon(["AB", "AA", "BB"]), None, rng=random.Random(0)))
        # with BA added, every 2x2 square over these four words still repeats a word
        self.assertIsNone(fill(pattern, lexicon(["AB", "AA", "BB", "BA"]), None, rng=random.Random(0)))

    def test_unsolvable_dictionary_returns_none(self):
        lex = lexicon([x for x in SQUARE if x != "DHLP"])
        self.assertIsNone(fill(square_pattern(), lex, "EFGH", rng=random.Random(0)))

    def test_missing_length_returns_none(self):
        self.assertIsNone(fill(square_pattern(), lexicon(["ABC", "DEF"]), "EFGH", rng=random.Random(0)))

    def test_node_limit_one_returns_none_quickly(self):
        lex = lexicon(SQUARE)
        stats = Stats()
        start = time.perf_counter()
        self.assertIsNone(fill(square_pattern(), lex, "EFGH", rng=random.Random(0), node_limit=1, stats=stats))
        self.assertLess(time.perf_counter() - start, 1.0)
        self.assertLessEqual(stats.nodes, 2)
        self.assertIsNotNone(fill(square_pattern(), lex, "EFGH", rng=random.Random(0), node_limit=100))

    def test_wrong_tajenka_for_the_pattern_is_a_fill_error(self):
        with self.assertRaises(FillError):
            fill(square_pattern(), lexicon(SQUARE), "EFG", rng=random.Random(0))
        with self.assertRaises(FillError):
            fill(square_pattern(), lexicon(SQUARE), "EF / GH", rng=random.Random(0))

    def test_dead_ends_are_counted_by_length(self):
        stats = Stats()
        lex = lexicon([x for x in SQUARE if x != "DHLP"] + ["DHLQ"])    # DHLQ fits the last column but ends row 4 wrongly
        self.assertIsNone(fill(square_pattern(), lex, "EFGH", rng=random.Random(0), stats=stats))
        self.assertGreater(sum(stats.dead_ends.values()), 0)
        self.assertEqual(set(stats.dead_ends), {4})

    def test_deterministic_for_same_seed(self):
        lex = lexicon(binary_words())
        p1 = fill(border_pattern(5, 5, [[(1, 1), (1, 2), (1, 3), (1, 4)]]), lex, "ABAB", rng=random.Random(3))
        p2 = fill(border_pattern(5, 5, [[(1, 1), (1, 2), (1, 3), (1, 4)]]), lex, "ABAB", rng=random.Random(3))
        self.assertIsNotNone(p1)
        self.assertEqual(p1, p2)
        self.assertEqual(validate.validate(p1), [])

    def test_two_tajenka_runs(self):
        # 8 rows x 5 cols, runs on rows 2 and 5, everything else white (4 columns x 7 rows of cells)
        pattern = border_pattern(8, 5, [[(2, 1), (2, 2), (2, 3), (2, 4)], [(5, 1), (5, 2), (5, 3), (5, 4)]])
        # a 4-wide interior over 7 rows is a column of 7-letter down words: need 4 of them; a tiny
        # binary alphabet cannot satisfy that with distinct words of length 7, so build them from AB
        # patterns: down words of length 7 over {A,B}, across words of length 4 over {A,B}.
        lex = lexicon(binary_words(4) + binary_words(7))
        puzzle = fill(pattern, lex, "ABBA / BAAB", rng=random.Random(0), node_limit=20000)
        self.assertIsNotNone(puzzle)
        self.assertEqual(validate.validate(puzzle), [])
        g = puzzle.grid()
        self.assertEqual("".join(g[r][c] for r, c in puzzle.tajenka_cells), "ABBABAAB")
        self.assertEqual(puzzle.tajenka, "ABBA / BAAB")


class SolveTests(unittest.TestCase):
    def test_solve_finds_a_fill_for_the_binary_dictionary(self):
        # every 4-letter word over A/B; with inner_share 0 a 5x5 grid is a full 4x4 square whatever row
        # the run lands on (the 4d default 0.13 would ask for 3 inner blocks and 2-3-cell words)
        lex = lexicon(binary_words())
        stats = Stats()
        result = solve(5, 5, "ABAB", lex, rng=random.Random(0), timeout=20, stats=stats, inner_share=0.0)
        self.assertIsNotNone(result)
        self.assertEqual(validate.validate(result.puzzle), [])
        self.assertEqual(result.puzzle.mode, "swedish")
        self.assertGreaterEqual(result.nodes, 7)
        self.assertGreaterEqual(result.restarts, 0)
        self.assertEqual(result.pattern.is_valid(), [])
        self.assertEqual(stats.nodes, result.nodes)
        self.assertEqual(sorted(result.puzzle.blocks), sorted(result.pattern.blocks))

    def test_solve_respects_the_timeout(self):
        lex = lexicon(binary_words()[:6])      # far too few words: no fill exists
        start = time.perf_counter()
        stats = Stats()
        result = solve(5, 5, "ABAB", lex, rng=random.Random(0), timeout=0.5, stats=stats, inner_share=0.0)
        elapsed = time.perf_counter() - start
        self.assertIsNone(result)
        self.assertGreaterEqual(elapsed, 0.4)
        self.assertLess(elapsed, 3.0)
        self.assertGreater(stats.restarts, 0)

    def test_solve_is_deterministic_for_a_seed(self):
        lex = lexicon(binary_words())
        a = solve(5, 5, "ABAB", lex, rng=random.Random(4), timeout=20, inner_share=0.0)
        b = solve(5, 5, "ABAB", lex, rng=random.Random(4), timeout=20, inner_share=0.0)
        self.assertEqual(a.puzzle, b.puzzle)

    def test_a_too_long_tajenka_is_a_pattern_error(self):
        with self.assertRaises(PatternError):
            solve(5, 5, "ABABA", lexicon(binary_words()), rng=random.Random(0), timeout=1)


# --- repair (slice 4d) ------------------------------------------------------------
COLUMN_4 = [(1, 4), (2, 4), (3, 4), (4, 4)]
# SQUARE without DHLP: column 4 cannot be filled; with DHLQ it has a root candidate that ends row 4
# wrongly (search dies); ABC / HLP and MNO / DHL make both legal repairs of column 4 fillable.
REPAIRABLE = [x for x in SQUARE if x != "DHLP"] + ["DHLQ", "ABC", "HLP", "MNO", "DHL"]


class RepairTests(unittest.TestCase):
    def test_block_options_of_the_failing_column(self):
        taj = set(SQUARE_RUN)
        opts = block_options(square_pattern(), COLUMN_4, cap=0.17)
        self.assertEqual(sorted(cell for cell, _, _ in opts), [(1, 4), (4, 4)])   # (2,4) tajenka, (3,4) leaves a 1-cell piece
        for cell, added, weight in opts:
            self.assertEqual(added, [cell])          # nothing cascades
            # one side of each is the edge: (3*0+1)*(0*3+1) / 1**2, two 3-cell pieces x sqrt(0.1) each
            self.assertAlmostEqual(weight, 0.1)
        self.assertEqual(block_options(square_pattern(), COLUMN_4, cap=0.05), [])   # 1/16 = 6.25 % > cap
        self.assertEqual(block_options(square_pattern(), SQUARE_RUN, cap=0.5), [])  # tajenka cells never
        for cell, added, _ in block_options(square_pattern(), [(1, 1), (1, 2), (1, 3), (1, 4)], cap=0.5):
            self.assertFalse(set(added) & taj)
            p = Pattern(5, 5, set(square_pattern().blocks) | set(added), [SQUARE_RUN])
            self.assertEqual(p.is_valid(), [], (cell, added))

    def test_block_options_through_a_tajenka_row_need_the_closure(self):
        # 2-cell down slot (1,1)-(2,1) where (2,1) is tajenka: blocking (1,1) would strand (2,1) -> no option
        pattern = border_pattern(3, 3, [[(2, 1), (2, 2)]])
        self.assertEqual(block_options(pattern, [(1, 1), (2, 1)], cap=1.0), [])
        # a 2-cell slot whose cells are free goes entirely (both cells added)
        wide = border_pattern(3, 5, [[(2, 1), (2, 2), (2, 3), (2, 4)]])
        opts = block_options(wide, [(1, 1), (1, 2), (1, 3), (1, 4)], cap=1.0)
        self.assertTrue(all(not (set(added) & set(SQUARE_RUN)) for _, added, _ in opts))

    def test_dead_by_slot_names_the_failing_slot(self):
        lex = lexicon([x for x in SQUARE if x != "DHLP"] + ["DHLQ"])
        search = _Search(square_pattern(), lex, tajenka_runs("EFGH"), random.Random(0),
                         node_limit=1000, max_branch=8, sample=40)
        self.assertIsNone(search.starved_slot())
        self.assertFalse(search.solve())
        worst = max(search.dead_by_slot, key=search.dead_by_slot.get)
        # DHLQ and MNOP collide in cell (4,4): the slot that runs empty is row 4 (or column 4), the
        # cell that empties it is (4,4) -> that is the cell the repair must block
        self.assertIn(search.slots[worst].cells, (COLUMN_4, [(4, 1), (4, 2), (4, 3), (4, 4)]))
        self.assertEqual(max(search.dead_by_cell, key=search.dead_by_cell.get), (4, 4))

    def test_starved_slot_is_an_index(self):
        lex = lexicon([x for x in SQUARE if x != "DHLP"])
        search = _Search(square_pattern(), lex, tajenka_runs("EFGH"), random.Random(0),
                         node_limit=10, max_branch=8, sample=40)
        self.assertEqual(search.slots[search.starved_slot()].cells, COLUMN_4)
        self.assertEqual(search.starved(), 4)

    def test_repair_fill_turns_an_unfillable_square_into_a_fillable_one(self):
        for seed in range(4):
            stats = Stats()
            puzzle, pattern = repair_fill(square_pattern(), lexicon(REPAIRABLE), "EFGH", rng=random.Random(seed), stats=stats)
            self.assertIsNotNone(puzzle, seed)
            self.assertEqual(validate.validate(puzzle), [])
            self.assertEqual(stats.repairs, 1)
            self.assertEqual(stats.repair_cells, 1)
            self.assertEqual(stats.repairs_rejected, 0)
            self.assertEqual(puzzle.meta["repairs"], 1)
            self.assertAlmostEqual(puzzle.meta["inner_share"], 1 / 16)
            self.assertEqual(sorted(puzzle.blocks), sorted(pattern.blocks))
            self.assertEqual(pattern.tajenka_runs, [SQUARE_RUN])
            inner = [b for b in pattern.blocks if b[0] > 0 and b[1] > 0]
            self.assertIn(inner, ([(1, 4)], [(4, 4)]))
            self.assertEqual(pattern.is_valid(), [])
            answers = {e.answer for e in puzzle.entries}
            self.assertTrue({"ABC", "HLP"} <= answers or {"MNO", "DHL"} <= answers, answers)

    def test_repair_also_fixes_a_pattern_starved_at_the_root(self):
        stats = Stats()
        puzzle, _ = repair_fill(square_pattern(), lexicon([x for x in SQUARE if x != "DHLP"] + ["ABC", "HLP", "MNO", "DHL"]),
                                "EFGH", rng=random.Random(0), stats=stats)
        self.assertIsNotNone(puzzle)
        self.assertEqual(stats.repairs, 1)
        self.assertEqual(validate.validate(puzzle), [])

    def test_repair_stops_at_the_cap_and_can_be_switched_off(self):
        lex = lexicon([x for x in SQUARE if x != "DHLP"] + ["DHLQ"])    # no 3-cell words: no repair helps
        stats = Stats()
        puzzle, pattern = repair_fill(square_pattern(), lex, "EFGH", rng=random.Random(0), stats=stats, repair_cap=0.17)
        self.assertIsNone(puzzle)
        self.assertLessEqual(stats.repairs, 2)                 # 3 of 16 inner cells would be 18.75 % > cap
        self.assertGreaterEqual(stats.repairs, 1)
        self.assertLessEqual(pattern.inner_share(), 0.17)
        self.assertEqual(pattern.is_valid(), [])
        off = Stats()
        puzzle, pattern = repair_fill(square_pattern(), lex, "EFGH", rng=random.Random(0), stats=off, repair=False)
        self.assertIsNone(puzzle)
        self.assertEqual(off.repairs, 0)
        self.assertEqual(off.restarts, 2)                      # patterns_per_fill 3 = today's three attempts
        self.assertEqual(pattern, square_pattern())

    def test_repair_fill_checks_its_arguments_like_fill(self):
        with self.assertRaises(FillError):
            repair_fill(square_pattern(), lexicon(SQUARE), "EFG", rng=random.Random(0))

    def test_solve_counts_repairs_and_keeps_the_repaired_pattern(self):
        stats = Stats()
        result = solve(5, 5, "EFGH", lexicon(REPAIRABLE), rng=random.Random(1), timeout=20, inner_share=0.0,
                       max_len=11, stats=stats)
        self.assertIsNotNone(result)
        self.assertEqual(validate.validate(result.puzzle), [])
        self.assertGreaterEqual(stats.repairs, 1)
        self.assertEqual(result.repairs, stats.repairs)
        self.assertEqual(result.puzzle.meta["repairs"], stats.repairs)
        self.assertGreater(result.pattern.inner_share(), 0.0)
        self.assertEqual(sorted(result.puzzle.blocks), sorted(result.pattern.blocks))

    def test_solve_defaults_are_the_magazine_shape_with_repair(self):
        # the renderer calls solve(rows, cols, tajenka, lexicon, rng=, timeout=) with defaults
        lex = lexicon(binary_words(2) + binary_words(3) + binary_words(4) + binary_words(5))
        stats = Stats()
        result = solve(6, 6, "ABABA", lex, rng=random.Random(0), timeout=20, stats=stats)
        self.assertIsNotNone(result)
        self.assertEqual(validate.validate(result.puzzle), [])
        self.assertGreater(result.pattern.inner_share(), 0.0)                 # inner_share 0.13 asks for blocks
        self.assertLessEqual(result.pattern.inner_share(), 0.20 + 1e-9)        # repair cap
        # node_limit 20 000 since 2026-10-21 (4f side finding: 16x12 mean word 4.5, out/bench4f/r2_nodes20k.txt)
        import inspect
        self.assertEqual(inspect.signature(solve).parameters["node_limit"].default, 20000)

    def test_default_repair_cap_depends_on_names(self):
        index = load_rows([("pes", "", 0, ""), ("Ohře", "", 0, "vl.")])
        self.assertAlmostEqual(default_repair_cap(Lexicon(index)), 0.20)
        self.assertAlmostEqual(default_repair_cap(Lexicon(index, names=True)), 0.17)
        # the cap is a bound on the repaired pattern, whichever default applies
        lex = lexicon([x for x in SQUARE if x != "DHLP"] + ["DHLQ"])
        stats = Stats()
        _, pattern = repair_fill(square_pattern(), lex, "EFGH", rng=random.Random(0), stats=stats)
        self.assertLessEqual(pattern.inner_share(), 0.20 + 1e-9)
        self.assertLessEqual(stats.repairs, 3)

    def test_solve_without_repair_equals_solve_with_repair_when_none_is_needed(self):
        lex = lexicon(binary_words())
        a, b = Stats(), Stats()
        with_ = solve(5, 5, "ABAB", lex, rng=random.Random(4), timeout=20, stats=a, inner_share=0.0)
        without = solve(5, 5, "ABAB", lex, rng=random.Random(4), timeout=20, stats=b, repair=False, inner_share=0.0)
        self.assertEqual(with_.puzzle, without.puzzle)
        self.assertEqual((a.repairs, b.repairs, with_.repairs), (0, 0, 0))

    def test_solve_block_share_is_still_accepted(self):
        lex = lexicon(binary_words())
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = solve(5, 5, "ABAB", lex, rng=random.Random(4), timeout=20, block_share=0.22, max_len=8)
        self.assertIsNotNone(result)
        self.assertTrue(any(w.category is DeprecationWarning for w in caught))
        with self.assertRaises(PatternError):
            solve(5, 5, "ABAB", lex, rng=random.Random(4), timeout=20, block_share=0.22, inner_share=0.1)


class KeepTests(unittest.TestCase):
    """Slice 4f: a dead attempt leaves its deepest assignment behind, and the attempt after a repair
    holds those words in the slots the repair left intact."""

    def search(self, words, seed=None, rng=0, stats=None):
        lex = lexicon(words)
        return lex, _Search(square_pattern(), lex, tajenka_runs("EFGH"), random.Random(rng),
                            node_limit=1000, max_branch=8, sample=40, stats=stats, seed=seed)

    def test_dead_search_leaves_its_deepest_assignment_behind(self):
        deepest = 0
        for rng in range(4):
            _, search = self.search([x for x in SQUARE if x != "DHLP"] + ["DHLQ"], rng=rng)
            self.assertFalse(search.solve())
            self.assertTrue(all(w is None for w in search.word))        # exhausted: fully unwound
            self.assertEqual(search.depth, 0)
            if search.best_depth:
                self.assertEqual(sum(w is not None for w in search.best_word), search.best_depth)
            else:
                self.assertIsNone(search.best_word)
            deepest = max(deepest, search.best_depth)
        self.assertGreaterEqual(deepest, 1)

    def test_deepest_assignment_survives_a_node_limit_stop(self):
        from krizovky.filler_dense import _Stop
        lex = lexicon(binary_words())
        search = _Search(border_pattern(5, 5), lex, [], random.Random(0), node_limit=3, max_branch=8, sample=40)
        with self.assertRaises(_Stop):
            search.solve()
        self.assertGreaterEqual(search.depth, 1)                             # stopped mid-branch, not unwound
        self.assertEqual(search.best_depth, sum(w is not None for w in search.best_word))
        self.assertGreaterEqual(search.best_depth, search.depth)

    def test_seed_from_keeps_only_slots_the_repair_left_intact(self):
        from krizovky.filler_dense import _seed_from
        longest = 0
        for rng in range(4):
            _, search = self.search([x for x in SQUARE if x != "DHLP"] + ["DHLQ"], rng=rng)
            search.solve()
            repaired = Pattern(5, 5, set(square_pattern().blocks) | {(4, 4)}, [SQUARE_RUN])
            seed = _seed_from(search, repaired)
            alive = {tuple(s.cells) for s in repaired.slots() if s.tajenka is None}
            self.assertTrue(set(seed) <= alive)
            self.assertFalse(any((4, 4) in cells for cells in seed))        # row 4 and column 4 were split
            by_cells = {tuple(s.cells): t for t, s in enumerate(search.slots)}
            for cells, idx in seed.items():
                self.assertEqual(idx, search.best_word[by_cells[cells]])     # the held word is the deepest one
            self.assertEqual(len(seed), search.best_depth - sum(1 for t, idx in enumerate(search.best_word or [])
                                                                if idx is not None and (4, 4) in search.slots[t].cells))
            longest = max(longest, len(seed))
        self.assertGreaterEqual(longest, 1)

    def test_seeded_search_holds_the_seed_and_searches_only_the_rest(self):
        lex = lexicon(SQUARE)
        idx = {w.word: i for i, w in enumerate(lex.words[4])}
        row1, row3 = [(1, c) for c in range(1, 5)], [(3, c) for c in range(1, 5)]
        stats = Stats()
        _, search = self.search(SQUARE, stats=stats,
                                seed={tuple(row1): idx["ABCD"], tuple(row3): idx["IJKL"], ((9, 9), (9, 10)): 0})
        self.assertEqual(search.kept, 2)                  # the unknown slot is ignored
        self.assertIsNone(search.starved_slot())          # a held slot is not "starved" by its own word
        self.assertTrue(search.solve())
        self.assertEqual(stats.nodes, 5)                  # 7 non-tajenka slots, 2 held: the other 5 chosen once
        self.assertEqual(stats.kept_dropped, 0)

    def test_seed_word_that_no_longer_fits_is_skipped(self):
        lex = lexicon(SQUARE)
        idx = {w.word: i for i, w in enumerate(lex.words[4])}
        col1 = [(r, 1) for r in range(1, 5)]              # holds E from the tajenka: BFJN cannot sit there
        stats = Stats()
        _, search = self.search(SQUARE, stats=stats, seed={tuple(col1): idx["BFJN"]})
        self.assertEqual((search.kept, stats.kept_dropped), (0, 1))
        self.assertTrue(search.solve())

    def test_kept_attempt_after_a_repair_fills_with_the_held_words(self):
        # keep_min 0: every repair whose dead attempt placed a word is followed by a kept attempt
        kept_successes = 0
        for seed in range(6):
            stats = Stats()
            puzzle, pattern = repair_fill(square_pattern(), lexicon(REPAIRABLE), "EFGH", rng=random.Random(seed),
                                          stats=stats, keep=True, keep_min=0.0)
            self.assertIsNotNone(puzzle, seed)
            self.assertEqual(validate.validate(puzzle), [])
            self.assertEqual(stats.repairs, 1)
            self.assertLessEqual(stats.kept_attempts, 1)
            self.assertEqual(stats.kept_dropped, 0)
            self.assertEqual(puzzle.meta["kept"], stats.kept_words if stats.kept_successes else 0)
            if stats.kept_successes:
                self.assertGreaterEqual(stats.kept_words, 1)
                self.assertEqual(stats.restarts, 1)       # fresh attempt, repair, kept attempt = 2 attempts
            else:
                self.assertEqual(stats.restarts, 1 + stats.kept_attempts)   # ... plus the fresh attempt after a dead kept one
            kept_successes += stats.kept_successes
        self.assertGreaterEqual(kept_successes, 1)

    def test_default_gate_opens_when_half_the_slots_were_placed(self):
        opened = 0
        for seed in range(8):
            stats = Stats()
            puzzle, _ = repair_fill(square_pattern(), lexicon(REPAIRABLE), "EFGH", rng=random.Random(seed), stats=stats, keep=True)
            self.assertIsNotNone(puzzle)
            opened += stats.kept_attempts
        self.assertGreaterEqual(opened, 1)                                   # seed 5 reaches 4 of 7 slots

    def test_no_kept_attempt_after_a_shallow_death_or_with_keep_off(self):
        # the square dies within the first three of its seven slots: below keep_min 0.5, nothing is kept
        stats = Stats()
        puzzle, _ = repair_fill(square_pattern(), lexicon(REPAIRABLE), "EFGH", rng=random.Random(0), stats=stats, keep=True)
        self.assertIsNotNone(puzzle)
        self.assertEqual((stats.kept_attempts, stats.kept_words, puzzle.meta["kept"]), (0, 0, 0))
        # starved at the root: no word placed, nothing to keep
        stats = Stats()
        puzzle, _ = repair_fill(square_pattern(), lexicon([x for x in SQUARE if x != "DHLP"] + ["ABC", "HLP", "MNO", "DHL"]),
                                "EFGH", rng=random.Random(0), stats=stats, keep=True, keep_min=0.0)
        self.assertIsNotNone(puzzle)
        self.assertEqual(stats.kept_attempts, 0)
        off = Stats()
        puzzle, _ = repair_fill(square_pattern(), lexicon(REPAIRABLE), "EFGH", rng=random.Random(0), stats=off,
                                keep=False, keep_min=0.0)
        self.assertIsNotNone(puzzle)
        self.assertEqual(off.kept_attempts, 0)

    def test_seed_on_a_root_starved_pattern_is_ignored(self):
        # after blocking (4,4) the square has 3-cell slots; SQUARE has no 3-letter word, so the pattern
        # is starved at the root and a seed must not be applied (it would cross a slot length the
        # lexicon has no masks for)
        lex = lexicon(SQUARE)
        idx = {w.word: i for i, w in enumerate(lex.words[4])}
        repaired = Pattern(5, 5, set(square_pattern().blocks) | {(4, 4)}, [SQUARE_RUN])
        row1 = tuple((1, c) for c in range(1, 5))
        stats = Stats()
        search = _Search(repaired, lex, tajenka_runs("EFGH"), random.Random(0), node_limit=100, max_branch=8,
                         sample=40, stats=stats, seed={row1: idx["ABCD"]})
        self.assertEqual((search.kept, stats.kept_dropped), (0, 0))
        self.assertIsNotNone(search.starved_slot())

    def test_keep_off_reproduces_the_slice_4e_result(self):
        # recorded on 5c1c07c before slice 4f (the call of test_solve_counts_repairs...)
        stats = Stats()
        result = solve(5, 5, "EFGH", lexicon(REPAIRABLE), rng=random.Random(1), timeout=20, inner_share=0.0,
                       max_len=11, stats=stats, keep=False)
        self.assertEqual([e.answer for e in result.puzzle.entries],
                         ["ABCD", "EFGH", "IJKL", "MNO", "AEIM", "BFJN", "CGKO", "DHL"])
        self.assertEqual(sorted(result.puzzle.blocks),
                         [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (1, 0), (2, 0), (3, 0), (4, 0), (4, 4)])
        self.assertEqual((stats.repairs, stats.restarts, stats.kept_attempts), (1, 1, 0))

    def test_keep_min_is_validated_and_keep_is_off_by_default(self):
        # off: the 4f bench showed no gain (WORKLOG.md 2026-10-21); the knob stays for experiments
        import inspect
        with self.assertRaises(FillError):
            repair_fill(square_pattern(), lexicon(SQUARE), "EFGH", rng=random.Random(0), keep_min=1.5)
        self.assertIs(inspect.signature(solve).parameters["keep"].default, False)
        self.assertIs(inspect.signature(repair_fill).parameters["keep"].default, False)


# --- real dictionary (no fill) ----------------------------------------------------
@unittest.skipUnless(wordlist.DATA.is_file(), "data/words.tsv.gz is not built")
class RealDictionaryTests(unittest.TestCase):
    def test_lexicon_counts_for_lengths_2_and_3(self):
        index = wordlist.load(extra=False)
        self.assertEqual(len(index.by_len(2)), 452)
        self.assertEqual(len(index.by_len(3)), 1574)   # slice 7b rules (sample blocklist: fě, fy, dra, pyj, tám, túze, vod, von); 4e: 478 / 1666 / 11 / 142, before 4e: 454 / 1551 / 11 / 130
        self.assertEqual(sum(1 for x in index.by_len(2) if "vl." in x.flags), 11)
        self.assertEqual(sum(1 for x in index.by_len(3) if "vl." in x.flags), 120)
        start = time.perf_counter()
        lex = Lexicon(index)
        self.assertLess(time.perf_counter() - start, 3.0)
        for n in (2, 3):
            keys = {x.keys("strict") for x in index.by_len(n) if "vl." not in x.flags}
            self.assertEqual(len(lex.words[n]), len(keys))
            self.assertTrue(all("vl." not in x.flags for x in lex.words[n]))
            self.assertTrue(all(wt > 0 for wt in lex.weight[n]))
        self.assertEqual(lex.stats()["by_len"][2], len(lex.words[2]))
        self.assertFalse(math.isnan(sum(lex.weight[3])))
        self.assertEqual(lex.candidates(3, {}, 0).bit_count(), len(lex.words[3]))


if __name__ == "__main__":
    unittest.main()
