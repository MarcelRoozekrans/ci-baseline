#!/usr/bin/env python3
"""Check commit messages, and optionally a pull request body, for text that does not belong in history.

Usage: check_commit_hygiene.py --from SHA --to SHA [--pr-body FILE] [--repo DIR]

Every commit in from..to is checked for:
- an AI co-author trailer, such as `Co-Authored-By: Claude <noreply@anthropic.com>`;
- an AI session link, such as https://claude.ai/code/session_...;
- an AI "Generated with" signature line;
- a nested parenthesis in the body, outside fenced code blocks. release-please cannot parse a
  commit with one and drops it from the changelog while its workflow still succeeds.

The pull request body is checked for session links only: a squash merge copies commit bodies,
not the pull request body, into history, and some tools append their own footer to the body.

Exit code 1 lists every problem as a ::error:: annotation; 2 means git could not read the range.
"""
import re
import subprocess
import sys

CO_AUTHOR = re.compile(
    r"^\s*co-authored-by:.*(claude|anthropic\.com|copilot|openai|chatgpt|codex|gemini|cursor)",
    re.IGNORECASE,
)
SESSION_LINK = re.compile(r"https?://(?:www\.)?claude\.ai/code/session_\S*", re.IGNORECASE)
SIGNATURE = re.compile(r"generated (?:with|by) \[?(?:claude code|copilot|codex|cursor)\]?", re.IGNORECASE)
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


def nested_parenthesis(body):
    """The 1-based line number of the first nested '(' in a commit body, outside fences, or None."""
    depth = 0
    fence = None
    for number, line in enumerate(body.splitlines(), start=1):
        match = FENCE.match(line)
        if fence is None and match:
            fence = match.group(1)[0] * len(match.group(1))
            continue
        if fence is not None:
            if line.strip().startswith(fence):
                fence = None
            continue
        for char in line:
            if char == "(":
                if depth >= 1:
                    return number
                depth += 1
            elif char == ")" and depth > 0:
                depth -= 1
    return None


def message_problems(sha, message):
    """Problems in one commit message, each naming the short sha and the line."""
    short = sha[:7]
    bad = []
    lines = message.splitlines()
    for number, line in enumerate(lines, start=1):
        if CO_AUTHOR.search(line):
            bad.append("%s line %d: AI co-author trailer: %s" % (short, number, line.strip()))
        if SESSION_LINK.search(line):
            bad.append("%s line %d: AI session link" % (short, number))
        if SIGNATURE.search(line):
            bad.append("%s line %d: AI signature line: %s" % (short, number, line.strip()))
    body = "\n".join(lines[2:]) if len(lines) > 2 else ""
    nested = nested_parenthesis(body)
    if nested is not None:
        bad.append(
            "%s line %d: nested parenthesis in the body; release-please would drop this commit"
            % (short, nested + 2)
        )
    return bad


def body_problems(body):
    """Problems in a pull request body."""
    return [
        "pull request body line %d: AI session link" % number
        for number, line in enumerate(body.splitlines(), start=1)
        if SESSION_LINK.search(line)
    ]


def commits(repo, start, end):
    """(sha, message) for every commit in start..end, oldest first."""
    out = subprocess.run(
        ["git", "-C", repo, "log", "--reverse", "--format=%H%x00%B%x01", "%s..%s" % (start, end)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    result = []
    for chunk in out.split("\x01"):
        chunk = chunk.lstrip("\n")
        if not chunk:
            continue
        sha, _, message = chunk.partition("\x00")
        result.append((sha, message))
    return result


def main(argv):
    args = {"--repo": "."}
    rest = list(argv)
    while rest:
        key = rest.pop(0)
        if key not in ("--from", "--to", "--pr-body", "--repo") or not rest:
            print("::error::usage: check_commit_hygiene.py --from SHA --to SHA [--pr-body FILE] [--repo DIR]")
            return 2
        args[key] = rest.pop(0)
    if "--from" not in args or "--to" not in args:
        print("::error::--from and --to are required")
        return 2
    try:
        found = commits(args["--repo"], args["--from"], args["--to"])
    except subprocess.CalledProcessError as exc:
        print("::error::git could not read %s..%s: %s" % (args["--from"], args["--to"], exc.stderr.strip()))
        return 2
    bad = []
    for sha, message in found:
        bad.extend(message_problems(sha, message))
    if "--pr-body" in args:
        with open(args["--pr-body"], encoding="utf-8") as handle:
            bad.extend(body_problems(handle.read()))
    for line in bad:
        print("::error::" + line)
    if bad:
        return 1
    print("commit hygiene: %d commit%s clean" % (len(found), "" if len(found) == 1 else "s"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
