"""Tests for compare-mode delta math and rendering."""
import unittest

from cinderlens.compare import compare_text, diff_snapshots, render_compare
from cinderlens.model import FunctionStats, ProfileSnapshot


def _snap(specs, target="app.py", total=0.0):
    funcs = {}
    for key, tt, ct, calls in specs:
        fil, ln, name = key.rsplit(":", 2)
        funcs[key] = FunctionStats(key, fil, int(ln), name, 1, calls, tt, ct, {})
    return ProfileSnapshot(target=target, total_time=total, functions=funcs)


class CompareTest(unittest.TestCase):
    def setUp(self):
        self.a = _snap(
            [("app.py:10:f", 1.0, 2.0, 10), ("app.py:20:g", 0.2, 0.2, 3)],
            total=2.2,
        )
        self.b = _snap(
            [("app.py:10:f", 0.6, 1.2, 10), ("app.py:30:h", 0.3, 0.3, 1)],
            total=1.5,
        )

    def test_delta_math(self):
        rows = diff_snapshots(self.a, self.b, top_n=10)
        by_name = {r["name"]: r for r in rows}
        f = by_name["f"]
        self.assertAlmostEqual(f["d_tt"], -0.4)
        self.assertAlmostEqual(f["d_ct"], -0.8)
        self.assertAlmostEqual(f["pct"], -0.4)
        self.assertEqual(f["verdict"], "faster")
        self.assertEqual(f["d_calls"], 0)

    def test_new_and_gone(self):
        rows = diff_snapshots(self.a, self.b, top_n=10)
        by_name = {r["name"]: r for r in rows}
        self.assertTrue(by_name["h"]["new"])
        self.assertTrue(by_name["g"]["gone"])
        self.assertEqual(by_name["h"]["ct_a"], 0.0)

    def test_sorted_by_abs_delta_cumtime(self):
        rows = diff_snapshots(self.a, self.b, top_n=10)
        deltas = [abs(r["d_ct"]) for r in rows]
        self.assertEqual(deltas, sorted(deltas, reverse=True))
        self.assertEqual(rows[0]["name"], "f")  # |−0.8| is biggest

    def test_cross_path_fallback_pairs_same_script(self):
        # Same script profiled from two different directories: functions
        # pair up by basename:lineno:name instead of showing as new/gone.
        a = _snap([("/home/u/old/app.py:10:f", 1.0, 2.0, 10)], total=2.0)
        b = _snap([("/home/u/new/app.py:10:f", 0.5, 1.0, 10)], total=1.0)
        rows = diff_snapshots(a, b, top_n=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "f")
        self.assertFalse(rows[0]["new"])
        self.assertFalse(rows[0]["gone"])
        self.assertAlmostEqual(rows[0]["d_ct"], -1.0)
        self.assertEqual(rows[0]["verdict"], "faster")

    def test_text_output(self):
        text = compare_text(self.a, self.b, top_n=10)
        self.assertIn("faster", text)
        self.assertIn("app.py:10:f", text)
        self.assertIn("Δ total", text)

    def test_html_output(self):
        page = render_compare(self.a, self.b, top_n=10)
        self.assertIn("<table", page)
        self.assertIn("verdict-faster", page)
        self.assertIn("Before / after", page)
        self.assertIn("faster", page)


if __name__ == "__main__":
    unittest.main()
