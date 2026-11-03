#!/usr/bin/env python3
"""Keep README.md in step with the code it documents. Run from the repo root, or pass the root.

Checks:
- each inputs table lists exactly the `inputs:` keys of its workflow or action;
- the fenced codecov.yml block equals fixtures/dotnet-clean/codecov.yml, byte for byte;
- every ci-baseline#anchor that a workflow or action links to is a heading in the README,
  and the anchors in REQUIRED_ANCHORS exist.
"""
import glob
import os
import re
import sys

import yaml

# README heading -> file whose inputs the table under that heading documents.
TABLES = {
    "baseline.yml inputs": ".github/workflows/baseline.yml",
    "history-scan.yml inputs": ".github/workflows/history-scan.yml",
    "coverage-gate inputs": "actions/coverage-gate/action.yml",
    "sbom inputs": "actions/sbom/action.yml",
}
CODECOV_FIXTURE = "fixtures/dotnet-clean/codecov.yml"
# nuget-audit's guard message names the NuGetAuditSuppress section; baseline.yml links to the other.
REQUIRED_ANCHORS = ("nugetauditsuppress", "codeql-upload-refused")
ANCHOR_REF = re.compile(r"ci-baseline#([A-Za-z0-9_-]+)")


class ReadmeError(Exception):
    pass


def slug(heading):
    """GitHub's heading anchor: lowercase, punctuation dropped, spaces to hyphens."""
    text = heading.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def headings(readme):
    found = []
    fenced = False
    for line in readme.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced:
            match = re.match(r"#{1,6}\s+(.*?)\s*#*\s*$", line)
            if match:
                found.append(match.group(1))
    return found


def table_inputs(readme, heading):
    """Names in the first cell of the table rows under `heading`, up to the next heading."""
    lines = readme.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if re.match(r"#{1,6}\s+" + re.escape(heading) + r"\s*$", line))
    except StopIteration:
        raise ReadmeError("README has no heading %r" % heading)
    names = set()
    for line in lines[start + 1:]:
        if line.startswith("#"):
            break
        match = re.match(r"\|\s*`([^`]+)`\s*\|", line)
        if match:
            names.add(match.group(1))
    if not names:
        raise ReadmeError("README has no inputs table under %r" % heading)
    return names


def yaml_inputs(path):
    with open(path) as handle:
        doc = yaml.safe_load(handle)
    # PyYAML (YAML 1.1) reads the top-level key `on` as the boolean True.
    triggers = doc.get("on", doc.get(True))
    node = triggers["workflow_call"] if isinstance(triggers, dict) and "workflow_call" in triggers else doc
    return set((node.get("inputs") or {}).keys())


def codecov_block(readme):
    """Content of the first fenced block that starts with `coverage:`."""
    for match in re.finditer(r"^```[a-z]*\n(.*?)^```$", readme, re.S | re.M):
        if match.group(1).startswith("coverage:"):
            return match.group(1)
    raise ReadmeError("README has no fenced codecov.yml block")


def referenced_anchors(root):
    paths = glob.glob(os.path.join(root, ".github", "workflows", "*.yml"))
    paths += glob.glob(os.path.join(root, "actions", "*", "action.yml"))
    refs = {}
    for path in sorted(paths):
        with open(path) as handle:
            for anchor in ANCHOR_REF.findall(handle.read()):
                refs.setdefault(anchor, os.path.relpath(path, root))
    return refs


def problems(root):
    with open(os.path.join(root, "README.md")) as handle:
        readme = handle.read()
    bad = []
    for heading, rel in TABLES.items():
        try:
            documented = table_inputs(readme, heading)
        except ReadmeError as exc:
            bad.append(str(exc))
            continue
        actual = yaml_inputs(os.path.join(root, rel))
        for name in sorted(actual - documented):
            bad.append("%s: input %r is missing from the README table %r" % (rel, name, heading))
        for name in sorted(documented - actual):
            bad.append("README table %r lists %r, which is not an input of %s" % (heading, name, rel))
    try:
        with open(os.path.join(root, CODECOV_FIXTURE)) as handle:
            fixture = handle.read()
        if codecov_block(readme) != fixture:
            bad.append("README codecov.yml block differs from %s" % CODECOV_FIXTURE)
    except ReadmeError as exc:
        bad.append(str(exc))
    anchors = {slug(h) for h in headings(readme)}
    for anchor in REQUIRED_ANCHORS:
        if anchor not in anchors:
            bad.append("README has no heading with the anchor #%s" % anchor)
    for anchor, where in referenced_anchors(root).items():
        if anchor not in anchors:
            bad.append("%s links to #%s, which is not a README heading" % (where, anchor))
    return bad


def main(argv):
    root = argv[0] if argv else "."
    try:
        bad = problems(root)
    except (OSError, yaml.YAMLError) as exc:
        print("::error::%s" % exc)
        return 1
    for line in bad:
        print("::error::" + line)
    if bad:
        return 1
    print("README matches the inputs, the codecov fixture and the linked anchors")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
