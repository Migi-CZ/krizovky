"""Word-list pipeline: build script (run as a subprocess, like the real build) + loader.

The expected rows below were derived BY HAND from the contract (slice 3 plan,
§ "Formát data/words.tsv.gz" and the selection rules) and the hand-written
fixture ``tests/fixtures/mini_wiktextract.jsonl``; they are not produced by the
code under test. Only basic forms are entries (SČHAK directive §10, owner's decision
2026-10-19): 1st case singular or plural for declined words, infinitive for verbs; a
form with a `nominative` tag or without any case/verb-form tag stays, the rest goes.
Fixture entry -> what the build must do with it:

  růže (noun, 7 forms)    base + ruža (alternative obsolete -> zast.); růža (alternative
                          dialectal) is a dialectal variant -> gone; růží (genitive plural) and
                          růži (dative/locative) are oblique cases -> gone; the form
                          equal to the lemma and "růže pěkná" (space) are skipped;
                          3 synonyms of 4
  růží (form-of růže)     disappears (its lemma exists)
  ptáčata (form-of ptáče) stays, flag "tvar" (gloss "nominativ plurálu…"); the English
                          entry "ptáče" is NOT a lemma
  světlá (form-of světlat, lemma missing) gloss "třetí osoba…" -> not a 1st case -> gone
  dvěma (num, own entry)  gloss "instrumentál číslovek…" -> a non-basic form filed as an
                          entry -> gone with its form dvouma
  šil (verb, own entry)   gloss "příčestí minulé…" -> a participle filed as an entry -> gone
  ČR (abbrev)             flag zkr.;  "atd." (period) disappears
  hlupák                  every sense vulgar/derogatory -> whole entry (and its form) gone
  pecka                   vulgar sense dropped, no-gloss sense skipped for the gloss
  červená karkulka        space -> gone
  čo (pron, dialectal)    nář.; slice 7b R22 (owner, 2026-10-21) drops dialect rows -> gone (the 2026-10-19
                          decision "a dialectal lemma stays with nář." is superseded)
  chata x2                CH is one cell (4 cells); chaty has two tag sets (nominative /
                          accusative plural) merged and sorted, gloss gets " (mn. č.)";
                          chatě, chatu gone;
                          second entry: same key -> first wins (base and chaty), only its
                          new form "chatky" is added (with the second gloss)
  toliko (adv)            every sense obsolete/archaic -> zast.
  dobře (adv)             lépe (comparative), nejlépe (superlative): no case tag -> stay,
                          glosses marked " (2. st.)" / " (3. st.)"
  pít (verb)              base infinitive + píti (alternative); pil, pije, pijte -> gone
  pes                     one colloquial sense of two -> no hovor.; psa gone, psi stays
  fotka                   every sense colloquial/slang -> hovor.
  Praha                   raw_tags vlastní -> vl., inherited by the form Prahy
                          (nominative plural merged with the gone genitive singular;
                          "singular" in the tags -> no plural mark)
  Jan (pos name)          vl.
  zelený (adj)            base + zelená (nominative singular, attested in mini_freq.txt ->
                          freq 7); zelení (nominative plural) is NOT in the frequency list
                          -> gone (adjective forms must be attested); zeleného oblique -> gone
  a / 22-cell word        outside 2..15 cells -> gone
  dog (en)                gone
Slice 4b leak rules (R1–R7, plan `Source/majestic-roaming-truffle.md`); mini_freq.txt line 8
is blank, so the added words get ranks 9–13:
  idem (no-gloss only)    R1 empty gloss -> gone
  nim                     R2 "(po předložce) dativ…": a case behind a leading label -> gone
  Syn                     "(v křesťanství) druhá osoba…": only cases are tested behind a label -> stays
  ho                      R3 "příklonný tvar…" (clitic form) -> gone
  sláb                    R4 "jmenný tvar přídavného jména…" -> gone
  participium             "jmenný tvar slovesa" (no adjective) -> stays (11 cells)
  mrdat (attested)        R5a vulgar sense dropped, every kept sense obsolete -> whole entry gone
  šulda (unattested)      R5b vulgar sense dropped, word not in the frequency list -> gone
  pták, pecka (attested)  vulgar sense dropped, entry kept -> listed as "vulgar-kept: 2 pecka pták"
  kokot (attested)        R8 on the vulgar blocklist (owner, 2026-10-19), no vulgar tag needed -> gone
  sračka (alt. form)      R8 also applies to a form row (attested alternative form of pták) -> gone
  pes -> pés              R6 alternative form not in the frequency list -> gone; ruža (rank 10)
                          and píti (rank 9) are attested alternatives -> stay
  Kč (symbol)             R7 flag zkr.
Slice 4e sources (plan `Source/4e-dictionary-2.md`), built on top of the rows above with
``--en-wikt mini_en_wiktextract.jsonl --syn mini_syn.tsv`` (SYN rank = line number):
  kocour (S1)             new: lemma row + kocouři (nominative plural from the declension table),
                          gloss and synonyms dropped (no English text), flag en-wikt; kočka (head
                          form, a derived word), "animate" / "cs-ndecl" (table pseudo forms) ->
                          non-table-form; kocoura, kocouře oblique -> gone; SYN line 4 -> 50004
  kocoura (S1, form-of)   its lemma kocour is known -> nothing
  pes (S1)                pes and psi are words of today's rows -> known-word (today's row wins
                          with its Czech gloss); psové is a new word -> added; psa oblique
  Praha (S1, pos name)    the word is already a row (pos noun) -> known-word, no duplicate
  blbeček (S1)            only sense "offensive" -> gone (tag added for S1)
  kafe / tuze (S1)        "colloquial" -> hovor., "dated" -> zast. (tags added for S1); kafe is attested
                          (mini_freq.txt line 16), else R25 unattested-slang drops it (slice 7b)
  Ostrava (S1, pos name)  vl.; "a city" is not a person -> no R16 (slice 7b)
  dog (S1, lang en)       gone
  mrdat (S1)              a current sense besides the vulgar one, attested; but the Czech
                          Wiktionary's rules dropped its entry (R5a) -> wikt-rejected, not resurrected
  mini_syn.tsv            pes keeps cs_50k rank 2; Praha capitalised; chatky, fotka, toliko (rows
                          with freq 0) -> 50 000 + line; jablko (line 5), hruška (line 12, 25 >= 20)
                          new rows flag syn, pos ""; hlupák, idem, kokot rejected by the Wiktionary
                          rules -> not resurrected; v (1 cell), co-to (hyphen) not words; second
                          jablko duplicate; švestka 19 < SYN_MIN 20; pták (known, rank 12 stays)
Slice 4e unit 3b (plan §G), ``mini_en_wiktextract_3b.jsonl`` + ``mini_syn_3b.tsv`` +
``mini_source_review_3b.tsv`` on top of the base fixtures (SYN rank = line number, count in column 3):
  Fučík (S1, surname)     R11: 300 SYN occurrences >= 100, group A, review keep -> row; the form
                          Fučíkové (vl. + a form tag) -> R9 name-form; Fučíka oblique -> gone
  Žbrdlík (S1, surname)   150 >= 100, group A, review drop -> gone
  Kapusta (S1, surname)   40 < 100 -> R11 surname, never reviewed
  Lada (S1, given name + surname)  not a pure surname -> no R11, no review; slice 7b: an unreviewed
                          en-wikt name has no gloss -> R16 name-no-gloss
  zešílet (S1, verb)      row; zešíleti (tag infinitive) -> R10 archaic-infinitive
  banjo / garden / tango  ASCII, 4+ cells, not a name: group B; banjo keep (+ its form banja, a form row,
                          is not reviewed), garden drop, tango (a noun and a verb row) has no verdict ->
                          review-missing twice, but one line in the export; without the review the verb
                          row goes by R13 non-infinitive (slice 7b, after the review step)
  ach / eh / Ida          2–3 cells: group C (before B, although ASCII; a name of 2–3 cells too);
                          ach, Ida keep, eh drop
  žluva                   diacritics, 5 cells: no group, no review -> row
  komárkův (SYN 80)       R12 possessive -> gone; Fučík, Žbrdlík, Kapusta, Lada capitalised -> gone
  about / sulc / timu / tmel  ASCII: group B; sulc keep, about + timu drop, tmel missing
  jo / xo                 2 cells: group C; jo keep, xo drop;  řeřicha: no group -> row
  nic (review line only)  matches no row -> "review unused"
Without --review every row of a group stays (the review step is off); R9–R12 still apply.
"""
from __future__ import annotations

import gzip
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from krizovky import wordlist
from krizovky.wordlist import Word, WordlistError

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "build_wordlist.py"
FIXTURES = ROOT / "tests" / "fixtures"
WIKT = FIXTURES / "mini_wiktextract.jsonl"
FREQ = FIXTURES / "mini_freq.txt"

HEADER = "word\tlemma\tpos\tform\tgloss\tsyn\tfreq\tflags"

_R = "rostlina s trnitým stonkem"
_RS = "kytka;růžička;květ"
_P = "hlavní město České republiky"
# (word, lemma, pos, form, gloss, syn, freq, flags); sorted by (cells, word, lemma, pos)
_D = "dobrým způsobem"
EXPECTED = [
    ("Kč", "Kč", "symbol", "", "koruna česká", "", "0", "zkr."),
    ("ČR", "ČR", "abbrev", "", "Česká republika", "", "0", "zkr."),
    ("Jan", "Jan", "name", "", "mužské rodné jméno", "", "0", "vl."),
    ("Syn", "Syn", "noun", "", "(v křesťanství) druhá osoba Nejsvětější Trojice", "", "0", ""),
    ("pes", "pes", "noun", "", "domácí šelma", "", "2", ""),
    ("psi", "pes", "noun", "animate nominative plural", "domácí šelma (mn. č.)", "", "0", ""),
    ("pít", "pít", "verb", "", "přijímat tekutinu", "", "0", ""),
    ("chata", "chata", "noun", "", "malá obytná stavba", "", "3", ""),
    ("chaty", "chata", "noun", "accusative nominative plural", "malá obytná stavba (mn. č.)", "", "0", ""),
    ("lépe", "dobře", "adv", "comparative", _D + " (2. st.)", "", "0", ""),
    ("pták", "pták", "noun", "", "opeřený obratlovec", "", "12", ""),
    ("píti", "pít", "verb", "alternative", "přijímat tekutinu", "", "9", ""),
    ("ruža", "růže", "noun", "alternative obsolete", _R, _RS, "10", "zast."),
    ("růže", "růže", "noun", "", _R, _RS, "4", ""),
    ("Praha", "Praha", "noun", "", _P, "", "6", "vl."),
    ("Prahy", "Praha", "noun", "genitive nominative plural singular", _P, "", "0", "vl."),
    ("chatky", "chata", "noun", "nominative plural", "jiná chata (mn. č.)", "", "0", ""),
    ("dobře", "dobře", "adv", "", _D, "", "0", ""),
    ("fotka", "fotka", "noun", "", "fotografie", "", "0", "hovor."),
    ("pecka", "pecka", "noun", "", "tvrdé jádro peckovice", "", "11", ""),
    ("toliko", "toliko", "adv", "", "pouze", "", "0", "zast."),
    ("zelená", "zelený", "adj", "feminine nominative singular", "mající barvu trávy", "", "7", ""),
    ("zelený", "zelený", "adj", "", "mající barvu trávy", "", "0", ""),
    ("nejlépe", "dobře", "adv", "superlative", _D + " (3. st.)", "", "0", ""),
    ("ptáčata", "ptáče", "noun", "", "nominativ plurálu substantiva ptáče", "", "0", "tvar"),
    ("participium", "participium", "noun", "", "jmenný tvar slovesa", "", "0", ""),
]
EXPECTED_LEN = {2: 2, 3: 5, 4: 7, 5: 6, 6: 3, 7: 2, 11: 1}
EXPECTED_POS = {"noun": 15, "abbrev": 1, "symbol": 1, "name": 1, "adv": 4, "verb": 2, "adj": 2}
EXPECTED_FLAGS = {"zkr.": 2, "vl.": 3, "zast.": 2, "kniž.": 0, "básn.": 0,
                  "hovor.": 1, "nář.": 0, "tvar": 1}
# one line per drop rule; non-basic-gloss = the slice-3 rule (dvěma, šil)
EXPECTED_DROPPED = {"empty-gloss": 1, "non-basic-gloss": 2, "case-label": 1, "clitic": 1,
                    "short-adj": 1, "vulgar-obsolete": 1, "vulgar-unattested": 1,
                    "vulgar-blocked": 1, "alternative-unattested": 1}


def run_build(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *args],
                          capture_output=True, text=True, cwd=ROOT)


def read_rows(path: Path) -> tuple[str, list[tuple[str, ...]]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as fh:
        lines = fh.read().split("\n")
    assert lines[-1] == "", "file must end with a newline"
    return lines[0], [tuple(line.split("\t")) for line in lines[1:-1]]


def stat_lines(stdout: str) -> set[str]:
    return {line.strip() for line in stdout.splitlines()}


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.gz = cls.tmp / "words.tsv.gz"
        cls.tsv = cls.tmp / "words.tsv"
        cls.proc = run_build("--wikt", str(WIKT), "--freq", str(FREQ), "--out", str(cls.gz))
        cls.proc_tsv = run_build("--wikt", str(WIKT), "--freq", str(FREQ), "--out", str(cls.tsv))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_exit_ok(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)
        self.assertEqual(self.proc_tsv.returncode, 0, self.proc_tsv.stderr)

    def test_gz_has_exactly_the_expected_rows(self):
        header, rows = read_rows(self.gz)
        self.assertEqual(header, HEADER)
        self.assertEqual(rows, EXPECTED)

    def test_plain_tsv_equals_gz(self):
        header, rows = read_rows(self.tsv)
        self.assertEqual(header, HEADER)
        self.assertEqual(rows, EXPECTED)
        self.assertEqual(gzip.decompress(self.gz.read_bytes()), self.tsv.read_bytes())

    def test_gz_is_really_gzip_and_deterministic(self):
        other = self.tmp / "again.tsv.gz"
        proc = run_build("--wikt", str(WIKT), "--freq", str(FREQ), "--out", str(other))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.gz.read_bytes()[:2], b"\x1f\x8b")
        self.assertEqual(self.gz.read_bytes(), other.read_bytes())

    def test_stats_counts(self):
        lines = stat_lines(self.proc.stdout)
        self.assertIn("total: 26", lines)
        self.assertIn("base: 17", lines)
        self.assertIn("dropped dialect: 1", lines)
        for n in range(2, 16):
            self.assertIn(f"len {n}: {EXPECTED_LEN.get(n, 0)}", lines)
        for pos, n in EXPECTED_POS.items():
            self.assertIn(f"pos {pos}: {n}", lines)
        for flag, n in EXPECTED_FLAGS.items():
            self.assertIn(f"flag {flag}: {n}", lines)

    def test_stats_drop_rules_and_vulgar_kept_list(self):
        lines = stat_lines(self.proc.stdout)
        for rule, n in EXPECTED_DROPPED.items():
            self.assertIn(f"dropped {rule}: {n}", lines)
        self.assertIn("vulgar-kept: 2 pecka pták", lines)

    def test_leaks_are_gone_and_lookalikes_stay(self):
        _, rows = read_rows(self.gz)
        words = {r[0] for r in rows}
        for gone in ("idem", "nim", "ho", "sláb", "mrdat", "šulda", "kokot", "sračka", "pés"):
            self.assertNotIn(gone, words)
        for kept in ("Syn", "participium", "pták", "pecka", "ruža", "píti"):
            self.assertIn(kept, words)

    def test_stats_list_input_hashes_and_output(self):
        import hashlib
        out = self.proc.stdout
        for path in (WIKT, FREQ):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertIn(f"sha256 {digest} {path}", out)
        self.assertIn(f"output: {self.gz} {self.gz.stat().st_size} bytes", out)

    def test_nested_output_folder_is_created(self):
        out = self.tmp / "a" / "b" / "w.tsv"
        proc = run_build("--wikt", str(WIKT), "--freq", str(FREQ), "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(out.is_file())

    def test_raw_dir_uses_fixed_names_and_gzip_input(self):
        raw = self.tmp / "raw"
        raw.mkdir()
        with gzip.open(raw / "raw-wiktextract-data.jsonl.gz", "wb") as fh:
            fh.write(WIKT.read_bytes())
        shutil.copy(FREQ, raw / "cs_50k.txt")
        out = self.tmp / "from_raw.tsv"
        proc = run_build("--raw", str(raw), "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(read_rows(out)[1], EXPECTED)

    def test_missing_input_is_a_clean_error(self):
        for args in (["--wikt", str(self.tmp / "nope.jsonl"), "--freq", str(FREQ)],
                     ["--wikt", str(WIKT), "--freq", str(self.tmp / "nope.txt")],
                     ["--raw", str(self.tmp / "no_such_dir")]):
            proc = run_build(*args, "--out", str(self.tmp / "x.tsv"))
            self.assertEqual(proc.returncode, 1, args)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertIn("nope" if "nope" in " ".join(args) else "no_such_dir", proc.stderr)

    def test_bad_json_line_names_the_line(self):
        bad = self.tmp / "bad.jsonl"
        bad.write_text('{"word": "pes", "lang_code": "cs", "senses": []}\n{"cs" nonsense\n',
                       encoding="utf-8")
        proc = run_build("--wikt", str(bad), "--freq", str(FREQ), "--out", str(self.tmp / "x.tsv"))
        self.assertEqual(proc.returncode, 1)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("bad.jsonl:2", proc.stderr)

    def test_usage_errors(self):
        out = str(self.tmp / "x.tsv")
        self.assertEqual(run_build("--out", out).returncode, 1)
        self.assertEqual(run_build("--wikt", str(WIKT), "--out", out).returncode, 1)
        both = run_build("--raw", str(self.tmp), "--wikt", str(WIKT), "--freq", str(FREQ), "--out", out)
        self.assertEqual(both.returncode, 1)


EN_WIKT = FIXTURES / "mini_en_wiktextract.jsonl"
SYN = FIXTURES / "mini_syn.tsv"
_FREQ_BY_SYN = {"chatky": "50003", "fotka": "50014", "toliko": "50016"}
EXPECTED_SOURCES = sorted(
    [r[:6] + (_FREQ_BY_SYN.get(r[0], r[6]), r[7]) for r in EXPECTED] + [
        ("kafe", "kafe", "noun", "", "", "", "16", "hovor.,en-wikt"),
        ("tuze", "tuze", "adv", "", "", "", "0", "zast.,en-wikt"),
        ("psové", "pes", "noun", "nominative plural", "", "", "0", "en-wikt"),
        ("kocour", "kocour", "noun", "", "", "", "50004", "en-wikt"),
        ("jablko", "jablko", "", "", "", "", "50005", "syn"),
        ("hruška", "hruška", "", "", "", "", "50012", "syn"),
        ("kocouři", "kocour", "noun", "nominative plural", "", "", "0", "en-wikt"),
        ("Ostrava", "Ostrava", "name", "", "", "", "0", "vl.,en-wikt"),
    ], key=lambda r: (len(wordlist.alphabet.tokenize(r[0])), r[0], r[1], r[2]))


class SourcesBuildTests(unittest.TestCase):
    """Slice 4e: English-Wiktionary Czech entries (S1) and the SYN2015 lemma list (S2)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.gz = cls.tmp / "words.tsv.gz"
        cls.args = ("--wikt", str(WIKT), "--freq", str(FREQ), "--en-wikt", str(EN_WIKT), "--syn", str(SYN))
        cls.proc = run_build(*cls.args, "--out", str(cls.gz))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def build(self, *args: str) -> subprocess.CompletedProcess:
        return run_build(*args, "--out", str(self.tmp / "x.tsv"))

    def test_exact_rows(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)
        header, rows = read_rows(self.gz)
        self.assertEqual(header, HEADER)
        self.assertEqual(rows, EXPECTED_SOURCES)

    def test_no_english_gloss_or_synonym(self):
        _, rows = read_rows(self.gz)
        for r in rows:
            if "en-wikt" in r[7].split(",") or "syn" in r[7].split(","):
                self.assertEqual((r[4], r[5]), ("", ""), r)
        words = {r[0] for r in rows}
        for gone in ("kočka", "animate", "kocoura", "blbeček", "dog", "mrdat", "hlupák", "idem", "kokot",
                     "švestka", "v", "macek"):
            self.assertNotIn(gone, words)

    def test_stats_per_source_and_rule(self):
        lines = stat_lines(self.proc.stdout)
        for line in ("total: 34", "source cs-wikt: 26", "source en-wikt: 6", "source syn: 2",
                     "attested-by-syn: 4",
                     "en-wikt dropped known-word: 3", "en-wikt dropped non-table-form: 3",
                     "en-wikt dropped wikt-rejected: 1", "vulgar-kept: 2 pecka pták",
                     "syn dropped capitalised: 1", "syn dropped rare: 1", "syn dropped not-a-word: 2",
                     "syn dropped known-word: 6", "syn dropped wikt-rejected: 3", "syn dropped duplicate: 1",
                     "len 4 sources: cs-wikt 7 en-wikt 2 syn 0 freq>0 6",
                     "len 6 sources: cs-wikt 3 en-wikt 1 syn 2 freq>0 5",
                     "flag en-wikt: 6", "flag syn: 2"):
            self.assertIn(line, lines)
        for rule, n in EXPECTED_DROPPED.items():   # the Czech Wiktionary's own evidence is unchanged
            self.assertIn(f"dropped {rule}: {n}", lines)
        import hashlib
        for path in (EN_WIKT, SYN):
            self.assertIn(f"sha256 {hashlib.sha256(path.read_bytes()).hexdigest()} {path}", self.proc.stdout)

    def test_syn_min_knob(self):
        proc = self.build(*self.args, "--syn-min", "300")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("source syn: 0", stat_lines(proc.stdout))
        # lower-case, not duplicate, under 300: lines 4–8, 9–10, 12–16
        self.assertIn("syn dropped rare: 12", stat_lines(proc.stdout))
        self.assertEqual(self.build(*self.args, "--syn-min", "0").returncode, 1)

    def test_zipped_syn_list_gives_the_same_rows(self):
        import zipfile
        zipped = self.tmp / "syn.zip"
        with zipfile.ZipFile(zipped, "w") as zf:
            zf.write(SYN, "syn2015_lemma_utf8.tsv")
        out = self.tmp / "from_zip.tsv.gz"
        proc = run_build("--wikt", str(WIKT), "--freq", str(FREQ), "--en-wikt", str(EN_WIKT),
                         "--syn", str(zipped), "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(out.read_bytes(), self.gz.read_bytes())

    def test_raw_dir_combines_with_the_new_sources(self):
        raw = self.tmp / "raw"
        raw.mkdir()
        with gzip.open(raw / "raw-wiktextract-data.jsonl.gz", "wb") as fh:
            fh.write(WIKT.read_bytes())
        shutil.copy(FREQ, raw / "cs_50k.txt")
        out = self.tmp / "raw.tsv"
        proc = run_build("--raw", str(raw), "--en-wikt", str(EN_WIKT), "--syn", str(SYN), "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(read_rows(out)[1], EXPECTED_SOURCES)

    def test_bad_inputs_are_clean_errors(self):
        import zipfile
        bad = self.tmp / "bad_syn.tsv"
        bad.write_text("1\tpes\t500\n\tkočka\tmnoho\n", encoding="utf-8")
        two = self.tmp / "two.zip"
        with zipfile.ZipFile(two, "w") as zf:
            zf.writestr("a.tsv", "1\tpes\t500\n")
            zf.writestr("b.tsv", "1\tpes\t500\n")
        base = ("--wikt", str(WIKT), "--freq", str(FREQ))
        for args, needle in ((("--syn", str(bad)), "bad_syn.tsv:2"),
                             (("--syn", str(two)), "two.zip"),
                             (("--syn", str(self.tmp / "nope.tsv")), "nope.tsv"),
                             (("--en-wikt", str(self.tmp / "nope.jsonl")), "nope.jsonl")):
            proc = self.build(*base, *args)
            self.assertEqual(proc.returncode, 1, args)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertIn(needle, proc.stderr)

    def test_loader_reads_and_excludes_the_source_flags(self):
        ix = wordlist.load(self.gz)
        self.assertEqual(len(ix), 34)
        self.assertEqual({w.word for w in ix.words if w.flags == ("syn",)}, {"jablko", "hruška"})
        kept = {w.word for w in wordlist.load(self.gz, exclude_flags=["en-wikt", "syn"]).words}
        self.assertEqual(kept, {r[0] for r in EXPECTED})


EN_WIKT_3B = FIXTURES / "mini_en_wiktextract_3b.jsonl"
SYN_3B = FIXTURES / "mini_syn_3b.tsv"
REVIEW_3B = FIXTURES / "mini_source_review_3b.tsv"
REVIEW_HEADER = "word\tsource\tgroup\tverdict\tnote"


def _sorted_rows(rows):
    return sorted(rows, key=lambda r: (len(wordlist.alphabet.tokenize(r[0])), r[0], r[1], r[2]))


_NEW_3B = [
    ("Fučík", "Fučík", "name", "", "", "", "0", "vl.,en-wikt"),
    ("Ida", "Ida", "name", "", "", "", "0", "vl.,en-wikt"),
    ("zešílet", "zešílet", "verb", "", "", "", "0", "en-wikt"),
    ("banjo", "banjo", "noun", "", "", "", "0", "en-wikt"),
    ("banja", "banjo", "noun", "nominative plural", "", "", "0", "en-wikt"),
    ("ach", "ach", "intj", "", "", "", "0", "en-wikt"),
    ("žluva", "žluva", "noun", "", "", "", "0", "en-wikt"),
    ("sulc", "sulc", "", "", "", "", "50007", "syn"),
    ("jo", "jo", "", "", "", "", "50010", "syn"),
    ("řeřicha", "řeřicha", "", "", "", "", "50012", "syn"),
]
EXPECTED_3B = _sorted_rows(list(EXPECTED) + _NEW_3B)
# the same without the review step: every row of a group stays
_UNREVIEWED_3B = [
    ("Žbrdlík", "Žbrdlík", "name", "", "", "", "0", "vl.,en-wikt"),
    ("garden", "garden", "noun", "", "", "", "0", "en-wikt"),
    ("tango", "tango", "noun", "", "", "", "0", "en-wikt"),
    ("eh", "eh", "intj", "", "", "", "0", "en-wikt"),
    ("about", "about", "", "", "", "", "50006", "syn"),
    ("timu", "timu", "", "", "", "", "50008", "syn"),
    ("tmel", "tmel", "", "", "", "", "50009", "syn"),
    ("xo", "xo", "", "", "", "", "50011", "syn"),
]
EXPECTED_3B_NO_REVIEW = _sorted_rows(EXPECTED_3B + _UNREVIEWED_3B)
EXPORT_3B = [
    ("Fučík", "en-wikt", "A"), ("Žbrdlík", "en-wikt", "A"),
    ("banjo", "en-wikt", "B"), ("garden", "en-wikt", "B"), ("tango", "en-wikt", "B"),
    ("about", "syn", "B"), ("sulc", "syn", "B"), ("timu", "syn", "B"), ("tmel", "syn", "B"),
    ("Ida", "en-wikt", "C"), ("ach", "en-wikt", "C"), ("eh", "en-wikt", "C"), ("jo", "syn", "C"), ("xo", "syn", "C"),
]


class ReviewRulesTests(unittest.TestCase):
    """Slice 4e unit 3b: rules R9–R12 and the model review of the new rows (plan §G)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.base = ("--wikt", str(WIKT), "--freq", str(FREQ), "--en-wikt", str(EN_WIKT_3B), "--syn", str(SYN_3B))
        cls.gz = cls.tmp / "words.tsv.gz"
        cls.proc = run_build(*cls.base, "--review", str(REVIEW_3B), "--out", str(cls.gz))
        cls.plain = cls.tmp / "plain.tsv"
        cls.proc_plain = run_build(*cls.base, "--out", str(cls.plain))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def build(self, *args: str) -> subprocess.CompletedProcess:
        return run_build(*self.base, *args, "--out", str(self.tmp / "x.tsv"))

    def review_file(self, *lines: str) -> Path:
        path = self.tmp / "review.tsv"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_reviewed_rows(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)
        self.assertEqual(read_rows(self.gz)[1], EXPECTED_3B)

    def test_without_review_every_group_row_stays_but_the_fixed_rules_apply(self):
        self.assertEqual(self.proc_plain.returncode, 0, self.proc_plain.stderr)
        rows = read_rows(self.plain)[1]
        self.assertEqual(rows, EXPECTED_3B_NO_REVIEW)
        words = {r[0] for r in rows}
        for gone in ("Fučíkové", "zešíleti", "Kapusta", "komárkův"):
            self.assertNotIn(gone, words)

    def test_stats_per_rule_and_review_group(self):
        lines = stat_lines(self.proc.stdout)
        for line in ("en-wikt dropped name-form: 1", "en-wikt dropped archaic-infinitive: 1",
                     "en-wikt dropped surname: 1", "syn dropped possessive: 1",
                     "review en-wikt A: keep 1 drop 1 missing 0",
                     "review en-wikt B: keep 1 drop 1 missing 2",
                     "review en-wikt C: keep 2 drop 1 missing 0",
                     "review syn B: keep 1 drop 2 missing 1",
                     "review syn C: keep 1 drop 1 missing 0",
                     "review unused: 1", "en-wikt dropped name-no-gloss: 1", "total: 36"):
            self.assertIn(line, lines)
        plain = stat_lines(self.proc_plain.stdout)
        self.assertIn("total: 44", plain)
        self.assertIn("en-wikt dropped non-infinitive: 1", plain)
        self.assertFalse([line for line in plain if line.startswith("review ")])

    def test_surname_threshold_needs_syn(self):
        proc = run_build("--wikt", str(WIKT), "--freq", str(FREQ), "--en-wikt", str(EN_WIKT_3B),
                         "--out", str(self.tmp / "nosyn.tsv"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        words = {r[0] for r in read_rows(self.tmp / "nosyn.tsv")[1]}
        self.assertNotIn("Fučík", words)       # no SYN list: no surname reaches 100
        lines = stat_lines(proc.stdout)        # a given name is not a surname: Lada goes by R16, not R11
        self.assertIn("en-wikt dropped surname: 3", lines)
        self.assertIn("en-wikt dropped name-no-gloss: 1", lines)

    def test_export_review_groups(self):
        out = self.tmp / "groups.tsv"
        proc = self.build("--export-review", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = out.read_text(encoding="utf-8").split("\n")
        self.assertEqual(lines[0], "word\tsource\tgroup")
        self.assertEqual([tuple(x.split("\t")) for x in lines[1:-1]], EXPORT_3B)
        self.assertEqual(lines[-1], "")

    def test_review_build_is_byte_reproducible(self):
        other = self.tmp / "again.tsv.gz"
        proc = run_build(*self.base, "--review", str(REVIEW_3B), "--out", str(other))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(other.read_bytes(), self.gz.read_bytes())

    def test_bad_review_files_are_clean_errors(self):
        good = "Fučík\ten-wikt\tA\tkeep\tJulius Fučík"
        for name, lines, needle in (
                ("header", ["word\tsource\tgroup", good], "review.tsv:1"),
                ("verdict", [REVIEW_HEADER, "Fučík\ten-wikt\tA\tmaybe\t"], "review.tsv:2"),
                ("group", [REVIEW_HEADER, "Fučík\ten-wikt\tD\tkeep\t"], "review.tsv:2"),
                ("source", [REVIEW_HEADER, "Fučík\tgeo\tA\tkeep\t"], "review.tsv:2"),
                ("columns", [REVIEW_HEADER, "Fučík\ten-wikt\tA\tkeep"], "review.tsv:2"),
                ("duplicate", [REVIEW_HEADER, good, good], "review.tsv:3")):
            proc = self.build("--review", str(self.review_file(*lines)))
            self.assertEqual(proc.returncode, 1, name)
            self.assertNotIn("Traceback", proc.stderr, name)
            self.assertIn(needle, proc.stderr, name)
        proc = self.build("--review", str(self.tmp / "nope.tsv"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("nope.tsv", proc.stderr)

    def test_review_note_stays_out_of_the_word_list(self):
        text = gzip.decompress(self.gz.read_bytes()).decode("utf-8")
        for note in ("novinář", "lemmatizační", "citoslovce"):
            self.assertNotIn(note, text)


WIKT_7B = FIXTURES / "mini_wiktextract_7b.jsonl"
EN_WIKT_7B = FIXTURES / "mini_en_wiktextract_7b.jsonl"
FREQ_7B = FIXTURES / "mini_freq_7b.txt"
BLOCK_7B = FIXTURES / "mini_blocklist_7b.tsv"
SYN_7B = FIXTURES / "mini_syn_7b.tsv"      # capitalised counts only (Novotný 150, Terynek 40): no syn rows
BLOCK_HEADER = "word\tlemma\tnote"
# Slice 7b (plan `Source/7b-dictionary-cleanup.md`), derived by hand from the rule table; ranks from
# mini_freq_7b.txt (jíti 1, dem 2, famu 3, one 4, ony 5, lesní 6, zity 7, fuč 8). Fixture entry -> what the build must do:
#   pudeme (verb)             R13 non-infinitive (dialect "půjdeme")
#   jít -> jíti, dem, jdu     jíti stays (attested alternative infinitive); dem R13; jdu not a basic form
#   jíti (verb lemma)         R14 archaic-infinitive by its gloss "tvar infinitivu"
#   chtíti (verb lemma)       R14 by the -t twin chtít in the lemma index;  routi (no twin, own gloss) stays
#   ěstí                      R15 bad-initial
#   haken (+ hakeni)          R17 insult "potupné označení", the entry with its forms
#   trotl, holomek            R17 "nadávka: …", "…; nadávka …";  nadávka, koketa ("(často hanlivě)") stay
#   Zita -> Zity, Zito        Zity R18 name-plural (gloss "jméno"); Zito oblique; a second Zita entry
#                             (attested alternative "Zity") must not add the dropped key back
#   Ála -> Ály                R18 too: a nickname whose gloss is only the full name ("Albína")
#   Vltava -> Vltavy          a plural of a place name stays
#   OČTŘ                      R19 unattested-abbrev (4 cells, freq 0);  FAMU (attested), ČD (2 cells) stay
#   můj -> muj, má, mé, mého  muj R20 nonstandard-form; mé stays (one of its two items is standard)
#   Eliin                     R21 name-possessive;  lesní stays
#   ee                        blocked (lemma "" = every row);  ona -> one blocked (one/ona), ony stays
#   blocklist laheve/lahev    matches nothing -> "blocklist unused: 1"
#   starej (dialectal)        R22 dialect (owner, 2026-10-21); oný "(nářečně) onen" too (label only);
#                             vdolek "(v moravské kuchyni) …" stays
#   Terynek / Novotný / Lada  "české mužské příjmení", SYN 40 < 100 -> R23 obscure-surname; Novotný (SYN 150)
#                             stays; Lada "ženské křestní jméno (a příjmení)" is a given name -> stays
#   Stoun (vl., colloquial)   R24 colloquial-name (owner's sample 2026-10-21: "Rolling Stones", Valmez, Pánbíček)
# English Wiktionary (mini_en_wiktextract_7b.jsonl):
#   Svata, Otík               R16 name-no-gloss (unreviewed person names); Leo (3 cells, group C) and
#                             Kigali (a capital, not a person) stay
#   muj                       its cs-wikt form went by R20 -> wikt-rejected, not brought back
#   haken -> hakenové         lemma wikt-rejected; its table form goes by R17 too (lemma dropped as an insult)
#   kecám                     R13 on every source;  žít stays
#   kasr (colloquial)         R25 unattested-slang (no Czech gloss, freq 0);  fuč (colloquial, attested) stays;
#                             a second kasr entry without the tag must not add the dropped key back
EXPECTED_7B = _sorted_rows([
    ("jít", "jít", "verb", "", "pohybovat se pěšky", "", "0", ""),
    ("jíti", "jít", "verb", "alternative", "pohybovat se pěšky", "", "1", ""),
    ("chtít", "chtít", "verb", "", "mít vůli", "", "0", ""),
    ("routi", "routi", "verb", "", "rvát, škubat", "", "0", ""),
    ("nadávka", "nadávka", "noun", "", "hrubé, urážlivé nebo vulgární oslovení", "", "0", ""),
    ("koketa", "koketa", "noun", "", "(často hanlivě) osoba usilující o náklonnost", "", "0", ""),
    ("Zita", "Zita", "noun", "", "ženské křestní jméno", "", "0", "vl."),
    ("Vltava", "Vltava", "noun", "", "řeka v Česku", "", "0", "vl."),
    ("Ála", "Ála", "noun", "", "Albína", "", "0", "vl."),
    ("Novotný", "Novotný", "noun", "", "české příjmení", "", "0", "vl."),
    ("Lada", "Lada", "noun", "", "ženské křestní jméno (a příjmení)", "", "0", "vl."),
    ("vdolek", "vdolek", "noun", "", "(v moravské kuchyni) kynutý koláč", "", "0", ""),
    ("Vltavy", "Vltava", "noun", "nominative plural", "řeka v Česku (mn. č.)", "", "0", "vl."),
    ("FAMU", "FAMU", "abbrev", "", "Filmová a televizní fakulta AMU", "", "3", "zkr."),
    ("ČD", "ČD", "abbrev", "", "České dráhy", "", "0", "zkr."),
    ("můj", "můj", "pron", "", "náležící mně", "", "0", ""),
    ("má", "můj", "pron", "feminine nominative singular", "náležící mně", "", "0", ""),
    ("mé", "můj", "pron", "neuter nominative singular", "náležící mně", "", "0", ""),
    ("lesní", "lesní", "adj", "", "týkající se lesa", "", "6", ""),
    ("ona", "ona", "pron", "", "označuje osobu ženského rodu", "", "0", ""),
    ("ony", "ona", "pron", "alternative", "označuje osobu ženského rodu", "", "5", ""),
    ("Leo", "Leo", "name", "", "", "", "0", "vl.,en-wikt"),
    ("Kigali", "Kigali", "name", "", "", "", "0", "vl.,en-wikt"),
    ("žít", "žít", "verb", "", "", "", "0", "en-wikt"),
    ("fuč", "fuč", "adv", "", "", "", "8", "hovor.,en-wikt"),
])
EXPECTED_7B_DROPPED = {"non-infinitive": 2, "archaic-infinitive": 2, "bad-initial": 1, "insult": 3,
                       "name-plural": 2, "unattested-abbrev": 1, "nonstandard-form": 1,
                       "name-possessive": 1, "blocked": 2, "alternative-unattested": 0,
                       "dialect": 2, "obscure-surname": 1, "colloquial-name": 1, "unattested-slang": 0}


class CleanupRulesTests(unittest.TestCase):
    """Slice 7b: leak rules R13–R25 and the hand blocklist."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.base = ("--wikt", str(WIKT_7B), "--freq", str(FREQ_7B), "--en-wikt", str(EN_WIKT_7B), "--syn", str(SYN_7B))
        cls.gz = cls.tmp / "words.tsv.gz"
        cls.proc = run_build(*cls.base, "--blocklist", str(BLOCK_7B), "--out", str(cls.gz))
        cls.rows = read_rows(cls.gz)[1] if cls.proc.returncode == 0 else []
        cls.words = {r[0] for r in cls.rows}
        cls.lines = stat_lines(cls.proc.stdout)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def build(self, *args: str) -> subprocess.CompletedProcess:
        return run_build(*self.base, *args, "--out", str(self.tmp / "x.tsv"))

    def gone(self, rule: str, n: int, *words: str, source: str = "") -> None:
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)
        self.assertIn(f"{source + ' ' if source else ''}dropped {rule}: {n}", self.lines)
        for word in words:
            self.assertNotIn(word, self.words, rule)

    def test_exact_rows(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)
        self.assertEqual(self.rows, EXPECTED_7B)

    def test_r13_non_infinitive(self):
        self.gone("non-infinitive", 2, "pudeme", "dem")
        self.gone("non-infinitive", 1, "kecám", source="en-wikt")
        self.assertIn("jíti", self.words)          # an attested -ti alternative of a kept verb stays

    def test_r14_archaic_infinitive(self):
        self.gone("archaic-infinitive", 2)
        self.assertNotIn(("jíti", "jíti", "verb"), {r[:3] for r in self.rows})
        self.assertNotIn("chtíti", self.words)
        self.assertIn("routi", self.words)         # no -t twin, no "tvar infinitivu" gloss

    def test_r15_bad_initial(self):
        self.gone("bad-initial", 1, "ěstí")

    def test_r16_name_no_gloss(self):
        self.gone("name-no-gloss", 2, "Svata", "Otík", source="en-wikt")
        self.assertIn("Leo", self.words)           # 2–3 cells: review group C decides, not R16
        self.assertIn("Kigali", self.words)        # a place: the clue writer knows it without a gloss

    def test_r17_insult(self):
        self.gone("insult", 3, "haken", "hakeni", "trotl", "holomek")
        self.gone("insult", 1, "hakenové", source="en-wikt")
        self.assertTrue({"nadávka", "koketa"} <= self.words)

    def test_r18_name_plural(self):
        self.gone("name-plural", 2, "Zity", "Ály")
        self.assertTrue({"Zita", "Ála", "Vltavy"} <= self.words)

    def test_r19_unattested_abbrev(self):
        self.gone("unattested-abbrev", 1, "OČTŘ")
        self.assertTrue({"FAMU", "ČD"} <= self.words)

    def test_r20_nonstandard_form(self):
        self.gone("nonstandard-form", 1, "muj")
        self.assertTrue({"má", "mé"} <= self.words)
        self.assertIn("en-wikt dropped wikt-rejected: 2", self.lines)   # muj (and haken) not brought back

    def test_r21_name_possessive(self):
        self.gone("name-possessive", 1, "Eliin")
        self.assertIn("lesní", self.words)

    def test_r22_dialect(self):
        self.gone("dialect", 2, "starej", "oný", "pudeme")
        self.assertIn("vdolek", self.words)    # pudeme (nář.) is counted by R13, checked first

    def test_r23_obscure_surname(self):
        self.gone("obscure-surname", 1, "Terynek")
        self.assertTrue({"Novotný", "Lada"} <= self.words)

    def test_r24_colloquial_name(self):
        self.gone("colloquial-name", 1, "Stoun")

    def test_r25_unattested_slang(self):
        self.gone("unattested-slang", 1, "kasr", source="en-wikt")
        self.assertIn("fuč", self.words)       # colloquial but attested by the frequency list

    def test_blocklist(self):
        self.gone("blocked", 2, "ee", "one")
        self.assertIn("ony", self.words)
        self.assertIn("blocklist unused: 1", self.lines)
        import hashlib
        self.assertIn(f"sha256 {hashlib.sha256(BLOCK_7B.read_bytes()).hexdigest()} {BLOCK_7B}", self.proc.stdout)

    def test_stats_lines(self):
        for rule, n in EXPECTED_7B_DROPPED.items():
            self.assertIn(f"dropped {rule}: {n}", self.lines)
        self.assertIn(f"total: {len(EXPECTED_7B)}", self.lines)

    def test_without_blocklist_the_rules_still_apply(self):
        out = self.tmp / "noblock.tsv"
        proc = run_build(*self.base, "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        words = {r[0] for r in read_rows(out)[1]}
        self.assertTrue({"ee", "one"} <= words)
        self.assertNotIn("Eliin", words)
        self.assertFalse([line for line in stat_lines(proc.stdout) if line.startswith("blocklist ")])

    def test_build_is_byte_reproducible(self):
        other = self.tmp / "again.tsv.gz"
        proc = run_build(*self.base, "--blocklist", str(BLOCK_7B), "--out", str(other))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(other.read_bytes(), self.gz.read_bytes())

    def test_bad_blocklist_files_are_clean_errors(self):
        good = "ee\t\tcitoslovce"
        for name, lines, needle in (
                ("header", ["word\tlemma", good], "blocklist.tsv:1"),
                ("columns", [BLOCK_HEADER, "ee\t"], "blocklist.tsv:2"),
                ("empty word", [BLOCK_HEADER, "\tona\tx"], "blocklist.tsv:2"),
                ("duplicate", [BLOCK_HEADER, good, good], "blocklist.tsv:3")):
            path = self.tmp / "blocklist.tsv"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            proc = self.build("--blocklist", str(path))
            self.assertEqual(proc.returncode, 1, name)
            self.assertNotIn("Traceback", proc.stderr, name)
            self.assertIn(needle, proc.stderr, name)
        proc = self.build("--blocklist", str(self.tmp / "nope.tsv"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("nope.tsv", proc.stderr)


class LoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.gz = cls.tmp / "words.tsv.gz"
        proc = run_build("--wikt", str(WIKT), "--freq", str(FREQ), "--out", str(cls.gz))
        assert proc.returncode == 0, proc.stderr
        cls.ix = wordlist.load(cls.gz)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def words(self, found):
        return [w.word for w in found]

    # --- constants ---------------------------------------------------------
    def test_constants(self):
        self.assertEqual(wordlist.COLUMNS, tuple(HEADER.split("\t")))
        self.assertEqual(wordlist.FLAGS, ("zkr.", "vl.", "zast.", "kniž.", "básn.", "hovor.", "nář.", "tvar",
                                          "en-wikt", "syn"))
        self.assertEqual(wordlist.EXTRA_NAME, "extra_words.tsv")
        self.assertEqual(wordlist.DATA.name, "words.tsv.gz")
        self.assertEqual(wordlist.DATA.parent.name, "data")

    # --- Word ----------------------------------------------------------------
    def test_word_fields(self):
        by = {(w.word, w.form): w for w in self.ix.words}
        ruze = by[("růže", "")]
        self.assertEqual((ruze.lemma, ruze.pos, ruze.freq, ruze.flags), ("růže", "noun", 4, ()))
        self.assertEqual(ruze.cells, ("R", "Ů", "Ž", "E"))
        self.assertEqual(ruze.syn, "kytka;růžička;květ")
        self.assertTrue(ruze.is_base)
        self.assertEqual(len(ruze), 4)
        tvar = by[("ptáčata", "")]
        self.assertEqual(tvar.flags, ("tvar",))
        self.assertFalse(tvar.is_base)
        self.assertFalse(by[("chaty", "accusative nominative plural")].is_base)
        self.assertFalse(by[("píti", "alternative")].is_base)

    def test_ch_counts_as_one_cell(self):
        chata = [w for w in self.ix.words if w.word == "chata"][0]
        self.assertEqual(chata.cells, ("CH", "A", "T", "A"))
        self.assertEqual(len(chata), 4)

    def test_word_keys(self):
        w = [w for w in self.ix.words if w.word == "růže"][0]
        self.assertEqual(w.keys(), ("R", "Ů", "Ž", "E"))
        self.assertEqual(w.keys("strict"), ("R", "Ů", "Ž", "E"))
        self.assertEqual(w.keys("length"), ("R", "U", "Ž", "E"))
        self.assertEqual(w.keys("none"), ("R", "U", "Z", "E"))

    def test_word_is_frozen(self):
        w = self.ix.words[0]
        with self.assertRaises(Exception):
            w.word = "x"

    # --- Index ---------------------------------------------------------------
    def test_loaded_in_file_order(self):
        self.assertEqual([w.word for w in self.ix.words], [r[0] for r in EXPECTED])

    def test_by_len(self):
        self.assertEqual(self.words(self.ix.by_len(2)), ["Kč", "ČR"])
        self.assertEqual(self.words(self.ix.by_len(3)), ["Jan", "Syn", "pes", "psi", "pít"])
        self.assertEqual(self.ix.by_len(9), [])

    def test_stats(self):
        st = self.ix.stats()
        self.assertEqual(st["total"], 26)
        self.assertEqual(st["base"], 16)        # 17 empty-form rows minus the "tvar" row
        self.assertEqual(st["by_len"], EXPECTED_LEN)
        self.assertEqual(st["by_pos"], EXPECTED_POS)

    def test_find_by_length_only(self):
        self.assertEqual(self.words(self.ix.find(2)), ["Kč", "ČR"])
        self.assertEqual(len(self.ix.find()), 26)
        self.assertNotIn("zelení", self.words(self.ix.words))   # unattested adjective form

    def test_find_string_pattern_sets_length(self):
        self.assertEqual(self.words(self.ix.find(pattern="..Ž.")), ["ruža", "růže"])
        self.assertEqual(self.words(self.ix.find(4, "..Ž.")), ["ruža", "růže"])

    def test_find_pattern_with_ch_cell(self):
        self.assertEqual(self.words(self.ix.find(pattern="CH...")), ["chata", "chaty"])
        self.assertEqual(self.words(self.ix.find(pattern="..CH.")), [])
        self.assertEqual(self.words(self.ix.find(pattern="ch...")), ["chata", "chaty"])
        self.assertEqual(self.words(self.ix.find(pattern="CH....")), ["chatky"])

    def test_find_dict_pattern(self):
        self.assertEqual(self.words(self.ix.find(4, {0: "CH"})), ["chata", "chaty"])
        self.assertEqual(self.words(self.ix.find(4, {2: "ž", 3: "e"})), ["růže"])
        # a dict without a length searches every length that can hold the cell
        self.assertEqual(self.words(self.ix.find(pattern={6: "A"})), ["ptáčata"])

    def test_find_match_modes_on_diacritics(self):
        self.assertEqual(self.words(self.ix.find(pattern=".Í..")), ["píti"])
        self.assertEqual(self.words(self.ix.find(pattern=".I..")), [])
        self.assertEqual(self.words(self.ix.find(pattern=".I..", match="length")), ["píti"])
        self.assertEqual(self.words(self.ix.find(pattern=".I..", match="none")), ["píti"])
        # Ů and U differ strictly and in "length" mode they share a key; Ž never folds in "length"
        self.assertEqual(self.words(self.ix.find(pattern=".U..")), ["ruža"])
        self.assertEqual(self.words(self.ix.find(pattern=".U..", match="length")), ["ruža", "růže"])
        self.assertEqual(self.words(self.ix.find(pattern="..Z.", match="length")), [])
        self.assertEqual(self.words(self.ix.find(pattern="..Z.", match="none")), ["ruža", "růže"])

    def test_find_match_none_matches_diacritic_with_plain_letter(self):
        self.assertEqual(self.words(self.ix.find(pattern="PTAC...", match="none")), ["ptáčata"])
        self.assertEqual(self.words(self.ix.find(pattern="PTAC...")), [])

    def test_find_pos_filter(self):
        self.assertEqual(self.words(self.ix.find(3, pos="name")), ["Jan"])
        self.assertEqual(self.words(self.ix.find(6, pos="noun")), [])
        self.assertEqual(self.words(self.ix.find(pos="adv")), ["lépe", "dobře", "toliko", "nejlépe"])
        self.assertEqual(self.words(self.ix.find(pos="verb")), ["pít", "píti"])

    def test_find_errors(self):
        with self.assertRaises(WordlistError):
            self.ix.find(5, "....")                    # pattern has 4 cells
        with self.assertRaises(WordlistError):
            self.ix.find(4, {4: "A"})                  # index outside the length
        with self.assertRaises(WordlistError):
            self.ix.find(4, {0: "1"})                  # not a cell
        with self.assertRaises(WordlistError):
            self.ix.find(pattern="..", match="loose")  # unknown match mode
        with self.assertRaises(WordlistError):
            self.ix.find(pattern="a1")

    # --- parse_pattern ---------------------------------------------------------
    def test_parse_pattern(self):
        self.assertEqual(wordlist.parse_pattern("..CH."), {2: "CH"})
        self.assertEqual(wordlist.pattern_length("..CH."), 4)
        self.assertEqual(wordlist.parse_pattern("?e.Ž"), {1: "E", 3: "Ž"})
        self.assertEqual(wordlist.pattern_length("?e.Ž"), 4)

    def test_parse_pattern_ch_split(self):
        self.assertEqual(wordlist.pattern_length("C.H"), 3)
        self.assertEqual(wordlist.parse_pattern("C|H"), {0: "C", 1: "H"})
        self.assertEqual(wordlist.pattern_length("C|H"), 2)

    def test_parse_pattern_rejects_bad_text(self):
        for bad in ("", "  ", "a b", "a1", "e-e", "ñ.."):
            with self.assertRaises(WordlistError, msg=bad):
                wordlist.parse_pattern(bad)

    # --- load options ------------------------------------------------------------
    def test_base_only(self):
        ix = wordlist.load(self.gz, base_only=True)
        self.assertEqual(ix.stats()["total"], 16)
        self.assertTrue(all(w.is_base for w in ix.words))
        self.assertNotIn("ptáčata", self.words(ix.words))
        self.assertEqual(self.words(ix.find(4)), ["chata", "pták", "růže"])

    def test_exclude_flags(self):
        ix = wordlist.load(self.gz, exclude_flags=("vl.", "tvar"))
        self.assertEqual(ix.stats()["total"], 22)
        ix = wordlist.load(self.gz, exclude_flags=["zast."])
        self.assertEqual(ix.stats()["total"], 24)
        self.assertNotIn("toliko", self.words(ix.words))
        self.assertNotIn("ruža", self.words(ix.words))
        self.assertEqual(wordlist.load(self.gz, exclude_flags=["nář."]).stats()["total"], 26)   # R22: no nář. rows
        self.assertEqual(wordlist.load(self.gz, exclude_flags=()).stats()["total"], 26)

    def test_length_window(self):
        ix = wordlist.load(self.gz, min_len=4, max_len=5)
        self.assertEqual(ix.stats()["by_len"], {4: 7, 5: 6})
        with self.assertRaises(WordlistError):
            wordlist.load(self.gz, min_len=6, max_len=4)

    def test_plain_tsv_and_str_path(self):
        plain = self.tmp / "plain.tsv"
        plain.write_bytes(gzip.decompress(self.gz.read_bytes()))
        self.assertEqual(wordlist.load(str(plain)).stats()["total"], 26)

    def test_unknown_exclude_flag_is_rejected(self):
        with self.assertRaises(WordlistError):
            wordlist.load(self.gz, exclude_flags=("bogus",))


class ExtraFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.main = self.tmp / "words.tsv.gz"
        proc = run_build("--wikt", str(WIKT), "--freq", str(FREQ), "--out", str(self.main))
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def write_extra(self, *rows: str):
        (self.tmp / "extra_words.tsv").write_text("\n".join((HEADER, *rows)) + "\n", encoding="utf-8")

    def test_extra_rows_are_added_and_duplicate_key_is_not_doubled(self):
        self.write_extra("žába\tžába\tnoun\t\tobojživelník\t\t0\t",
                         "pes\tpes\tnoun\t\tJINÝ POPIS\t\t0\t")
        ix = wordlist.load(self.main)
        self.assertEqual(ix.stats()["total"], 27)
        self.assertEqual([w.word for w in ix.find(4, "ŽÁ..")], ["žába"])
        pes = [w for w in ix.find(3) if w.word == "pes"]
        self.assertEqual(len(pes), 1)
        self.assertEqual(pes[0].gloss, "domácí šelma")      # main file wins

    def test_extra_false_ignores_the_file(self):
        self.write_extra("žába\tžába\tnoun\t\tobojživelník\t\t0\t")
        self.assertEqual(wordlist.load(self.main, extra=False).stats()["total"], 26)

    def test_extra_rows_follow_the_same_filters(self):
        self.write_extra("žába\tžába\tnoun\t\tobojživelník\t\t0\tvl.", "kůň\tkůň\tnoun\t\t\t\t7\t")
        ix = wordlist.load(self.main, exclude_flags=("vl.",))
        self.assertEqual([w.word for w in ix.find(3, "K..")], ["kůň"])
        self.assertEqual(ix.find(4, "ŽÁ.."), [])
        self.assertEqual(wordlist.load(self.main).find(3, "K..")[0].freq, 7)

    def test_extra_file_errors_name_the_extra_file(self):
        (self.tmp / "extra_words.tsv").write_text("word\tlemma\n", encoding="utf-8")
        with self.assertRaises(WordlistError) as cm:
            wordlist.load(self.main)
        self.assertIn("extra_words.tsv", str(cm.exception))

    def test_blank_lines_are_tolerated(self):
        self.write_extra("", "žába\tžába\tnoun\t\t\t\t0\t", "")
        self.assertEqual(wordlist.load(self.main).stats()["total"], 27)


class LoadErrorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def write(self, name: str, *lines: str) -> Path:
        path = self.tmp / name
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_missing_file_message(self):
        missing = self.tmp / "nope.tsv.gz"
        with self.assertRaises(WordlistError) as cm:
            wordlist.load(missing)
        msg = str(cm.exception)
        self.assertIn("word list not found", msg)
        self.assertIn(str(missing), msg)
        self.assertIn("build_wordlist", msg)

    def test_bad_header(self):
        path = self.write("w.tsv", "word\tlemma\tpos", "pes\tpes\tnoun")
        with self.assertRaises(WordlistError) as cm:
            wordlist.load(path)
        self.assertIn("w.tsv", str(cm.exception))
        self.assertIn("header", str(cm.exception))

    def test_empty_file(self):
        path = self.tmp / "e.tsv"
        path.write_text("", encoding="utf-8")
        with self.assertRaises(WordlistError):
            wordlist.load(path)

    def test_non_letter_word_names_file_and_line(self):
        path = self.write("w.tsv", HEADER, "pes\tpes\tnoun\t\t\t\t0\t", "pes-1\tpes\tnoun\t\t\t\t0\t")
        with self.assertRaises(WordlistError) as cm:
            wordlist.load(path)
        self.assertIn("w.tsv:3", str(cm.exception))

    def test_wrong_column_count_names_line(self):
        path = self.write("w.tsv", HEADER, "pes\tpes\tnoun")
        with self.assertRaises(WordlistError) as cm:
            wordlist.load(path)
        self.assertIn("w.tsv:2", str(cm.exception))

    def test_non_integer_freq_names_line(self):
        path = self.write("w.tsv", HEADER, "pes\tpes\tnoun\t\t\t\tmnoho\t")
        with self.assertRaises(WordlistError) as cm:
            wordlist.load(path)
        self.assertIn("w.tsv:2", str(cm.exception))

    def test_unknown_flag_in_file_names_line(self):
        path = self.write("w.tsv", HEADER, "pes\tpes\tnoun\t\t\t\t0\tzvláštní")
        with self.assertRaises(WordlistError) as cm:
            wordlist.load(path)
        self.assertIn("w.tsv:2", str(cm.exception))

    def test_broken_gzip(self):
        path = self.tmp / "w.tsv.gz"
        path.write_bytes(b"this is not gzip")
        with self.assertRaises(WordlistError) as cm:
            wordlist.load(path)
        self.assertIn("w.tsv.gz", str(cm.exception))

    def test_flags_are_split_on_comma(self):
        path = self.write("w.tsv", HEADER, "pes\tpes\tnoun\t\tx\ta;b\t3\tzast.,hovor.")
        w = wordlist.load(path).words[0]
        self.assertEqual(w.flags, ("zast.", "hovor."))
        self.assertEqual((w.freq, w.syn, w.gloss), (3, "a;b", "x"))


if __name__ == "__main__":
    unittest.main()


class CliWordsTests(unittest.TestCase):
    """``python3 -m krizovky words`` through ``cli.main`` with captured output."""

    ROWS = [
        ("pes", "pes", "noun", "", "domácí šelma", "", "2", ""),
        ("psi", "pes", "noun", "animate nominative plural", "domácí šelma", "", "0", ""),
        ("chata", "chata", "noun", "", "malá obytná stavba", "", "3", ""),
        ("Praha", "Praha", "noun", "", "hlavní město", "", "6", "vl."),
        ("žába", "žába", "noun", "", "obojživelník", "", "0", ""),
    ]
    EXTRA = [("Ohře", "Ohře", "noun", "", "řeka", "", "0", "vl.")]

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.data = cls.tmp / "words.tsv"
        cls.data.write_text("\n".join([HEADER] + ["\t".join(r) for r in cls.ROWS]) + "\n", encoding="utf-8")
        (cls.tmp / wordlist.EXTRA_NAME).write_text(
            "\n".join([HEADER] + ["\t".join(r) for r in cls.EXTRA]) + "\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_cli(self, *args: str) -> tuple[int, list[str], str]:
        import contextlib
        import io
        from krizovky import cli
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["words", "--data", str(self.data), *args])
        return code, out.getvalue().splitlines(), err.getvalue()

    def test_len_and_contains_1_based(self):
        code, rows, err = self.run_cli("--len", "4", "--contains", "A@2")
        self.assertEqual(code, 0)
        self.assertEqual(rows, ["chata\tnoun\t\t\tmalá obytná stavba"])   # strict: Á of žába is not A
        self.assertIn("1 word(s) match", err)
        code, rows, err = self.run_cli("--len", "4", "--contains", "A@2", "--match", "length")
        self.assertEqual(rows, ["chata\tnoun\t\t\tmalá obytná stavba", "žába\tnoun\t\t\tobojživelník"])
        self.assertIn("2 word(s) match", err)

    def test_pattern_with_ch_cell_and_match_none(self):
        code, rows, _ = self.run_cli("--pattern", "CH.T.")
        self.assertEqual(code, 0)
        self.assertEqual([r.split("\t")[0] for r in rows], ["chata"])
        code, rows, _ = self.run_cli("--len", "4", "--contains", "Z@1", "--match", "none")
        self.assertEqual([r.split("\t")[0] for r in rows], ["žába"])
        code, rows, _ = self.run_cli("--len", "4", "--contains", "Z@1")
        self.assertEqual(rows, [])

    def test_extra_words_merged_and_flags_printed(self):
        code, rows, _ = self.run_cli("--len", "4", "--pos", "noun", "--limit", "0")
        self.assertEqual(code, 0)
        self.assertIn("Ohře\tnoun\t\tvl.\třeka", rows)
        code, rows, _ = self.run_cli("--len", "4", "--exclude", "vl.", "--limit", "0")
        self.assertEqual([r.split("\t")[0] for r in rows], ["chata", "žába"])

    def test_base_random_and_limit(self):
        code, rows, _ = self.run_cli("--len", "3", "--limit", "0")
        self.assertEqual([r.split("\t")[0] for r in rows], ["pes", "psi"])
        code, rows, _ = self.run_cli("--len", "3", "--base")
        self.assertEqual([r.split("\t")[0] for r in rows], ["pes"])
        code, rows, _ = self.run_cli("--random", "2", "--seed", "1")
        self.assertEqual(code, 0)
        self.assertEqual(len(rows), 2)
        code, rows, _ = self.run_cli("--limit", "1")
        self.assertEqual(len(rows), 1)

    def test_bad_arguments_exit_1(self):
        code, rows, err = self.run_cli("--contains", "E@3")
        self.assertEqual((code, rows), (1, []))
        self.assertIn("--len", err)
        code, _, err = self.run_cli("--len", "3", "--contains", "E3")
        self.assertEqual(code, 1)
        code, _, err = self.run_cli("--len", "3", "--contains", "E@4")
        self.assertEqual(code, 1)
        code, _, err = self.run_cli("--len", "3", "--pattern", "..E..")
        self.assertEqual(code, 1)
        self.assertIn("cells", err)

    def test_missing_data_file_names_the_build(self):
        import contextlib
        import io
        from krizovky import cli
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = cli.main(["words", "--data", str(self.tmp / "nope.tsv.gz"), "--len", "3"])
        self.assertEqual(code, 1)
        self.assertIn("build_wordlist", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())
