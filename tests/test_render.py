import shutil
import tempfile
import subprocess
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from krizovky import model, render_pdf, render_svg
from krizovky.model import Entry, Placement, Puzzle
try:
    from test_validate import column_puzzle, web_puzzle   # discover -s tests
except ImportError:
    from tests.test_validate import column_puzzle, web_puzzle

SVG = "{http://www.w3.org/2000/svg}"


def parse(text):
    return ET.fromstring(text)


def cells(root):
    return [r for r in root.iter(SVG + "rect")]


def all_text(root):
    return " ".join("".join(t.itertext()) for t in root.iter(SVG + "text"))


def clued_column():
    p = column_puzzle()
    p.entries[0].clue = "Jede po kolejích"
    p.entries[1].clue = "Příliš žluťoučký kůň"
    p.entries[2].clue = None
    return p


def numbered_web():
    p = web_puzzle()
    p.placements[0].number = 1
    p.placements[1].number = 2
    p.entries[0].clue = "Věrný přítel"
    p.entries[1].clue = "Spánek"
    return p


class SvgBasicsTests(unittest.TestCase):
    def test_root_is_a4_in_mm(self):
        root = parse(render_svg.render_svg(clued_column(), solution=False))
        self.assertEqual(root.get("width"), "210mm")
        self.assertEqual(root.get("height"), "297mm")
        self.assertEqual(root.get("viewBox"), "0 0 210 297")

    def test_one_rect_per_filled_cell(self):
        p = clued_column()
        filled = sum(1 for row in p.grid() for k in row if k is not None)
        root = parse(render_svg.render_svg(p, solution=False))
        self.assertEqual(len(cells(root)), filled)

    def test_tajenka_cells_are_grey_with_thick_border(self):
        p = clued_column()
        root = parse(render_svg.render_svg(p, solution=False))
        grey = [r for r in cells(root) if r.get("fill") == "#e0e0e0"]
        self.assertEqual(len(grey), len(p.tajenka_cells))
        self.assertTrue(all(r.get("stroke-width") == "0.9" for r in grey))
        others = [r for r in cells(root) if r.get("fill") != "#e0e0e0"]
        self.assertTrue(all(r.get("stroke-width") == "0.4" for r in others))

    def test_blocks_are_black_cells(self):
        p = web_puzzle()
        p.blocks = [(4, 4)]
        root = parse(render_svg.render_svg(p, solution=False))
        self.assertEqual(len([r for r in cells(root) if r.get("fill") == "#000000"]), 1)

    def test_puzzle_hides_letters_and_tajenka_solution_shows_them(self):
        p = clued_column()
        puzzle_text = all_text(parse(render_svg.render_svg(p, solution=False)))
        solution_text = all_text(parse(render_svg.render_svg(p, solution=True)))
        self.assertNotIn("LES", puzzle_text.upper().replace("PŘÍLIŠ", ""))
        for letter in "VLAK":
            self.assertIn(letter, solution_text)
        self.assertNotIn("VLAK", puzzle_text)

    def test_title_default_and_custom(self):
        p = clued_column()
        self.assertIn("Křížovka", all_text(parse(render_svg.render_svg(p, solution=False))))
        text = all_text(parse(render_svg.render_svg(p, solution=False, title="Den Země")))
        self.assertIn("Den Země", text)

    def test_text_is_escaped(self):
        p = clued_column()
        p.entries[0].clue = "Tom & Jerry <3"
        root = parse(render_svg.render_svg(p, solution=False))
        self.assertIn("Tom & Jerry <3", all_text(root))

    def test_theme_in_footer(self):
        p = clued_column()
        p.meta["theme"] = "Ekologie"
        self.assertIn("Ekologie", all_text(parse(render_svg.render_svg(p, solution=False))))

    def test_ch_cell_uses_smaller_font(self):
        p = column_puzzle()
        p.entries[0] = Entry.from_word("chata")
        p.entries[0].clue = "Domek"
        p.tajenka = None
        p.tajenka_cells = []
        root = parse(render_svg.render_svg(p, solution=True))
        sizes = {"".join(t.itertext()): t.get("font-size") for t in root.iter(SVG + "text")}
        self.assertEqual(sizes["CH"], "4.2")
        self.assertEqual(sizes["A"], "6")


class ColumnModeTests(unittest.TestCase):
    def test_numbered_by_row_and_missing_clue_placeholder(self):
        text = all_text(parse(render_svg.render_svg(clued_column(), solution=False)))
        self.assertIn("1. Jede po kolejích", text)
        self.assertIn("2. Příliš žluťoučký kůň", text)
        self.assertIn("3. (doplňte)", text)

    def test_word_separator_lines(self):
        p = clued_column()
        p.tajenka = "ab c"          # words of 2 and 1 cells; only 3 tajenka cells
        root = parse(render_svg.render_svg(p, solution=False))
        thick = [ln for ln in root.iter(SVG + "line") if ln.get("stroke-width") == "0.9"]
        self.assertEqual(len(thick), 1)   # between word 1 and word 2 only

    def test_no_separator_for_single_word(self):
        root = parse(render_svg.render_svg(clued_column(), solution=False))
        self.assertEqual([ln for ln in root.iter(SVG + "line")], [])


class WebModeTests(unittest.TestCase):
    def test_clue_numbers_and_groups(self):
        text = all_text(parse(render_svg.render_svg(numbered_web(), solution=False)))
        self.assertIn("Vodorovně", text)
        self.assertIn("Svisle", text)
        self.assertIn("1. Věrný přítel", text)
        self.assertIn("2. Spánek", text)

    def test_cell_number_small_text(self):
        root = parse(render_svg.render_svg(numbered_web(), solution=False))
        small = [t for t in root.iter(SVG + "text") if t.get("font-size") == "2.8"]
        self.assertEqual(sorted("".join(t.itertext()) for t in small), ["1", "2"])

    def test_tajenka_index_in_web(self):
        p = numbered_web()
        p.tajenka = "ps"
        p.tajenka_cells = [(0, 0), (0, 1)]
        root = parse(render_svg.render_svg(p, solution=False))
        idx = [t for t in root.iter(SVG + "text") if t.get("font-size") == "2.2"]
        self.assertEqual(sorted("".join(t.itertext()) for t in idx), ["1", "2"])


class FitTests(unittest.TestCase):
    def test_wide_grid_is_scaled_down(self):
        p = Puzzle(mode="web", width=30, height=3,
                   entries=[Entry.from_word("pes", clue="x")], placements=[Placement(0, 0, model.ACROSS)])
        text = render_svg.render_svg(p, solution=False)
        self.assertIn("scale(0.", text)

    def test_many_clues_use_second_column(self):
        n = 30
        entries = [Entry.from_word("pes", clue="dlouhá nápověda " * 2) for _ in range(n)]
        placements = [Placement(i, 0, model.ACROSS) for i in range(n)]
        p = Puzzle(mode="column", width=3, height=n, entries=entries, placements=placements)
        root = parse(render_svg.render_svg(p, solution=False))
        xs = {t.get("x") for t in root.iter(SVG + "text") if t.get("font-size") == "3.4"}
        self.assertEqual(xs, {"15", "110"})

    def test_overflow_raises(self):
        entries = [Entry.from_word("pes", clue="nápověda " * 6) for _ in range(300)]
        placements = [Placement(i, 0, model.ACROSS) for i in range(300)]
        p = Puzzle(mode="column", width=3, height=300, entries=entries, placements=placements)
        with self.assertRaises(render_svg.RenderError):
            render_svg.render_svg(p, solution=False)


class SolutionMdTests(unittest.TestCase):
    def test_exact_small_example(self):
        p = clued_column()
        p.entries[0].clue = "Jede po kolejích"
        expected = (
            "# Křížovka – řešení\n"
            "\n"
            "**Tajenka:** les\n"
            "\n"
            "```text\n"
            ". V L A K\n"
            ". P E S .\n"
            "K O S . .\n"
            "```\n"
            "\n"
            "## Nápovědy\n"
            "\n"
            "1. VLAK — Jede po kolejích\n"
            "2. PES — Příliš žluťoučký kůň\n"
            "3. KOS — (doplňte)\n"
        )
        self.assertEqual(render_svg.render_solution_md(p), expected)

    def test_web_groups_and_ch_alignment(self):
        p = numbered_web()
        md = render_svg.render_solution_md(p)
        self.assertIn("## Vodorovně", md)
        self.assertIn("1. PES — Věrný přítel", md)
        self.assertIn("2. SEN — Spánek", md)
        p2 = column_puzzle()
        p2.entries[0] = Entry.from_word("chata")
        p2.tajenka = None
        p2.tajenka_cells = []
        self.assertIn("CH A T A", render_svg.render_solution_md(p2).replace("  ", " "))


def tajenka_web(text="SEN", cells=((0, 2), (1, 2), (2, 2))):
    p = numbered_web()
    p.tajenka = text
    p.tajenka_cells = [tuple(c) for c in cells]
    return p


def tajenka_boxes(root):
    return [r for r in root.iter(SVG + "rect") if r.get("class") == "tajenka-box"]


def below_grid_texts(root, min_y=50.0):
    """Texts of the grid group that sit under the 5x5 grid (the tajenka boxes area)."""
    return [(float(t.get("x")), float(t.get("y")), "".join(t.itertext()))
            for t in root.iter(SVG + "text")
            if t.get("font-size") != "3.4" and float(t.get("y")) > min_y and float(t.get("y")) < 120]


class TajenkaBoxTests(unittest.TestCase):
    def test_boxes_empty_in_puzzle(self):
        root = parse(render_svg.render_svg(tajenka_web(), solution=False))
        self.assertEqual(len(tajenka_boxes(root)), 3)
        texts = below_grid_texts(root)
        self.assertEqual(sorted(t for _, _, t in texts), ["1", "2", "3"])

    def test_indexes_and_letters_in_solution(self):
        root = parse(render_svg.render_svg(tajenka_web(), solution=True))
        self.assertEqual(len(tajenka_boxes(root)), 3)
        contents = [t for _, _, t in below_grid_texts(root)]
        for expected in ("1", "2", "3", "S", "E", "N"):
            self.assertIn(expected, contents)
        boxes = sorted(tajenka_boxes(root), key=lambda r: float(r.get("x")))
        letters = sorted((x, t) for x, _, t in below_grid_texts(root) if t in "SEN")
        self.assertEqual(len(letters), 3)
        for (x, t), box, want in zip(letters, boxes, "SEN"):
            self.assertAlmostEqual(x, float(box.get("x")) + 3.0, places=1)
            self.assertEqual(t, want)

    def test_two_word_tajenka_has_gap(self):
        p = tajenka_web("PES SEN", [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2), (3, 2)])
        boxes = sorted(tajenka_boxes(parse(render_svg.render_svg(p, solution=False))),
                       key=lambda r: float(r.get("x")))
        self.assertEqual(len(boxes), 6)
        self.assertGreater(float(boxes[3].get("x")), float(boxes[2].get("x")) + 6 + 1)
        self.assertAlmostEqual(float(boxes[2].get("x")) + 6, float(boxes[1].get("x")) + 12)

    def test_long_tajenka_wraps_to_second_row(self):
        text = "AAAAAAAAAAAA"                     # 12 boxes = 72 mm > 50 mm grid
        cells = [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2), (0, 3), (0, 4), (1, 4), (2, 4), (3, 4), (4, 4), (4, 3)]
        boxes = tajenka_boxes(parse(render_svg.render_svg(tajenka_web(text, cells), solution=False)))
        self.assertEqual(len(boxes), 12)
        self.assertEqual(len({r.get("y") for r in boxes}), 2)
        self.assertTrue(all(float(r.get("x")) + 6 <= 50.0 + 1e-6 for r in boxes))

    def test_clues_start_below_boxes(self):
        def first_clue_y(p):
            root = parse(render_svg.render_svg(p, solution=False))
            return min(float(t.get("y")) for t in root.iter(SVG + "text") if t.get("font-size") == "3.4")
        self.assertGreater(first_clue_y(tajenka_web()), first_clue_y(numbered_web()) + 8)

    def test_no_boxes_in_column_mode_or_without_tajenka(self):
        self.assertEqual(tajenka_boxes(parse(render_svg.render_svg(clued_column(), solution=True))), [])
        self.assertEqual(tajenka_boxes(parse(render_svg.render_svg(numbered_web(), solution=True))), [])


def many_clue_web(n, clue):
    entries = [Entry.from_word("pes", clue=clue) for _ in range(n)]
    placements = [Placement(0, 0, model.ACROSS, number=i + 1) for i in range(n)]
    return Puzzle(mode="web", width=5, height=5, entries=entries, placements=placements)


def clue_xs(p):
    root = parse(render_svg.render_svg(p, solution=False))
    return {t.get("x") for t in root.iter(SVG + "text") if t.get("font-size") == "3.4"}


class ClueColumnsTests(unittest.TestCase):
    # Short clues keep the line count equal in both wraps, so only the column count differs.
    def test_many_clues_use_three_columns(self):
        xs = clue_xs(many_clue_web(100, "Krátká nápověda číslo"))
        step = (160 / 3) + 10
        got = sorted(float(x) for x in xs)
        self.assertEqual(len(got), 3)
        for x, want in zip(got, (15.0, 15 + step, 15 + 2 * step)):
            self.assertAlmostEqual(x, want, places=2)

    def test_short_list_uses_at_most_two_columns(self):
        self.assertLessEqual(len(clue_xs(many_clue_web(8, "Krátká nápověda"))), 2)
        self.assertLessEqual(len(clue_xs(many_clue_web(70, "Krátká"))), 2)

    def test_three_columns_rewrap_long_clues_at_28(self):
        p = many_clue_web(100, "Krátká nápověda číslo")
        p.entries[0].clue = "Velmi dlouhá nápověda, která se musí zalomit na více řádků"
        root = parse(render_svg.render_svg(p, solution=False))
        lengths = [len(t.text) for t in root.iter(SVG + "text") if t.get("font-size") == "3.4"]
        self.assertEqual(len({t.get("x") for t in root.iter(SVG + "text") if t.get("font-size") == "3.4"}), 3)
        self.assertLessEqual(max(lengths), 28)

    def test_two_column_wrap_unchanged_when_it_fits(self):
        p = many_clue_web(10, "Velmi dlouhá nápověda, která se musí zalomit na více řádků")
        root = parse(render_svg.render_svg(p, solution=False))
        lengths = [len(t.text) for t in root.iter(SVG + "text") if t.get("font-size") == "3.4"]
        self.assertGreater(max(lengths), 28)
        self.assertLessEqual(max(lengths), 45)


class DroppedWordsMdTests(unittest.TestCase):
    def test_dropped_section_lists_words(self):
        p = numbered_web()
        p.dropped = ["ALFA", "BETA"]
        md = render_svg.render_solution_md(p)
        self.assertIn("## Neumístěná slova", md)
        self.assertIn("- ALFA\n- BETA\n", md)

    def test_no_section_without_dropped(self):
        self.assertNotIn("Neumístěná", render_svg.render_solution_md(numbered_web()))


class WriteAllTests(unittest.TestCase):
    def test_writes_three_files(self):
        with tempfile.TemporaryDirectory() as d:
            out = render_svg.write_all(clued_column(), Path(d) / "sub")
            self.assertEqual(set(out), {"puzzle_svg", "solution_svg", "solution_md"})
            for path in out.values():
                self.assertTrue(path.is_file())
            self.assertEqual(out["puzzle_svg"].name, "puzzle.svg")
            parse(out["solution_svg"].read_text(encoding="utf-8"))


@unittest.skipUnless(render_pdf.soffice_path(), "soffice not installed")
class PdfTests(unittest.TestCase):
    def test_pdf_starts_with_header_and_keeps_czech_glyphs(self):
        p = column_puzzle()
        p.width = 8
        p.entries[0] = Entry.from_word("řeřicha", clue="Příliš žluťoučký kůň")
        p.entries[1].clue = "Ostrůvek"
        p.entries[2].clue = "Žluťoučký"
        p.tajenka = None
        p.tajenka_cells = []
        with tempfile.TemporaryDirectory() as d:
            out = render_svg.write_all(p, Path(d))
            pdf = render_pdf.to_pdf(out["solution_svg"])
            self.assertEqual(pdf, Path(d) / "solution.pdf")
            self.assertEqual(pdf.read_bytes()[:4], b"%PDF")
            if shutil.which("pdftotext"):
                text = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True,
                                      text=True, check=True).stdout
                self.assertTrue("Ř" in text or "ř" in text, text)
                self.assertIn("ů", text)

    def test_missing_svg_raises(self):
        with self.assertRaises(render_pdf.PdfError):
            render_pdf.to_pdf(Path("/nonexistent/x.svg"))


class PdfErrorTests(unittest.TestCase):
    def test_missing_soffice_raises(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            svg = Path(d) / "a.svg"
            svg.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
            with mock.patch.object(render_pdf, "soffice_path", return_value=None):
                with self.assertRaises(render_pdf.PdfError):
                    render_pdf.to_pdf(svg)


if __name__ == "__main__":
    unittest.main()
