"""Benchmark of the dense Swedish-grid filler (slice 4 go/no-go, slice 4d repair fill).

    python3 scripts/bench_fill.py --sizes 11x12 16x12 --runs 20
        [--timeout 60] [--inner-share 0.13] [--max-len 11] [--soft-len 8] [--long-slots 2] [--stump 0.1]
        [--repair-cap 0.17|0.20] [--no-repair] [--match strict] [--names] [--exclude-flags zkr. …]
        [--tajenka "RÁNO / MOUDŘEJŠÍ / VEČERA"] [--magazine GRID.txt …]
        [--jobs N] [--save out/bench] [--show] [--seed 0]

Every run builds a fresh pattern + fill for one size (seed = --seed + run number, tajenka
variant = run number % 4 unless --tajenka is given). Each success is checked with
``validate.validate``; a puzzle that fails it is NOT counted as a success and the number of such
failures is printed (it must be 0). Sizes are ``RxC`` = rows x columns. The shape table compares
the filled (repaired) patterns with the magazine targets and, with ``--magazine``, with the
transcribed magazine grids. ``--block-share`` is deprecated (``--inner-share``).
"""
from __future__ import annotations

import sys
from pathlib import Path

# explicit project root, so the script runs from anywhere (also under `python3 -I`)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse  # noqa: E402
import math  # noqa: E402
import multiprocessing  # noqa: E402
import os  # noqa: E402
import random  # noqa: E402
import statistics  # noqa: E402
import time  # noqa: E402
from collections import Counter  # noqa: E402

from krizovky import validate, wordlist  # noqa: E402
from krizovky.cli import CliError, parse_size  # noqa: E402
from krizovky.filler_dense import Lexicon, Stats, default_repair_cap, solve  # noqa: E402
from krizovky.model import Puzzle  # noqa: E402
from krizovky.pattern_swedish import PatternError, shape_stats  # noqa: E402
from grid_stats import GridError, read_grid  # noqa: E402

VARIANTS = (
    ("1 run", "DEN ZEMĚ"),
    ("2 runs", "KDO SE SMĚJE / NAPOSLED"),
    ("3 runs", "RÁNO / MOUDŘEJŠÍ / VEČERA"),
    ("11+9", "LEPŠÍ VRABEC / V HRSTI NEŽ"),
)
# magazine targets (EXECUTION.md slice 4b calibration): blocks <= 27 %, inner <= 13.3 %, mean >= 4.5, 2-3-cell <= 38 %
TARGETS = {"blocks%": 27.3, "inner%": 13.3, "mean_len": 4.5, "2-3cell%": 38.1}

_LEXICONS: dict[tuple[str, bool, tuple[str, ...]], Lexicon] = {}


def get_lexicon(match: str, names: bool, exclude_flags: tuple[str, ...] = ()) -> Lexicon:
    """Built once per process (forked workers inherit the parent's)."""
    key = (match, names, exclude_flags)
    if key not in _LEXICONS:
        index = wordlist.load(exclude_flags=(() if names else ("vl.",)) + exclude_flags)
        _LEXICONS[key] = Lexicon(index, match=match, names=names)
    return _LEXICONS[key]


def run_one(task: dict) -> dict:
    """One solve; returns plain data (the puzzle only for validated successes)."""
    lex = get_lexicon(task["match"], task["names"], task["exclude_flags"])
    stats = Stats()
    out = {"size": task["size"], "i": task["i"], "seed": task["seed"], "variant": task["variant"],
           "ok": False, "invalid": [], "error": "", "puzzle": None, "pattern_share": None, "shape": None}
    start = time.monotonic()
    try:
        result = solve(task["rows"], task["cols"], task["tajenka"], lex, rng=random.Random(task["seed"]),
                       timeout=task["timeout"], pattern_tries=task["pattern_tries"],
                       node_limit=task["node_limit"], block_share=task["block_share"],
                       inner_share=task["inner_share"], max_len=task["max_len"], soft_len=task["soft_len"],
                       long_slots=task["long_slots"], stump=task["stump"], repair=task["repair"],
                       repair_cap=task["repair_cap"], max_branch=task["max_branch"], sample=task["sample"],
                       patterns_per_fill=task["patterns_per_fill"], stats=stats)
    except PatternError as exc:
        out["error"] = f"pattern: {exc}"
        result = None
    out.update(seconds=time.monotonic() - start, nodes=stats.nodes, restarts=stats.restarts,
               patterns=stats.patterns, dead_ends=dict(stats.dead_ends), starved=dict(stats.starved),
               repairs=stats.repairs, repair_cells=stats.repair_cells, repairs_rejected=stats.repairs_rejected,
               stopped=stats.stopped)
    if result is not None:
        violations = validate.validate(result.puzzle)   # the oracle: every success goes through it
        out["pattern_share"] = result.pattern.inner_share()
        out["shape"] = shape_stats(result.pattern)
        if violations:
            out["invalid"] = violations[:5]
        else:
            result.puzzle.meta["seed"] = task["seed"]
            result.puzzle.meta["tajenka_variant"] = task["variant"]
            out["ok"] = True
            out["puzzle"] = result.puzzle
    return out


# --- measurements of one puzzle -------------------------------------------------------
def entry_rows(p: Puzzle) -> list[tuple[int, dict]]:
    """(length, dictionary info) of every non-tajenka entry."""
    taj = set(map(tuple, p.tajenka_cells))
    info = p.meta.get("dictionary", {})
    rows = []
    for e, pl in zip(p.entries, p.placements):
        if set(pl.coords(len(e))) <= taj:
            continue
        rows.append((len(e), info.get(e.answer, {})))
    return rows


def render_text(p: Puzzle) -> str:
    g = p.grid()
    blocks = set(map(tuple, p.blocks))
    taj = set(map(tuple, p.tajenka_cells))
    lines = []
    for r in range(p.height):
        cells = []
        for c in range(p.width):
            if (r, c) in blocks:
                cells.append("#".center(4))
            else:
                key = g[r][c] or "?"
                cells.append((f"[{key}]" if (r, c) in taj else key).center(4))
        lines.append("".join(cells).rstrip())
    return "\n".join(lines)


def render_words(p: Puzzle) -> str:
    info = p.meta.get("dictionary", {})
    rows = sorted(zip(p.entries, p.placements), key=lambda x: (x[1].direction, x[1].row, x[1].col))
    out = []
    for e, pl in rows:
        d = info.get(e.answer)
        if d is None:
            out.append(f"  {pl.direction:6} ({pl.row},{pl.col})  {e.answer:<12} [tajenka]")
            continue
        tags = " ".join(filter(None, [d["form"] and f"form={d['form']}", ",".join(d["flags"]),
                                      d["freq"] and f"freq#{d['freq']}"]))
        out.append(f"  {pl.direction:6} ({pl.row},{pl.col})  {e.answer:<12} {d['gloss'][:60]}" + (f"  <{tags}>" if tags else ""))
    return "\n".join(out)


# --- statistics ---------------------------------------------------------------------
def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}" if whole else "-"


def fmt(x, spec: str = ".1f") -> str:
    return "-" if x is None else format(x, spec)


def median(values):
    return statistics.median(values) if values else None


def p90(values):
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, math.ceil(0.9 * len(s)) - 1)]


def table(header: list[str], rows: list[list[str]]) -> str:
    widths = [max(len(header[i]), *(len(r[i]) for r in rows)) for i in range(len(header))]
    lines = ["  ".join(h.rjust(w) if i else h.ljust(w) for i, (h, w) in enumerate(zip(header, widths)))]
    lines += ["  ".join(c.rjust(w) if i else c.ljust(w) for i, (c, w) in enumerate(zip(r, widths))) for r in rows]
    return "\n".join(lines)


SHAPE_COLS = ("blocks%", "inner%", "mean_len", "2-3cell%", "2cell%", "longest", "long>8", "both%", "diag%")


def shape_row(label: str, shapes: list[dict]) -> list[str]:
    """Mean of every shape column over ``shapes`` (``longest`` = max, ``long>8`` = mean)."""
    row = [label]
    for col in SHAPE_COLS:
        values = [s[col] for s in shapes]
        if not values:
            row.append("-")
        elif col == "longest":
            row.append(str(max(values)))
        else:
            row.append(fmt(statistics.mean(values), ".1f"))
    return row


def report(results: list[dict], sizes: list[str], args, magazines: list[tuple[str, dict]] = ()) -> int:
    """Prints the tables; returns the number of validate failures."""
    invalid_total = sum(1 for r in results if r["invalid"])
    main_rows, quality_rows, dead_lines, starved_lines, variant_lines, shape_rows = [], [], [], [], [], []
    shape_rows.append(["target (magazines)", f"<={TARGETS['blocks%']:.0f}", f"<={TARGETS['inner%']:.1f}",
                       f">={TARGETS['mean_len']:.1f}", f"<={TARGETS['2-3cell%']:.0f}", "10-17", "11-12", "0-2", "57-82", "43-68"])
    for path, st in magazines:
        shape_rows.append(shape_row(Path(path).name, [st]))
    for size in sizes:
        rs = [r for r in results if r["size"] == size]
        ok = [r for r in rs if r["ok"]]
        times = [r["seconds"] for r in ok]
        rows_ = [r for p in ok for r in entry_rows(p["puzzle"])]
        n_entries = len(rows_)
        per_grid = [len(entry_rows(r["puzzle"])) for r in ok]
        shares = [r["pattern_share"] for r in ok]
        main_rows.append([
            size, str(len(rs)), str(len(ok)), pct(len(ok), len(rs)), fmt(median(times)), fmt(p90(times)),
            fmt(median([r["nodes"] for r in ok]), ".0f"), fmt(median([r["restarts"] for r in ok]), ".0f"),
            fmt(statistics.mean(r["restarts"] for r in rs) if rs else None),
            fmt(median([r["repairs"] for r in ok]), ".0f"),
            fmt(statistics.mean(r["repairs"] for r in rs) if rs else None),
            fmt(median(shares), ".3f"),
            str(sum(1 for r in rs if r["invalid"])),
        ])
        shape_rows.append(shape_row(size, [r["shape"] for r in ok]))
        quality_rows.append([
            size, fmt(statistics.mean(per_grid) if per_grid else None),
            fmt(statistics.mean(n for n, _ in rows_) if rows_ else None),
            pct(sum(1 for n, _ in rows_ if n <= 3), n_entries),
            pct(sum(1 for _, d in rows_ if d.get("form")), n_entries),
            pct(sum(1 for _, d in rows_ if "tvar" in d.get("flags", ())), n_entries),
            pct(sum(1 for _, d in rows_ if "zkr." in d.get("flags", ())), n_entries),
            pct(sum(1 for _, d in rows_ if d.get("freq", 0) > 0), n_entries),
        ])
        dead, starved = Counter(), Counter()
        for r in rs:
            dead.update({int(k): v for k, v in r["dead_ends"].items()})
            starved.update({int(k): v for k, v in r["starved"].items()})
        dead_lines.append(f"  {size}: " + (", ".join(f"{n}:{v}" for n, v in sorted(dead.items())) or "none")
                          + (f"   (total {sum(dead.values())})" if dead else ""))
        starved_lines.append(f"  {size}: " + (", ".join(f"{n}:{v}" for n, v in sorted(starved.items())) or "none"))
        for label in dict.fromkeys(r["variant"] for r in rs):
            vs = [r for r in rs if r["variant"] == label]
            variant_lines.append(f"  {size} {label}: {sum(1 for r in vs if r['ok'])}/{len(vs)} ok")
        stopped = Counter(r["stopped"] or "dead end" for r in rs if not r["ok"])
        if stopped:
            variant_lines.append(f"  {size} failures ended by: " + ", ".join(f"{k} {v}" for k, v in stopped.items())
                                 + f"; repairs rejected {sum(r['repairs_rejected'] for r in rs)}")
    print()
    print(table(["size", "runs", "ok", "success%", "median_s", "p90_s", "nodes", "restarts", "restarts/run",
                 "repairs", "repairs/run", "inner", "validate_fail"], main_rows))
    print("  (median_s, p90_s, nodes, restarts, repairs, inner: over the successes; restarts/run, repairs/run: mean over all runs)")
    print("\nShape of the filled patterns (mean over the successes) against the magazine targets:")
    print(table(["grid", *SHAPE_COLS], shape_rows))
    print("\nWord quality over successful grids (entries without the tajenka runs):")
    print(table(["size", "words/grid", "mean_len", "2-3cell%", "form%", "tvar%", "zkr.%", "freq>0%"], quality_rows))
    print("\nDead ends by slot length (length:count, all runs):")
    print("\n".join(dead_lines))
    print("\nCandidate patterns rejected because the tajenka letters starve a slot (slot length:count):")
    print("\n".join(starved_lines))
    print("\nBy tajenka variant:")
    print("\n".join(variant_lines))
    errors = Counter(r["error"] for r in results if r["error"])
    for message, n in errors.items():
        print(f"\n{n} run(s) failed with {message}")
    print(f"\nvalidate failures: {invalid_total}")
    for r in results:
        if r["invalid"]:
            print(f"  {r['size']} seed {r['seed']}: " + "; ".join(r["invalid"]))
    return invalid_total


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sizes", nargs="+", default=["11x12", "16x12"], help="RxC = rows x columns, e.g. 16x12")
    ap.add_argument("--runs", type=int, default=20, help="runs per size")
    ap.add_argument("--timeout", type=float, default=60.0, help="seconds per run")
    ap.add_argument("--block-share", type=float, default=None, help="deprecated: blocks over all cells (use --inner-share)")
    ap.add_argument("--inner-share", type=float, default=0.13, help="blocks among the inner cells the pattern aims for")
    ap.add_argument("--max-len", type=int, default=11, help="longest word the pattern allows")
    ap.add_argument("--soft-len", type=int, default=8, help="words longer than this are limited to --long-slots")
    ap.add_argument("--long-slots", type=int, default=2, help="non-tajenka words longer than --soft-len per grid")
    ap.add_argument("--stump", type=float, default=0.1, help="weight factor of a split leaving a 2-cell piece (sqrt of it for 3)")
    ap.add_argument("--repair-cap", type=float, default=None, help="repairs stop when the inner share would exceed this (default 0.17 with --names, 0.20 without)")
    ap.add_argument("--no-repair", action="store_true", help="today's fixed-pattern loop (no repairs)")
    ap.add_argument("--magazine", nargs="+", default=[], metavar="FILE", help="transcribed magazine grids for the shape table")
    ap.add_argument("--match", choices=("strict", "length", "none"), default="strict")
    ap.add_argument("--names", action="store_true", help="admit names (vl.) with a low weight")
    ap.add_argument("--exclude-flags", nargs="+", default=[], choices=wordlist.FLAGS, metavar="FLAG",
                    help="leave out dictionary rows with any of these flags, e.g. zkr.")
    ap.add_argument("--tajenka", help='one tajenka for all runs, runs separated by "/"')
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--save", metavar="DIR", help="write puzzle.json of every success to DIR/<size>_s<seed>/")
    ap.add_argument("--show", action="store_true", help="print the first successful grid per size and its words")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--node-limit", type=int, default=5000, help="search nodes per fill attempt")
    ap.add_argument("--max-branch", type=int, default=8, help="values tried per node")
    ap.add_argument("--sample", type=int, default=40, help="candidates examined per node")
    ap.add_argument("--pattern-tries", type=int, default=50, help="candidate patterns per generated pattern")
    ap.add_argument("--patterns-per-fill", type=int, default=3, help="fill attempts per pattern")
    args = ap.parse_args(argv)

    try:
        sizes = [parse_size(s) for s in args.sizes]
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    names = [f"{r}x{c}" for r, c in sizes]

    start = time.monotonic()
    exclude = tuple(args.exclude_flags)
    lex = get_lexicon(args.match, args.names, exclude)
    stats = lex.stats()
    print(f"Lexicon ({args.match}, {'with' if args.names else 'no'} names, excluded {' '.join(exclude) or '-'}): "
          f"{stats['total']} words in "
          f"{time.monotonic() - start:.1f}s; per length " + " ".join(f"{n}:{v}" for n, v in stats["by_len"].items()))
    shape = (f"block_share {args.block_share} (deprecated)" if args.block_share is not None
             else f"inner_share {args.inner_share}")
    if args.repair_cap is None:
        args.repair_cap = default_repair_cap(lex)
    print(f"runs/size {args.runs}, timeout {args.timeout:g}s, {shape}, max_len {args.max_len}, soft_len {args.soft_len}, "
          f"long_slots {args.long_slots}, stump {args.stump}, repair {'off' if args.no_repair else f'on, cap {args.repair_cap}'}, "
          f"node_limit {args.node_limit}, max_branch {args.max_branch}, sample {args.sample}, "
          f"patterns_per_fill {args.patterns_per_fill}, jobs {args.jobs}, seed {args.seed}")
    try:
        magazines = [(path, shape_stats(*read_grid(Path(path)))) for path in args.magazine]
    except GridError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    tasks = []
    for (rows, cols), size in zip(sizes, names):
        for i in range(args.runs):
            label, text = ("custom", args.tajenka) if args.tajenka else VARIANTS[i % len(VARIANTS)]
            tasks.append(dict(
                size=size, rows=rows, cols=cols, i=i, seed=args.seed + i, variant=label, tajenka=text,
                timeout=args.timeout, match=args.match, names=args.names, exclude_flags=exclude,
                block_share=args.block_share, inner_share=None if args.block_share is not None else args.inner_share,
                max_len=args.max_len, soft_len=args.soft_len, long_slots=args.long_slots, stump=args.stump,
                repair=not args.no_repair, repair_cap=args.repair_cap,
                node_limit=args.node_limit, max_branch=args.max_branch, sample=args.sample,
                pattern_tries=args.pattern_tries, patterns_per_fill=args.patterns_per_fill))

    if args.jobs > 1 and len(tasks) > 1:
        methods = multiprocessing.get_all_start_methods()
        ctx = multiprocessing.get_context("fork" if "fork" in methods else None)   # fork: workers inherit the lexicon
        with ctx.Pool(min(args.jobs, len(tasks))) as pool:
            results = pool.map(run_one, tasks, chunksize=1)
    else:
        results = [run_one(t) for t in tasks]
    order = {name: n for n, name in enumerate(names)}
    results.sort(key=lambda r: (order[r["size"]], r["i"]))

    print("\nPer run:")
    for r in results:
        status = "ok" if r["ok"] else ("INVALID" if r["invalid"] else (r["error"] or "no fill"))
        print(f"  {r['size']:>6} seed {r['seed']:<4} {r['variant']:<7} {status:<8} {r['seconds']:6.1f}s "
              f"nodes {r['nodes']:<7} restarts {r['restarts']:<4} repairs {r['repairs']:<3} "
              f"inner {fmt(r['pattern_share'], '.3f')}")
    invalid = report(results, names, args, magazines)

    if args.show:
        for size in names:
            first = next((r for r in results if r["size"] == size and r["ok"]), None)
            print(f"\n=== first success {size} (seed {first['seed']}, tajenka {first['puzzle'].tajenka!r}) ===" if first
                  else f"\n=== {size}: no success to show ===")
            if first:
                print(render_text(first["puzzle"]))
                print(render_words(first["puzzle"]))
    if args.save:
        for r in results:
            if r["ok"]:
                folder = Path(args.save) / f"{r['size']}_s{r['seed']}"
                folder.mkdir(parents=True, exist_ok=True)
                r["puzzle"].save(folder / "puzzle.json")
        print(f"\nsaved {sum(1 for r in results if r['ok'])} puzzle(s) under {args.save}/")
    return 1 if invalid else 0


if __name__ == "__main__":
    sys.exit(main())
