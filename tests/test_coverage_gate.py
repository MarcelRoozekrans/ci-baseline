import contextlib
import io
import json
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
        self.assertEqual(str(ctx.exception), "floor 40 is below 80; set floor-override-reason")

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


class MaxDropTests(unittest.TestCase):
    def test_max_drop_ok(self):
        self.assertEqual(coverage_gate.validate_max_drop("1"), 1.0)
        self.assertEqual(coverage_gate.validate_max_drop("0"), 0.0)

    def test_max_drop_rejected(self):
        for bad in ("nan", "-1", "inf", "lots", ""):
            with self.assertRaises(GateError, msg=bad):
                coverage_gate.validate_max_drop(bad)


class NarrowedPolicyTests(unittest.TestCase):
    def test_policy_paths_narrowed(self):
        errors = coverage_gate.codecov_policy_errors(readme_block(paths=["src/"]), 1.0)
        self.assertEqual(len(errors), 1)
        self.assertIn("project status narrowed by paths/flags", errors[0])

    def test_policy_flags_narrowed(self):
        errors = coverage_gate.codecov_policy_errors(readme_block(flags=["unit"]), 1.0)
        self.assertEqual(len(errors), 1)
        self.assertIn("project status narrowed by paths/flags", errors[0])

    def test_policy_top_level_ignore_allowed(self):
        cfg = readme_block()
        cfg["ignore"] = ["tests/**"]
        self.assertEqual(coverage_gate.codecov_policy_errors(cfg, 1.0), [])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.summary = os.path.join(self.tmp.name, "summary.md")
        old = os.environ.get("GITHUB_STEP_SUMMARY")
        os.environ["GITHUB_STEP_SUMMARY"] = self.summary

        def restore():
            if old is None:
                os.environ.pop("GITHUB_STEP_SUMMARY", None)
            else:
                os.environ["GITHUB_STEP_SUMMARY"] = old

        self.addCleanup(restore)

    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = coverage_gate.main(list(args))
        return code, out.getvalue()

    def summary_text(self):
        if not os.path.exists(self.summary):
            return ""
        with open(self.summary) as handle:
            return handle.read()

    def write(self, name, text):
        path = os.path.join(self.tmp.name, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write(text)
        return path

    def test_validate_floor_override_writes_reason(self):
        code, out = self.run_cli("validate-floor", "40", "legacy code")
        self.assertEqual(code, 0)
        self.assertIn("legacy code", self.summary_text())

    def test_validate_floor_without_reason_fails(self):
        code, out = self.run_cli("validate-floor", "40", "")
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("::error::"))
        self.assertIn("floor 40 is below 80", out)

    def test_validate_floor_default_writes_nothing(self):
        code, _ = self.run_cli("validate-floor", "80", "")
        self.assertEqual(code, 0)
        self.assertEqual(self.summary_text(), "")

    def test_check_floor_pass_writes_summary(self):
        path = self.write("s.json", json.dumps({"summary": {"linecoverage": 83.3}}))
        code, _ = self.run_cli("check-floor", path, "80")
        self.assertEqual(code, 0)
        self.assertIn("Line coverage: 83.3% (floor 80%)", self.summary_text())

    def test_check_floor_below_fails(self):
        path = self.write("s.json", json.dumps({"summary": {"linecoverage": 42.8}}))
        code, out = self.run_cli("check-floor", path, "80")
        self.assertEqual(code, 1)
        self.assertIn("::error::", out)
        self.assertIn("Line coverage: 42.8% (floor 80%)", self.summary_text())

    def test_check_floor_rounding_cannot_contradict(self):
        path = self.write("s.json", json.dumps({"summary": {"linecoverage": 79.996}}))
        code, out = self.run_cli("check-floor", path, "80")
        self.assertEqual(code, 0, out)
        self.assertIn("Line coverage: 80% (floor 80%)", self.summary_text())

    def test_check_floor_just_below_fails(self):
        path = self.write("s.json", json.dumps({"summary": {"linecoverage": 79.99}}))
        code, out = self.run_cli("check-floor", path, "80")
        self.assertEqual(code, 1)
        self.assertIn("79.99%", out)

    def test_check_floor_bad_floor_is_error_not_traceback(self):
        path = self.write("s.json", json.dumps({"summary": {"linecoverage": 90}}))
        code, out = self.run_cli("check-floor", path, "abc")
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith("::error::"))

    def test_check_floor_unreadable_summary(self):
        code, out = self.run_cli("check-floor", os.path.join(self.tmp.name, "none.json"), "80")
        self.assertEqual(code, 2)
        self.assertEqual(out.count("::error::"), 1)

    def test_check_floor_malformed_json_is_exit_2(self):
        path = self.write("s.json", "{not json")
        code, out = self.run_cli("check-floor", path, "80")
        self.assertEqual(code, 2)
        self.assertEqual(out.count("::error::"), 1)

    def test_check_floor_missing_linecoverage_is_exit_2(self):
        path = self.write("s.json", json.dumps({"summary": {}}))
        code, out = self.run_cli("check-floor", path, "80")
        self.assertEqual(code, 2)
        self.assertEqual(out.count("::error::"), 1)
        self.assertEqual(self.summary_text(), "")

    def test_check_codecov_ok(self):
        import yaml

        self.write("codecov.yml", yaml.safe_dump(readme_block()))
        code, _ = self.run_cli("check-codecov", self.tmp.name, "1")
        self.assertEqual(code, 0)

    def test_check_codecov_failure(self):
        self.write("codecov.yml", "coverage:\n  status:\n    project: off\n")
        code, out = self.run_cli("check-codecov", self.tmp.name, "1")
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("::error::"))

    def test_check_codecov_missing_file(self):
        code, out = self.run_cli("check-codecov", self.tmp.name, "1")
        self.assertEqual(code, 1)
        self.assertIn("no codecov.yml found", out)

    def test_check_codecov_bad_max_drop(self):
        code, out = self.run_cli("check-codecov", self.tmp.name, "nan")
        self.assertEqual(code, 1)
        self.assertIn("max-drop", out)

    def test_unknown_command(self):
        code, out = self.run_cli("nope")
        self.assertEqual(code, 1)
        self.assertIn("::error::", out)


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
