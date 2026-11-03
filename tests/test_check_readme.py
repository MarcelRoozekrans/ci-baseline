import contextlib
import io
import os
import sys
import tempfile
import unittest

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.normpath(os.path.join(REPO, "lib")))

import check_readme  # noqa: E402

CODECOV = "coverage:\n  status:\n    project:\n      default:\n        target: auto\n"

README = """# t

## Inputs

### baseline.yml inputs

| Input | Default | What it does |
| --- | --- | --- |
| `languages` | `csharp` | x |
| `solution` | empty | x |

### coverage-gate inputs

| Input | Default | What it does |
| --- | --- | --- |
| `floor` | `80` | x |

## NuGetAuditSuppress

text

## CodeQL upload refused

text

```yaml
coverage:
  status:
    project:
      default:
        target: auto
```
"""

BASELINE = (
    "on:\n  workflow_call:\n    inputs:\n"
    "      languages:\n        default: csharp\n"
    "      solution:\n        default: ''\n"
    "jobs: {}\n"
)
GATE = "name: g\ninputs:\n  floor:\n    default: '80'\nruns:\n  using: composite\n  steps: []\n"


HISTORY = "on:\n  workflow_call:\n    secrets:\n      GITLEAKS_CONFIG:\n        required: false\njobs: {}\n"


def make_repo(root, readme=README, baseline=BASELINE, gate=GATE, codecov=CODECOV, extra_ref="", history=HISTORY):
    def write(rel, text):
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    write("README.md", readme)
    write(".github/workflows/baseline.yml", baseline + extra_ref)
    write("actions/coverage-gate/action.yml", gate)
    write("fixtures/dotnet-clean/codecov.yml", codecov)
    write(".github/workflows/history-scan.yml", history)


class TableTest(unittest.TestCase):
    def test_table_keys(self):
        self.assertEqual(
            check_readme.table_inputs(README, "baseline.yml inputs"), {"languages", "solution"}
        )

    def test_missing_heading_is_an_error(self):
        with self.assertRaises(check_readme.ReadmeError):
            check_readme.table_inputs(README, "sbom inputs")

    def test_table_stops_at_next_heading(self):
        self.assertEqual(check_readme.table_inputs(README, "coverage-gate inputs"), {"floor"})


class CodecovBlockTest(unittest.TestCase):
    def test_extracts_the_codecov_block(self):
        self.assertEqual(check_readme.codecov_block(README), CODECOV)

    def test_no_block_is_an_error(self):
        with self.assertRaises(check_readme.ReadmeError):
            check_readme.codecov_block("# nothing\n")


class SlugTest(unittest.TestCase):
    def test_github_slugs(self):
        self.assertEqual(check_readme.slug("NuGetAuditSuppress"), "nugetauditsuppress")
        self.assertEqual(check_readme.slug("CodeQL upload refused"), "codeql-upload-refused")
        self.assertEqual(check_readme.slug("Moving `v1` by hand"), "moving-v1-by-hand")


class MainTest(unittest.TestCase):
    def setUp(self):
        saved = check_readme.TABLES
        check_readme.TABLES = {
            "baseline.yml inputs": ".github/workflows/baseline.yml",
            "coverage-gate inputs": "actions/coverage-gate/action.yml",
        }
        self.addCleanup(setattr, check_readme, "TABLES", saved)
        saved_none = check_readme.NO_INPUTS
        check_readme.NO_INPUTS = (".github/workflows/history-scan.yml",)
        self.addCleanup(setattr, check_readme, "NO_INPUTS", saved_none)

    def run_main(self, **kwargs):
        with tempfile.TemporaryDirectory() as root:
            make_repo(root, **kwargs)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = check_readme.main([root])
            return rc, out.getvalue()

    def test_consistent_repo_passes(self):
        rc, out = self.run_main()
        self.assertEqual(rc, 0, out)

    def test_input_missing_from_table(self):
        rc, out = self.run_main(
            baseline=BASELINE.replace("jobs: {}", "      extra: {}\njobs: {}")
        )
        self.assertEqual(rc, 1)
        self.assertIn("extra", out)
        self.assertIn("missing from the README", out)

    def test_table_row_without_input(self):
        rc, out = self.run_main(gate="name: g\ninputs:\n  other:\n    default: x\nruns: {using: composite}\n")
        self.assertEqual(rc, 1)
        self.assertIn("floor", out)
        self.assertIn("not an input", out)

    def test_default_drift(self):
        rc, out = self.run_main(baseline=BASELINE.replace("default: csharp", "default: python"))
        self.assertEqual(rc, 1)
        self.assertIn("languages", out)
        self.assertIn("default", out)

    def test_boolean_empty_and_required_defaults(self):
        table = "| `a` | `true` | x |\n| `b` | empty | x |\n| `c` | required | x |\n"
        yml = "inputs:\n  a:\n    default: true\n  b:\n    default: ''\n  c:\n    required: true\n"
        self.assertEqual(check_readme.table_defaults("### t\n\n" + table, "t"), {"a": "true", "b": "empty", "c": "required"})
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "a.yml")
            with open(path, "w") as f:
                f.write(yml)
            self.assertEqual(check_readme.yaml_defaults(path), {"a": "true", "b": "empty", "c": "required"})

    def test_codecov_drift(self):
        rc, out = self.run_main(codecov=CODECOV + "        threshold: 1%\n")
        self.assertEqual(rc, 1)
        self.assertIn("codecov", out)

    def test_referenced_anchor_must_exist(self):
        rc, out = self.run_main(extra_ref="# see https://github.com/MarcelRoozekrans/ci-baseline#no-such-section\n")
        self.assertEqual(rc, 1)
        self.assertIn("no-such-section", out)

    def test_referenced_anchor_that_exists_passes(self):
        rc, out = self.run_main(extra_ref="# see https://github.com/MarcelRoozekrans/ci-baseline#nugetauditsuppress\n")
        self.assertEqual(rc, 0, out)

    def test_workflow_without_inputs_passes(self):
        rc, out = self.run_main(history=HISTORY.replace("    secrets:", "    inputs: {}\n    secrets:"))
        self.assertEqual(rc, 0, out)

    def test_input_on_a_workflow_documented_without_inputs(self):
        rc, out = self.run_main(
            history=HISTORY.replace("    secrets:", "    inputs:\n      baseline-ref:\n        default: v1\n    secrets:")
        )
        self.assertEqual(rc, 1)
        self.assertIn("history-scan.yml", out)
        self.assertIn("baseline-ref", out)

    def test_required_anchor_missing(self):
        rc, out = self.run_main(readme=README.replace("## NuGetAuditSuppress", "## Something else"))
        self.assertEqual(rc, 1)
        self.assertIn("nugetauditsuppress", out)


if __name__ == "__main__":
    unittest.main()
