"""Tests for the snapshot model and JSON round-trip."""
import os
import tempfile
import unittest

from cinderlens.model import FunctionStats, ProfileSnapshot


def _snapshot():
    f1 = FunctionStats(
        "a.py:10:foo", "a.py", 10, "foo", 1, 5, 1.5, 2.5,
        {"b.py:1:<module>": (1, 5, 1.5, 2.5)},
    )
    f2 = FunctionStats("b.py:1:<module>", "b.py", 1, "<module>", 1, 1, 0.1, 2.6, {})
    return ProfileSnapshot(
        target="app.py",
        timestamp="2026-10-23T00:00:00+05:30",
        python="3.12.3",
        total_time=2.6,
        wall_time=2.7,
        functions={f1.key: f1, f2.key: f2},
    )


class ModelTest(unittest.TestCase):
    def test_key_format(self):
        f = FunctionStats("a.py:10:foo", "a.py", 10, "foo", 1, 5, 1.5, 2.5)
        self.assertEqual(f.key, "a.py:10:foo")
        self.assertEqual(f.short, "a.py:10:foo")
        self.assertAlmostEqual(f.per_call, 0.3)

    def test_json_round_trip(self):
        snap = _snapshot()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "snap.json")
            snap.save(path)
            snap2 = ProfileSnapshot.load(path)
        self.assertEqual(snap2.target, "app.py")
        self.assertEqual(snap2.timestamp, "2026-10-23T00:00:00+05:30")
        self.assertEqual(snap2.python, "3.12.3")
        self.assertEqual(snap2.total_time, 2.6)
        self.assertEqual(snap2.wall_time, 2.7)
        self.assertEqual(set(snap2.functions), set(snap.functions))
        f = snap2.functions["a.py:10:foo"]
        self.assertEqual(f, snap.functions["a.py:10:foo"])
        self.assertEqual(f.callers["b.py:1:<module>"], (1, 5, 1.5, 2.5))

    def test_slowest_helpers(self):
        snap = _snapshot()
        self.assertEqual(snap.slowest_function().name, "foo")
        path, t = snap.slowest_module()
        self.assertEqual(path, "a.py")
        self.assertEqual(t, 1.5)

    def test_load_rejects_garbage(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.json")
            with open(bad, "w") as fh:
                fh.write("{not json")
            with self.assertRaises(ValueError):
                ProfileSnapshot.load(bad)
            wrong = os.path.join(d, "wrong.json")
            with open(wrong, "w") as fh:
                fh.write('{"hello": "world"}')
            with self.assertRaises(ValueError):
                ProfileSnapshot.load(wrong)

    def test_load_missing_file(self):
        with self.assertRaises(OSError):
            ProfileSnapshot.load("/nonexistent/path/snap.json")


if __name__ == "__main__":
    unittest.main()
