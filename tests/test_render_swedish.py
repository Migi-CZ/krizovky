import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from krizovky import model, render_svg
from krizovky.model import Puzzle
try:
    from swedish_fixture import swedish_puzzle   # discover -s tests
except ImportError:
    from tests.swedish_fixture import swedish_puzzle

SVG = "{http://www.w3.org/2000/svg}"
LOGGER = "krizovky.render_swedish"


def swedish():
    from krizovky import render_swedish
    return render_swedish


def parse(text):
    return ET.fromstring(text)


def by_class(root, tag, cls):
    return [e for e in root.iter(SVG + tag) if e.get("class") == cls]


def text_of(e):
    return "".join(e.itertext())


def num(e, attr):
    return float(e.get(attr))


def render(p, *, solution=False, title=None):
    return parse(swedish().render_svg(p, solution=solution, title=title))


def cell_rect(root, r, c, cols=5):
    return by_class(root, "rect", "cell")[r * cols + c]


def texts_in(root, cls, rect):
    """Text elements of a class whose anchor point lies inside the given cell rect."""
    x, y, w, h = (num(rect, a) for a in ("x", "y", "width", "height"))
    return [t for t in by_class(root, "text", cls)
            if x <= num(t, "x") <= x + w and y <= num(t, "y") <= y + h]


def tajenka_puzzle():
    p = swedish_puzzle()
    p.entries[1].clue = "tajenka"
    return p


class TextFitTests(unittest.TestCase):
    def test_width_uses_table_bold_is_wider_and_unknown_is_07(self):
        m = swedish()
        w = m.text_width("AB", 10)
        self.assertAlmostEqual(w, (m._ADVANCE["A"] + m._ADVANCE["B"]) * 10)
        self.assertAlmostEqual(m.text_width("AB", 10, bold=True), w * 1.12)
        self.assertAlmostEqual(m.text_width("☃", 10), 7.0)

    def test_wrap_is_greedy_by_words(self):
        m = swedish()
        one = m.text_width("AAA BBB", 2)
        self.assertEqual(m.wrap("AAA BBB", 2, one + 0.1, False), ["AAA BBB"])
        self.assertEqual(m.wrap("AAA BBB", 2, one - 0.1, False), ["AAA", "BBB"])
        self.assertEqual(m.wrap("", 2, 10, False), [])

    def test_long_word_is_hyphenated_on_every_piece_but_the_last(self):
        m = swedish()
        max_w = m.text_width("KONSTR-", 2) + 0.05
        lines = m.wrap("KONSTRUKCE", 2, max_w, False)
        self.assertGreater(len(lines), 1)
        self.assertTrue(all(l.endswith("-") for l in lines[:-1]))
        self.assertFalse(lines[-1].endswith("-"))
        self.assertEqual("".join(l.rstrip("-") for l in lines), "KONSTRUKCE")
        self.assertTrue(all(m.text_width(l, 2) <= max_w for l in lines))

    def test_syllable_breaks_follow_czech_syllables(self):
        m = swedish()
        # cut positions k of word[:k] | word[k:]; pieces of one letter are never cut off
        self.assertEqual(m.syllable_breaks("LASICOVITA"), [2, 4, 6, 8])
        self.assertEqual(m.syllable_breaks("ADENOSINTRIFOSFÁT"), [3, 5, 8, 11, 14])   # sin|tri, fos|fát
        self.assertEqual(m.syllable_breaks("BECHYNĚ"), [2, 5])       # CH is one letter
        self.assertEqual(m.syllable_breaks("MOUKA"), [3])           # OU is one syllable
        self.assertEqual(m.syllable_breaks("KRTEK"), [2])           # syllabic R
        self.assertEqual(m.syllable_breaks("FRANCOUZSKÉ"), [4, 8])   # FRANCOUZ-SKÉ, not FRANCOUZS-KÉ
        self.assertEqual(m.syllable_breaks("VLK"), [])
        self.assertEqual(m.syllable_breaks("(ZKR.)"), [])           # never next to punctuation

    def test_long_word_is_cut_between_syllables(self):
        # the slice 6 sheet had LASICOVIT-A and ADENOSINTR-IFOSFÁT
        m = swedish()
        max_w = m.text_width("LASICOVIT-", 2) + 0.05
        self.assertEqual(m.wrap("LASICOVITA", 2, max_w, False), ["LASICOVI-", "TA"])
        max_w = m.text_width("ADENO-", 2) + 0.05
        self.assertEqual(m.wrap("ADENOSINTRIFOSFÁT", 2, max_w, False), ["ADENO-", "SINTRI-", "FOSFÁT"])

    def test_cut_without_a_syllable_break_leaves_no_single_letter(self):
        m = swedish()
        max_w = m.text_width("WWWWWW-", 2) + 0.05
        lines = m.wrap("WWWWWWW", 2, max_w, False)
        self.assertEqual(lines, ["WWWWW-", "WW"])

    def test_fit_prefers_largest_size_and_28_chars_fit_half_cell_at_13(self):
        m = swedish()
        S = 13.0
        for text in ("POHÁDKOVÁ POSTAVA ZE SEVERU", "ZAHRADNICKÉ NÁŘADÍ NA SEKÁNÍ",
                     "DRUH MOŘSKÉ ŘASY (MN. Č.)"):
            size, lines, dropped = m.fit(text, S - 1.2, S / 2 - 0.9, S, False)
            self.assertEqual(dropped, 0, text)
            self.assertLessEqual(len(lines) * m.LINE_H * size, S / 2 - 0.9 + 1e-9)
            self.assertIn(size, [S * f for f in (0.16, 0.145, 0.13, 0.115)])
        size, lines, dropped = m.fit("LÁN", S - 1.2, S - 1.2, S, False)
        self.assertEqual((size, lines, dropped), (0.16 * S, ["LÁN"], 0))

    def test_fit_drops_lines_that_do_not_fit_at_the_smallest_size(self):
        m = swedish()
        S = 13.0
        size, lines, dropped = m.fit("W" * 28, S - 1.2, S / 2 - 0.9, S, False)
        self.assertEqual(size, 0.115 * S)
        self.assertGreater(dropped, 0)
        self.assertLessEqual(len(lines) * m.LINE_H * size, S / 2 - 0.9 + 1e-9)

    def test_baselines_centre_the_block(self):
        m = swedish()
        lh = m.LINE_H * 2.0
        ys = m.baselines(2, 2.0, 10.0, 10.0)
        self.assertAlmostEqual(ys[0], 10 + (10 - 2 * lh) / 2 + m.BASELINE * 2.0)
        self.assertAlmostEqual(ys[1] - ys[0], lh)


class CellTests(unittest.TestCase):
    def test_25_cells_3_black_discs(self):
        root = render(swedish_puzzle())
        rects = by_class(root, "rect", "cell")
        self.assertEqual(len(rects), 25)
        S = num(rects[0], "width")
        self.assertEqual(S, 15)
        discs = by_class(root, "circle", "black")
        self.assertEqual(len(discs), 3)
        for d in discs:
            self.assertAlmostEqual(num(d, "r"), 0.3 * S, places=2)
        centres = {(round(num(d, "cx"), 2), round(num(d, "cy"), 2)) for d in discs}
        expect = {(round(num(cell_rect(root, r, c), "x") + S / 2, 2),
                   round(num(cell_rect(root, r, c), "y") + S / 2, 2))
                  for r, c in ((0, 0), (0, 1), (1, 0))}
        self.assertEqual(centres, expect)

    def test_cell_borders_and_outer_border(self):
        root = render(swedish_puzzle())
        self.assertTrue(all(r.get("stroke-width") == "0.3" for r in by_class(root, "rect", "cell")))
        border = by_class(root, "rect", "border")
        self.assertEqual(len(border), 1)
        self.assertEqual(border[0].get("stroke-width"), "0.8")
        self.assertEqual(border[0].get("fill"), "none")

    def test_split_cell_has_one_line_across_above_down_below(self):
        root = render(swedish_puzzle())
        rect = cell_rect(root, 1, 1)
        x, y, S = num(rect, "x"), num(rect, "y"), num(rect, "width")
        lines = by_class(root, "line", "split")
        self.assertEqual(len(lines), 1)
        ln = lines[0]
        self.assertAlmostEqual(num(ln, "y1"), y + S / 2, places=2)
        self.assertAlmostEqual(num(ln, "y2"), y + S / 2, places=2)
        self.assertAlmostEqual(num(ln, "x1"), x, places=2)
        self.assertAlmostEqual(num(ln, "x2"), x + S, places=2)
        above = [t for t in texts_in(root, "clue", rect) if num(t, "y") < y + S / 2]
        below = [t for t in texts_in(root, "clue", rect) if num(t, "y") > y + S / 2]
        self.assertEqual(" ".join(text_of(t) for t in above), "DOMÁCÍ ZVÍŘE")
        self.assertEqual(" ".join(text_of(t) for t in below), "ČÁST CELKU")

    def test_whole_cell_clue_is_centred_and_upper_case(self):
        root = render(tajenka_puzzle())
        rect = cell_rect(root, 0, 2)
        S = num(rect, "width")
        ts = texts_in(root, "clue", rect)
        self.assertEqual([text_of(t) for t in ts], ["LÁN"])
        self.assertEqual(ts[0].get("text-anchor"), "middle")
        self.assertAlmostEqual(num(ts[0], "x"), num(rect, "x") + S / 2, places=2)
        for t in by_class(root, "text", "clue"):
            self.assertEqual(text_of(t), text_of(t).upper())

    def test_clue_text_stays_inside_its_cell(self):
        root = render(swedish_puzzle())
        for t in by_class(root, "text", "clue"):
            owners = [r for r in by_class(root, "rect", "cell")
                      if num(r, "x") <= num(t, "x") <= num(r, "x") + num(r, "width")
                      and num(r, "y") < num(t, "y") <= num(r, "y") + num(r, "height")]
            self.assertEqual(len(owners), 1)

    def test_tajenka_cells_grey_and_label_bold(self):
        root = render(tajenka_puzzle())
        grey = [r for r in by_class(root, "rect", "cell") if r.get("fill") == "#e0e0e0"]
        self.assertEqual(len(grey), 4)
        ts = texts_in(root, "clue", cell_rect(root, 2, 0))
        self.assertEqual([text_of(t) for t in ts], ["TAJENKA"])
        self.assertEqual(ts[0].get("font-weight"), "bold")
        bold = [t for t in by_class(root, "text", "clue") if t.get("font-weight") == "bold"]
        self.assertEqual(len(bold), 1)

    def test_missing_clue_placeholder(self):
        root = render(swedish_puzzle())          # entry 1 (tajenka) has no clue
        ts = texts_in(root, "clue", cell_rect(root, 2, 0))
        self.assertEqual([text_of(t) for t in ts], [render_svg.MISSING_CLUE])

    def test_text_is_escaped(self):
        p = tajenka_puzzle()
        p.entries[0].clue = "Tom & Jerry <3"
        self.assertIn("TOM & JERRY <3", " ".join(text_of(t) for t in by_class(render(p), "text", "clue")))

    def test_puzzle_hides_letters_solution_shows_them(self):
        p = tajenka_puzzle()
        self.assertEqual(by_class(render(p), "text", "letter"), [])
        sol = by_class(render(p, solution=True), "text", "letter")
        self.assertEqual(sorted(text_of(t) for t in sol),
                         sorted("PESKOSAULADSETO" ))
        root = render(p, solution=True)
        S = 15
        self.assertTrue(all(num(t, "font-size") == 0.6 * S for t in by_class(root, "text", "letter")))

    def test_ch_letter_is_smaller(self):
        p = Puzzle(mode="swedish", width=3, height=2, blocks=[(0, 0), (0, 1), (0, 2), (1, 0)],
                   entries=[model.Entry.from_word("cha", clue="Kolo")],
                   placements=[model.Placement(1, 1, model.ACROSS)])
        sizes = {text_of(t): num(t, "font-size")
                 for t in by_class(render(p, solution=True), "text", "letter")}
        self.assertEqual(set(sizes), {"CH", "A"})
        self.assertAlmostEqual(sizes["CH"], 0.42 * 15)
        self.assertAlmostEqual(sizes["A"], 0.6 * 15)

    def test_empty_non_block_cell_is_a_white_letter_cell(self):
        p = Puzzle(mode="swedish", width=3, height=2, blocks=[(0, 0)])
        root = render(p)
        rects = by_class(root, "rect", "cell")
        self.assertEqual(len(rects), 6)
        self.assertEqual(len(by_class(root, "circle", "black")), 1)
        self.assertTrue(all(r.get("fill") == "#ffffff" for r in rects))


class PageTests(unittest.TestCase):
    def test_title_header_and_solution_suffix(self):
        p = tajenka_puzzle()
        p.meta["header"] = "Slova " * 40
        root = render(p, solution=True, title="Zkouška")
        self.assertEqual(text_of(by_class(root, "text", "title")[0]), "Zkouška – řešení")
        lines = [text_of(t) for t in by_class(root, "text", "header")]
        self.assertGreater(len(lines), 1)
        self.assertTrue(all(len(l) <= 95 for l in lines))
        self.assertEqual(" ".join(lines), ("Slova " * 40).strip())
        self.assertTrue(all(t.get("font-size") == "3.2" for t in by_class(root, "text", "header")))

    def test_header_falls_back_to_theme_and_grid_moves_up_without_it(self):
        p = tajenka_puzzle()
        y_none = num(cell_rect(render(p), 0, 0), "y")
        p.meta["theme"] = "Ekologie"
        root = render(p)
        self.assertEqual([text_of(t) for t in by_class(root, "text", "header")], ["Ekologie"])
        self.assertGreater(num(cell_rect(root, 0, 0), "y"), y_none)

    def test_clue_overflow_logs_warning_not_exception(self):
        p = tajenka_puzzle()
        p.entries[0].clue = "W" * 40             # upper half of the split cell (1,1)
        with self.assertLogs(LOGGER, "WARNING") as cm:
            render(p)
        self.assertIn("does not fit", cm.output[0])

    def test_28_char_clue_in_a_split_cell_logs_nothing(self):
        p = tajenka_puzzle()
        p.entries[0].clue = "Pohádková postava ze severu"
        with self.assertNoLogs(LOGGER, "WARNING"):
            render(p)

    def test_fixture_renders_without_warnings(self):
        with self.assertNoLogs(LOGGER, "WARNING"):
            render(tajenka_puzzle(), solution=True)

    def test_pomucka_line(self):
        p = tajenka_puzzle()
        p.meta["pomucka"] = ["Seto", "Sado"]
        root = render(p)
        pom = by_class(root, "text", "pomucka")
        self.assertEqual([text_of(t) for t in pom], ["Pomůcka:", "Seto, Sado."])
        self.assertEqual(pom[0].get("font-weight"), "bold")
        self.assertEqual({t.get("text-anchor") for t in pom}, {"start"})
        self.assertGreater(num(pom[1], "x"), num(pom[0], "x"))
        last = cell_rect(root, 4, 4)
        self.assertAlmostEqual(num(pom[0], "y"), num(last, "y") + num(last, "height") + 5, places=2)
        self.assertEqual(by_class(render(tajenka_puzzle()), "text", "pomucka"), [])

    def test_answer_boxes_empty_in_puzzle_filled_in_solution(self):
        p = tajenka_puzzle()
        self.assertEqual(len(by_class(render(p), "rect", "tajenka-box")), 4)
        self.assertEqual(by_class(render(p), "text", "box-letter"), [])
        sol = render(p, solution=True)
        self.assertEqual(len(by_class(sol, "rect", "tajenka-box")), 4)
        self.assertEqual("".join(text_of(t) for t in by_class(sol, "text", "box-letter")), "KOSA")
        grid_bottom = max(num(r, "y") + num(r, "height") for r in by_class(sol, "rect", "cell"))
        self.assertTrue(all(num(b, "y") > grid_bottom for b in by_class(sol, "rect", "tajenka-box")))

    def test_no_boxes_without_tajenka(self):
        p = tajenka_puzzle()
        p.tajenka, p.tajenka_cells = None, []
        self.assertEqual(by_class(render(p), "rect", "tajenka-box"), [])

    def test_no_forbidden_svg_features(self):
        s = swedish().render_svg(tajenka_puzzle(), solution=True)
        for bad in ("tspan", "textLength", "dominant-baseline", "<style"):
            self.assertNotIn(bad, s)

    def test_16x12_grid_shrinks_between_9_and_15(self):
        p = Puzzle(mode="swedish", width=12, height=16,
                   blocks=[(0, c) for c in range(12)] + [(r, 0) for r in range(1, 16)],
                   tajenka_cells=[(5, c) for c in range(1, 12)], tajenka="XXXXXXXXXXX",
                   meta={"header": "Hlavička křížovky", "pomucka": ["anis"]})
        S = num(render(p, solution=True).findall(f".//{SVG}rect[@class='cell']")[0], "width")
        self.assertGreaterEqual(S, 9)
        self.assertLess(S, 15)

    def test_cell_below_9_mm_raises(self):
        p = Puzzle(mode="swedish", width=25, height=3)
        with self.assertRaises(render_svg.RenderError):
            swedish().render_svg(p, solution=False)


class DispatchTests(unittest.TestCase):
    def test_write_all_uses_swedish_renderer(self):
        with tempfile.TemporaryDirectory() as d:
            out = render_svg.write_all(tajenka_puzzle(), Path(d) / "sub", title="T")
            self.assertEqual(set(out), {"puzzle_svg", "solution_svg", "solution_md"})
            root = parse(out["puzzle_svg"].read_text(encoding="utf-8"))
            self.assertEqual(len(by_class(root, "rect", "cell")), 25)
            sol = parse(out["solution_svg"].read_text(encoding="utf-8"))
            self.assertEqual(len(by_class(sol, "text", "letter")), 15)

    def test_column_output_is_unchanged_by_dispatch(self):
        try:
            from test_render import clued_column
        except ImportError:
            from tests.test_render import clued_column
        p = clued_column()
        with tempfile.TemporaryDirectory() as d:
            out = render_svg.write_all(p, Path(d))
            self.assertEqual(out["puzzle_svg"].read_text(encoding="utf-8"),
                             render_svg.render_svg(p, solution=False))

    def test_solution_md_lists_clues_by_position_and_pomucka(self):
        p = tajenka_puzzle()
        p.meta["pomucka"] = ["Seto", "Sado"]
        md = render_svg.render_solution_md(p, title="T")
        self.assertIn("**Tajenka:** KOSA\n\n**Pomůcka:** Seto, Sado\n", md)
        across = md.split("## Vodorovně")[1].split("## Svisle")[0]
        self.assertEqual([l for l in across.splitlines() if l.startswith("-")],
                         ["- PES — Domácí zvíře", "- KOSA — tajenka",
                          "- ULAD — Smyšlené slovo", "- SETO — Japonské moře"])
        down = md.split("## Svisle")[1]
        self.assertEqual([l.split(" — ")[0] for l in down.splitlines() if l.startswith("-")],
                         ["- POLE", "- ESAT", "- SADO", "- KUS"])

    def test_solution_md_without_pomucka_has_no_line(self):
        self.assertNotIn("Pomůcka", render_svg.render_solution_md(tajenka_puzzle()))


if __name__ == "__main__":
    unittest.main()
