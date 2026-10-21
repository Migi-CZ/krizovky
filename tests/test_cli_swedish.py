"""Slice 5 / U3: ``generate --mode swedish`` through ``cli.main`` without the real dictionary.

``filler_dense.solve`` is mocked to return the hand-made fixture puzzle; ``--data`` points at a
3-row dictionary in a temp folder, so ``wordlist.load`` and ``Lexicon`` still run for real.
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from krizovky import cli, filler_dense, wordlist
from krizovky.pattern_swedish import PatternError
try:
    from tests.swedish_fixture import swedish_puzzle
except ImportError:
    from swedish_fixture import swedish_puzzle   # discover -s tests

SOLVE = "krizovky.cli.filler_dense.solve"
ROWS = ["pes\tpes\tnoun\t\tdomácí šelma\t\t10\t", "kosa\tkosa\tnoun\t\tnástroj na sekání\t\t8\t",
        "seto\tseto\tnoun\t\tjaponské moře\t\t5\t"]
TAJENKA = "KOSA"


def fresh_puzzle():
    """The fixture as the filler delivers it: no clues yet."""
    p = swedish_puzzle()
    for e in p.entries:
        e.clue = None
    return p


def fill_result():
    return filler_dense.FillResult(puzzle=fresh_puzzle(), nodes=1, restarts=0, seconds=0.1,
                                   pattern=None, repairs=0)


def run(argv):
    """cli.main in-process -> (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class TimeoutDefaultTests(unittest.TestCase):
    def test_swedish_timeout_default_is_180_s(self):
        # 180 s since 2026-10-21 (slice 7b, owner): the cleaned dictionary has fewer short words, the 16x12 p90
        # is 63 s and one bench run of 40 needed more than 120 s (`out/bench7b/r3_final.txt`)
        args = cli.build_parser().parse_args(["generate", "--mode", "swedish", "--tajenka", "A", "--out", "x"])
        self.assertEqual(args.timeout, 180)


class SwedishCliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.data = self.tmp / "words.tsv"
        self.data.write_text("\t".join(wordlist.COLUMNS) + "\n" + "\n".join(ROWS) + "\n", encoding="utf-8")
        self.out = self.tmp / "out"

    def generate(self, *extra, tajenka=TAJENKA):
        return run(["generate", "--mode", "swedish", "--size", "5", "--tajenka", tajenka,
                    "--data", str(self.data), "--out", str(self.out), *extra])

    def test_generate_requests_clues(self):
        with mock.patch(SOLVE, return_value=fill_result()) as solve:
            code, out, _ = self.generate("--title", "Zkouška", "--header", "Úvod", "--seed", "4", "--timeout", "7")
        self.assertEqual(code, cli.EXIT_CLUES)
        args = solve.call_args
        self.assertEqual(args.args[:3], (5, 5, TAJENKA))
        self.assertEqual(args.kwargs["timeout"], 7.0)
        self.assertIn("filled 5x5 in 0.1 s: 8 words, 0 repairs, inner blocks 0 %", out)
        for name in ("puzzle.json", "puzzle.svg", "solution.svg", "solution.md", "request.json"):
            self.assertTrue((self.out / name).is_file(), name)
        saved = json.loads((self.out / "puzzle.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["entries"][1]["clue"], "tajenka")
        self.assertEqual(saved["meta"]["header"], "Úvod")
        self.assertEqual((saved["meta"]["seed"], saved["meta"]["names"], saved["meta"]["timeout"]),
                         (4, True, 7.0))
        items = json.loads((self.out / "request.json").read_text(encoding="utf-8"))["items"]
        self.assertEqual(len(items), 7)
        by_answer = {i["answer"]: i for i in items}
        self.assertNotIn("KOSA", by_answer)
        self.assertEqual(by_answer["PES"]["gloss"], "domácí šelma")

    def test_names_are_passed_to_the_lexicon(self):
        for extra, names in (((), True), (("--no-names",), False)):
            with mock.patch(SOLVE, return_value=fill_result()) as solve:
                self.generate(*extra)
            self.assertEqual(solve.call_args.args[3].names, names)

    def test_clues_round_trip_with_pomucka(self):
        with mock.patch(SOLVE, return_value=fill_result()):
            self.generate()
        clues = {"Pes": "Domácí zvíře", "Ulad": "Smyšlené slovo", "Seto": "Japonské moře", "Kus": "Část celku",
                 "Pole": "Lán", "Esat": "Zkratka (zkr.)", "Sado": "Japonský ostrov"}
        (self.out / "clues.json").write_text(json.dumps(
            {"version": 1, "clues": {k.upper(): v for k, v in clues.items()}, "pomucka": ["Seto", "Sado"]},
            ensure_ascii=False), encoding="utf-8")
        code, _, _ = run(["clues", str(self.out)])
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("Pomůcka", (self.out / "puzzle.svg").read_text(encoding="utf-8"))
        self.assertIn("**Pomůcka:**", (self.out / "solution.md").read_text(encoding="utf-8"))
        code, out, _ = run(["validate", str(self.out)])
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("mode swedish", out)

    def test_request_shrinks_to_the_missing_clues_and_goes_when_none_is_missing(self):
        with mock.patch(SOLVE, return_value=fill_result()):
            self.generate()
        request = self.out / "request.json"
        clues = {"PES": "Domácí zvíře", "ULAD": "Smyšlené slovo", "SETO": "Japonské moře", "KUS": "Část celku",
                 "POLE": "Lán", "ESAT": "Zkratka (zkr.)"}                  # SADO still missing
        (self.out / "clues.json").write_text(json.dumps({"version": 1, "clues": clues}, ensure_ascii=False),
                                             encoding="utf-8")
        code, out, _ = run(["clues", str(self.out)])
        self.assertEqual(code, cli.EXIT_CLUES)
        self.assertIn("1 clue(s) missing: SADO", out)
        self.assertEqual([i["answer"] for i in json.loads(request.read_text(encoding="utf-8"))["items"]], ["SADO"])
        clues["SADO"] = "Japonský ostrov"
        (self.out / "clues.json").write_text(json.dumps({"version": 1, "clues": clues}, ensure_ascii=False),
                                             encoding="utf-8")
        code, _, _ = run(["clues", str(self.out)])
        self.assertEqual(code, cli.EXIT_OK)
        self.assertFalse(request.exists())      # it would list a clue that is already answered

    def test_a_request_of_another_kind_or_an_unreadable_one_stays(self):
        with mock.patch(SOLVE, return_value=fill_result()):
            self.generate()
        clues = {"PES": "Domácí zvíře", "ULAD": "Smyšlené slovo", "SETO": "Japonské moře", "KUS": "Část celku",
                 "POLE": "Lán", "ESAT": "Zkratka (zkr.)", "SADO": "Japonský ostrov"}
        (self.out / "clues.json").write_text(json.dumps({"version": 1, "clues": clues}, ensure_ascii=False),
                                             encoding="utf-8")
        request = self.out / "request.json"
        for text in ('{"kind": "theme_words"}', "not json", "[1]"):
            request.write_text(text, encoding="utf-8")
            self.assertEqual(run(["clues", str(self.out)])[0], cli.EXIT_OK)
            self.assertEqual(request.read_text(encoding="utf-8"), text)

    def test_title_is_kept_and_first_run_does_not_warn_per_clue(self):
        with mock.patch(SOLVE, return_value=fill_result()):
            code, out, err = self.generate("--title", "Zkouška")
        self.assertEqual(code, cli.EXIT_CLUES)
        self.assertNotIn("missing in clues.json", err)   # the summary line already lists them
        self.assertIn("7 clue(s) missing", out)
        clues = {"PES": "Domácí zvíře", "ULAD": "Smyšlené slovo", "SETO": "Japonské moře", "KUS": "Část celku",
                 "POLE": "Lán", "ESAT": "Zkratka (zkr.)", "SADO": "Japonský ostrov"}
        (self.out / "clues.json").write_text(json.dumps({"version": 1, "clues": clues}, ensure_ascii=False),
                                             encoding="utf-8")
        code, _, _ = run(["clues", str(self.out)])            # no --title here: the saved one is used
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("Zkouška", (self.out / "puzzle.svg").read_text(encoding="utf-8"))
        code, _, _ = run(["render", str(self.out), "--title", "Jiný"])
        self.assertIn("Jiný", (self.out / "puzzle.svg").read_text(encoding="utf-8"))

    def test_words_file_is_refused(self):
        words = self.tmp / "w.txt"
        words.write_text("vlak\n", encoding="utf-8")
        with mock.patch(SOLVE, return_value=fill_result()) as solve:
            code, _, err = self.generate("--words", str(words))
        self.assertEqual(code, cli.EXIT_INPUT)
        self.assertIn("--words is not used", err)
        solve.assert_not_called()

    def test_no_ch_is_refused(self):
        with mock.patch(SOLVE, return_value=fill_result()) as solve:
            code, _, err = self.generate("--no-ch")
        self.assertEqual(code, cli.EXIT_INPUT)
        self.assertIn("CH as one cell", err)
        solve.assert_not_called()

    def test_bad_size_and_tajenka_and_data(self):
        with mock.patch(SOLVE, return_value=fill_result()) as solve:
            self.assertEqual(run(["generate", "--mode", "swedish", "--size", "abc", "--tajenka", TAJENKA,
                                  "--data", str(self.data), "--out", str(self.out)])[0], cli.EXIT_INPUT)
            self.assertEqual(self.generate(tajenka="/")[0], cli.EXIT_INPUT)   # no run at all
            code, _, err = run(["generate", "--mode", "swedish", "--tajenka", TAJENKA,
                                "--data", str(self.tmp / "missing.tsv"), "--out", str(self.out)])
            self.assertEqual(code, cli.EXIT_INPUT)
            self.assertIn("error:", err)
        solve.assert_not_called()

    def test_no_fill_is_exit_2(self):
        with mock.patch(SOLVE, return_value=None):
            code, out, err = self.generate("--timeout", "3")
        self.assertEqual(code, cli.EXIT_PLACEMENT)
        self.assertIn("no fill of 5x5 for this tajenka within 3 s", err)
        self.assertIn("--timeout", err)
        self.assertNotIn("filled", out)

    def test_pattern_error_is_exit_1(self):
        with mock.patch(SOLVE, side_effect=PatternError("x")):
            code, _, err = self.generate()
        self.assertEqual(code, cli.EXIT_INPUT)
        self.assertIn("error: x", err)

    def test_column_mode_is_unchanged(self):
        words = self.tmp / "w.txt"
        words.write_text("vlak\npes\nkos\n", encoding="utf-8")
        with mock.patch(SOLVE) as solve:
            code, out, _ = run(["generate", "--mode", "column", "--tajenka", "les", "--words", str(words),
                                "--out", str(self.tmp / "col")])
        self.assertEqual(code, cli.EXIT_CLUES)
        self.assertNotIn("filled", out)
        solve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
