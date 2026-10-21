"""Block share and word-length statistics of hand-transcribed Swedish grids (slice 4b calibration).

    python3 scripts/grid_stats.py GRID1.txt GRID2.txt ...

File format: one line per grid row, ``#`` = clue or black cell, ``.`` = letter cell,
``=`` = tajenka letter cell; lines starting with ``# `` (hash + space) are comments.
The grids come from magazines, so ``Pattern.is_valid`` is not applied (a magazine may leave
a letter cell in one word only); such cells are counted instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

# explicit project root, so the script runs from anywhere (also under `python3 -I`)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse  # noqa: E402

from krizovky.pattern_swedish import Coord, Pattern, shape_stats  # noqa: E402

CELL_CHARS = {"#", ".", "="}


class GridError(Exception):
    """Unreadable or malformed grid file; reported on stderr, exit code 1."""


def read_grid(path: Path) -> tuple[Pattern, set[Coord]]:
    """The pattern and the tajenka cells of one grid file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GridError(f"cannot read {path}: {exc.strerror or exc}")
    rows: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("# ") or not line.strip():
            continue
        line = line.strip()
        bad = set(line) - CELL_CHARS
        if bad:
            raise GridError(f"{path}:{number}: unexpected character(s) {''.join(sorted(bad))!r}")
        if rows and len(line) != len(rows[0]):
            raise GridError(f"{path}:{number}: row has {len(line)} cells, the first row has {len(rows[0])}")
        rows.append(line)
    if not rows:
        raise GridError(f"{path}: no grid rows")
    blocks = {(r, c) for r, line in enumerate(rows) for c, ch in enumerate(line) if ch == "#"}
    tajenka = {(r, c) for r, line in enumerate(rows) for c, ch in enumerate(line) if ch == "="}
    return Pattern(len(rows), len(rows[0]), blocks), tajenka


def stats(pattern: Pattern, tajenka: set[Coord]) -> dict[str, object]:
    """``pattern_swedish.shape_stats`` plus the magazine-only counts (tajenka cells, cells in one
    word only)."""
    slots = pattern.slots()
    covered = {"across": set(), "down": set()}
    for s in slots:
        covered[s.direction].update(s.cells)
    white = pattern.white()
    out = shape_stats(pattern, tajenka)
    out["tajenka"] = len(tajenka)
    # white cells outside an across or a down word (magazines allow them at the edge)
    out["one_dir"] = sum(1 for cell in white if (cell in covered["across"]) != (cell in covered["down"]))
    out["no_word"] = sum(1 for cell in white if cell not in covered["across"] and cell not in covered["down"])
    return out


def fmt(value: object) -> str:
    return f"{value:.1f}" if isinstance(value, float) else str(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="+", help="grid files (see the module docstring)")
    args = parser.parse_args(argv)
    try:
        table = [(path, stats(*read_grid(Path(path)))) for path in args.files]
    except GridError as exc:
        print(f"grid_stats: error: {exc}", file=sys.stderr)
        return 1
    header = ["file", *table[0][1].keys()]
    lines = [header] + [[path, *(fmt(v) for v in row.values())] for path, row in table]
    widths = [max(len(line[i]) for line in lines) for i in range(len(header))]
    for line in lines:
        print("  ".join(cell.ljust(width) for cell, width in zip(line, widths)).rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
