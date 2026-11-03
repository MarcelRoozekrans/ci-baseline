"""Helpers for the ci-baseline actions. Standard library only."""

import argparse
import glob
import json
import os
import re
import sys

LEVELS = {
    "low": ["NU1901", "NU1902", "NU1903", "NU1904"],
    "moderate": ["NU1902", "NU1903", "NU1904"],
    "high": ["NU1903", "NU1904"],
    "critical": ["NU1904"],
}


class BaselineError(Exception):
    pass


def resolve_solution(root, solution):
    if solution:
        if not os.path.isfile(solution):
            raise BaselineError("solution not found: " + solution)
        return solution
    found = sorted(
        glob.glob(os.path.join(root, "*.sln")) + glob.glob(os.path.join(root, "*.slnx"))
    )
    if len(found) == 1:
        return found[0]
    if not found:
        raise BaselineError("no .sln or .slnx found in " + root + "; set the solution input")
    names = ", ".join(os.path.basename(p) for p in found)
    raise BaselineError("more than one solution in " + root + " (" + names + "); set the solution input")


def failing_codes(level):
    key = (level or "").strip().lower()
    if key not in LEVELS:
        raise BaselineError(
            "invalid nuget-audit-level '" + str(level) + "'; valid levels: " + ", ".join(LEVELS)
        )
    return list(LEVELS[key])


def _tokens(value):
    return [t.strip().upper() for t in re.split(r"[;,]", value or "") if t.strip()]


def nowarn_violations(evaluations, codes):
    """One line per audit code that a project property or PackageReference mutes.

    Each evaluation is the JSON of `dotnet msbuild -getProperty:NoWarn
    -getProperty:WarningsNotAsErrors -getItem:PackageReference` plus the keys
    `project` and `tfm`.
    """
    wanted = [c.upper() for c in codes]
    lines = []
    for ev in evaluations:
        where = "%s [%s]" % (ev.get("project", "?"), ev.get("tfm", "?"))
        props = ev.get("Properties") or {}
        for prop in ("NoWarn", "WarningsNotAsErrors"):
            present = _tokens(props.get(prop))
            for code in wanted:
                if code in present:
                    lines.append("%s: %s contains %s" % (where, prop, code))
        refs = (ev.get("Items") or {}).get("PackageReference") or []
        for ref in refs:
            present = _tokens(ref.get("NoWarn"))
            for code in wanted:
                if code in present:
                    lines.append(
                        "%s: PackageReference %s NoWarn contains %s"
                        % (where, ref.get("Identity", "?"), code)
                    )
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(prog="baseline_lib")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("resolve-solution")
    p.add_argument("--root", default=".")
    p.add_argument("--solution", default="")
    p = sub.add_parser("failing-codes")
    p.add_argument("--level", required=True)
    p = sub.add_parser("nowarn-check")
    p.add_argument("--codes", required=True, help="semicolon separated codes")
    args = parser.parse_args(argv)
    try:
        if args.command == "resolve-solution":
            print(resolve_solution(args.root, args.solution))
        elif args.command == "failing-codes":
            print(";".join(failing_codes(args.level)))
        else:
            try:
                evaluations = json.load(sys.stdin)
            except ValueError as exc:
                raise BaselineError("nowarn-check needs a JSON array on stdin: " + str(exc))
            lines = nowarn_violations(evaluations, _tokens(args.codes))
            for line in lines:
                print(line)
            return 1 if lines else 0
    except BaselineError as exc:
        print("::error::" + str(exc))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
