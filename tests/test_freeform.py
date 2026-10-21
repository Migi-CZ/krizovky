import random
import time
import unittest
from collections import Counter

from krizovky import alphabet, validate
from krizovky.model import ACROSS, DOWN, Entry
from krizovky.placer_freeform import PlacementError, place

WORDS = ("demokracie,volby,listopad,revoluce,ústava,právo,nezávislost,občan,parlament,disident,"
         "cenzura,hranice,odboj,charta,odvaha,projev,tisk,vlajka,hymna,protest,bojkot,obrana,boj,"
         "stávka").split(",")
SMALL = ["stolek", "kost", "les", "pes", "okno", "voda", "ráno"]


def entries(words=WORDS, **kw):
    return [Entry.from_word(w, **kw) for w in words]


def answers(es):
    return [e.answer for e in es]


def tajenka_letters(p):
    g = p.grid()
    return [g[r][c] for r, c in p.tajenka_cells]


def cell_owners(p):
    owners = Counter()
    for e, pl in zip(p.entries, p.placements):
        owners.update(pl.coords(len(e)))
    return owners


class PlaceTests(unittest.TestCase):
    def test_example_list_is_valid_and_spells_tajenka(self):
        p = place(entries(), "SVOBODA")
        self.assertEqual(validate.validate(p), [])
        self.assertEqual(p.mode, "web")
        self.assertGreaterEqual(len(p.entries), 2)
        self.assertEqual(tajenka_letters(p), ["S", "V", "O", "B", "O", "D", "A"])
        self.assertEqual(p.tajenka, "SVOBODA")

    def test_every_entry_crosses_another(self):
        p = place(entries(), "SVOBODA")
        owners = cell_owners(p)
        for e, pl in zip(p.entries, p.placements):
            self.assertTrue(any(owners[c] > 1 for c in pl.coords(len(e))), e.answer)

    def test_a_reasonable_share_of_the_example_list_is_placed(self):
        # Strict adjacency on 11x11 holds about 9-12 of these 24 words; guard against a regression.
        for seed in range(5):
            p = place(entries(), "SVOBODA", rng=random.Random(seed))
            self.assertGreaterEqual(len(p.entries), 8, f"seed {seed}")

    def test_no_word_is_lost(self):
        p = place(entries(), "SVOBODA")
        self.assertEqual(sorted(answers(p.entries) + p.dropped + p.meta["unused"]),
                         sorted(w.upper() for w in WORDS))
        self.assertEqual(set(p.dropped) & set(answers(p.entries)), set())

    def test_size_limit_and_trim(self):
        p = place(entries(), "SVOBODA")
        self.assertLessEqual(p.width, 11)
        self.assertLessEqual(p.height, 11)
        # trimmed: something sits in the first row/column and in the last ones
        g = p.grid()
        self.assertTrue(any(g[0]) and any(row[0] for row in g))
        self.assertTrue(any(g[-1]) and any(row[-1] for row in g))

    def test_non_square_size_is_respected(self):
        for seed in range(3):
            p = place(entries(), "SVOBODA", rows=7, cols=13, rng=random.Random(seed))
            self.assertEqual(validate.validate(p), [])
            self.assertLessEqual(p.height, 7)
            self.assertLessEqual(p.width, 13)

    def test_numbers_are_set_and_shared_by_a_common_start(self):
        shared = 0
        for seed in range(20):
            p = place(entries(), "SVOBODA", rng=random.Random(seed))
            self.assertTrue(all(pl.number is not None for pl in p.placements))
            by_start = {}
            for pl in p.placements:
                by_start.setdefault((pl.row, pl.col), []).append(pl)
            for group in by_start.values():
                self.assertEqual(len({pl.number for pl in group}), 1)
                if {pl.direction for pl in group} == {ACROSS, DOWN}:
                    shared += 1
            self.assertEqual(len({pl.number for pl in p.placements}), len(by_start))
        self.assertGreater(shared, 0, "no seed produced an across+down pair starting together")

    def test_deterministic_for_same_rng_seed(self):
        a = place(entries(), "SVOBODA", rng=random.Random(7))
        b = place(entries(), "SVOBODA", rng=random.Random(7))
        self.assertEqual(a, b)

    def test_default_rng_is_deterministic(self):
        self.assertEqual(place(entries(), "SVOBODA"), place(entries(), "SVOBODA"))

    def test_meta_reports_tries_and_crossings(self):
        p = place(entries(), "SVOBODA", tries=4)
        self.assertEqual(p.meta["tries"], 4)
        owners = cell_owners(p)
        self.assertEqual(p.meta["crossings"], sum(1 for n in owners.values() if n > 1))

    def test_tajenka_is_spread_over_several_words(self):
        p = place(entries(), "SVOBODA")
        owner_of = {}
        for i, (e, pl) in enumerate(zip(p.entries, p.placements)):
            for c in pl.coords(len(e)):
                owner_of.setdefault(c, set()).add(i)
        used = {i for c in p.tajenka_cells for i in owner_of[c]}
        self.assertGreaterEqual(len(used), 5)

    def test_speed_30_words_20_tries(self):
        words = WORDS + [w for w in ("kolo", "dům", "strom", "voda", "slunce", "zima")]
        start = time.perf_counter()
        p = place(entries(words), "SVOBODA", tries=20)
        self.assertLess(time.perf_counter() - start, 2.0)
        self.assertEqual(validate.validate(p), [])


class CandidateTests(unittest.TestCase):
    def test_word_longer_than_the_grid_is_unused(self):
        words = ["stolek", "kost", "les", "pes", "parlament", "a"]
        p = place(entries(words), "es", rows=6, cols=6)
        self.assertEqual(validate.validate(p), [])
        self.assertIn("PARLAMENT", p.meta["unused"])
        self.assertIn("A", p.meta["unused"])
        self.assertNotIn("PARLAMENT", answers(p.entries))

    def test_word_fitting_only_the_longer_side_is_kept_as_candidate(self):
        p = place(entries(["nezávislost", "stolek", "okno"]), "no", rows=5, cols=11)
        self.assertEqual(validate.validate(p), [])
        self.assertNotIn("NEZÁVISLOST", p.meta["unused"])

    def test_duplicate_word_is_used_once(self):
        words = ["les", "les", "pes", "kost", "stolek"]
        p = place(entries(words), "es")
        self.assertEqual(validate.validate(p), [])
        self.assertLessEqual(answers(p.entries).count("LES"), 1)
        self.assertEqual(sorted(answers(p.entries) + p.dropped + p.meta["unused"]),
                         sorted(w.upper() for w in words))

    def test_tajenka_word_is_never_an_entry(self):
        p = place(entries(["les", "stolek", "pes", "kost", "okno"]), "Les")
        self.assertEqual(validate.validate(p), [])
        self.assertNotIn("LES", answers(p.entries))
        self.assertIn("LES", p.meta["unused"])


class AlphabetTests(unittest.TestCase):
    def test_ch_cell_in_word_and_tajenka(self):
        p = place(entries(["chata", "les", "voda", "ráno", "kos"]), "ach")
        self.assertEqual(validate.validate(p), [])
        self.assertEqual(tajenka_letters(p), ["A", "CH"])
        self.assertIn("CHATA", answers(p.entries))

    def test_ch_as_two_cells_when_disabled(self):
        p = place(entries(["chata", "hrad", "les"], ch_one_cell=False), "ch",
                  ch_one_cell=False)
        self.assertEqual(validate.validate(p), [])
        self.assertEqual(tajenka_letters(p), ["C", "H"])
        self.assertFalse(p.ch_one_cell)

    def test_match_none_uses_letters_without_diacritics(self):
        p = place(entries(["žába", "bota", "zelí", "les", "vlak"]), "zl", match="none")
        self.assertEqual(validate.validate(p), [])
        self.assertEqual(tajenka_letters(p), ["Z", "L"])

    def test_match_length_merges_long_and_short_vowels(self):
        p = place(entries(["ráno", "okno", "kost", "les"]), "ak", match="length")
        self.assertEqual(validate.validate(p), [])
        self.assertEqual(tajenka_letters(p), ["A", "K"])

    def test_strict_does_not_accept_missing_diacritics(self):
        with self.assertRaises(PlacementError) as ctx:
            place(entries(["žába", "kos", "les"]), "zl", match="strict")
        self.assertIn("Z", str(ctx.exception))


class PlacementErrorTests(unittest.TestCase):
    def test_missing_letters_are_named(self):
        with self.assertRaises(PlacementError) as ctx:
            place(entries(["les", "pes", "kost"]), "lxq")
        msg = str(ctx.exception)
        self.assertIn("X", msg)
        self.assertIn("Q", msg)

    def test_letter_needed_twice_but_present_once(self):
        with self.assertRaises(PlacementError) as ctx:
            place(entries(["kost", "pes"]), "kk")
        self.assertIn("K", str(ctx.exception))

    def test_two_words_without_a_common_letter(self):
        with self.assertRaises(PlacementError):
            place(entries(["pes", "kov"]), "pk")

    def test_single_word(self):
        with self.assertRaises(PlacementError):
            place(entries(["pes"]), "pe")

    def test_tajenka_longer_than_the_grid_can_hold(self):
        with self.assertRaises(PlacementError) as ctx:
            place(entries(["pes", "les", "kos"]), "pesleskos", rows=3, cols=3, tries=5)
        self.assertIn("tajenka letters not placed", str(ctx.exception))

    def test_empty_entries(self):
        with self.assertRaises(PlacementError):
            place([], "les")

    def test_empty_tajenka(self):
        with self.assertRaises(alphabet.AlphabetError):
            place(entries(SMALL), "  ...  ")

    def test_bad_arguments(self):
        for kw in ({"rows": 0}, {"cols": 1}, {"match": "fuzzy"}, {"tries": 0}):
            with self.subTest(kw=kw), self.assertRaises(PlacementError):
                place(entries(SMALL), "les", **kw)


class LegalityTests(unittest.TestCase):
    def test_a_word_is_never_extended_into_a_longer_one(self):
        for seed in range(10):
            try:
                p = place(entries(["pes", "pesek"]), "pe", rng=random.Random(seed))
            except PlacementError:
                continue
            self.assertEqual(validate.validate(p), [], f"seed {seed}")

    def test_random_lists_never_give_an_invalid_puzzle(self):
        pool = WORDS + SMALL + ["pesek", "kos", "kost", "stolice", "les", "lesník", "ano", "ne"]
        for seed in range(25):
            rng = random.Random(seed)
            words = rng.sample(pool, 12)
            try:
                p = place(entries(words), "ano", rows=rng.randint(5, 11), cols=rng.randint(5, 11),
                          tries=3, rng=random.Random(seed))
            except PlacementError:
                continue
            self.assertEqual(validate.validate(p), [], f"seed {seed}: {words}")


if __name__ == "__main__":
    unittest.main()
