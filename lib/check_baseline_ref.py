#!/usr/bin/env python3
"""Fail unless the baseline-ref default of each reusable workflow is v<major>.

<major> comes from .release-please-manifest.json key ".", or, while that key is
absent, from initial-version in release-please-config.json. Run from the repo root,
or pass the root as the only argument.
"""
import json
import os
import sys

import yaml

WORKFLOWS = (".github/workflows/baseline.yml", ".github/workflows/history-scan.yml")


class RefError(Exception):
    pass


def expected_ref(manifest, config):
    version = manifest.get(".")
    if not version:
        version = config.get("initial-version") or (config.get("packages", {}).get(".", {}).get("initial-version"))
    if not version:
        raise RefError("no version in the manifest key \".\" and no initial-version in the config")
    return "v" + str(version).split(".")[0]


def workflow_default(path):
    with open(path) as handle:
        doc = yaml.safe_load(handle)
    # PyYAML (YAML 1.1) reads the top-level key `on` as the boolean True.
    triggers = doc.get("on", doc.get(True)) or {}
    try:
        return triggers["workflow_call"]["inputs"]["baseline-ref"]["default"]
    except (KeyError, TypeError):
        raise RefError("%s: no on.workflow_call.inputs.baseline-ref.default" % path)


def _load_json(path):
    try:
        with open(path) as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        raise RefError("cannot read %s: %s" % (path, exc))


def main(argv):
    root = argv[0] if argv else "."
    try:
        expected = expected_ref(
            _load_json(os.path.join(root, ".release-please-manifest.json")),
            _load_json(os.path.join(root, "release-please-config.json")),
        )
        bad = []
        for rel in WORKFLOWS:
            actual = workflow_default(os.path.join(root, rel))
            if actual != expected:
                bad.append("%s: baseline-ref default is %r, expected %r" % (rel, actual, expected))
    except (RefError, OSError, yaml.YAMLError) as exc:
        print("::error::%s" % exc)
        return 1
    for line in bad:
        print("::error::" + line)
    if bad:
        return 1
    print("baseline-ref default is %s in %d workflows" % (expected, len(WORKFLOWS)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
