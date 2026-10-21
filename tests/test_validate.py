import unittest

from krizovky import model, validate
from krizovky.model import Entry, Placement, Puzzle

try:
    from tests.swedish_fixture import swedish_puzzle
except ImportError:  # run from inside tests/
    from swedish_fixture import swedish_puzzle


def column_puzzle():
    entries = [Entry.from_word("vlak"), Entry.from_word("pes"), Entry.from_word("kos")]
    placements = [Placement(0, 1, model.ACROSS), Placement(1, 1, model.ACROSS), Placement(2, 0, model.ACROSS)]
    return Puzzle(mode="column", width=5, height=3, entries=entries, placements=placements,
                  tajenka="les", tajenka_cells=[(0, 2), (1, 2), (2, 2)])


def web_puzzle():
    """PES across at (0,0), SEN down at (0,2) sharing S."""
    entries = [Entry.from_word("pes"), Entry.from_word("sen")]
    placements = [Placement(0, 0, model.ACROSS), Placement(0, 2, model.DOWN)]
    return Puzzle(mode="web", width=5, height=5, entries=entries, placements=placements)


class ValidColumnTests(unittest.TestCase):
    def test_valid_column_puzzle_has_no_violations(self):
        self.assertEqual(validate.validate(column_puzzle()), [])

    def test_wrong_tajenka_letters(self):
        p = column_puzzle()
        p.tajenka = "LAS"
        self.assertTrue(any("tajenka" in v for v in validate.validate(p)))

    def test_tajenka_cell_outside_grid(self):
        p = column_puzzle()
        p.tajenka_cells[0] = (0, 9)
        self.assertTrue(any("tajenka" in v for v in validate.validate(p)))

    def test_tajenka_declared_but_no_cells(self):
        p = column_puzzle()
        p.tajenka_cells = []
        self.assertTrue(any("tajenka" in v for v in validate.validate(p)))

    def test_no_tajenka_is_allowed(self):
        p = column_puzzle()
        p.tajenka = None
        p.tajenka_cells = []
        self.assertEqual(validate.validate(p), [])

    def test_column_mode_requires_across(self):
        p = column_puzzle()
        p.placements[1] = Placement(1, 1, model.DOWN)
        self.assertTrue(any("across" in v for v in validate.validate(p)))


class StructureTests(unittest.TestCase):
    def test_unknown_mode(self):
        p = column_puzzle()
        p.mode = "spiral"
        self.assertTrue(any("mode" in v for v in validate.validate(p)))

    def test_entries_and_placements_must_pair(self):
        p = column_puzzle()
        p.placements.pop()
        self.assertTrue(any("placement" in v for v in validate.validate(p)))

    def test_out_of_bounds(self):
        p = column_puzzle()
        p.width = 4
        self.assertTrue(any("bounds" in v for v in validate.validate(p)))

    def test_too_short_entry(self):
        p = web_puzzle()
        p.entries.append(Entry.from_word("a"))
        p.placements.append(Placement(4, 0, model.ACROSS))
        self.assertTrue(any("short" in v for v in validate.validate(p)))

    def test_duplicate_entry(self):
        p = column_puzzle()
        p.entries[2] = Entry.from_word("pes")
        p.placements[2] = Placement(2, 1, model.ACROSS)
        p.tajenka = None
        p.tajenka_cells = []
        self.assertTrue(any("twice" in v for v in validate.validate(p)))

    def test_duplicate_by_key_in_none_mode(self):
        p = Puzzle(mode="web", width=5, height=5, match="none",
                   entries=[Entry.from_word("rad"), Entry.from_word("řád")],
                   placements=[Placement(0, 0, model.ACROSS), Placement(0, 0, model.DOWN)])
        self.assertTrue(any("twice" in v for v in validate.validate(p)))

    def test_dropped_word_must_not_be_placed(self):
        p = column_puzzle()
        p.dropped = ["PES"]
        self.assertTrue(any("dropped" in v for v in validate.validate(p)))


class CrossingTests(unittest.TestCase):
    def test_valid_web_puzzle(self):
        self.assertEqual(validate.validate(web_puzzle()), [])

    def test_conflicting_crossing(self):
        p = web_puzzle()
        p.entries.append(Entry.from_word("kos"))
        p.placements.append(Placement(2, 0, model.ACROSS))  # S over N at (2,2)
        self.assertTrue(any("conflict" in v for v in validate.validate(p)))

    def test_isolated_word_in_web_mode(self):
        p = web_puzzle()
        p.entries.append(Entry.from_word("dub"))
        p.placements.append(Placement(4, 0, model.ACROSS))
        self.assertTrue(any("cross" in v for v in validate.validate(p)))

    def test_adjacent_words_form_unintended_words(self):
        p = web_puzzle()
        p.entries.append(Entry.from_word("les"))
        p.placements.append(Placement(1, 0, model.ACROSS))  # under PES: PL, EE vertical runs
        self.assertTrue(any("unintended" in v for v in validate.validate(p)))

    def test_column_mode_ignores_vertical_runs(self):
        self.assertEqual(validate.validate(column_puzzle()), [])

    def test_crossing_compares_keys_not_letters(self):
        p = Puzzle(mode="web", width=5, height=5, match="none",
                   entries=[Entry.from_word("pes"), Entry.from_word("šen")],
                   placements=[Placement(0, 0, model.ACROSS), Placement(0, 2, model.DOWN)])
        self.assertEqual(validate.validate(p), [])
        p.match = "strict"
        self.assertTrue(any("conflict" in v for v in validate.validate(p)))


class ClueTests(unittest.TestCase):
    def test_clue_containing_answer_stem_is_rejected(self):
        self.assertTrue(validate.clue_violations("ZEMĚ", "naše země", "column"))
        self.assertTrue(validate.clue_violations("LES", "lesní porost", "web"))
        self.assertTrue(validate.clue_violations("RECYKLACE", "recyklační proces", "web"))

    def test_good_clue_passes(self):
        self.assertEqual(validate.clue_violations("ZEMĚ", "planeta, na které žijeme", "column"), [])
        self.assertEqual(validate.clue_violations("LES", "místo plné stromů", "web"), [])
        self.assertEqual(validate.clue_violations("LES", "kde rostou plesnivé houby", "web"), [])

    def test_clue_length_limits(self):
        long_clue = "x" * 71
        self.assertTrue(validate.clue_violations("PES", long_clue, "web"))
        self.assertEqual(validate.clue_violations("PES", "x" * 70, "web"), [])
        self.assertTrue(validate.clue_violations("PES", "x" * 29, "swedish"))

    def test_empty_clue_rejected(self):
        self.assertTrue(validate.clue_violations("PES", "   ", "web"))

    def test_puzzle_reports_clue_problems_only_when_clue_set(self):
        p = column_puzzle()
        self.assertEqual(validate.validate(p), [])
        p.entries[1].clue = "pes domácí"
        self.assertTrue(any("clue" in v for v in validate.validate(p)))


class SwedishTests(unittest.TestCase):
    def test_blocks_must_be_empty(self):
        p = Puzzle(mode="swedish", width=3, height=3,
                   entries=[Entry.from_word("pes"), Entry.from_word("sen")],
                   placements=[Placement(0, 0, model.ACROSS), Placement(0, 2, model.DOWN)],
                   blocks=[(1, 0)])
        p.blocks = [(1, 0), (1, 2)]
        v = validate.validate(p)
        self.assertTrue(any("block" in x and "filled" in x for x in v))

    def test_asymmetric_blocks_allowed_in_swedish_only(self):
        # PROJECT_SPEC §2: the Swedish grid is not symmetric (directive §19 allows it)
        def puzzle(mode):
            return Puzzle(mode=mode, width=3, height=3,
                          entries=[Entry.from_word("pes"), Entry.from_word("sen")],
                          placements=[Placement(0, 0, model.ACROSS), Placement(0, 2, model.DOWN)],
                          blocks=[(1, 0)])
        # (the sparse 3x3 breaks the swedish cell rules of slice 5; only the symmetry rule matters here)
        self.assertFalse(any("symmetr" in x for x in validate.validate(puzzle("swedish"))))
        self.assertTrue(any("symmetr" in x for x in validate.validate(puzzle("web"))))


class SwedishRulesTests(unittest.TestCase):
    def test_fixture_is_valid(self):
        self.assertEqual(validate.validate(swedish_puzzle()), [])

    def test_empty_cell(self):
        p = swedish_puzzle()
        p.blocks.remove((0, 0))
        self.assertIn("cell (0,0) is empty: neither a letter nor a block", validate.validate(p))

    def test_cell_in_no_down_word(self):
        p = swedish_puzzle()
        del p.entries[7], p.placements[7]          # SADO: (4,4) is left in SETO only
        self.assertIn("cell (4,4) is in no down word", validate.validate(p))

    def test_cell_in_no_across_word(self):
        p = swedish_puzzle()
        del p.entries[0], p.placements[0]          # PES: (1,2) is left in POLE only
        self.assertIn("cell (1,2) is in no across word", validate.validate(p))

    def test_entry_without_clue_cell(self):
        p = swedish_puzzle()
        p.blocks.remove((0, 2))                    # the clue cell of POLE (down, entry 5)
        v = validate.validate(p)
        self.assertTrue(any("entry 5 POLE has no clue cell" in x for x in v), v)

    def test_across_entry_at_left_edge_has_no_clue_cell(self):
        p = Puzzle(mode="swedish", width=3, height=2,
                   entries=[Entry.from_word("pes"), Entry.from_word("pos")],
                   placements=[Placement(1, 0, model.ACROSS), Placement(0, 0, model.DOWN)],
                   blocks=[(0, 1), (0, 2)])
        v = validate.validate(p)
        self.assertTrue(any("entry 0 PES has no clue cell" in x for x in v), v)

    def test_tajenka_run_must_be_a_whole_entry(self):
        p = swedish_puzzle()
        p.tajenka = "KOS"
        p.tajenka_cells = [(2, 1), (2, 2), (2, 3)]
        v = validate.validate(p)
        self.assertTrue(any("tajenka run 0 is not a whole entry" in x for x in v), v)

    def test_every_run_is_checked(self):
        p = swedish_puzzle()
        p.tajenka = "KO / SA"
        v = validate.validate(p)
        self.assertTrue(any("tajenka run 0 is not a whole entry" in x for x in v), v)
        self.assertTrue(any("tajenka run 1 is not a whole entry" in x for x in v), v)

    def test_two_runs_that_are_whole_entries(self):
        p = swedish_puzzle()
        p.tajenka = "PES / ULAD"
        p.tajenka_cells = [(1, 2), (1, 3), (1, 4), (3, 1), (3, 2), (3, 3), (3, 4)]
        self.assertFalse(any("whole entry" in x for x in validate.validate(p)))

    def test_rules_do_not_apply_to_column_and_web(self):
        self.assertEqual(validate.validate(web_puzzle()), [])      # empty cells, no clue cells: fine
        self.assertEqual(validate.validate(column_puzzle()), [])


if __name__ == "__main__":
    unittest.main()
