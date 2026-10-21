import unittest

from krizovky import alphabet
from krizovky.alphabet import AlphabetError


class TokenizeTests(unittest.TestCase):
    def test_ch_is_one_cell_by_default(self):
        self.assertEqual(alphabet.tokenize("chata"), ["CH", "A", "T", "A"])

    def test_ch_can_be_split(self):
        self.assertEqual(alphabet.tokenize("chata", ch_one_cell=False), ["C", "H", "A", "T", "A"])

    def test_split_mark_forces_two_cells(self):
        self.assertEqual(alphabet.tokenize("c|hata"), ["C", "H", "A", "T", "A"])

    def test_uppercases_and_keeps_diacritics(self):
        self.assertEqual(alphabet.tokenize("Země"), ["Z", "E", "M", "Ě"])
        self.assertEqual(alphabet.tokenize("Řeřicha"), ["Ř", "E", "Ř", "I", "CH", "A"])

    def test_nfd_input_is_normalised(self):
        decomposed = "Z" + "e" + "m" + "Ě"  # E + combining caron
        self.assertEqual(alphabet.tokenize(decomposed), ["Z", "E", "M", "Ě"])

    def test_rejects_non_letters(self):
        for bad in ("", "   ", "pe s", "pes1", "pes-les", "ñandu", "pes€"):
            with self.assertRaises(AlphabetError, msg=bad):
                alphabet.tokenize(bad)

    def test_check_length(self):
        alphabet.check_length(["P", "E", "S"])
        with self.assertRaises(AlphabetError):
            alphabet.check_length(["A"])
        with self.assertRaises(AlphabetError):
            alphabet.check_length(list("ABCDEFGHIJKLMNOP"))


class PhraseTests(unittest.TestCase):
    def test_phrase_splits_words_and_drops_punctuation(self):
        words = alphabet.tokenize_phrase("Den Země!")
        self.assertEqual(words, [["D", "E", "N"], ["Z", "E", "M", "Ě"]])
        self.assertEqual(alphabet.flatten(words), ["D", "E", "N", "Z", "E", "M", "Ě"])

    def test_phrase_with_quote_punctuation(self):
        words = alphabet.tokenize_phrase("„Kdo nic nedělá, nic nezkazí.“")
        self.assertEqual([len(w) for w in words], [3, 3, 6, 3, 7])

    def test_phrase_without_letters_fails(self):
        with self.assertRaises(AlphabetError):
            alphabet.tokenize_phrase("... !!!")


class KeyTests(unittest.TestCase):
    def test_strict_keeps_everything(self):
        self.assertEqual(alphabet.word_key(["Z", "E", "M", "Ě"], "strict"), ("Z", "E", "M", "Ě"))

    def test_length_mode_merges_long_and_short_vowels_only(self):
        self.assertEqual(alphabet.cell_key("Á", "length"), "A")
        self.assertEqual(alphabet.cell_key("Ů", "length"), "U")
        self.assertEqual(alphabet.cell_key("Ě", "length"), "Ě")
        self.assertEqual(alphabet.cell_key("Ř", "length"), "Ř")
        self.assertEqual(alphabet.cell_key("CH", "length"), "CH")

    def test_none_mode_strips_all_diacritics(self):
        self.assertEqual(alphabet.word_key(["Ř", "E", "Ř", "I", "CH", "Ů"], "none"), ("R", "E", "R", "I", "CH", "U"))

    def test_unknown_mode_rejected(self):
        with self.assertRaises(ValueError):
            alphabet.cell_key("A", "fuzzy")

    def test_strip_diacritics_for_text(self):
        self.assertEqual(alphabet.strip_diacritics("Příliš žluťoučký kůň"), "Prilis zlutoucky kun")


if __name__ == "__main__":
    unittest.main()
