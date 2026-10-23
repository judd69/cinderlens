"""Diff two profile snapshots: delta math plus text/HTML rendering.

Conventions: A is the "before" run, B is the "after" run.  A negative
``d_ct`` means B spent less total time in the function — B is *faster*
(shown green); positive means slower (shown red).
"""
from __future__ import annotations

import os

from . import __version__
from .report import _CSS, esc, fmt_pct, fmt_time


def _short_key(f) -> tuple:
    return (os.path.basename(f.file), f.lineno, f.name)


def _pair_functions(a, b) -> list[tuple]:
    """Pair up functions across two snapshots.

    Exact ``file:lineno:name`` match first; then a ``basename:lineno:name``
    fallback so runs of the same script from different paths (or machines)
    still line up.  Returns ``(key_in_a | None, key_in_b | None)`` pairs.
    """
    b_by_short: dict[tuple, list] = {}
    for kb, fb in b.functions.items():
        b_by_short.setdefault(_short_key(fb), []).append(kb)
    pairs, used_b = [], set()
    for ka, fa in a.functions.items():
        if ka in b.functions:
            pairs.append((ka, ka))
            used_b.add(ka)
            continue
        cands = [
            kb for kb in b_by_short.get(_short_key(fa), []) if kb not in used_b
        ]
        if len(cands) == 1:
            pairs.append((ka, cands[0]))
            used_b.add(cands[0])
        else:
            pairs.append((ka, None))
    for kb in b.functions:
        if kb not in used_b:
            pairs.append((None, kb))
    return pairs


def diff_snapshots(a, b, top_n: int = 30) -> list[dict]:
    """Per-function deltas, sorted by biggest absolute total-time change."""
    rows = []
    for ka, kb in _pair_functions(a, b):
        fa = a.functions.get(ka) if ka else None
        fb = b.functions.get(kb) if kb else None
        f = fb or fa
        key = kb or ka
        calls_a = fa.calls if fa else 0
        calls_b = fb.calls if fb else 0
        tt_a = fa.tottime if fa else 0.0
        tt_b = fb.tottime if fb else 0.0
        ct_a = fa.cumtime if fa else 0.0
        ct_b = fb.cumtime if fb else 0.0
        d_ct = ct_b - ct_a
        rows.append(
            {
                "key": key,
                "name": f.name,
                "file": f.file,
                "lineno": f.lineno,
                "short": f.short,
                "calls_a": calls_a,
                "calls_b": calls_b,
                "d_calls": calls_b - calls_a,
                "tt_a": tt_a,
                "tt_b": tt_b,
                "d_tt": tt_b - tt_a,
                "ct_a": ct_a,
                "ct_b": ct_b,
                "d_ct": d_ct,
                "pct": (d_ct / ct_a) if ct_a > 0 else (float("inf") if d_ct > 0 else 0.0),
                "verdict": "faster" if d_ct < 0 else ("slower" if d_ct > 0 else "same"),
                "new": fa is None,
                "gone": fb is None,
            }
        )
    rows.sort(key=lambda r: abs(r["d_ct"]), reverse=True)
    return rows[:top_n]


def _verdict_word(row: dict) -> str:
    if row["new"]:
        return "new"
    if row["gone"]:
        return "gone"
    return row["verdict"]


def compare_text(a, b, top_n: int = 30) -> str:
    rows = diff_snapshots(a, b, top_n)
    d_total = b.total_time - a.total_time
    pct = (d_total / a.total_time) if a.total_time > 0 else 0.0
    verdict = "B is faster" if d_total < 0 else ("B is slower" if d_total > 0 else "no change")
    lines = [
        f"CinderLens compare: {a.target}  vs  {b.target}",
        f"  A  {a.timestamp}  total {fmt_time(a.total_time)} ({len(a.functions):,} functions)",
        f"  B  {b.timestamp}  total {fmt_time(b.total_time)} ({len(b.functions):,} functions)",
        f"  Δ total {fmt_time(abs(d_total))} ({fmt_pct(abs(pct))}) — {verdict}",
        "",
        "Biggest total-time changes:",
        f"  {'function':<30} {'location':<20} {'calls A→B':>17} "
        f"{'Δ self':>10} {'Δ total':>10} {'Δ total %':>10}  verdict",
    ]
    for r in rows:
        loc = r["short"]
        if len(loc) > 20:
            loc = "…" + loc[-19:]
        pct_s = "n/a" if r["pct"] == float("inf") else fmt_pct(abs(r["pct"]))
        lines.append(
            f"  {r['name'][:30]:<30} {loc:<20} "
            f"{r['calls_a']:>8,}→{r['calls_b']:<8,} "
            f"{fmt_time(abs(r['d_tt'])):>9} {'-' if r['d_tt'] < 0 else '+'}"
            f"{fmt_time(abs(r['d_ct'])):>9} {'-' if r['d_ct'] < 0 else '+'}"
            f"{pct_s:>10}  {_verdict_word(r)}"
        )
    return "\n".join(lines)


_CMP_EXTRA_CSS = """
.verdict-faster td.dv{color:var(--green);font-weight:700}
.verdict-slower td.dv{color:var(--red);font-weight:700}
.verdict-same td.dv{color:var(--muted)}
.tag{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.5px;
  text-transform:uppercase;padding:2px 9px;border-radius:20px;margin-left:8px}
.t-new{background:rgba(87,199,255,.14);color:#57c7ff}
.t-gone{background:rgba(125,143,163,.16);color:#7d8fa3}
.bars{display:flex;flex-direction:column;gap:4px;min-width:180px}
.bar{height:9px;border-radius:5px}
.bar-a{background:#5b5348}
.bar-b{background:var(--accent)}
.bar-row{display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:11.5px;color:var(--muted)}
.bar-row .bl{width:120px;flex:none;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.legend{display:flex;gap:18px;color:var(--muted);font-size:13px;margin:10px 0 16px}
.sw{display:inline-block;width:22px;height:9px;border-radius:5px;margin-right:6px;vertical-align:middle}
"""

_CMP_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CinderLens compare &mdash; __LABEL_A__ vs __LABEL_B__</title>
<style>__CSS__</style>
</head>
<body>
<div class="wrap">
  <header class="rep-head">
    <div class="brand">
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 2c1 4-4 6-4 11a4.5 4.5 0 0 0 9 0c0-2-1-3.5-2-5-.5 1.5-1.5 2-2.5 2C13 8 13 4 12 2z"
          fill="#ff6b35" opacity=".9"/>
      </svg>
      CinderLens <span class="ver">v__VERSION__</span>
    </div>
    <div class="meta">compare<br>__LABEL_A__ <b>vs</b> __LABEL_B__</div>
  </header>

  <h1>Before <span style="color:var(--muted)">&rarr;</span> after</h1>
  <p class="lede">Per-function deltas between two runs, sorted by biggest absolute
  total-time change. Green means the "after" run got <b>faster</b>, red means it got
  <b>slower</b>.</p>

  <div class="cards">__CARDS__</div>

  <section>
    <h2>Biggest changes</h2>
    <div class="legend">
      <span><span class="sw" style="background:#5b5348"></span>before (A)</span>
      <span><span class="sw" style="background:var(--accent)"></span>after (B)</span>
    </div>
    <div class="tbl-wrap">
    <table class="sortable">
      <thead><tr>
        <th data-sort="str">Function <span class="dir"></span></th>
        <th data-sort="num" class="num">Calls A&rarr;B <span class="dir"></span></th>
        <th data-sort="num" class="num">&Delta; self <span class="dir"></span></th>
        <th data-sort="num" class="num">&Delta; total <span class="dir"></span></th>
        <th data-sort="str">&Delta; total % <span class="dir"></span></th>
        <th>Before / after</th>
        <th data-sort="str">Verdict <span class="dir"></span></th>
      </tr></thead>
      <tbody>__ROWS__</tbody>
    </table>
    </div>
  </section>

  <footer>
    Generated by <a href="https://github.com/judd69/cinderlens">CinderLens</a>
    v__VERSION__ &middot; single-file report, no tracking, no network calls.
  </footer>
</div>
<script>
(function () {
  "use strict";
  document.querySelectorAll("table.sortable").forEach(function (tbl) {
    var ths = tbl.querySelectorAll("thead th[data-sort]");
    ths.forEach(function (th, idx) {
      th.addEventListener("click", function () {
        var tbody = tbl.tBodies[0];
        var rows = Array.prototype.slice.call(tbody.rows);
        var num = th.getAttribute("data-sort") === "num";
        var asc = th.getAttribute("data-dir") !== "asc";
        ths.forEach(function (o) {
          o.removeAttribute("data-dir");
          var d = o.querySelector(".dir");
          if (d) d.textContent = "";
        });
        th.setAttribute("data-dir", asc ? "asc" : "desc");
        var d = th.querySelector(".dir");
        if (d) d.textContent = asc ? " \\u25b2" : " \\u25bc";
        rows.sort(function (a, b) {
          var av = a.cells[idx].getAttribute("data-v") || "";
          var bv = b.cells[idx].getAttribute("data-v") || "";
          var c = num ? parseFloat(av) - parseFloat(bv) : av.localeCompare(bv);
          return (c || 0) * (asc ? 1 : -1);
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
      });
    });
  });
})();
</script>
</body>
</html>
"""


def _fmt_delta(seconds: float) -> str:
    sign = "-" if seconds < 0 else "+"
    return f"{sign}{fmt_time(abs(seconds))}"


def render_compare(a, b, top_n: int = 30) -> str:
    rows = diff_snapshots(a, b, top_n)
    d_total = b.total_time - a.total_time
    pct = (d_total / a.total_time) if a.total_time > 0 else 0.0
    verdict = (
        "B is faster" if d_total < 0 else ("B is slower" if d_total > 0 else "no change")
    )
    label_a = esc(os.path.basename(a.target))
    label_b = esc(os.path.basename(b.target))

    cards = f"""
    <div class="card"><div class="k">Before (A)</div>
      <div class="v">{esc(fmt_time(a.total_time))}</div>
      <div class="s">{label_a} &middot; {esc(a.timestamp.replace("T", " ")[:19])}</div></div>
    <div class="card"><div class="k">After (B)</div>
      <div class="v">{esc(fmt_time(b.total_time))}</div>
      <div class="s">{label_b} &middot; {esc(b.timestamp.replace("T", " ")[:19])}</div></div>
    <div class="card"><div class="k">&Delta; total</div>
      <div class="v">{esc(_fmt_delta(d_total))} <small>{esc(fmt_pct(abs(pct)))}</small></div>
      <div class="s">{esc(verdict)}</div></div>
    <div class="card"><div class="k">Functions</div>
      <div class="v">{len(a.functions):,} <small>&rarr; {len(b.functions):,}</small></div>
      <div class="s">profiled in A &rarr; B</div></div>
    """

    body = []
    for r in rows:
        scale = max(r["ct_a"], r["ct_b"], 1e-12)
        wa = 100.0 * r["ct_a"] / scale
        wb = 100.0 * r["ct_b"] / scale
        pct_s = "n/a" if r["pct"] == float("inf") else _fmt_delta(r["d_ct"]) + f" ({fmt_pct(abs(r['pct']))})"
        tag = ""
        if r["new"]:
            tag = '<span class="tag t-new">new</span>'
        elif r["gone"]:
            tag = '<span class="tag t-gone">gone</span>'
        base = "" if r["file"] in ("~", "") else os.path.basename(r["file"])
        loc = f"{base}:{r['lineno']}" if base else f"line {r['lineno']}"
        body.append(
            f'<tr class="verdict-{r["verdict"]}">'
            f'<td data-v="{esc(r["name"].lower())}"><span class="fn">{esc(r["name"])}</span>{tag}'
            f'<span class="loc">{esc(loc)}</span></td>'
            f'<td data-v="{r["d_calls"]}" class="num">{r["calls_a"]:,} &rarr; {r["calls_b"]:,}</td>'
            f'<td data-v="{r["d_tt"]}" class="num dv">{esc(_fmt_delta(r["d_tt"]))}</td>'
            f'<td data-v="{r["d_ct"]}" class="num dv">{esc(_fmt_delta(r["d_ct"]))}</td>'
            f'<td data-v="{esc(str(abs(r["pct"])))}">{esc(pct_s)}</td>'
            f'<td><div class="bars">'
            f'<div class="bar-row"><span class="bl">{esc(fmt_time(r["ct_a"]))}</span>'
            f'<div class="bar bar-a" style="width:{wa:.1f}%"></div></div>'
            f'<div class="bar-row"><span class="bl">{esc(fmt_time(r["ct_b"]))}</span>'
            f'<div class="bar bar-b" style="width:{wb:.1f}%"></div></div>'
            f"</div></td>"
            f'<td data-v="{esc(_verdict_word(r))}" class="dv">{esc(_verdict_word(r))}</td>'
            "</tr>"
        )

    page = _CMP_PAGE
    page = page.replace("__CSS__", _CSS + _CMP_EXTRA_CSS)
    page = page.replace("__LABEL_A__", label_a)
    page = page.replace("__LABEL_B__", label_b)
    page = page.replace("__VERSION__", esc(__version__))
    page = page.replace("__CARDS__", cards)
    page = page.replace("__ROWS__", "\n".join(body))
    return page
