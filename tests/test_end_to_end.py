"""End-to-end smoke test: profile a tiny fixture script for real."""
import os
import subprocess
import sys
import tempfile
import unittest

STAGING_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FIXTURE = '''\
def work(n):
    total = 0
    for i in range(n):
        total += i * i
    return total


def helper(x):
    return x + 1


def main():
    acc = 0
    for _ in range(50):
        acc += helper(work(2000))
    return acc


main()
'''


class EndToEndTest(unittest.TestCase):
    def test_profile_report_json_text_and_compare(self):
        from cinderlens.compare import compare_text, render_compare
        from cinderlens.model import ProfileSnapshot
        from cinderlens.profiler import profile_script
        from cinderlens.report import render_report, render_text_summary

        with tempfile.TemporaryDirectory() as d:
            script = os.path.join(d, "tiny.py")
            with open(script, "w") as fh:
                fh.write(FIXTURE)

            snap = profile_script(script, [])
            self.assertIsNone(snap.error)
            key_names = " ".join(snap.functions)
            self.assertIn(":work", key_names)
            self.assertIn(":helper", key_names)
            self.assertGreater(snap.total_time, 0)

            html_report = render_report(snap)
            self.assertIn("<svg", html_report)
            self.assertIn("work", html_report)
            self.assertIn("flamegraph", html_report.lower())
            self.assertIn("treedata", html_report)

            text = render_text_summary(snap)
            self.assertIn("work", text)
            self.assertIn("Top functions", text)

            json_path = os.path.join(d, "snap.json")
            snap.save(json_path)
            snap2 = ProfileSnapshot.load(json_path)
            self.assertEqual(set(snap2.functions), set(snap.functions))

            cmp_html = render_compare(snap, snap2)
            self.assertIn("work", cmp_html)
            cmp_text = compare_text(snap, snap2)
            self.assertIn("work", cmp_text)

    def test_argv_passthrough(self):
        from cinderlens.profiler import profile_script

        with tempfile.TemporaryDirectory() as d:
            script = os.path.join(d, "args.py")
            with open(script, "w") as fh:
                fh.write("import sys\nprint(','.join(sys.argv[1:]))\n")
            snap = profile_script(script, ["--foo", "bar"])
            self.assertIsNone(snap.error)

    def test_missing_script_errors(self):
        import contextlib
        import io

        from cinderlens.cli import main

        with contextlib.redirect_stderr(io.StringIO()):
            rc = main(["profile", "/nonexistent/xyz.py", "--out", os.devnull])
        self.assertEqual(rc, 1)

    def test_module_entrypoint(self):
        proc = subprocess.run(
            [sys.executable, "-m", "cinderlens", "--version"],
            cwd=STAGING_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("cinderlens", proc.stdout)


if __name__ == "__main__":
    unittest.main()
