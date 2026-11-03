import os
import sys
import io
import json
import tempfile
import unittest

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.normpath(os.path.join(REPO, "lib")))

import baseline_lib  # noqa: E402
from baseline_lib import BaselineError  # noqa: E402


def evaluation(no_warn="1701;1702", not_as_errors="", refs=None, project="src/App/App.csproj", tfm="net10.0"):
    """Mirror of `dotnet msbuild -getProperty -getItem` JSON plus project and tfm keys."""
    items = []
    for ref in refs or []:
        item = {
            "Identity": ref["Identity"],
            "Version": ref.get("Version", "1.0.0"),
            "FullPath": "/work/src/App/" + ref["Identity"],
            "DefiningProjectName": "App",
        }
        if "NoWarn" in ref:
            item["NoWarn"] = ref["NoWarn"]
        items.append(item)
    return {
        "Properties": {"NoWarn": no_warn, "WarningsNotAsErrors": not_as_errors},
        "Items": {"PackageReference": items},
        "project": project,
        "tfm": tfm,
    }


class ResolveSolutionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def touch(self, name):
        path = os.path.join(self.root, name)
        open(path, "w").close()
        return path

    def test_resolve_single_slnx(self):
        path = self.touch("App.slnx")
        self.assertEqual(baseline_lib.resolve_solution(self.root, ""), path)

    def test_resolve_two_solutions_raises(self):
        self.touch("A.sln")
        self.touch("B.slnx")
        with self.assertRaises(BaselineError) as ctx:
            baseline_lib.resolve_solution(self.root, "")
        self.assertIn("A.sln", str(ctx.exception))
        self.assertIn("B.slnx", str(ctx.exception))

    def test_resolve_none_raises(self):
        with self.assertRaises(BaselineError) as ctx:
            baseline_lib.resolve_solution(self.root, "")
        self.assertIn("no .sln or .slnx found in " + self.root, str(ctx.exception))

    def test_resolve_explicit_missing_raises(self):
        missing = os.path.join(self.root, "Nope.sln")
        with self.assertRaises(BaselineError) as ctx:
            baseline_lib.resolve_solution(self.root, missing)
        self.assertEqual(str(ctx.exception), "solution not found: " + missing)

    def test_resolve_explicit_ok(self):
        path = self.touch("Chosen.sln")
        self.touch("Other.sln")
        self.assertEqual(baseline_lib.resolve_solution(self.root, path), path)


class FailingCodesTest(unittest.TestCase):
    def test_failing_codes_moderate(self):
        self.assertEqual(baseline_lib.failing_codes("moderate"), ["NU1902", "NU1903", "NU1904"])

    def test_failing_codes_case_insensitive(self):
        self.assertEqual(baseline_lib.failing_codes("High"), ["NU1903", "NU1904"])

    def test_failing_codes_low(self):
        self.assertEqual(
            baseline_lib.failing_codes("low"), ["NU1901", "NU1902", "NU1903", "NU1904"]
        )

    def test_failing_codes_critical(self):
        self.assertEqual(baseline_lib.failing_codes("critical"), ["NU1904"])

    def test_failing_codes_invalid_raises(self):
        with self.assertRaises(BaselineError) as ctx:
            baseline_lib.failing_codes("medium")
        for level in ("low", "moderate", "high", "critical"):
            self.assertIn(level, str(ctx.exception))


class NowarnViolationsTest(unittest.TestCase):
    CODES = ["NU1902", "NU1903", "NU1904"]

    def test_nowarn_property_hit(self):
        ev = evaluation(no_warn=";NU1903", tfm="net9.0")
        self.assertEqual(
            baseline_lib.nowarn_violations([ev], self.CODES),
            ["src/App/App.csproj [net9.0]: NoWarn contains NU1903"],
        )

    def test_warnings_not_as_errors_hit(self):
        ev = evaluation(not_as_errors="NU1904")
        self.assertEqual(
            baseline_lib.nowarn_violations([ev], self.CODES),
            ["src/App/App.csproj [net10.0]: WarningsNotAsErrors contains NU1904"],
        )

    def test_package_reference_nowarn_hit(self):
        ev = evaluation(refs=[{"Identity": "Newtonsoft.Json", "NoWarn": "NU1903"}])
        self.assertEqual(
            baseline_lib.nowarn_violations([ev], self.CODES),
            ["src/App/App.csproj [net10.0]: PackageReference Newtonsoft.Json NoWarn contains NU1903"],
        )

    def test_nowarn_low_code_ignored_at_moderate(self):
        ev = evaluation(no_warn="NU1901")
        self.assertEqual(baseline_lib.nowarn_violations([ev], self.CODES), [])

    def test_nowarn_comma_and_spaces(self):
        ev = evaluation(no_warn="1701, nu1903 ,NU1904")
        self.assertEqual(
            baseline_lib.nowarn_violations([ev], self.CODES),
            [
                "src/App/App.csproj [net10.0]: NoWarn contains NU1903",
                "src/App/App.csproj [net10.0]: NoWarn contains NU1904",
            ],
        )

    def test_clean_evaluation_returns_empty(self):
        ev = evaluation(refs=[{"Identity": "Newtonsoft.Json", "Version": "13.0.3"}])
        self.assertEqual(baseline_lib.nowarn_violations([ev], self.CODES), [])

    def test_missing_keys_tolerated(self):
        self.assertEqual(
            baseline_lib.nowarn_violations([{"project": "p", "tfm": "t"}], self.CODES), []
        )


class CliExitCodeTest(unittest.TestCase):
    def run_check(self, stdin_text):
        old_in, old_out = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = io.StringIO(stdin_text), io.StringIO()
        try:
            code = baseline_lib.main(["nowarn-check", "--codes", "NU1903"])
            return code, sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = old_in, old_out

    def test_clean_exits_0(self):
        self.assertEqual(self.run_check(json.dumps([evaluation()]))[0], 0)

    def test_violation_exits_1(self):
        code, out = self.run_check(json.dumps([evaluation(no_warn="NU1903")]))
        self.assertEqual(code, 1)
        self.assertIn("NoWarn contains NU1903", out)
        self.assertNotIn("::error::", out)

    def test_bad_json_exits_2_with_single_error_prefix(self):
        code, out = self.run_check("not json")
        self.assertEqual(code, 2)
        self.assertEqual(out.count("::error::"), 1)

    def test_wrong_shape_json_exits_2(self):
        bad = evaluation()
        bad["Items"]["PackageReference"] = "Newtonsoft.Json"
        code, out = self.run_check(json.dumps([bad]))
        self.assertEqual(code, 2)
        self.assertEqual(out.count("::error::"), 1)
        self.assertIn("::error::nowarn-check failed: AttributeError", out)

    def test_non_list_top_level_exits_2(self):
        code, out = self.run_check("{}")
        self.assertEqual(code, 2)


class SplitLanguagesTest(unittest.TestCase):
    def test_split_languages_trims(self):
        self.assertEqual(baseline_lib.split_languages(" csharp , actions "), ["csharp", "actions"])

    def test_split_languages_dedup(self):
        self.assertEqual(
            baseline_lib.split_languages("csharp,actions,csharp,,actions"), ["csharp", "actions"]
        )

    def test_split_languages_empty_raises(self):
        for value in ("", " ", " , ,"):
            with self.assertRaises(BaselineError):
                baseline_lib.split_languages(value)

    def test_split_languages_cli_prints_compact_json(self):
        old_out = sys.stdout
        sys.stdout = io.StringIO()
        try:
            code = baseline_lib.main(["split-languages", "--languages", "csharp, actions"])
            out = sys.stdout.getvalue()
        finally:
            sys.stdout = old_out
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), '["csharp","actions"]')

    def test_split_languages_cli_empty_exits_2(self):
        old_out = sys.stdout
        sys.stdout = io.StringIO()
        try:
            code = baseline_lib.main(["split-languages", "--languages", " "])
            out = sys.stdout.getvalue()
        finally:
            sys.stdout = old_out
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith("::error::"))


if __name__ == "__main__":
    unittest.main()
