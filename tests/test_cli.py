"""Tests for CLI argument parsing."""
import contextlib
import io
import unittest

from cinderlens.cli import build_parser, main


class CliTest(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_profile_basic(self):
        args = self.parser.parse_args(["profile", "app.py"])
        self.assertEqual(args.command, "profile")
        self.assertEqual(args.script, "app.py")
        self.assertEqual(args.script_args, [])
        self.assertEqual(args.out, "cinderlens-report.html")
        self.assertIsNone(args.json)
        self.assertFalse(args.text)
        self.assertEqual(args.top, 30)
        self.assertEqual(args.threshold, 1.0)

    def test_dashdash_separator_passes_script_args(self):
        # main() strips `--` before argparse; option-looking script args survive.
        # rc == 1 means clean "script not found", not an argparse crash (exit 2).
        with contextlib.redirect_stderr(io.StringIO()):
            rc = main(["profile", "app.py", "--", "--foo", "bar"])
        self.assertEqual(rc, 1)

    def test_profile_options_before_script(self):
        args = self.parser.parse_args(
            ["profile", "--out", "r.html", "--json", "s.json", "--text",
             "--top", "5", "--threshold", "0", "app.py", "a1", "a2"]
        )
        self.assertEqual(args.out, "r.html")
        self.assertEqual(args.json, "s.json")
        self.assertTrue(args.text)
        self.assertEqual(args.top, 5)
        self.assertEqual(args.threshold, 0)
        self.assertEqual(args.script_args, ["a1", "a2"])

    def test_profile_positional_script_args(self):
        args = self.parser.parse_args(["profile", "app.py", "x", "y"])
        self.assertEqual(args.script, "app.py")
        self.assertEqual(args.script_args, ["x", "y"])

    def test_compare_parse(self):
        args = self.parser.parse_args(
            ["compare", "a.json", "b.json", "--text", "--top", "10", "--out", "c.html"]
        )
        self.assertEqual(args.command, "compare")
        self.assertEqual(args.run_a, "a.json")
        self.assertEqual(args.run_b, "b.json")
        self.assertTrue(args.text)
        self.assertEqual(args.top, 10)
        self.assertEqual(args.out, "c.html")

    def test_no_command_prints_help(self):
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = main([])
        self.assertEqual(rc, 0)
        self.assertIn("profile", buf.getvalue())

    def test_version(self):
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            with self.assertRaises(SystemExit) as cm:
                main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("cinderlens", buf.getvalue())

    def test_profile_help(self):
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            with self.assertRaises(SystemExit) as cm:
                main(["profile", "--help"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("--threshold", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
