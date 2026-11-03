import os
import sys
import tempfile
import unittest

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.normpath(os.path.join(REPO, "lib")))

import coverage_gate  # noqa: E402
from coverage_gate import GateError  # noqa: E402


def readme_block(**project_overrides):
    default = {"target": "auto", "threshold": "1%"}
    default.update(project_overrides)
    return {"coverage": {"status": {"project": {"default": default}}}}


class ValidateFloorTests(unittest.TestCase):
    def test_floor_default_ok(self):
        self.assertEqual(coverage_gate.validate_floor("80", ""), 80.0)

    def test_floor_below_80_without_reason_raises(self):
        with self.assertRaises(GateError) as ctx:
            coverage_gate.validate_floor("40", "")
        self.assertEqual(str(ctx.exception), "floor 40.0 is below 80; set floor-override-reason")

    def test_floor_below_80_whitespace_reason_raises(self):
        with self.assertRaises(GateError):
            coverage_gate.validate_floor("40", "  \n\t ")

    def test_floor_below_80_with_reason_ok(self):
        self.assertEqual(coverage_gate.validate_floor("40", "legacy code"), 40.0)

    def test_floor_non_numeric_raises(self):
        with self.assertRaises(GateError):
            coverage_gate.validate_floor("high", "")

    def test_floor_above_100_raises(self):
        with self.assertRaises(GateError):
            coverage_gate.validate_floor("101", "")

    def test_floor_negative_raises(self):
        with self.assertRaises(GateError):
            coverage_gate.validate_floor("-1", "reason")

    def test_floor_nan_raises(self):
        with self.assertRaises(GateError):
            coverage_gate.validate_floor("nan", "reason")


class FindConfigTests(unittest.TestCase):
    def test_find_config_in_dot_github(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".github"))
            path = os.path.join(root, ".github", "codecov.yml")
            open(path, "w").close()
            self.assertEqual(coverage_gate.find_codecov_config(root), path)

    def test_find_config_prefers_root(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".github"))
            open(os.path.join(root, ".github", "codecov.yml"), "w").close()
            top = os.path.join(root, "codecov.yml")
            open(top, "w").close()
            self.assertEqual(coverage_gate.find_codecov_config(root), top)

    def test_find_config_missing_raises(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(GateError) as ctx:
                coverage_gate.find_codecov_config(root)
            self.assertEqual(str(ctx.exception), "no codecov.yml found")


class PolicyTests(unittest.TestCase):
    def test_policy_readme_block_ok(self):
        self.assertEqual(coverage_gate.codecov_policy_errors(readme_block(), 1.0), [])

    def test_policy_threshold_string_5pct(self):
        errors = coverage_gate.codecov_policy_errors(readme_block(threshold="5%"), 1.0)
        self.assertEqual(len(errors), 1)
        self.assertIn("threshold", errors[0])

    def test_policy_threshold_number_1_ok(self):
        self.assertEqual(coverage_gate.codecov_policy_errors(readme_block(threshold=1), 1.0), [])

    def test_policy_fixed_target_70pct(self):
        errors = coverage_gate.codecov_policy_errors(readme_block(target="70%"), 1.0)
        self.assertEqual(len(errors), 1)
        self.assertIn("target", errors[0])

    def test_policy_informational(self):
        errors = coverage_gate.codecov_policy_errors(readme_block(informational=True), 1.0)
        self.assertEqual(len(errors), 1)
        self.assertIn("informational", errors[0])

    def test_policy_project_off(self):
        for off in (False, "off"):
            cfg = {"coverage": {"status": {"project": off}}}
            errors = coverage_gate.codecov_policy_errors(cfg, 1.0)
            self.assertEqual(len(errors), 1, off)
        # PyYAML parses a bare `off` as False
        import yaml
        cfg = yaml.safe_load("coverage:\n  status:\n    project: off\n")
        self.assertEqual(len(coverage_gate.codecov_policy_errors(cfg, 1.0)), 1)

    def test_policy_project_default_off(self):
        cfg = {"coverage": {"status": {"project": {"default": False}}}}
        self.assertEqual(len(coverage_gate.codecov_policy_errors(cfg, 1.0)), 1)

    def test_policy_project_without_default(self):
        cfg = {"coverage": {"status": {"project": {"core": {"target": "auto", "threshold": "1%"}}}}}
        self.assertEqual(len(coverage_gate.codecov_policy_errors(cfg, 1.0)), 1)

    def test_policy_threshold_missing(self):
        cfg = {"coverage": {"status": {"project": {"default": {"target": "auto"}}}}}
        errors = coverage_gate.codecov_policy_errors(cfg, 1.0)
        self.assertEqual(len(errors), 1)
        self.assertIn("threshold", errors[0])

    def test_policy_threshold_unparseable(self):
        errors = coverage_gate.codecov_policy_errors(readme_block(threshold="lots"), 1.0)
        self.assertEqual(len(errors), 1)

    def test_policy_empty_file(self):
        self.assertEqual(len(coverage_gate.codecov_policy_errors(None, 1.0)), 1)

    def test_policy_wrong_shape(self):
        self.assertEqual(len(coverage_gate.codecov_policy_errors({"coverage": "x"}, 1.0)), 1)

    def test_policy_reports_every_problem(self):
        errors = coverage_gate.codecov_policy_errors(
            readme_block(target="70%", threshold="5%", informational=True), 1.0
        )
        self.assertEqual(len(errors), 3)


class LineCoverageTests(unittest.TestCase):
    def test_line_coverage_reads_summary(self):
        self.assertEqual(coverage_gate.line_coverage({"summary": {"linecoverage": 83.3}}), 83.3)

    def test_line_coverage_missing_key_raises(self):
        with self.assertRaises(GateError):
            coverage_gate.line_coverage({"summary": {}})
        with self.assertRaises(GateError):
            coverage_gate.line_coverage({})


if __name__ == "__main__":
    unittest.main()
