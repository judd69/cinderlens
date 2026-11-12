# Contributing to CinderLens

Thanks for helping improve CinderLens — the zero-dependency Python profiler that turns `cProfile` stats into a self-contained interactive HTML flamegraph report, plus an A/B `compare` mode.

## Ground rules

- **Zero third-party dependencies — no exceptions.** Everything, including the tests, uses the Python standard library only. Do not add a dependency to `pyproject.toml` or import one anywhere in `cinderlens/` or `tests/`.
- **Python 3.9+.** `pyproject.toml` sets `requires-python = ">=3.9"`; do not use syntax or stdlib APIs newer than 3.9.
- **Keep the report self-contained.** The HTML report (`--out report.html`) must work opened straight from disk: no CDN links, no external assets.
- **Honest numbers.** CinderLens reports what `cProfile` measured. Do not smooth, estimate, or invent timings, and do not hide the known limitations documented in the README (instrumentation overhead, no wall-clock I/O attribution, merged recursive frames, one combined thread view).

## Layout

| Path | What lives there |
| --- | --- |
| `cinderlens/cli.py` | Argument parsing and the `cinderlens` console entry point (`cinderlens.cli:main`) |
| `cinderlens/profiler.py` | Running the target script under `cProfile` (real argv, real `sys.path`, `__name__ == "__main__"`) |
| `cinderlens/model.py` | The profile data model / snapshot format behind `--json` |
| `cinderlens/tree.py` | Rebuilding the call tree from per-function totals and per-caller breakdowns |
| `cinderlens/compare.py` | The `compare` diff between two `--json` snapshots |
| `cinderlens/report.py` | The self-contained interactive HTML report (SVG flamegraph, hot-path table, summary cards) |
| `tests/` | Stdlib `unittest` suite (30 tests) |
| `examples/demo_slow.py` | Demo script used for smoke-testing and for the sample report |
| `docs/sample-report.html` | Sample report from profiling the demo script — regenerate it with the profiler, never hand-edit it |

## Workflow

1. Fork the repo and create a branch off `main`.
2. Make your change, then run the full gate before opening a PR:

```bash
python -m unittest discover -s tests -t .   # 30 tests, stdlib only — all must pass
python -m cinderlens profile examples/demo_slow.py --out /tmp/r.html --text
```

   Open `/tmp/r.html` in a browser and check the flamegraph, hot-path table, and summary cards still render and respond (click to zoom, search to highlight).
3. If you touched the report output, regenerate `docs/sample-report.html` by profiling `examples/demo_slow.py` instead of editing the HTML by hand.
4. Open a pull request against `main` describing what changed and why, with the test command output.

## What makes a good PR here

- **Bug fixes:** include a failing case first — a test in `tests/` that reproduces the bug, then the fix.
- **New flags / output fields:** update the README usage section and `--help` text in the same PR, and add tests covering the new behaviour.
- **Tree-building changes** (`tree.py`): recursion, caller cycles, and single-child pass-through folding are subtle — add a test for each edge case you touch, and keep the deterministic tie-breaking.
- **Compare changes** (`compare.py`): keep the faster-in-green / slower-in-red verdicts and the sort by biggest absolute total-time change.
- **Performance work:** measure with the tool itself — profile before and after with `compare` and quote the delta in the PR.

## What not to do

- Do not add dependencies, build tooling, or a test framework — `unittest` and `setuptools` are the whole toolchain.
- Do not commit generated reports or profiling snapshots (`report.html`, `*.json` snapshots) except the curated `docs/sample-report.html`.
- Do not change the `--json` snapshot schema without updating `compare.py` and the tests that read it.

## License

By contributing you agree your work is released under the MIT License, as in `LICENSE` (© 2026 Jude Davies).
