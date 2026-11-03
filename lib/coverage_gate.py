"""Helpers for the coverage-gate action. Standard library only; PyYAML is imported where a codecov file is read."""

import json
import math
import os
import sys

MIN_FLOOR = 80.0
CONFIG_NAMES = [
    "codecov.yml",
    ".codecov.yml",
    ".github/codecov.yml",
    ".github/.codecov.yml",
    "dev/codecov.yml",
    "dev/.codecov.yml",
]


class GateError(Exception):
    pass


def _fmt(value):
    return "%g" % value


def validate_floor(floor, reason):
    try:
        value = float(str(floor).strip())
    except ValueError:
        raise GateError("floor '%s' is not a number" % floor)
    if math.isnan(value) or value < 0 or value > 100:
        raise GateError("floor '%s' must be between 0 and 100" % floor)
    if value < MIN_FLOOR and not (reason or "").strip():
        raise GateError("floor %s is below 80; set floor-override-reason" % value)
    return value


def find_codecov_config(root):
    for name in CONFIG_NAMES:
        path = os.path.join(root, name)
        if os.path.isfile(path):
            return path
    raise GateError("no codecov.yml found")


def _percent(value):
    """A threshold as a number: 1, 1.5, "1%" and "1.5" all parse. None when unparseable."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().rstrip("%").strip())
        except ValueError:
            return None
    return None


def codecov_policy_errors(cfg, max_drop):
    """Why a parsed codecov.yml does not enforce the project coverage status."""
    where = "coverage.status.project.default"
    if not isinstance(cfg, dict):
        return [where + " is missing: the codecov file is empty"]
    node = cfg
    for key in ("coverage", "status", "project"):
        node = node.get(key) if isinstance(node, dict) else None
    # PyYAML parses a bare `off` as False; the string "off" is accepted too.
    if node is None or node is False or (isinstance(node, str) and node.strip().lower() == "off"):
        return [where + " is missing or off: project status must be enabled"]
    default = node.get("default") if isinstance(node, dict) else None
    if default is None or default is False or (isinstance(default, str) and default.strip().lower() == "off"):
        return [where + " is missing or off: project status must be enabled"]
    if not isinstance(default, dict):
        return [where + " must be a mapping with target and threshold"]
    errors = []
    if default.get("informational") is True:
        errors.append(where + ".informational is true: the status can never fail")
    if "target" in default and str(default["target"]).strip().lower() != "auto":
        errors.append(
            where + ".target is '%s': use 'auto' so the status compares with the base commit" % default["target"]
        )
    if "threshold" not in default:
        errors.append(where + ".threshold is missing: set it to at most %s%%" % _fmt(max_drop))
    else:
        drop = _percent(default["threshold"])
        if drop is None:
            errors.append(where + ".threshold '%s' is not a percentage" % default["threshold"])
        elif drop > max_drop:
            errors.append(
                where + ".threshold %s%% allows a larger drop than max-drop %s%%" % (_fmt(drop), _fmt(max_drop))
            )
    return errors


def line_coverage(summary):
    try:
        return float(summary["summary"]["linecoverage"])
    except (KeyError, TypeError, ValueError):
        raise GateError("coverage summary has no summary.linecoverage value")


def _summary(*lines):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a") as handle:
        for line in lines:
            handle.write(line + "\n")


def _load_config(path):
    import yaml

    try:
        with open(path) as handle:
            return yaml.safe_load(handle)
    except (OSError, yaml.YAMLError) as exc:
        raise GateError("cannot read %s: %s" % (path, exc))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    usage = "usage: coverage_gate.py validate-floor <floor> <reason> | check-codecov <root> <max-drop> | check-floor <summary.json> <floor>"
    try:
        if not argv:
            raise GateError(usage)
        command, args = argv[0], argv[1:]
        if command == "validate-floor" and len(args) == 2:
            value = validate_floor(args[0], args[1])
            if value < MIN_FLOOR:
                _summary("Coverage floor lowered to %s%%. Reason: %s" % (_fmt(value), args[1].strip()))
        elif command == "check-codecov" and len(args) == 2:
            try:
                max_drop = float(args[1])
            except ValueError:
                raise GateError("max-drop '%s' is not a number" % args[1])
            path = find_codecov_config(args[0])
            errors = codecov_policy_errors(_load_config(path), max_drop)
            if errors:
                _summary("### Coverage gate: codecov policy", *["- " + e for e in errors])
                raise GateError("; ".join("%s: %s" % (path, e) for e in errors))
            _summary("codecov policy: %s enforces project status" % path)
        elif command == "check-floor" and len(args) == 2:
            floor = float(args[1])
            try:
                with open(args[0]) as handle:
                    value = line_coverage(json.load(handle))
            except (OSError, ValueError) as exc:
                raise GateError("cannot read coverage summary %s: %s" % (args[0], exc))
            _summary("Line coverage: %s%% (floor %s%%)" % (_fmt(round(value, 2)), _fmt(floor)))
            if value < floor:
                raise GateError("line coverage %s%% is below the floor of %s%%" % (_fmt(round(value, 2)), _fmt(floor)))
        else:
            raise GateError(usage)
    except GateError as exc:
        print("::error::" + str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
