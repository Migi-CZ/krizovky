import json
import tempfile
import unittest
from pathlib import Path

from krizovky import clues, model
from krizovky.model import Entry, Placement, Puzzle

try:
    from tests.swedish_fixture import swedish_puzzle
except ImportError:  # run from inside tests/
    from swedish_fixture import swedish_puzzle


def puzzle(match="strict", mode="web"):
    entries = [Entry.from_word("zeme"), Entry.from_word("pes"), Entry.from_word("kos")]
    entries[0] = Entry.from_word("země")
    entries[2].clue = "černý pěvec"
    placements = [Placement(0, 0, model.ACROSS), Placement(2, 0, model.ACROSS), Placement(4, 0, model.ACROSS)]
    return Puzzle(mode=mode, width=6, height=6, match=match, entries=entries,
                  placements=placements, tajenka="Den Země")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class RequestTests(unittest.TestCase):
    def test_request_lists_only_missing_entries(self):
        p = puzzle()
        p.entries[1].clue = "   "  # blank counts as missing
        with tempfile.TemporaryDirectory() as d:
            path = clues.write_request(p, Path(d), theme="příroda")
            self.assertEqual(path.name, clues.REQUEST_NAME)
            req = load(path)
        self.assertEqual(req["kind"], "clues")
        self.assertEqual(req["theme"], "příroda")
        self.assertEqual(req["tajenka"], "Den Země")
        self.assertEqual([i["answer"] for i in req["items"]], ["ZEMĚ", "PES"])
        self.assertEqual(req["items"][0]["cells"], ["Z", "E", "M", "Ě"])
        self.assertEqual(req["items"][0]["length"], 4)
        self.assertEqual(req["schema"], {"version": 1, "clues": {"<ANSWER>": "<clue>"}})
        self.assertEqual(len(clues.missing_clues(p)), 2)

    def test_request_is_utf8_not_escaped(self):
        with tempfile.TemporaryDirectory() as d:
            path = clues.write_request(puzzle(), Path(d))
            self.assertIn("ZEMĚ", path.read_text(encoding="utf-8"))

    def test_theme_request_must_contain_from_tajenka(self):
        with tempfile.TemporaryDirectory() as d:
            path = clues.write_theme_request(Path(d), theme="ekologie", tajenka="Chudoba dd",
                                             count=30, max_len=9)
            req = load(path)
        self.assertEqual(req["kind"], "theme_words")
        cells = [m["cell"] for m in req["need"]["must_contain"]]
        self.assertEqual(cells, ["CH", "U", "D", "O", "B", "A"])  # CH one cell, deduplicated, in order
        self.assertTrue(all(m["min_words"] == 2 for m in req["need"]["must_contain"]))
        self.assertEqual(req["need"]["count"], 30)
        self.assertEqual(req["need"]["max_len"], 9)

    def test_theme_request_ch_two_cells(self):
        with tempfile.TemporaryDirectory() as d:
            req = load(clues.write_theme_request(Path(d), theme="x", tajenka="ch", count=5,
                                                 max_len=8, ch_one_cell=False))
        self.assertEqual([m["cell"] for m in req["need"]["must_contain"]], ["C", "H"])

    def test_theme_request_rejects_bad_tajenka(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                clues.write_theme_request(Path(d), theme="x", tajenka="12", count=5, max_len=8)


class ReadTests(unittest.TestCase):
    def read(self, text):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / clues.CLUES_NAME).write_text(text, encoding="utf-8")
            return clues.read_clues(Path(d))

    def test_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(clues.read_clues(Path(d)), {})

    def test_valid_file(self):
        data = self.read('{"version": 1, "clues": {"ZEMĚ": "planeta"}}')
        self.assertEqual(data["clues"], {"ZEMĚ": "planeta"})

    def test_malformed_files_raise_with_file_name(self):
        for text in ["{not json", "[]", '{"version": 2}', '{"version": 1, "clues": []}',
                     '{"version": 1, "clues": {"A": 1}}', '{"version": 1, "theme_words": {}}']:
            with self.subTest(text=text):
                with self.assertRaises(clues.CluesError) as cm:
                    self.read(text)
                self.assertIn(clues.CLUES_NAME, str(cm.exception))


class ApplyTests(unittest.TestCase):
    def test_valid_clue_applied(self):
        p = puzzle()
        problems = clues.apply_clues(p, {"clues": {"země": "planeta, na které žijeme", "PES": "věrný společník"}})
        self.assertEqual(problems, [])
        self.assertEqual(p.entries[0].clue, "planeta, na které žijeme")
        self.assertEqual(p.entries[1].clue, "věrný společník")

    def test_clue_with_answer_stem_reported_not_applied(self):
        p = puzzle()
        problems = clues.apply_clues(p, {"clues": {"ZEMĚ": "naše země", "PES": "věrný společník"}})
        self.assertEqual(len(problems), 1)
        self.assertIn("ZEMĚ", problems[0])
        self.assertIsNone(p.entries[0].clue)
        self.assertEqual(p.entries[1].clue, "věrný společník")

    def test_missing_clue_reported(self):
        p = puzzle()
        problems = clues.apply_clues(p, {"clues": {"ZEMĚ": "planeta"}})
        self.assertTrue(any("PES" in x and "missing" in x for x in problems))
        self.assertEqual(p.entries[2].clue, "černý pěvec")  # already had one: untouched, not reported
        self.assertFalse(any("KOS" in x for x in problems))

    def test_unknown_answer_reported(self):
        p = puzzle()
        problems = clues.apply_clues(p, {"clues": {"SLON": "velké zvíře"}})
        self.assertTrue(any("SLON" in x for x in problems))

    def test_diacritics_free_key_only_in_match_none(self):
        data = {"clues": {"ZEME": "planeta, na které žijeme"}}
        strict = puzzle("strict")
        problems = clues.apply_clues(strict, data)
        self.assertIsNone(strict.entries[0].clue)
        self.assertTrue(problems)
        loose = puzzle("none")
        clues.apply_clues(loose, data)
        self.assertEqual(loose.entries[0].clue, "planeta, na které žijeme")

    def test_bad_values_do_not_raise(self):
        p = puzzle()
        problems = clues.apply_clues(p, {"clues": {"ZEMĚ": 5, "PES": ""}})
        self.assertTrue(problems)
        self.assertIsNone(p.entries[0].clue)
        problems = clues.apply_clues(p, {"clues": "oops"})
        self.assertTrue(problems)

    def test_swedish_cap(self):
        p = puzzle(mode="swedish")
        problems = clues.apply_clues(p, {"clues": {"ZEMĚ": "planeta, na které všichni žijeme dnes"}})
        self.assertTrue(any("ZEMĚ" in x for x in problems))
        self.assertIsNone(p.entries[0].clue)


class ThemeWordsTests(unittest.TestCase):
    def test_invalid_word_skipped_and_logged(self):
        data = {"theme_words": [{"word": "recyklace", "clue": "třídění odpadu"},
                                {"word": "r2d2", "clue": "robot"},
                                {"word": "les"}, 42, {"clue": "x"}, {"word": "les", "clue": "dup"}]}
        with self.assertLogs("krizovky.clues", level="WARNING") as cm:
            out = clues.theme_words(data)
        self.assertEqual(out, [("RECYKLACE", "třídění odpadu"), ("LES", None)])
        self.assertTrue(any("R2D2" in m for m in cm.output))

    def test_no_theme_words(self):
        self.assertEqual(clues.theme_words({}), [])


class FallbackTests(unittest.TestCase):
    def test_gloss_cut_at_semicolon(self):
        item = {"answer": "ZEMĚ", "gloss": "planeta Sluneční soustavy; třetí od Slunce", "synonyms": []}
        self.assertEqual(clues.fallback_clue(item, "web"), "planeta Sluneční soustavy")

    def test_gloss_cut_at_parenthesis(self):
        item = {"answer": "PES", "gloss": "zvíře (šelma) domácí", "synonyms": []}
        self.assertEqual(clues.fallback_clue(item, "web"), "zvíře")

    def test_synonym_when_no_gloss(self):
        item = {"answer": "PES", "gloss": None, "synonyms": ["čtyřnožec", "ohař"]}
        self.assertEqual(clues.fallback_clue(item, "web"), "čtyřnožec")

    def test_none_when_invalid_or_empty(self):
        self.assertIsNone(clues.fallback_clue({"answer": "ZEMĚ", "gloss": "země kolem nás"}, "web"))
        self.assertIsNone(clues.fallback_clue({"answer": "PES", "gloss": None, "synonyms": []}, "web"))
        self.assertIsNone(clues.fallback_clue({"answer": "PES", "gloss": "x" * 90}, "web"))


class SwedishLabelTests(unittest.TestCase):
    def test_single_run_label(self):
        p = swedish_puzzle()
        self.assertEqual(clues.label_tajenka(p), ["tajenka"])
        self.assertEqual(p.entries[1].clue, "tajenka")
        self.assertEqual(clues.missing_clues(p), [])

    def test_idempotent_and_keeps_existing_clue(self):
        p = swedish_puzzle()
        clues.label_tajenka(p)
        self.assertEqual(clues.label_tajenka(p), [])
        self.assertEqual(p.entries[1].clue, "tajenka")
        p.entries[1].clue = "Vlastní popisek"
        self.assertEqual(clues.label_tajenka(p), [])
        self.assertEqual(p.entries[1].clue, "Vlastní popisek")

    def test_several_runs_are_numbered(self):
        p = swedish_puzzle()
        p.tajenka = "PES / ULAD"
        p.tajenka_cells = [(1, 2), (1, 3), (1, 4), (3, 1), (3, 2), (3, 3), (3, 4)]
        p.entries[0].clue = p.entries[2].clue = None
        self.assertEqual(clues.label_tajenka(p), ["1. díl tajenky", "2. díl tajenky"])
        self.assertEqual((p.entries[0].clue, p.entries[2].clue), ("1. díl tajenky", "2. díl tajenky"))

    def test_other_modes_are_untouched(self):
        p = swedish_puzzle()
        p.mode = "web"
        self.assertEqual(clues.label_tajenka(p), [])
        self.assertIsNone(p.entries[1].clue)


class SwedishRequestTests(unittest.TestCase):
    def request(self, p):
        with tempfile.TemporaryDirectory() as d:
            return load(clues.write_request(p, Path(d)))

    def puzzle(self):
        p = swedish_puzzle()
        clues.label_tajenka(p)
        for i in (0, 3, 6):                       # PES, SETO, ESAT
            p.entries[i].clue = None
        return p

    def test_items_carry_dictionary_data(self):
        req = self.request(self.puzzle())
        items = {i["answer"]: i for i in req["items"]}
        self.assertEqual(list(items), ["PES", "SETO", "ESAT"])     # tajenka entry is not asked for
        self.assertEqual((items["PES"]["gloss"], items["PES"]["form"], items["PES"]["flags"], items["PES"]["freq"]),
                         ("domácí šelma", "", [], 1200))
        self.assertEqual(items["ESAT"]["flags"], ["zkr."])
        self.assertEqual(items["PES"]["cells"], ["P", "E", "S"])
        self.assertEqual(items["PES"]["length"], 3)

    def test_item_without_dictionary_row(self):
        item = next(i for i in self.request(self.puzzle())["items"] if i["answer"] == "SETO")
        self.assertEqual((item["gloss"], item["form"], item["flags"], item["freq"]), (None, "", [], 0))

    def test_instructions_and_schema(self):
        req = self.request(self.puzzle())
        self.assertEqual(req["schema"], {"version": 1, "clues": {"<ANSWER>": "<clue>"}, "pomucka": ["<answer>"]})
        for word in ("28", "(zkr.)", "(mn. č.)", "zast.", "kniž.", "hovor.", "nář.", "slovensky", "domácky",
                     "SPZ", "chem. zn.", "(římsky)", "pomucka"):
            self.assertIn(word, req["instructions"])

    def test_instructions_read_freq_as_a_rank(self):
        # freq is the rank in the frequency list (wordlist.Word.freq): a lower number is a commoner word
        text = self.request(self.puzzle())["instructions"]
        self.assertNotIn("čím vyšší, tím běžnější", text)
        self.assertIn("čím nižší, tím běžnější", text)

    def test_other_modes_keep_the_old_request(self):
        req = self.request(puzzle())
        self.assertEqual(req["schema"], {"version": 1, "clues": {"<ANSWER>": "<clue>"}})
        self.assertNotIn("freq", req["items"][0])
        self.assertNotIn("pomucka", req["instructions"])


class PomuckaTests(unittest.TestCase):
    def read(self, text):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / clues.CLUES_NAME).write_text(text, encoding="utf-8")
            return clues.read_clues(Path(d))

    def test_read_accepts_list_of_strings(self):
        self.assertEqual(self.read('{"version": 1, "pomucka": ["anis", "MTI"]}')["pomucka"], ["anis", "MTI"])

    def test_read_rejects_other_types(self):
        for text in ['{"version": 1, "pomucka": "anis"}', '{"version": 1, "pomucka": {"a": 1}}',
                     '{"version": 1, "pomucka": ["anis", 3]}']:
            with self.subTest(text=text):
                with self.assertRaises(clues.CluesError) as cm:
                    self.read(text)
                self.assertIn(clues.CLUES_NAME, str(cm.exception))

    def test_apply_stores_matches_as_given_in_order(self):
        p = swedish_puzzle()
        problems = clues.apply_clues(p, {"clues": {"KOSA": "tajenka"}, "pomucka": [" Esat ", "pes"]})
        self.assertEqual(problems, [])
        self.assertEqual(p.meta["pomucka"], ["Esat", "pes"])

    def test_apply_reports_unmatched_item(self):
        p = swedish_puzzle()
        problems = clues.apply_clues(p, {"pomucka": ["Denali", "esat"]})
        self.assertIn("pomucka: 'Denali' matches no entry", problems)
        self.assertEqual(p.meta["pomucka"], ["esat"])

    def test_apply_diacritics_free_only_in_match_none(self):
        strict = puzzle("strict")
        self.assertTrue(any(x.startswith("pomucka") for x in clues.apply_clues(strict, {"pomucka": ["zeme"]})))
        self.assertNotIn("pomucka", strict.meta)
        loose = puzzle("none")
        self.assertFalse(any(x.startswith("pomucka") for x in clues.apply_clues(loose, {"pomucka": ["zeme"]})))
        self.assertEqual(loose.meta["pomucka"], ["zeme"])

    def test_apply_empty_list_removes_the_key(self):
        p = swedish_puzzle()
        p.meta["pomucka"] = ["esat"]
        clues.apply_clues(p, {"pomucka": []})
        self.assertNotIn("pomucka", p.meta)

    def test_apply_without_pomucka_leaves_meta_alone(self):
        p = swedish_puzzle()
        p.meta["pomucka"] = ["esat"]
        clues.apply_clues(p, {"clues": {}})
        self.assertEqual(p.meta["pomucka"], ["esat"])


if __name__ == "__main__":
    unittest.main()
