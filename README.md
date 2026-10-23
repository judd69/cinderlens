# CinderLens

**See where your Python spends its time.** CinderLens profiles any Python script with the standard library alone and turns the numbers into a self-contained, interactive HTML report — flamegraph, hot-path tables, summary cards — plus an A/B compare mode for diffing two runs.

Zero third-party dependencies. Not one. (Even the tests use stdlib `unittest`.)

```
$ cinderlens profile app.py --out report.html --json run1.json --text
```

## The problem

`cProfile` gives you the truth about your program's performance, but its raw output — walls of `pstats` tables — answers "what was slow" without showing you *where the time flows*. CinderLens rebuilds the call tree from those stats and renders it as an interactive flamegraph you can click, zoom, and search, so the bottleneck finds *you*.

## What it does

- **`cinderlens profile script.py`** — runs your script under `cProfile` (real argv, real `sys.path`, `__name__ == "__main__"`) and writes:
  - `--out report.html` — self-contained interactive HTML report (default `cinderlens-report.html`)
  - `--json stats.json` — machine-readable snapshot of the run (needed for `compare`)
  - `--text` — compact top-functions table on stdout
  - `--top N` (default 30), `--threshold PCT` (default 1.0 — hide flame frames under X% of total time)
- **`cinderlens compare runA.json runB.json`** — side-by-side diff report: per-function deltas (calls, self time, total time) with before/after bars, sorted by biggest absolute total-time change, faster in green / slower in red. `--text` prints a console diff table; `--out` sets the HTML path.
- **`cinderlens --version` / `--help`** — with examples.

The HTML report contains:

- **Interactive flamegraph (SVG)** — width is total time, color heat is self time; click to zoom with breadcrumbs, search to highlight, hover for exact numbers (function, file:line, calls, self/total time).
- **Hot-path table** — top functions by self time; sortable columns; click a row to flash the function in the flamegraph.
- **Summary cards** — total time, function count, slowest function, slowest module.

## Install

Python 3.9+.

```bash
pip install .
# or, isolated:
pipx install .
# or just run it in place:
python -m cinderlens --version
```

## Usage

```bash
# Profile a script; pass script args after --
cinderlens profile app.py -- --input data.csv --workers 4

# HTML report + JSON snapshot + console summary
cinderlens profile app.py --out report.html --json run1.json --text

# After optimizing, snapshot again and diff the two runs
cinderlens profile app.py --json run2.json
cinderlens compare run1.json run2.json --out compare.html
cinderlens compare run1.json run2.json --text
```

Example output (`--text`):

```
CinderLens profile: app.py
  total time  1.736s (wall 1.736s)
  functions   74

Top functions by self time:
  function                         location                    calls       self   per-call      total  % total
  fib                              demo_slow.py:21:fib     1,028,457   853.25ms      0.8µs   853.25ms    49.1%
  iterencode                       …der.py:205:iterencode         41   234.08ms     5.71ms   234.08ms    13.5%
  raw_decode                       …der.py:343:raw_decode         40   196.31ms     4.91ms   196.31ms    11.3%
  concat_loop                      …low.py:28:concat_loop          1   193.15ms   193.15ms   193.15ms    11.1%
```

Compare output (`--text`):

```
CinderLens compare: run1.json  vs  run2.json
  Δ total 461.45ms (31.5%) — B is faster

Biggest total-time changes:
  function                       location                     calls A→B     Δ self    Δ total  Δ total %  verdict
  fib                            demo_slow.py:21:fib  1,028,457→150,049   525.59ms - 525.59ms -     85.8%  faster
```

A live sample report (CinderLens profiling its own demo script) ships in `docs/sample-report.html` — open it and click around.

## How the tree is built

`cProfile` records per-function totals plus a per-caller breakdown. CinderLens attaches each function to the caller contributing the largest share of its cumulative time. Self-recursive edges are merged (a recursive function appears once, carrying its full cost), caller cycles are broken deterministically, single-child pass-through wrappers (`exec` driver, `<module>` → `main()`) are folded, and the profiler's own frames are filtered out.

## Development

```bash
python -m unittest discover -s tests -t .   # 30 tests, stdlib only
python -m cinderlens profile examples/demo_slow.py --out /tmp/r.html --text
```

## Honest limitations

- Sampling profilers (like `py-spy`) have lower overhead; `cProfile` instruments every call, which slows the target (roughly 2–5×) and slightly distorts timings. Relative hotspots are still accurate.
- No wall-clock attribution for I/O waits — `cProfile` measures CPU time per call; a function blocked on the network looks cheap.
- Flame widths come from cumulative time, so overlapping recursive/mutually-recursive calls are shown merged, not as they interleaved.
- Threads: profiled together into one set of stats; per-thread breakdowns aren't separated.

## License

MIT © 2026 Jude Davies.
