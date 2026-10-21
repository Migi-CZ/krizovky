import random
import unittest

from krizovky import alphabet, placer_column, validate
from krizovky.model import ACROSS, Entry
from krizovky.placer_column import PlacementError, place

WORDS = "recyklace,příroda,strom,voda,energie,odpad,země,vzduch,les,chata,ekologie,květina".split(",")


def entries(words=WORDS):
    return [Entry.from_word(w) for w in words]


def column_letters(p):
    return [p.grid()[r][c] for r, c in p.tajenka_cells]


class PlaceTests(unittest.TestCase):
    def test_result_is_valid_and_spells_tajenka(self):
        p = place(entries(), "Den Země", width=12)
        self.assertEqual(validate.validate(p), [])
        self.assertEqual(column_letters(p), ["D", "E", "N", "Z", "E", "M", "Ě"])
        self.assertEqual(p.mode, "column")
        self.assertEqual(p.height, 7)
        self.assertEqual(p.tajenka, "Den Země")
        self.assertEqual(p.dropped, [])

    def test_tajenka_cells_share_one_column_and_rows_are_across(self):
        p = place(entries(), "Den Země", width=12)
        self.assertEqual({c for _, c in p.tajenka_cells}, {p.tajenka_cells[0][1]})
        self.assertEqual([r for r, _ in p.tajenka_cells], list(range(p.height)))
        self.assertTrue(all(pl.direction == ACROSS and pl.row == i for i, pl in enumerate(p.placements)))

    def test_width_is_needed_width_and_within_limit(self):
        p = place(entries(), "Den Země", width=14)
        needed = max(pl.col + len(e) for e, pl in zip(p.entries, p.placements))
        self.assertEqual(p.width, needed)
        self.assertLessEqual(p.width, 14)

    def test_each_entry_used_once_and_unused_listed(self):
        p = place(entries(), "Den Země", width=12)
        used = [e.answer for e in p.entries]
        self.assertEqual(len(used), len(set(used)))
        self.assertEqual(sorted(used + p.meta["unused"]), sorted(w.upper() for w in WORDS))

    def test_ch_cell_in_word_and_tajenka(self):
        p = place(entries(["chata", "les", "voda", "ráno", "kos"]), "ach", width=8)
        self.assertEqual(validate.validate(p), [])
        self.assertEqual(column_letters(p), ["A", "CH"])
        self.assertEqual(p.height, 2)

    def test_ch_as_two_cells_when_disabled(self):
        es = [Entry.from_word(w, ch_one_cell=False) for w in ("chata", "hrad", "les")]
        p = place(es, "ch", ch_one_cell=False)
        self.assertEqual(validate.validate(p), [])
        self.assertEqual(column_letters(p), ["C", "H"])

    def test_match_none_uses_letters_without_diacritics(self):
        p = place(entries(["žába", "kos", "les"]), "zl", match="none")
        self.assertEqual(validate.validate(p), [])

    def test_strict_does_not_accept_missing_diacritics(self):
        with self.assertRaises(PlacementError):
            place(entries(["žába", "kos"]), "zk", match="strict")

    def test_deterministic_for_same_rng_seed(self):
        a = place(entries(), "Den Země", width=12, rng=random.Random(5))
        b = place(entries(), "Den Země", width=12, rng=random.Random(5))
        self.assertEqual(a, b)

    def test_backtracking_when_greedy_choice_blocks(self):
        # Both rows want an A; only one word has two. STRAN must go to row 0 (S) and
        # the A of row 1 must come from KAJ, never from reusing STRAN.
        es = entries(["stran", "kaj", "pes"])
        for seed in range(10):
            p = place(es, "sa", width=6, rng=random.Random(seed))
            self.assertEqual(validate.validate(p), [])
            self.assertEqual(len({e.answer for e in p.entries}), 2)

    def test_width_too_small_reports_minimal_width(self):
        with self.assertRaises(PlacementError) as ctx:
            place(entries(["vlak", "pes", "kos"]), "les", width=4)
        self.assertIn("width 5 would work", str(ctx.exception))
        p = place(entries(["vlak", "pes", "kos"]), "les", width=5)
        self.assertEqual(validate.validate(p), [])

    def test_word_longer_than_width_is_never_chosen(self):
        with self.assertRaises(PlacementError) as ctx:
            place(entries(["vlak", "pes", "kos"]), "les", width=3)
        self.assertIn("L", str(ctx.exception))

    def test_example_list_needs_width_12(self):
        # Brute-force checked: with these words "Den Země" cannot fit in 11 columns.
        with self.assertRaises(PlacementError) as ctx:
            place(entries(), "Den Země", width=11)
        self.assertIn("width 12 would work", str(ctx.exception))
        self.assertEqual(validate.validate(place(entries(), "Den Země", width=12)), [])

    def test_too_long_and_too_short_words_are_unused(self):
        p = place(entries(["a", "recyklace", "les", "pes"]), "es", width=4)
        self.assertEqual(validate.validate(p), [])
        self.assertIn("RECYKLACE", p.meta["unused"])
        self.assertIn("A", p.meta["unused"])

    def test_duplicate_entries_not_both_used(self):
        p = place(entries(["les", "les", "pes"]), "ee")
        self.assertEqual(validate.validate(p), [])
        self.assertEqual(sorted(e.answer for e in p.entries), ["LES", "PES"])


class PlacementErrorTests(unittest.TestCase):
    def test_missing_letters_are_named(self):
        with self.assertRaises(PlacementError) as ctx:
            place(entries(["les", "pes"]), "lxq")
        msg = str(ctx.exception)
        self.assertIn("X", msg)
        self.assertIn("Q", msg)

    def test_not_enough_distinct_words(self):
        with self.assertRaises(PlacementError):
            place(entries(["les"]), "ee")

    def test_empty_entries(self):
        with self.assertRaises(PlacementError):
            place([], "les")

    def test_empty_tajenka(self):
        with self.assertRaises(alphabet.AlphabetError):
            place(entries(), "  ...  ")

    def test_bad_arguments(self):
        with self.assertRaises(PlacementError):
            place(entries(), "les", width=0)
        with self.assertRaises(PlacementError):
            place(entries(), "les", match="fuzzy")


if __name__ == "__main__":
    unittest.main()


class TajenkaWordExcludedTests(unittest.TestCase):
    def test_tajenka_word_is_never_an_entry(self):
        from krizovky import placer_column
        from krizovky.model import Entry
        words = ["dýně", "strašidlo", "netopýr", "čarodějnice", "měsíc", "duch"]
        p = placer_column.place([Entry.from_word(w) for w in words], "DÝNĚ", width=11)
        self.assertNotIn("DÝNĚ", [e.answer for e in p.entries])
        self.assertIn("DÝNĚ", p.meta["unused"])
