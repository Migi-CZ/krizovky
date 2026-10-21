# Licences of the word list sources

`data/words.tsv.gz` is derived from four downloads that are not part of this repository
(the maintainer keeps them with `SOURCES.txt` and `SHA256SUMS.txt`). The first two were
downloaded 2026-10-19T15:52:53Z, the other two 2026-10-20T19:20:47Z. Publisher checksums
were not available; the sha256 values below were computed locally after the download.
The licence statements below were read on the sources' own pages on 2026-10-21.

## Summary
| File | Licence | Why |
|---|---|---|
| `data/words.tsv.gz` | CC BY-SA 4.0 | derived from Wiktionary text (sources 1 and 3), share-alike |
| `data/source_review.tsv` | CC BY-SA 4.0 | a review of words taken from the same sources |
| `data/extra_words.tsv` | MIT (`LICENSE`) | written by hand by the author, no external source |
| `data/blocklist.tsv` | MIT (`LICENSE`) | the author's own verdicts on single words, no external source |
| `examples/eko_krizovka/` | CC BY-SA 4.0 | the sample puzzle; `puzzle.json` and `request.json` quote Wiktionary glosses |
| code (`krizovky/`, `scripts/`, `tests/`) | MIT (`LICENSE`) | written for this project |

Attribution to give when you share `words.tsv.gz` or anything made from it:
"Wiktionary and Wikislovník contributors (CC BY-SA 4.0), via wiktextract/kaikki.org by Tatu Ylonen;
frequency data hermitdave/FrequencyWords (MIT) and the Czech National Corpus SYN2015 lemma
list (CC BY 4.0)."

## 1. Czech Wiktionary extract (kaikki.org / wiktextract)
- File: `raw-wiktextract-data.jsonl.gz` — https://kaikki.org/cswiktionary/raw-wiktextract-data.jsonl.gz
- sha256: `5f0180e1a33452110eb2c1740af7ab12535f2840d87fe02ae215ff1926044e44`
- Content: machine-readable extract of cs.wiktionary.org (Wikislovník) made by wiktextract
  (Tatu Ylonen, kaikki.org). The dictionary text is the work of Wikislovník contributors.
- Licence: **CC BY-SA 4.0**. Read 2026-10-21:
  - https://kaikki.org/cswiktionary/index.html: "This data is made available under the same
    licenses as Wiktionary - both CC-BY-SA and GFDL." (no version named there)
  - https://cs.wiktionary.org/wiki/Wikislovník:Autorské_právo: "Text je dostupný pod licencí
    Creative Commons Uveďte původ – Zachovejte licenci", linked to
    https://creativecommons.org/licenses/by-sa/4.0/; the page does not mention the GFDL.
- Attribution: "Wikislovník contributors, via wiktextract/kaikki.org". kaikki.org asks academic
  users to cite Tatu Ylonen, *Wiktextract: Wiktionary as Machine-Readable Structured Data*,
  LREC 2022, pp. 1317–1325, and would appreciate a link to https://kaikki.org.
- Derived data such as `words.tsv.gz` must carry the same licence (share-alike).

## 2. Czech frequency list (hermitdave / FrequencyWords)
- File: `cs_50k.txt` — https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/cs/cs_50k.txt
- sha256: `1fb0576ef07cf5a543789d394cde1168573fc9e7adf427fd143249fd5547458d`
- Licence: **MIT**, "Copyright (c) 2016 Hermit Dave"
  (https://github.com/hermitdave/FrequencyWords/blob/master/LICENSE, read 2026-10-19 and
  2026-10-21). Word counts come from the OpenSubtitles 2018 corpus; only the rank is used
  here (`freq` column).

## 3. English Wiktionary, Czech entries (kaikki.org / wiktextract), slice 4e
- File: `kaikki.org-dictionary-Czech.jsonl` — https://kaikki.org/dictionary/Czech/kaikki.org-dictionary-Czech.jsonl
- sha256: `f3ddffaa79c4070fc31022f5cc44432fa149a3980f0d2b33ed98e2a3b1677bbf`; downloaded 2026-10-20T19:20:47Z
- Content: the Czech entries of en.wiktionary.org extracted by wiktextract (the page
  https://kaikki.org/dictionary/Czech/index.html, read 2026-10-21, says: extracted 2026-10-03
  from the enwiktionary dump dated 2026-09-02). Only words, part of speech and form tags are
  used; the English glosses and synonyms are not written into `words.tsv.gz`.
- Licence: **CC BY-SA 4.0** (and GFDL for older text). Read 2026-10-21:
  - https://en.wiktionary.org/wiki/Wiktionary:Main_Page, footer: "Definitions and other text
    are available under the Creative Commons Attribution-ShareAlike License", linked to
    https://creativecommons.org/licenses/by-sa/4.0/
  - https://en.wiktionary.org/wiki/Wiktionary:Copyrights: text "dual-licensed to the public
    under both the Creative Commons Attribution-ShareAlike 4.0 International License" and the
    GFDL 1.1 or later (the page itself is marked as outdated)
  - the kaikki.org page of this extract states no licence of its own.
- Attribution: "Wiktionary contributors, via wiktextract/kaikki.org".

## 4. ČNK comparative lemma list SYN2015 (Czech National Corpus), slice 4e
- File: `syn2015_lemma_utf8.zip` (holds `syn2015_lemma_utf8.tsv`, sha256
  `bd15b3b10283020606f90f9a5b329b26f8f6005f3b32e3fcd0739b196cb5e8f8`) —
  https://wiki.korpus.cz/lib/exe/fetch.php/seznamy:syn2015_lemma_utf8.zip
- sha256: `4536f9ac59b373f15eb002ae7befe9a4a6700a9c5b5c2b8aa80bbebd1c35fa4f`; downloaded 2026-10-20T19:20:47Z
- Licence: **CC BY 4.0**. The download page https://wiki.korpus.cz/doku.php/seznamy:srovnavaci_seznamy
  (read 2026-10-21) says "Toto dílo podléhá licenci Creative Commons CC BY 4.0 International"
  (https://creativecommons.org/licenses/by/4.0/). The statement covers the page with all its
  lists; the SYN2015 file is not named in it separately: `Unverified ❗` whether the ČNK means
  it for the downloads too (the page offers no other terms).
- Lemma and frequency (column 3) are used; rank = line number.
- Citation the ČNK asks for "ve vědecké práci" (same page, verbatim):
  "Český národní korpus: Srovnávací frekvenční seznamy. Ústav Českého národního korpusu FF UK,
  Praha 2016. Dostupné z WWW: http://www.korpus.cz"

## 5. Hand-added words
- `data/extra_words.tsv` is written by the author (Michal Stasiak) and licensed under the MIT
  License in `LICENSE`, like the code.
- `data/blocklist.tsv` (words to leave out, each with a note) is the author's own work, licensed
  under the MIT License in `LICENSE` as well.

## 6. Generated puzzles
- Every puzzle the tool writes includes `puzzle.json` and `request.json`, which quote the
  Wiktionary gloss of each answer verbatim. If you publish or pass on those two files, they are
  CC BY-SA 4.0: give the attribution above and keep the licence.
- The printed sheet (SVG/PDF) and `solution.md` show only the grid letters and the clues; they are
  yours to license as you wish, provided the clues are written in your own words and do not copy
  the glosses (single words are not protected, and one puzzle uses far less than a substantial
  part of the dictionary).
- The MIT licence of the code is not affected by the data licence.
- Basis: a reading of the CC BY-SA 4.0 legal code (§1(a) Adapted Material, §3(b) share-alike, §4
  database rights) made for this project on 2026-10-21, not legal advice.
