import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.normpath(os.path.join(REPO, "lib")))

import check_baseline_ref  # noqa: E402

CONFIG = {"packages": {".": {"release-type": "simple", "initial-version": "1.0.0"}}}


def workflow(default):
    # `on:` is deliberately unquoted: PyYAML reads it as the boolean True.
    return (
        "name: x\n"
        "on:\n"
        "  workflow_call:\n"
        "    inputs:\n"
        "      baseline-ref:\n"
        "        type: string\n"
        "        default: %s\n"
        "jobs: {}\n" % default
    )


class ExpectedRefTest(unittest.TestCase):
    def test_expected_ref_from_manifest(self):
        self.assertEqual(check_baseline_ref.expected_ref({".": "2.3.0"}, CONFIG), "v2")

    def test_expected_ref_initial_version(self):
        self.assertEqual(check_baseline_ref.expected_ref({}, CONFIG), "v1")

    def test_expected_ref_top_level_initial_version(self):
        self.assertEqual(check_baseline_ref.expected_ref({}, {"initial-version": "3.0.0"}), "v3")

    def test_package_initial_version_wins_over_top_level(self):
        config = {"initial-version": "3.0.0", "packages": {".": {"initial-version": "2.0.0"}}}
        self.assertEqual(check_baseline_ref.expected_ref({}, config), "v2")

    def test_expected_ref_without_any_version_is_an_error(self):
        with self.assertRaises(check_baseline_ref.RefError):
            check_baseline_ref.expected_ref({}, {})


class MainTest(unittest.TestCase):
    def run_main(self, baseline, history, manifest=None):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".github", "workflows"))
            for name, default in (("baseline.yml", baseline), ("history-scan.yml", history)):
                with open(os.path.join(root, ".github", "workflows", name), "w") as f:
                    f.write(workflow(default))
            with open(os.path.join(root, "release-please-config.json"), "w") as f:
                json.dump(CONFIG, f)
            with open(os.path.join(root, ".release-please-manifest.json"), "w") as f:
                json.dump(manifest or {}, f)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = check_baseline_ref.main([root])
            return rc, out.getvalue()

    def test_match_exits_0(self):
        rc, _ = self.run_main("v1", "v1")
        self.assertEqual(rc, 0)

    def test_mismatch_exits_1(self):
        rc, out = self.run_main("v2", "v1")
        self.assertEqual(rc, 1)
        self.assertIn("baseline.yml", out)
        self.assertNotIn("history-scan.yml", out)

    def test_history_scan_mismatch_exits_1(self):
        rc, out = self.run_main("v1", "v2")
        self.assertEqual(rc, 1)
        self.assertIn("history-scan.yml", out)
        self.assertNotIn("baseline.yml:", out)

    def test_manifest_major_bump_requires_new_default(self):
        rc, _ = self.run_main("v1", "v1", {".": "2.0.0"})
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
