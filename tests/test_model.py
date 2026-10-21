import json
import tempfile
import unittest
from pathlib import Path

from krizovky import model
from krizovky.model import Entry, Placement, Puzzle

try:
    from tests.swedish_fixture import swedish_puzzle
except ImportError:  # run from inside tests/
    from swedish_fixture import swedish_puzzle


def column_puzzle():
    """Tajenka LES in column 2: VLAK / PES / KOS."""
    entries = [Entry.from_word("vlak"), Entry.from_word("pes"), Entry.from_word("kos")]
    placements = [Placement(0, 1, model.ACROSS), Placement(1, 1, model.ACROSS), Placement(2, 0, model.ACROSS)]
    return Puzzle(mode="column", width=5, height=3, entries=entries, placements=placements,
                  tajenka="les", tajenka_cells=[(0, 2), (1, 2), (2, 2)])


class EntryTests(unittest.TestCase):
    def test_from_word_tokenizes_and_normalises(self):
        e = Entry.from_word("řeřicha", clue="bylina do salátu", pos="noun")
        self.assertEqual(e.answer, "ŘEŘICHA")
        self.assertEqual(e.cells, ["Ř", "E", "Ř", "I", "CH", "A"])
        self.assertEqual(e.keys("none"), ("R", "E", "R", "I", "CH", "A"))

    def test_split_mark_not_kept_in_answer(self):
        e = Entry.from_word("c|hata")
        self.assertEqual(e.answer, "CHATA")
        self.assertEqual(e.cells, ["C", "H", "A", "T", "A"])


class PlacementTests(unittest.TestCase):
    def test_coords(self):
        self.assertEqual(Placement(2, 3, model.ACROSS).coords(3), [(2, 3), (2, 4), (2, 5)])
        self.assertEqual(Placement(2, 3, model.DOWN).coords(2), [(2, 3), (3, 3)])

    def test_bad_direction(self):
        with self.assertRaises(model.ModelError):
            Placement(0, 0, "diagonal").coords(2)


class PuzzleTests(unittest.TestCase):
    def test_grid_is_built_from_placements(self):
        grid = column_puzzle().grid()
        self.assertEqual(grid[0], [None, "V", "L", "A", "K"])
        self.assertEqual(grid[1], [None, "P", "E", "S", None])
        self.assertEqual(grid[2], ["K", "O", "S", None, None])

    def test_grid_uses_match_keys(self):
        p = Puzzle(mode="web", width=4, height=1, match="none",
                   entries=[Entry.from_word("země")], placements=[Placement(0, 0, model.ACROSS)])
        self.assertEqual(p.grid()[0], ["Z", "E", "M", "E"])

    def test_grid_out_of_bounds_is_ignored_not_fatal(self):
        p = Puzzle(mode="web", width=2, height=1, entries=[Entry.from_word("pes")],
                   placements=[Placement(0, 0, model.ACROSS)])
        self.assertEqual(p.grid()[0], ["P", "E"])

    def test_json_round_trip(self):
        p = column_puzzle()
        p.entries[0].clue = "dopravní prostředek na kolejích"
        p.dropped = ["ŽELVA"]
        p.meta = {"theme": "zvířata"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "puzzle.json"
            p.save(path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["version"], model.FORMAT_VERSION)
            q = Puzzle.load(path)
        self.assertEqual(q, p)
        self.assertEqual(q.tajenka_cells, [(0, 2), (1, 2), (2, 2)])
        self.assertIsInstance(q.tajenka_cells[0], tuple)

    def test_load_rejects_wrong_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "puzzle.json"
            path.write_text(json.dumps({"version": 99}), encoding="utf-8")
            with self.assertRaises(model.ModelError):
                Puzzle.load(path)

    def test_tajenka_words(self):
        p = column_puzzle()
        p.tajenka = "Den Země"
        self.assertEqual(p.tajenka_words(), [["D", "E", "N"], ["Z", "E", "M", "Ě"]])
        self.assertEqual(p.tajenka_keys(), ("D", "E", "N", "Z", "E", "M", "Ě"))


class TajenkaRunTests(unittest.TestCase):
    def test_single_run_without_slash(self):
        p = swedish_puzzle()
        self.assertEqual(p.tajenka_run_cells(), [[(2, 1), (2, 2), (2, 3), (2, 4)]])

    def test_runs_split_at_slash(self):
        p = swedish_puzzle()
        p.tajenka = "KO / SA"
        self.assertEqual(p.tajenka_run_cells(), [[(2, 1), (2, 2)], [(2, 3), (2, 4)]])

    def test_ch_cell_counts_once(self):
        p = Puzzle(mode="swedish", width=5, height=1, tajenka="CHA / SA",
                   tajenka_cells=[(0, 0), (0, 1), (0, 2), (0, 3)])
        self.assertEqual(p.tajenka_run_cells(), [[(0, 0), (0, 1)], [(0, 2), (0, 3)]])
        p.ch_one_cell = False
        p.width, p.tajenka_cells = 6, [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4)]
        self.assertEqual(p.tajenka_run_cells(), [[(0, 0), (0, 1), (0, 2)], [(0, 3), (0, 4)]])

    def test_empty_pieces_are_skipped(self):
        p = swedish_puzzle()
        p.tajenka = "/ KOSA /"
        self.assertEqual(p.tajenka_run_cells(), [[(2, 1), (2, 2), (2, 3), (2, 4)]])

    def test_lengths_that_do_not_add_up_give_one_run(self):
        p = swedish_puzzle()
        p.tajenka = "KO / S"
        self.assertEqual(p.tajenka_run_cells(), [[(2, 1), (2, 2), (2, 3), (2, 4)]])

    def test_untokenisable_tajenka_gives_one_run(self):
        p = swedish_puzzle()
        p.tajenka = "12 / 34"
        self.assertEqual(p.tajenka_run_cells(), [[(2, 1), (2, 2), (2, 3), (2, 4)]])

    def test_no_tajenka_or_no_cells(self):
        p = swedish_puzzle()
        p.tajenka = None
        self.assertEqual(p.tajenka_run_cells(), [])
        p = swedish_puzzle()
        p.tajenka_cells = []
        self.assertEqual(p.tajenka_run_cells(), [])

    def test_tajenka_entries_maps_entry_to_run(self):
        self.assertEqual(swedish_puzzle().tajenka_entries(), {1: 0})

    def test_tajenka_entries_two_runs(self):
        p = swedish_puzzle()
        p.tajenka = "PES / ULAD"
        p.tajenka_cells = [(1, 2), (1, 3), (1, 4), (3, 1), (3, 2), (3, 3), (3, 4)]
        self.assertEqual(p.tajenka_entries(), {0: 0, 2: 1})

    def test_tajenka_entries_down_entry(self):
        p = swedish_puzzle()
        p.tajenka = "KUS"
        p.tajenka_cells = [(2, 1), (3, 1), (4, 1)]
        self.assertEqual(p.tajenka_entries(), {4: 0})

    def test_tajenka_entries_run_that_is_no_entry(self):
        p = swedish_puzzle()
        p.tajenka = "KOS"
        p.tajenka_cells = [(2, 1), (2, 2), (2, 3)]
        self.assertEqual(p.tajenka_entries(), {})
        p.tajenka = None
        self.assertEqual(p.tajenka_entries(), {})


if __name__ == "__main__":
    unittest.main()
