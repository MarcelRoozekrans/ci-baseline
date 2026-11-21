import contextlib
import io
import os
import sys
import tempfile
import unittest

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.normpath(os.path.join(REPO, "lib")))

import check_links  # noqa: E402


def write(root, rel, content):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


class SlugTest(unittest.TestCase):
    def test_github_rules(self):
        self.assertEqual(check_links.slug("Moving `v1` by hand"), "moving-v1-by-hand")
        self.assertEqual(check_links.slug("1. Add the baseline job"), "1-add-the-baseline-job")
        self.assertEqual(check_links.slug("ADR-248: Publish a policy"), "adr-248-publish-a-policy")
        self.assertEqual(check_links.slug("See [the docs](x.md)"), "see-the-docs")

    def test_repeated_headings_get_suffixes(self):
        found = check_links.anchors("# Usage\n\n## Usage\n\n### Usage\n")
        self.assertEqual(found, {"usage", "usage-1", "usage-2"})

    def test_headings_in_fences_do_not_count(self):
        self.assertEqual(check_links.anchors("```\n# not a heading\n```\n# Real\n"), {"real"})

    def test_html_anchors_count(self):
        self.assertIn("custom", check_links.anchors('<a name="custom"></a>\n'))


class ProblemsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_clean_repo(self):
        write(self.root, "README.md", "# Top\n\n[doc](docs/a.md#part-one) [dir](docs/) [self](#top)\n")
        write(self.root, "docs/a.md", "## Part one\n\n[back](../README.md) ![img](img.png)\n")
        write(self.root, "docs/img.png", "")
        self.assertEqual(check_links.problems(self.root), [])

    def test_missing_file(self):
        write(self.root, "README.md", "x\n\n[gone](docs/gone.md)\n")
        self.assertEqual(check_links.problems(self.root), ["README.md:3: docs/gone.md does not exist"])

    def test_missing_anchor(self):
        write(self.root, "README.md", "[a](a.md#nope)\n")
        write(self.root, "a.md", "# Yes\n")
        self.assertEqual(check_links.problems(self.root), ["README.md:1: #nope is not a heading in a.md"])

    def test_missing_anchor_in_same_file(self):
        write(self.root, "README.md", "# Top\n\n[x](#bottom)\n")
        self.assertEqual(check_links.problems(self.root), ["README.md:3: #bottom is not a heading in README.md"])

    def test_reference_definitions_are_checked(self):
        write(self.root, "README.md", "[x][ref]\n\n[ref]: missing.md\n")
        self.assertEqual(check_links.problems(self.root), ["README.md:3: missing.md does not exist"])

    def test_absolute_and_rooted_links_are_skipped(self):
        write(
            self.root,
            "README.md",
            "[a](https://example.org/x.md) [b](mailto:a@b.c) [c](/abs/path.md) [d](http://x)\n",
        )
        self.assertEqual(check_links.problems(self.root), [])

    def test_code_is_ignored(self):
        write(self.root, "README.md", "`[a](gone.md)`\n\n```md\n[b](gone.md)\n```\n\n~~~\n[c](gone.md)\n~~~\n")
        self.assertEqual(check_links.problems(self.root), [])

    def test_titles_angle_brackets_and_escapes(self):
        write(self.root, "my file.md", "# T\n")
        write(self.root, "README.md", '[a](<my file.md> "title") [b](my%20file.md#t)\n')
        self.assertEqual(check_links.problems(self.root), [])

    def test_excluded_and_always_skipped_directories(self):
        write(self.root, "fixtures/broken/README.md", "[x](gone.md)\n")
        write(self.root, "node_modules/p/README.md", "[x](gone.md)\n")
        write(self.root, ".ci-baseline/README.md", "[x](gone.md)\n")
        self.assertEqual(check_links.problems(self.root, ["fixtures/broken"]), [])
        self.assertEqual(len(check_links.problems(self.root)), 1)

    def test_fragment_on_non_markdown_target_is_not_checked(self):
        write(self.root, "a.yml", "x: 1\n")
        write(self.root, "README.md", "[x](a.yml#L1)\n")
        self.assertEqual(check_links.problems(self.root), [])

    def test_balanced_and_escaped_parentheses(self):
        write(self.root, "docs/a(b).md", "# T\n")
        write(self.root, "README.md", "[x](docs/a(b).md) [y](docs/a\\(b\\).md#t)\n")
        self.assertEqual(check_links.problems(self.root), [])

    def test_image_inside_a_link_is_checked(self):
        write(self.root, "README.md", "[![badge](missing.png)](README.md)\n")
        self.assertEqual(check_links.problems(self.root), ["README.md:1: missing.png does not exist"])

    def test_code_span_text_counts_in_heading_anchors(self):
        write(self.root, "README.md", "# Using `foo`\n\n[x](#using-foo)\n")
        self.assertEqual(check_links.problems(self.root), [])

    def test_setext_headings(self):
        write(self.root, "README.md", "Usage\n=====\n\nMore\n---\n\n[a](#usage) [b](#more)\n")
        self.assertEqual(check_links.problems(self.root), [])

    def test_multi_line_setext_heading(self):
        self.assertEqual(check_links.anchors("First\nSecond\n---\n"), {"first-second"})

    def test_links_in_titles_are_not_checked(self):
        write(self.root, "README.md", "[doc](README.md \"example [x](missing.md)\") [d2](<README.md> 'a [y](gone.md)')\n")
        self.assertEqual(check_links.problems(self.root), [])

    def test_links_after_an_unfinished_title_are_checked(self):
        write(self.root, "README.md", '[doc](README.md "unfinished [broken](missing.md)\n')
        self.assertEqual(check_links.problems(self.root), ["README.md:1: missing.md does not exist"])

    def test_thematic_break_before_a_setext_heading(self):
        self.assertEqual(check_links.anchors("---\nTitle\n---\n"), {"title"})

    def test_thematic_break_after_blank_line_is_not_a_heading(self):
        self.assertEqual(check_links.anchors("Text\n\n---\n"), set())

    def test_root_must_be_a_directory(self):
        with self.assertRaises(NotADirectoryError):
            check_links.problems(os.path.join(self.root, "missing"))
        self.assertEqual(check_links.problems(self.root), [])


class MainTest(unittest.TestCase):
    def run_main(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = check_links.main(argv)
        return code, out.getvalue()

    def test_exit_codes_and_annotations(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/README.md", "[x](gone.md)\n")
            code, out = self.run_main([root])
            self.assertEqual(code, 1)
            self.assertIn("::error::docs/README.md:1: gone.md does not exist", out)
            code, out = self.run_main([root, "--exclude", "docs"])
            self.assertEqual(code, 0)

    def test_missing_root_fails(self):
        code, out = self.run_main([os.path.join(tempfile.gettempdir(), "no-such-dir-for-check-links")])
        self.assertEqual(code, 1)
        self.assertIn("is not a directory", out)

    def test_exclude_needs_a_value(self):
        code, out = self.run_main(["--exclude"])
        self.assertEqual(code, 2)
        self.assertIn("--exclude needs a directory", out)


if __name__ == "__main__":
    unittest.main()
