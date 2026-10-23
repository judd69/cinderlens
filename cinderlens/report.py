"""Self-contained interactive HTML report generator.

Everything is inlined — CSS, JS, and the call-tree data — so the report is a
single ``.html`` file with no CDN or network dependency.  The centerpiece is
an interactive flamegraph (SVG): width encodes total time, color encodes
self-time heat, with click-to-zoom, breadcrumbs, search, and hover tooltips.
"""
from __future__ import annotations

import html
import json
import os

from . import __version__
from .tree import TreeNode, build_forest


# --------------------------------------------------------------------------
# formatting helpers
# --------------------------------------------------------------------------
def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def fmt_time(seconds: float) -> str:
    """Human time: 12.3µs, 4.56ms, 1.234s."""
    if seconds < 0:
        return "-" + fmt_time(-seconds)
    if seconds < 1e-3:
        return f"{seconds * 1e6:.1f}µs"
    if seconds < 1:
        return f"{seconds * 1e3:.2f}ms"
    return f"{seconds:.3f}s"


def fmt_pct(frac: float) -> str:
    return f"{100.0 * frac:.1f}%"


def fmt_int(n: int) -> str:
    return f"{n:,}"


# --------------------------------------------------------------------------
# flamegraph colors (ember scale: dim warm gray -> bright ember)
# --------------------------------------------------------------------------
def flame_color(self_frac: float, name: str) -> str:
    t = max(0.0, min(1.0, self_frac)) ** 0.65
    jitter = ((hash(name) & 0xFF) - 128) / 128 * 10  # ±10 texture
    r = int(min(255, max(0, 58 + (255 - 58) * t + jitter)))
    g = int(min(255, max(0, 52 + (106 - 52) * t + jitter * 0.6)))
    b = int(min(255, max(0, 46 + (26 - 46) * t)))
    return f"#{r:02x}{g:02x}{b:02x}"


def flame_text_color(self_frac: float) -> str:
    return "#1c0f06" if self_frac > 0.55 else "#f5efe8"


def tree_to_dict(node: TreeNode, cutoff: float) -> dict:
    """TreeNode -> JSON-able dict, pruning subtrees under *cutoff* cumtime."""
    return {
        "key": node.key,
        "name": node.name,
        "file": node.file,
        "line": node.lineno,
        "calls": node.calls,
        "tottime": node.tottime,
        "cumtime": node.cumtime,
        "col": flame_color(node.self_frac, node.name),
        "tcol": flame_text_color(node.self_frac),
        "children": [
            tree_to_dict(c, cutoff)
            for c in node.children
            if c.cumtime >= cutoff
        ],
    }


# --------------------------------------------------------------------------
# text summary
# --------------------------------------------------------------------------
def render_text_summary(snapshot, top_n: int = 30) -> str:
    total = snapshot.total_time or 1e-9
    lines = [
        f"CinderLens profile: {snapshot.target}",
        f"  timestamp   {snapshot.timestamp}",
        f"  python      {snapshot.python}",
        f"  total time  {fmt_time(snapshot.total_time)} "
        f"(wall {fmt_time(snapshot.wall_time)})",
        f"  functions   {len(snapshot.functions)}",
        "",
        "Top functions by self time:",
        f"  {'function':<32} {'location':<22} {'calls':>10} "
        f"{'self':>10} {'per-call':>10} {'total':>10} {'% total':>8}",
    ]
    rows = sorted(snapshot.functions.values(), key=lambda f: f.tottime, reverse=True)
    for f in rows[:top_n]:
        loc = f.short
        if len(loc) > 22:
            loc = "…" + loc[-21:]
        lines.append(
            f"  {f.name[:32]:<32} {loc:<22} {f.calls:>10,} "
            f"{fmt_time(f.tottime):>10} {fmt_time(f.per_call):>10} "
            f"{fmt_time(f.cumtime):>10} {fmt_pct(f.tottime / total):>8}"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# HTML report
# --------------------------------------------------------------------------
_CSS = """
:root{
  --bg:#0d0b09; --panel:#151210; --panel2:#1a1512; --line:#2b241d;
  --text:#f3ece2; --muted:#a89a86; --accent:#ff6b35; --accent2:#ffb347;
  --green:#4ade80; --red:#f87171;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  line-height:1.6}
.wrap{max-width:1220px;margin:0 auto;padding:0 24px 60px}
.mono{font-family:var(--mono)}
.rep-head{display:flex;justify-content:space-between;align-items:center;gap:16px;
  padding:22px 0;border-bottom:1px solid var(--line);flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:10px;font-weight:800;font-size:20px}
.brand .ver{font-size:12px;color:var(--muted);font-weight:600;background:var(--panel2);
  border:1px solid var(--line);padding:2px 9px;border-radius:20px}
.meta{color:var(--muted);font-size:13.5px;font-family:var(--mono);text-align:right}
.meta b{color:var(--text)}
h1{font-size:34px;letter-spacing:-.5px;margin:34px 0 4px}
h1 .tgt{color:var(--accent2);font-family:var(--mono);font-size:28px}
.lede{color:var(--muted);margin-bottom:26px;max-width:760px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin:8px 0 8px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 20px}
.card .k{font-size:12px;text-transform:uppercase;letter-spacing:.7px;color:var(--muted);margin-bottom:6px}
.card .v{font-size:24px;font-weight:700}
.card .v small{font-size:14px;color:var(--muted);font-weight:500}
.card .s{font-size:12.5px;color:var(--muted);font-family:var(--mono);margin-top:4px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
section{padding:34px 0 6px}
h2{font-size:24px;letter-spacing:-.3px;margin-bottom:6px}
.sub{color:var(--muted);margin-bottom:18px;max-width:760px;font-size:15px}
/* flamegraph */
.flame-controls{display:flex;gap:12px;align-items:center;margin-bottom:10px;flex-wrap:wrap}
#flamesearch{background:var(--panel);border:1px solid var(--line);color:var(--text);
  border-radius:8px;padding:9px 14px;font-size:14px;width:300px;outline:none}
#flamesearch:focus{border-color:var(--accent)}
#matchcount{color:var(--muted);font-size:13.5px}
#flamereset{background:var(--panel2);border:1px solid var(--line);color:var(--text);
  border-radius:8px;padding:9px 16px;font-size:13.5px;cursor:pointer;font-weight:600}
#flamereset:hover{border-color:var(--accent)}
.crumbs{font-family:var(--mono);font-size:13px;color:var(--muted);margin:2px 0 10px;min-height:22px}
.crumb{background:none;border:none;color:var(--accent2);font:inherit;cursor:pointer;padding:2px 4px;border-radius:4px}
button.crumb:hover{background:var(--panel2)}
span.crumb{color:var(--text)}
.flame-wrap{position:relative;background:var(--panel);border:1px solid var(--line);
  border-radius:12px;padding:14px;overflow-x:auto}
#flame{width:100%;height:auto;display:block}
#flame .frame{cursor:pointer;stroke:rgba(0,0,0,.35);stroke-width:1}
#flame .frame:hover{stroke:#fff;stroke-width:1.6}
#flame.searching .frame{opacity:.22}
#flame.searching .frame.match{opacity:1;stroke:var(--accent2);stroke-width:2}
#flame .frame.flash{animation:flsh 1.1s ease}
@keyframes flsh{0%,100%{stroke:rgba(0,0,0,.35);stroke-width:1}
  25%,60%{stroke:#fff;stroke-width:3}}
.flabel{font-family:var(--mono);font-size:12px}
.flametip{position:absolute;z-index:5;background:#211a14;border:1px solid var(--accent);
  border-radius:10px;padding:12px 14px;font-size:13px;min-width:230px;max-width:320px;
  box-shadow:0 14px 40px rgba(0,0,0,.5);pointer-events:none}
.flametip b{font-family:var(--mono);font-size:14px;color:var(--accent2);display:block}
.flametip>span{font-family:var(--mono);font-size:12px;color:var(--muted);display:block;margin-bottom:8px;
  word-break:break-all}
.flametip .trow{display:flex;justify-content:space-between;gap:18px;padding:2px 0}
.flametip .trow span{color:var(--muted)}
.flametip .trow b{font-family:var(--mono);font-weight:600;color:var(--text);display:inline;font-size:13px}
.hint{color:var(--muted);font-size:13px;margin-top:10px}
#locatenote{background:rgba(255,179,71,.1);border:1px solid var(--accent2);color:var(--accent2);
  border-radius:8px;padding:10px 14px;font-size:13.5px;margin-top:10px}
/* tables */
.tbl-wrap{overflow:auto;border:1px solid var(--line);border-radius:12px;max-height:560px;background:var(--panel)}
table{width:100%;border-collapse:collapse;font-size:14px}
thead th{position:sticky;top:0;background:var(--panel2);text-align:left;padding:12px 14px;
  font-size:12.5px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);
  cursor:pointer;user-select:none;white-space:nowrap;z-index:2}
thead th:hover{color:var(--text)}
thead th .dir{color:var(--accent2)}
tbody td{padding:10px 14px;border-top:1px solid var(--line);vertical-align:top}
tbody tr{cursor:pointer}
tbody tr:hover{background:rgba(255,107,53,.06)}
td.num,th.num{text-align:right;font-family:var(--mono);white-space:nowrap}
td .fn{font-family:var(--mono);font-weight:600;color:var(--text)}
td .loc{display:block;font-family:var(--mono);font-size:12px;color:var(--muted)}
footer{border-top:1px solid var(--line);margin-top:44px;padding:26px 0;color:var(--muted);
  font-size:13.5px;text-align:center}
footer a{color:var(--accent2);text-decoration:none}
@media(max-width:700px){h1{font-size:26px}.meta{text-align:left}}
"""

_JS = """
(function () {
  "use strict";
  var TREE = JSON.parse(document.getElementById("treedata").textContent);
  var W = 1160, ROW_H = 26, PAD = 10;
  var svgNS = "http://www.w3.org/2000/svg";
  var svg = document.getElementById("flame");
  var tip = document.getElementById("flametip");
  var crumbs = [{ node: TREE, label: "all" }];
  var keyToNode = {};
  (function index(n) {
    if (!(n.key in keyToNode)) keyToNode[n.key] = n;
    (n.children || []).forEach(index);
  })(TREE);
  var query = "";

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function fmtT(s) {
    if (s < 0.001) return (s * 1e6).toFixed(1) + "\\u00b5s";
    if (s < 1) return (s * 1e3).toFixed(2) + "ms";
    return s.toFixed(3) + "s";
  }
  function shortLabel(n) {
    var base = n.file ? n.file.split("/").pop() : "";
    return n.name + (base ? "  " + base + ":" + n.line : "");
  }
  function maxDepth(n) {
    var m = 0, kids = n.children || [], i;
    for (i = 0; i < kids.length; i++) m = Math.max(m, 1 + maxDepth(kids[i]));
    return m;
  }

  function renderCrumbs() {
    var c = document.getElementById("crumbs");
    c.innerHTML = "";
    crumbs.forEach(function (cr, i) {
      if (i > 0) c.appendChild(document.createTextNode(" \\u203a "));
      var el = document.createElement(i === crumbs.length - 1 ? "span" : "button");
      el.textContent = cr.label;
      el.className = "crumb";
      if (i < crumbs.length - 1) {
        (function (idx) {
          el.addEventListener("click", function () {
            crumbs = crumbs.slice(0, idx + 1);
            render();
          });
        })(i);
      }
      c.appendChild(el);
    });
  }

  function applySearch() {
    var rects = svg.querySelectorAll("rect.frame"), n = 0, i, r, m;
    for (i = 0; i < rects.length; i++) {
      r = rects[i];
      m = !!query && r.getAttribute("data-name").indexOf(query) !== -1;
      r.classList.toggle("match", m);
      if (m) n++;
    }
    svg.classList.toggle("searching", !!query);
    document.getElementById("matchcount").textContent = query ? n + " match" + (n === 1 ? "" : "es") : "";
  }

  function render() {
    var root = crumbs[crumbs.length - 1].node;
    var depth = maxDepth(root);
    var H = (depth + 1) * ROW_H + PAD * 2;
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var frames = [];
    (function layout(node, x, w, d) {
      frames.push({ node: node, x: x, w: w, d: d });
      var kids = node.children || [], tot = 0, i, cx = x;
      for (i = 0; i < kids.length; i++) tot += kids[i].cumtime;
      var fit = tot > node.cumtime && node.cumtime > 0 ? node.cumtime / tot : 1;
      var unit = node.cumtime > 0 ? (w / node.cumtime) * fit : 0;
      for (i = 0; i < kids.length; i++) {
        var kw = kids[i].cumtime * unit;
        layout(kids[i], cx, kw, d + 1);
        cx += kw;
      }
    })(root, 0, W, 0);

    var frag = document.createDocumentFragment();
    frames.forEach(function (f) {
      if (f.w < 0.5) return;
      var y = PAD + (depth - f.d) * ROW_H; /* root at the bottom, flames rise */
      var g = document.createElementNS(svgNS, "g");
      var r = document.createElementNS(svgNS, "rect");
      r.setAttribute("x", f.x.toFixed(1));
      r.setAttribute("y", y);
      r.setAttribute("width", Math.max(f.w - 0.6, 1).toFixed(1));
      r.setAttribute("height", ROW_H - 4);
      r.setAttribute("rx", 3);
      r.setAttribute("fill", f.node.col);
      r.setAttribute("class", "frame");
      r.setAttribute("data-key", f.node.key);
      r.setAttribute("data-name", f.node.name.toLowerCase());
      g.appendChild(r);
      if (f.w > 52) {
        var label = f.node.name;
        var maxChars = Math.max(1, Math.floor((f.w - 14) / 7));
        if (label.length > maxChars) label = label.slice(0, maxChars - 1) + "\\u2026";
        var t = document.createElementNS(svgNS, "text");
        t.textContent = label;
        t.setAttribute("x", (f.x + 7).toFixed(1));
        t.setAttribute("y", y + 17);
        t.setAttribute("class", "flabel");
        t.setAttribute("fill", f.node.tcol);
        t.style.pointerEvents = "none";
        g.appendChild(t);
      }
      frag.appendChild(g);
    });
    svg.appendChild(frag);
    renderCrumbs();
    applySearch();
  }

  /* tooltip */
  svg.addEventListener("mousemove", function (ev) {
    var t = ev.target;
    if (!t || t.tagName !== "rect" || !t.getAttribute("data-key")) {
      tip.hidden = true;
      return;
    }
    var n = keyToNode[t.getAttribute("data-key")];
    if (!n) { tip.hidden = true; return; }
    var selfPct = n.cumtime > 0 ? (100 * n.tottime) / n.cumtime : 0;
    var totPct = TREE.cumtime > 0 ? (100 * n.cumtime) / TREE.cumtime : 0;
    tip.innerHTML =
      "<b>" + esc(n.name) + "</b><span>" + esc(n.file) + ":" + n.line + "</span>" +
      "<div class='trow'><span>calls</span><b>" + n.calls.toLocaleString("en-US") + "</b></div>" +
      "<div class='trow'><span>self time</span><b>" + fmtT(n.tottime) + " (" + selfPct.toFixed(1) + "%)</b></div>" +
      "<div class='trow'><span>total time</span><b>" + fmtT(n.cumtime) + " (" + totPct.toFixed(1) + "%)</b></div>";
    tip.hidden = false;
    var wrap = svg.parentElement.getBoundingClientRect();
    var left = ev.clientX - wrap.left + 16;
    var top = ev.clientY - wrap.top + 12;
    if (left + 330 > wrap.width) left = ev.clientX - wrap.left - 340;
    tip.style.left = Math.max(8, left) + "px";
    tip.style.top = Math.max(8, top) + "px";
  });
  svg.addEventListener("mouseleave", function () { tip.hidden = true; });

  /* click to zoom */
  svg.addEventListener("click", function (ev) {
    var t = ev.target;
    if (!t || t.tagName !== "rect" || !t.getAttribute("data-key")) return;
    var n = keyToNode[t.getAttribute("data-key")];
    if (!n || !(n.children && n.children.length)) return;
    crumbs.push({ node: n, label: shortLabel(n) });
    render();
  });
  document.getElementById("flamereset").addEventListener("click", function () {
    crumbs = [crumbs[0]];
    render();
  });

  /* search */
  document.getElementById("flamesearch").addEventListener("input", function (ev) {
    query = ev.target.value.trim().toLowerCase();
    applySearch();
  });

  /* sortable tables */
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

  /* hot-path row -> locate frame in the flamegraph */
  document.querySelectorAll("#hotpaths tbody tr").forEach(function (tr) {
    tr.addEventListener("click", function () {
      var key = tr.getAttribute("data-key");
      var note = document.getElementById("locatenote");
      if (!keyToNode[key]) {
        note.textContent =
          "That function is below the flamegraph detail threshold " +
          "(--threshold). Re-run with a lower threshold to see it in the flame.";
        note.hidden = false;
        return;
      }
      note.hidden = true;
      crumbs = [crumbs[0]];
      render();
      var r = svg.querySelector('rect.frame[data-key="' + key.replace(/"/g, "\\\\\\"") + '"]');
      if (r) {
        r.scrollIntoView({ block: "nearest", behavior: "smooth" });
        r.classList.remove("flash");
        void r.getBoundingClientRect();
        r.classList.add("flash");
      }
    });
  });

  render();
})();
"""

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CinderLens report &mdash; __TARGET__</title>
<style>__CSS__</style>
</head>
<body>
<div class="wrap">

  <header class="rep-head">
    <div class="brand">
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 2c1 4-4 6-4 11a4.5 4.5 0 0 0 9 0c0-2-1-3.5-2-5-.5 1.5-1.5 2-2.5 2C13 8 13 4 12 2z"
          fill="#ff6b35" opacity=".9"/>
        <path d="M12 22a6.5 6.5 0 0 1-6.5-6.5c0-1.2.3-2.3.8-3.3C5 13.5 4 15 4 17a8 8 0 0 0 16 0c0-4.5-3-6.5-3.5-11-.3 2-1.2 3.2-2.4 4C14.5 7 14 4 12 2v20z"
          fill="#ff6b35" opacity=".25"/>
      </svg>
      CinderLens <span class="ver">v__VERSION__</span>
    </div>
    <div class="meta">profile of <b>__TARGET__</b><br>__TIMESTAMP__ &middot; Python __PYTHON__</div>
  </header>

  <h1>Where did the time go?</h1>
  <p class="lede">An interactive flamegraph of <span class="mono">__TARGET__</span>:
  frame width is total time spent under that call, color heat is self time.
  Click any frame to zoom in, search to highlight, hover for exact numbers.</p>

  <div class="cards">__CARDS__</div>

  <section id="flamegraph">
    <h2>Flamegraph</h2>
    <p class="sub">Root at the bottom, callees stacked above. Hotter frames burn more
    of their own time; wide frames own more of the run.</p>
    <div class="flame-controls">
      <input id="flamesearch" type="search" placeholder="Search functions&hellip; (e.g. fib)" autocomplete="off">
      <span id="matchcount"></span>
      <button id="flamereset" type="button">Reset zoom</button>
    </div>
    <div id="crumbs" class="crumbs"></div>
    <div class="flame-wrap">
      <svg id="flame" role="img" aria-label="Interactive flamegraph"></svg>
      <div id="flametip" class="flametip" hidden></div>
    </div>
    <p class="hint">Click a frame to zoom &middot; hover for details &middot;
    width = total time, color = self-time heat</p>
    <div id="locatenote" hidden></div>
  </section>

  <section id="hotpaths">
    <h2>Hot paths</h2>
    <p class="sub">Top functions by self time. Click a column header to sort;
    click a row to find the function in the flamegraph.</p>
    <div class="tbl-wrap">
    <table class="sortable">
      <thead><tr>
        <th data-sort="str">Function <span class="dir"></span></th>
        <th data-sort="num" class="num">Calls <span class="dir"></span></th>
        <th data-sort="num" class="num">Self <span class="dir"></span></th>
        <th data-sort="num" class="num">Per call <span class="dir"></span></th>
        <th data-sort="num" class="num">Total <span class="dir"></span></th>
        <th data-sort="num" class="num">% of run <span class="dir"></span></th>
      </tr></thead>
      <tbody>__ROWS__</tbody>
    </table>
    </div>
  </section>

  <footer>
    Generated by <a href="https://github.com/judd69/cinderlens">CinderLens</a>
    v__VERSION__ &middot; __TIMESTAMP__ &middot; single-file report, no tracking, no network calls.
  </footer>
</div>
<script type="application/json" id="treedata">__TREE_JSON__</script>
<script>__JS__</script>
</body>
</html>
"""


def _cards_html(snapshot) -> str:
    total = snapshot.total_time or 1e-9
    sf = snapshot.slowest_function()
    mod_path, mod_time = snapshot.slowest_module()
    if mod_path in (None, "", "~"):
        mod_label, mod_sub = "&mdash;", ""
    else:
        mod_label = esc(os.path.basename(mod_path))
        mod_sub = esc(mod_path)
    if sf is None:
        slow_label, slow_sub = "&mdash;", ""
    else:
        slow_label = esc(sf.name)
        slow_sub = esc(sf.short)
    return f"""
    <div class="card"><div class="k">Total time</div>
      <div class="v">{esc(fmt_time(snapshot.total_time))} <small>wall {esc(fmt_time(snapshot.wall_time))}</small></div>
      <div class="s">{esc(snapshot.target)}</div></div>
    <div class="card"><div class="k">Functions</div>
      <div class="v">{len(snapshot.functions):,}</div>
      <div class="s">profiled in this run</div></div>
    <div class="card"><div class="k">Slowest function <small>(self)</small></div>
      <div class="v">{slow_label} <small>{esc(fmt_time(sf.tottime)) if sf else ""}</small></div>
      <div class="s">{slow_sub}</div></div>
    <div class="card"><div class="k">Slowest module <small>(self)</small></div>
      <div class="v">{mod_label} <small>{esc(fmt_time(mod_time))}</small></div>
      <div class="s">{mod_sub}</div></div>
    """


def _rows_html(snapshot, top_n: int) -> str:
    total = snapshot.total_time or 1e-9
    rows = sorted(snapshot.functions.values(), key=lambda f: f.tottime, reverse=True)
    out = []
    for f in rows[:top_n]:
        base = "" if f.file in ("~", "") else os.path.basename(f.file)
        loc = f"{base}:{f.lineno}" if base else f"line {f.lineno}"
        out.append(
            f'<tr data-key="{esc(f.key)}">'
            f'<td data-v="{esc(f.name.lower())}"><span class="fn">{esc(f.name)}</span>'
            f'<span class="loc">{esc(loc)}</span></td>'
            f'<td data-v="{f.calls}" class="num">{fmt_int(f.calls)}</td>'
            f'<td data-v="{f.tottime}" class="num">{esc(fmt_time(f.tottime))}</td>'
            f'<td data-v="{f.per_call}" class="num">{esc(fmt_time(f.per_call))}</td>'
            f'<td data-v="{f.cumtime}" class="num">{esc(fmt_time(f.cumtime))}</td>'
            f'<td data-v="{f.tottime / total}" class="num">{esc(fmt_pct(f.tottime / total))}</td>'
            "</tr>"
        )
    return "\n".join(out)


def render_report(snapshot, top_n: int = 30, threshold_pct: float = 1.0) -> str:
    """Build the complete self-contained HTML report."""
    root = build_forest(snapshot)
    total = snapshot.total_time or 1e-9
    cutoff = (threshold_pct / 100.0) * total
    tree_json = json.dumps(tree_to_dict(root, cutoff))
    # Keep the JSON parseable inside <script type="application/json">.
    tree_json = tree_json.replace("</", "<\\/")
    target_base = os.path.basename(snapshot.target)
    page = _PAGE
    page = page.replace("__CSS__", _CSS)
    page = page.replace("__JS__", _JS)
    page = page.replace("__TREE_JSON__", tree_json)
    page = page.replace("__TARGET__", esc(target_base))
    page = page.replace("__VERSION__", esc(__version__))
    page = page.replace(
        "__TIMESTAMP__", esc(snapshot.timestamp.replace("T", " ")[:19])
    )
    page = page.replace("__PYTHON__", esc(snapshot.python))
    page = page.replace("__CARDS__", _cards_html(snapshot))
    page = page.replace("__ROWS__", _rows_html(snapshot, top_n))
    return page
