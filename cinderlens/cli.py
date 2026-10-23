"""Command-line interface for CinderLens."""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .compare import compare_text, render_compare
from .model import ProfileSnapshot
from .profiler import profile_script
from .report import render_report, render_text_summary

EXAMPLES = """\
examples:
  cinderlens profile app.py
      Profile app.py, write cinderlens-report.html.

  cinderlens profile app.py -- --input data.csv --verbose
      Everything after `--` is passed to the script as argv.

  cinderlens profile --out report.html --json run1.json --text app.py
      Also save a JSON snapshot (needed for `compare`) and print a text table.

  cinderlens compare run1.json run2.json --out compare.html
      Side-by-side diff report, sorted by biggest total-time change.

  cinderlens compare run1.json run2.json --text
      Print the diff table to the console instead.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cinderlens",
        description=(
            "Profile any Python script with stdlib cProfile and get a "
            "self-contained interactive HTML flamegraph report. "
            "Zero third-party dependencies."
        ),
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"cinderlens {__version__}"
    )
    parser.set_defaults(command=None)
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p = sub.add_parser(
        "profile",
        help="Profile a script and write an HTML report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EXAMPLES,
    )
    p.add_argument("script", help="Python script to profile.")
    p.add_argument(
        "script_args",
        nargs="*",
        default=[],
        help="Arguments passed to the script (or everything after `--`).",
    )
    p.add_argument(
        "--out",
        default="cinderlens-report.html",
        help="HTML report path (default: cinderlens-report.html).",
    )
    p.add_argument(
        "--json",
        default=None,
        metavar="STATS.JSON",
        help="Also write a machine-readable JSON snapshot (needed for `compare`).",
    )
    p.add_argument(
        "--text",
        action="store_true",
        help="Print a compact top-functions table to stdout.",
    )
    p.add_argument(
        "--top",
        type=int,
        default=30,
        metavar="N",
        help="Rows shown in summary tables (default: 30).",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=1.0,
        metavar="PCT",
        help="Hide flamegraph frames under PCT%% of total time (default: 1.0).",
    )
    p.set_defaults(command="profile")

    c = sub.add_parser(
        "compare",
        help="Diff two JSON snapshots from `profile --json`.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EXAMPLES,
    )
    c.add_argument("run_a", help="First (before) snapshot JSON.")
    c.add_argument("run_b", help="Second (after) snapshot JSON.")
    c.add_argument(
        "--out",
        default="compare.html",
        help="HTML diff report path (default: compare.html).",
    )
    c.add_argument(
        "--text",
        action="store_true",
        help="Print the diff table to stdout (HTML is still written).",
    )
    c.add_argument(
        "--top",
        type=int,
        default=30,
        metavar="N",
        help="Rows shown (default: 30).",
    )
    c.set_defaults(command="compare")
    return parser


def _cmd_profile(args: argparse.Namespace) -> int:
    try:
        snap = profile_script(args.script, args.script_args or [])
    except FileNotFoundError as exc:
        print(f"cinderlens: error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"cinderlens: error: cannot read {args.script}: {exc}", file=sys.stderr)
        return 1

    if args.json:
        snap.save(args.json)
        print(f"wrote {args.json}")

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(render_report(snap, top_n=args.top, threshold_pct=args.threshold))
    print(
        f"wrote {args.out} "
        f"({len(snap.functions):,} functions, {snap.total_time:.3f}s total)"
    )

    if args.text:
        print()
        print(render_text_summary(snap, top_n=args.top))

    if snap.error is not None:
        print(
            f"cinderlens: warning: target raised "
            f"{type(snap.error).__name__}: {snap.error}",
            file=sys.stderr,
        )
        print(
            "cinderlens: partial profile written from data collected "
            "before the error",
            file=sys.stderr,
        )
        return 2
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    try:
        snap_a = ProfileSnapshot.load(args.run_a)
    except (OSError, ValueError) as exc:
        print(f"cinderlens: error: {exc}", file=sys.stderr)
        return 1
    try:
        snap_b = ProfileSnapshot.load(args.run_b)
    except (OSError, ValueError) as exc:
        print(f"cinderlens: error: {exc}", file=sys.stderr)
        return 1

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(render_compare(snap_a, snap_b, top_n=args.top))
    print(f"wrote {args.out}")

    if args.text:
        print()
        print(compare_text(snap_a, snap_b, top_n=args.top))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `profile` swallows everything after `--` as script argv, before argparse
    # ever sees it (otherwise option-looking script args break parsing).
    if argv[:1] == ["profile"] and "--" in argv:
        cut = argv.index("--")
        head, tail = argv[:cut], argv[cut + 1 :]
        args = build_parser().parse_args(head)
        if args.command == "profile":
            args.script_args = tail
    else:
        args = build_parser().parse_args(argv)

    if args.command == "profile":
        return _cmd_profile(args)
    if args.command == "compare":
        return _cmd_compare(args)
    build_parser().print_help()
    return 0
