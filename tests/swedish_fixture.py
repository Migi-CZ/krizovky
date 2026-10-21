"""Hand-made 5x5 Swedish puzzle shared by the slice-5 tests (not a test module).

    c:  0  1  2  3  4
r0:     #  #  #  #  #      blocks: row 0, column 0 and (1,1)
r1:     #  #  P  E  S      across: PES (1,2), KOSA (2,1), ULAD (3,1), SETO (4,1)
r2:     #  K  O  S  A      down:   KUS (2,1), POLE (1,2), ESAT (1,3), SADO (1,4)
r3:     #  U  L  A  D      tajenka "KOSA" = cells (2,1)..(2,4)
r4:     #  S  E  T  O

Clue cells: (1,1) split (PES across, KUS down); (0,2) (0,3) (0,4) down only; (2,0) the
tajenka label, (3,0) (4,0) across only; black cells (0,0) (0,1) (1,0). The words are
letter strings, not dictionary words; ``validate.validate`` accepts the puzzle.
"""
from krizovky import model
from krizovky.model import Entry, Placement, Puzzle

WORDS = [
    ("pes", 1, 2, model.ACROSS, "Domácí zvíře"),
    ("kosa", 2, 1, model.ACROSS, None),                 # the tajenka run: label set by clues.label_tajenka
    ("ulad", 3, 1, model.ACROSS, "Smyšlené slovo"),
    ("seto", 4, 1, model.ACROSS, "Japonské moře"),
    ("kus", 2, 1, model.DOWN, "Část celku"),
    ("pole", 1, 2, model.DOWN, "Lán"),
    ("esat", 1, 3, model.DOWN, "Zkratka (zkr.)"),
    ("sado", 1, 4, model.DOWN, "Japonský ostrov"),
]


def swedish_puzzle() -> Puzzle:
    entries = [Entry.from_word(w, clue=clue) for w, _, _, _, clue in WORDS]
    placements = [Placement(r, c, d) for _, r, c, d, _ in WORDS]
    blocks = [(0, c) for c in range(5)] + [(r, 0) for r in range(1, 5)] + [(1, 1)]
    return Puzzle(
        mode="swedish", width=5, height=5, entries=entries, placements=placements,
        tajenka="KOSA", tajenka_cells=[(2, 1), (2, 2), (2, 3), (2, 4)], blocks=sorted(blocks),
        meta={"dictionary": {
            "PES": {"gloss": "domácí šelma", "form": "", "flags": [], "freq": 1200},
            "ESAT": {"gloss": "smyšlená zkratka", "form": "", "flags": ["zkr."], "freq": 0},
        }},
    )
