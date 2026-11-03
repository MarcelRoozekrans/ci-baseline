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
| `baseline-ref` | `v1` | self-test only |

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

BASELINE = "on:\n  workflow_call:\n    inputs:\n      languages: {}\n      baseline-ref: {}\njobs: {}\n"
GATE = "name: g\ninputs:\n  floor:\n    default: '80'\nruns:\n  using: composite\n  steps: []\n"


def make_repo(root, readme=README, baseline=BASELINE, gate=GATE, codecov=CODECOV, extra_ref=""):
    def write(rel, text):
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    write("README.md", readme)
    write(".github/workflows/baseline.yml", baseline + extra_ref)
    write("actions/coverage-gate/action.yml", gate)
    write("fixtures/dotnet-clean/codecov.yml", codecov)


class TableTest(unittest.TestCase):
    def test_table_keys(self):
        self.assertEqual(
            check_readme.table_inputs(README, "baseline.yml inputs"), {"languages", "baseline-ref"}
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
            baseline="on:\n  workflow_call:\n    inputs:\n      languages: {}\n      baseline-ref: {}\n      extra: {}\njobs: {}\n"
        )
        self.assertEqual(rc, 1)
        self.assertIn("extra", out)
        self.assertIn("missing from the README", out)

    def test_table_row_without_input(self):
        rc, out = self.run_main(gate="name: g\ninputs:\n  other:\n    default: x\nruns: {using: composite}\n")
        self.assertEqual(rc, 1)
        self.assertIn("floor", out)
        self.assertIn("not an input", out)

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

    def test_required_anchor_missing(self):
        rc, out = self.run_main(readme=README.replace("## NuGetAuditSuppress", "## Something else"))
        self.assertEqual(rc, 1)
        self.assertIn("nugetauditsuppress", out)


if __name__ == "__main__":
    unittest.main()
