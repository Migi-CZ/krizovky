import unittest

from krizovky import grid, model
from krizovky.model import Entry, Placement, Puzzle


def web_puzzle():
    """PES across at (0,0), SEN down at (0,2) sharing S."""
    entries = [Entry.from_word("pes"), Entry.from_word("sen")]
    placements = [Placement(0, 0, model.ACROSS), Placement(0, 2, model.DOWN)]
    return Puzzle(mode="web", width=5, height=5, entries=entries, placements=placements)


def shifted_puzzle():
    """Same web puzzle moved to (1,2): row 0 and columns 0-1 are empty."""
    p = web_puzzle()
    p.placements = [Placement(1, 2, model.ACROSS), Placement(1, 4, model.DOWN)]
    p.width, p.height = 7, 5
    return p


class FilledCellsTests(unittest.TestCase):
    def test_filled_cells_maps_coords_to_keys(self):
        self.assertEqual(grid.filled_cells(web_puzzle()),
                         {(0, 0): "P", (0, 1): "E", (0, 2): "S", (1, 2): "E", (2, 2): "N"})

    def test_bounding_box(self):
        self.assertEqual(grid.bounding_box(web_puzzle()), (0, 0, 2, 2))
        self.assertEqual(grid.bounding_box(shifted_puzzle()), (1, 2, 3, 4))

    def test_bounding_box_of_empty_puzzle_raises(self):
        with self.assertRaises(ValueError):
            grid.bounding_box(Puzzle(mode="web", width=3, height=3))


class TrimTests(unittest.TestCase):
    def test_trim_shifts_everything_to_origin(self):
        p = shifted_puzzle()
        p.tajenka = "ee"
        p.tajenka_cells = [(1, 3), (2, 4)]
        p.blocks = [(0, 0)]
        t = grid.trim(p)
        self.assertEqual((t.width, t.height), (3, 3))
        self.assertEqual([(x.row, x.col) for x in t.placements], [(0, 0), (0, 2)])
        self.assertEqual(t.tajenka_cells, [(0, 1), (1, 2)])
        self.assertEqual(t.blocks, [(-1, -2)])
        self.assertEqual(t.grid(), [["P", "E", "S"], [None, None, "E"], [None, None, "N"]])

    def test_trim_does_not_modify_the_original(self):
        p = shifted_puzzle()
        grid.trim(p)
        self.assertEqual((p.width, p.height, p.placements[0].row), (7, 5, 1))

    def test_trim_of_tight_puzzle_is_identity(self):
        p = web_puzzle()
        p.width = p.height = 3
        self.assertEqual(grid.trim(p), p)


class NumberingTests(unittest.TestCase):
    def test_web_example_numbers(self):
        p = web_puzzle()
        grid.number_entries(p)
        self.assertEqual([x.number for x in p.placements], [1, 2])

    def test_across_and_down_starting_together_share_a_number(self):
        entries = [Entry.from_word("pes"), Entry.from_word("pan"), Entry.from_word("sen")]
        placements = [Placement(0, 0, model.ACROSS), Placement(0, 0, model.DOWN),
                      Placement(0, 2, model.DOWN)]
        p = Puzzle(mode="web", width=5, height=5, entries=entries, placements=placements)
        grid.number_entries(p)
        self.assertEqual([x.number for x in p.placements], [1, 1, 2])

    def test_numbers_follow_row_major_order_not_entry_order(self):
        entries = [Entry.from_word("sen"), Entry.from_word("pes")]
        placements = [Placement(0, 2, model.DOWN), Placement(0, 0, model.ACROSS)]
        p = Puzzle(mode="web", width=5, height=5, entries=entries, placements=placements)
        grid.number_entries(p)
        self.assertEqual([x.number for x in p.placements], [2, 1])


if __name__ == "__main__":
    unittest.main()
