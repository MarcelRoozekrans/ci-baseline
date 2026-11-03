#!/usr/bin/env python3
"""Keep README.md in step with the code it documents. Run from the repo root, or pass the root.

Checks:
- each inputs table lists exactly the `inputs:` keys of its workflow or action, with the same defaults
  (`true`, `empty` for an empty string or none, `required`, or the value);
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


def table_defaults(readme, heading):
    """Map of input name to the Default cell, without backticks, for the table under `heading`."""
    lines = readme.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if re.match(r"#{1,6}\s+" + re.escape(heading) + r"\s*$", line))
    except StopIteration:
        raise ReadmeError("README has no heading %r" % heading)
    rows = {}
    for line in lines[start + 1:]:
        if line.startswith("#"):
            break
        match = re.match(r"\|\s*`([^`]+)`\s*\|\s*([^|]*?)\s*\|", line)
        if match:
            rows[match.group(1)] = match.group(2).strip("`")
    if not rows:
        raise ReadmeError("README has no inputs table under %r" % heading)
    return rows


def table_inputs(readme, heading):
    """Names in the first cell of the table rows under `heading`, up to the next heading."""
    return set(table_defaults(readme, heading))


def _inputs_node(path):
    with open(path) as handle:
        doc = yaml.safe_load(handle)
    # PyYAML (YAML 1.1) reads the top-level key `on` as the boolean True.
    triggers = doc.get("on", doc.get(True))
    node = triggers["workflow_call"] if isinstance(triggers, dict) and "workflow_call" in triggers else doc
    return node.get("inputs") or {}


def yaml_inputs(path):
    return set(_inputs_node(path))


def yaml_defaults(path):
    """Map of input name to its default as the README spells it: true, empty, required or the value."""
    out = {}
    for name, spec in _inputs_node(path).items():
        spec = spec or {}
        if "default" not in spec:
            out[name] = "required" if spec.get("required") else "empty"
        elif spec["default"] is True or spec["default"] is False:
            out[name] = "true" if spec["default"] else "false"
        elif spec["default"] in ("", None):
            out[name] = "empty"
        else:
            out[name] = str(spec["default"])
    return out


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
            documented_defaults = table_defaults(readme, heading)
            documented = set(documented_defaults)
        except ReadmeError as exc:
            bad.append(str(exc))
            continue
        actual_defaults = yaml_defaults(os.path.join(root, rel))
        actual = set(actual_defaults)
        for name in sorted(actual - documented):
            bad.append("%s: input %r is missing from the README table %r" % (rel, name, heading))
        for name in sorted(documented - actual):
            bad.append("README table %r lists %r, which is not an input of %s" % (heading, name, rel))
        for name in sorted(actual & documented):
            if documented_defaults[name] != actual_defaults[name]:
                bad.append(
                    "%s: input %r has default %r, but README table %r says %r"
                    % (rel, name, actual_defaults[name], heading, documented_defaults[name])
                )
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
