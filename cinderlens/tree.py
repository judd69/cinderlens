"""Call-tree reconstruction from flat cProfile stats.

cProfile records per-function totals plus a per-caller breakdown.  A tree is
rebuilt by attaching every function to the caller that contributes the
largest share of its cumulative time:

* self-recursive edges are merged — a recursive function appears once, under
  its non-recursive caller, carrying its full cumulative time;
* caller cycles (A calls B calls A) are broken deterministically so tree
  expansion always terminates; the repeated frame is shown once as a
  "(recursive)" leaf;
* single-child chains that span ~all of the parent (the ``exec`` wrapper,
  ``<module>`` -> ``main()``) are folded so the flame starts at the real
  entry point.
"""
from __future__ import annotations


class TreeNode:
    """One frame in the reconstructed call tree."""

    __slots__ = (
        "key",
        "name",
        "file",
        "lineno",
        "prim_calls",
        "calls",
        "tottime",
        "cumtime",
        "self_frac",
        "children",
        "recursive",
    )

    def __init__(
        self,
        key: str,
        name: str,
        file: str,
        lineno: int,
        prim_calls: int,
        calls: int,
        tottime: float,
        cumtime: float,
    ) -> None:
        self.key = key
        self.name = name
        self.file = file
        self.lineno = lineno
        self.prim_calls = prim_calls
        self.calls = calls
        self.tottime = tottime
        self.cumtime = cumtime
        self.self_frac = (tottime / cumtime) if cumtime > 0 else 0.0
        self.children: list["TreeNode"] = []
        self.recursive = False

    def count(self) -> int:
        """Total nodes in this subtree (iterative — safe on deep trees)."""
        total, stack = 0, [self]
        while stack:
            node = stack.pop()
            total += 1
            stack.extend(node.children)
        return total

    def max_depth(self) -> int:
        depth, stack = 0, [(self, 0)]
        while stack:
            node, d = stack.pop()
            depth = max(depth, d)
            stack.extend((c, d + 1) for c in node.children)
        return depth


def build_forest(snapshot) -> TreeNode:
    """Rebuild the call tree; return a single synthetic ``total`` root."""
    funcs = snapshot.functions
    total = snapshot.total_time or sum(f.tottime for f in funcs.values())
    if total <= 0:
        total = 1e-9

    # 1. Attach each function to its biggest cumulative-time contributor.
    parent_of: dict[str, str | None] = {}
    for key, fs in funcs.items():
        best_key: str | None = None
        best_ct = -1.0
        for ckey, (_cc, _nc, _tt, ct) in fs.callers.items():
            if ckey == key or ckey not in funcs:
                continue
            if ct > best_ct:
                best_key, best_ct = ckey, ct
        parent_of[key] = best_key

    # 2. Break caller cycles deterministically: a node whose ancestor chain
    #    loops back on itself is re-attached to the root.
    for key in funcs:
        seen: set[str] = set()
        cur: str | None = key
        while cur is not None and cur not in seen:
            seen.add(cur)
            cur = parent_of.get(cur)
        if cur is not None:
            parent_of[key] = None

    # 3. Splice out the profiler's exec driver.  The exec() call that runs the
    #    target shows up as a root-level builtin frame spanning the whole run
    #    with ~zero self time — a useless full-width flame frame.  Drop it and
    #    re-attach its children to the root.
    exec_frames = {
        key
        for key, fs in funcs.items()
        if parent_of.get(key) is None
        and fs.name == "<built-in method builtins.exec>"
        and fs.tottime <= 0.02 * (fs.cumtime or 1e-9)
    }
    for ekey in exec_frames:
        del parent_of[ekey]
    for key in list(parent_of):
        if parent_of[key] in exec_frames:
            parent_of[key] = None

    children_of: dict[str | None, list[str]] = {}
    for key, pkey in parent_of.items():
        children_of.setdefault(pkey, []).append(key)
    for kids in children_of.values():
        kids.sort(key=lambda k: funcs[k].cumtime, reverse=True)

    def expand(key: str, ancestors: frozenset) -> TreeNode:
        fs = funcs[key]
        node = TreeNode(
            key, fs.name, fs.file, fs.lineno,
            fs.prim_calls, fs.calls, fs.tottime, fs.cumtime,
        )
        for ckey in children_of.get(key, ()):
            if ckey in ancestors:
                cfs = funcs[ckey]
                leaf = TreeNode(
                    ckey, cfs.name + " (recursive)", cfs.file, cfs.lineno,
                    cfs.prim_calls, cfs.calls, cfs.tottime, cfs.cumtime,
                )
                leaf.recursive = True
                node.children.append(leaf)
            else:
                node.children.append(expand(ckey, ancestors | {ckey}))
        return node

    root = TreeNode("__root__", "total", "", 0, 0, 0, 0.0, total)
    for key in children_of.get(None, ()):
        root.children.append(expand(key, frozenset({key})))
    _compress_chains(root)
    return root


def _compress_chains(node: TreeNode) -> None:
    """Fold pass-through wrappers into their single child.

    Only folds when the child spans ~all of the parent *and* the parent burns
    negligible self time (e.g. the ``exec`` driver, ``<module>`` delegating to
    ``main()``).  A frame with real self time is never folded away.
    """
    while len(node.children) == 1 and not node.children[0].recursive:
        child = node.children[0]
        if (
            node.cumtime > 0
            and child.cumtime >= 0.995 * node.cumtime
            and node.tottime <= 0.02 * node.cumtime
        ):
            node.key = child.key
            node.name = child.name
            node.file = child.file
            node.lineno = child.lineno
            node.prim_calls = child.prim_calls
            node.calls = child.calls
            node.tottime = child.tottime
            node.cumtime = child.cumtime
            node.self_frac = child.self_frac
            node.children = child.children
        else:
            break
    for child in node.children:
        _compress_chains(child)
