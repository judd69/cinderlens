"""Tests for call-tree reconstruction from synthetic stats fixtures."""
import unittest

from cinderlens.model import FunctionStats, ProfileSnapshot
from cinderlens.tree import TreeNode, build_forest


def make_snapshot(specs):
    """specs: list of (key, tottime, cumtime, {caller_key: caller_ct})."""
    funcs = {}
    for key, tt, ct, callers in specs:
        fil, ln, name = key.rsplit(":", 2)
        cmap = {ck: (1, 1, 0.0, cct) for ck, cct in callers.items()}
        funcs[key] = FunctionStats(key, fil, int(ln), name, 1, 1, tt, ct, cmap)
    total = sum(tt for _, tt, _, _ in specs)
    return ProfileSnapshot(target="t.py", total_time=total, functions=funcs)


def names_bfs(root):
    out, stack = [], [root]
    while stack:
        node = stack.pop(0)
        out.append(node.name)
        stack.extend(node.children)
    return out


def find(root, name):
    stack = [root]
    while stack:
        node = stack.pop()
        if node.name == name:
            return node
        stack.extend(node.children)
    return None


class TreeTest(unittest.TestCase):
    def test_linear_chain_and_compression(self):
        # main -> a -> b ; single-child chains fold, so root becomes main.
        snap = make_snapshot([
            ("t.py:1:<module>", 0.01, 1.0, {}),
            ("t.py:10:main", 0.05, 0.996, {"t.py:1:<module>": 0.996}),
            ("t.py:20:a", 0.2, 0.9, {"t.py:10:main": 0.9}),
            ("t.py:30:b", 0.7, 0.7, {"t.py:20:a": 0.7}),
        ])
        root = build_forest(snap)
        self.assertEqual(root.name, "main")  # folded: total -> <module> -> main
        a = find(root, "a")
        self.assertIsNotNone(a)
        self.assertEqual([c.name for c in a.children], ["b"])

    def test_diamond_attaches_to_biggest_caller(self):
        # main calls b and c; both call d; b contributes more of d's time.
        snap = make_snapshot([
            ("t.py:1:main", 0.1, 1.0, {}),
            ("t.py:10:b", 0.1, 0.6, {"t.py:1:main": 0.6}),
            ("t.py:20:c", 0.1, 0.4, {"t.py:1:main": 0.4}),
            ("t.py:30:d", 0.5, 0.6, {"t.py:10:b": 0.5, "t.py:20:c": 0.1}),
        ])
        root = build_forest(snap)
        b = find(root, "b")
        c = find(root, "c")
        self.assertIsNotNone(b)
        self.assertIsNotNone(c)
        self.assertEqual([ch.name for ch in b.children], ["d"])
        self.assertEqual(c.children, [])

    def test_self_recursion_merges(self):
        # fib's biggest caller is itself -> merged, attached under main once.
        snap = make_snapshot([
            ("t.py:1:main", 0.05, 10.0, {}),
            ("t.py:10:fib", 9.0, 9.95, {"t.py:10:fib": 9.9, "t.py:1:main": 0.05}),
        ])
        root = build_forest(snap)
        self.assertEqual(names_bfs(root).count("fib"), 1)
        fib = find(root, "fib")
        self.assertIsNotNone(fib)
        self.assertAlmostEqual(fib.cumtime, 9.95)  # full recursive cost kept

    def test_mutual_recursion_terminates(self):
        # a <-> b cycle: broken deterministically, both appear, no hang.
        snap = make_snapshot([
            ("t.py:1:e", 0.01, 1.0, {}),
            ("t.py:10:a", 0.4, 0.9, {"t.py:10:b": 0.8, "t.py:1:e": 0.1}),
            ("t.py:20:b", 0.4, 0.85, {"t.py:10:a": 0.8}),
        ])
        root = build_forest(snap)
        self.assertLessEqual(root.count(), 6)
        a = find(root, "a")
        b = find(root, "b")
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        # One must be an ancestor of the other (cycle broken into a chain).
        def is_ancestor(anc, node):
            stack = [anc]
            while stack:
                n = stack.pop()
                if n is node:
                    return True
                stack.extend(n.children)
            return False
        self.assertTrue(is_ancestor(a, b) or is_ancestor(b, a))

    def test_exec_driver_spliced_out(self):
        # The profiler's exec() driver is a root-level full-width frame with
        # no self time: it must not appear in the tree; its child moves up.
        snap = make_snapshot([
            ("~:0:<built-in method builtins.exec>", 0.0001, 1.0, {}),
            ("t.py:1:<module>", 0.0, 0.99, {"~:0:<built-in method builtins.exec>": 0.99}),
            ("t.py:10:main", 0.5, 0.98, {"t.py:1:<module>": 0.98}),
        ])
        root = build_forest(snap)
        self.assertIsNone(find(root, "<built-in method builtins.exec>"))
        self.assertIsNotNone(find(root, "main"))

    def test_empty_snapshot(self):
        snap = ProfileSnapshot(target="t.py", total_time=0.0, functions={})
        root = build_forest(snap)
        self.assertEqual(root.name, "total")
        self.assertEqual(root.children, [])

    def test_node_helpers(self):
        snap = make_snapshot([
            ("t.py:1:main", 0.1, 1.0, {}),
            ("t.py:10:a", 0.9, 0.9, {"t.py:1:main": 0.9}),
        ])
        root = build_forest(snap)
        self.assertEqual(root.count(), 2)
        self.assertEqual(root.max_depth(), 1)
        self.assertIsInstance(root, TreeNode)


def _walk(root):
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.children)


if __name__ == "__main__":
    unittest.main()
