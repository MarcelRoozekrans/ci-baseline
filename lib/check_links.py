#!/usr/bin/env python3
"""Check the relative links in a repo's Markdown files. Run from the repo root, or pass the root.

Usage: check_links.py [root] [--exclude DIR]...

For every *.md file under the root, outside .git, node_modules and the excluded directories, each
inline link, image and reference definition is checked when its target is relative:
- the file or directory it points to exists, resolved from the linking file;
- a #fragment on a Markdown target, or a bare #fragment, is a heading anchor in that file.

Absolute URLs (any scheme such as https: or mailto:) and links that start with / are not
checked: they need the network or a site root. Links inside fenced code blocks and inline code
are ignored. Exit code 1 lists every broken link as a ::error:: annotation.
"""
import os
import re
import sys
from urllib.parse import unquote

ALWAYS_SKIPPED = {".git", "node_modules", ".ci-baseline"}
# [label]: target
REFERENCE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
SETEXT_UNDERLINE = re.compile(r"^\s{0,3}(=+|-+)\s*$")
INLINE_CODE = re.compile(r"(`+)(?:(?!\1).)+?\1")
HTML_ANCHOR = re.compile(r"<a\s+[^>]*(?:name|id)=[\"']([^\"']+)[\"']", re.IGNORECASE)


def slug(heading):
    """GitHub's heading anchor: markup dropped, lowercase, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    text = text.replace("`", "").strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def text_lines(content, keep_code_spans=False):
    """The lines outside fenced code blocks as (number, line) pairs, with inline code removed
    unless keep_code_spans is set."""
    fence = None
    for number, line in enumerate(content.splitlines(), start=1):
        match = FENCE.match(line)
        if fence is None and match:
            fence = match.group(1)[0] * len(match.group(1))
            continue
        if fence is not None:
            if line.strip().startswith(fence):
                fence = None
            continue
        yield number, line if keep_code_spans else INLINE_CODE.sub("", line)


def anchors(content):
    """Every heading anchor in a Markdown file, with GitHub's -1, -2 suffixes for repeats."""
    found = set()
    seen = {}
    paragraph = []  # consecutive text lines since the last blank line, for Setext headings
    last_number = None
    for number, line in text_lines(content, keep_code_spans=True):
        if last_number is not None and number != last_number + 1:
            paragraph = []  # a fenced block sat in between
        last_number = number
        for name in HTML_ANCHOR.findall(line):
            found.add(name.lower())
        heading = None
        match = HEADING.match(line)
        if match:
            heading = match.group(1)
            paragraph = []
        elif SETEXT_UNDERLINE.match(line):
            # An underline below a paragraph makes it a heading; without one it is a thematic break.
            if paragraph:
                heading = " ".join(text.strip() for text in paragraph)
            paragraph = []
        elif line.strip():
            paragraph.append(line)
        else:
            paragraph = []
        if heading is None:
            continue
        base = slug(heading)
        count = seen.get(base, 0)
        seen[base] = count + 1
        found.add(base if count == 0 else "%s-%d" % (base, count))
    return found


def _skip_title(line, start):
    """The index just past the ")" that closes a link, after an optional title at line[start].

    Only a complete title followed by ")" is skipped; otherwise scanning resumes at start, so later
    links on the line are still found.
    """
    i = start
    while i < len(line) and line[i] in " \t":
        i += 1
    if i < len(line) and line[i] in "\"'(":
        closing = ")" if line[i] == "(" else line[i]
        end = line.find(closing, i + 1)
        if end == -1:
            return start
        i = end + 1
        while i < len(line) and line[i] in " \t":
            i += 1
    return i + 1 if i < len(line) and line[i] == ")" else start


def destination(line, start):
    """The link destination that starts at line[start], just after "](", and the index after the
    link's closing ")", as (target or None, end).

    Handles <...> destinations, balanced parentheses such as docs/a(b).md, and an optional title,
    whose text is not scanned for links.
    """
    i = start
    while i < len(line) and line[i] in " \t":
        i += 1
    if i < len(line) and line[i] == "<":
        end = line.find(">", i + 1)
        if end == -1:
            return None, i + 1
        return line[i + 1 : end], _skip_title(line, end + 1)
    depth = 0
    j = i
    while j < len(line):
        char = line[j]
        if char == "\\" and j + 1 < len(line):
            j += 2
            continue
        if char.isspace():
            break
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                break
            depth -= 1
        j += 1
    return (line[i:j] if j > i else None), _skip_title(line, j)


def targets(content):
    """Every link target in a Markdown file, as (line number, target) pairs.

    Each "](" that follows a "[" starts a destination, so an image inside a link yields both.
    """
    for number, line in text_lines(content):
        position = line.find("](")
        while position != -1:
            end = position + 2
            if "[" in line[:position]:
                target, end = destination(line, position + 2)
                if target:
                    yield number, target
            position = line.find("](", max(end, position + 2))
        match = REFERENCE.match(line)
        if match:
            yield number, match.group(1)


def _raise(error):
    raise error


def markdown_files(root, excluded):
    if not os.path.isdir(root):
        raise NotADirectoryError("%s is not a directory" % root)
    skipped = {os.path.normpath(os.path.join(root, path)) for path in excluded}
    for directory, subdirs, files in os.walk(root, onerror=_raise):
        subdirs[:] = sorted(
            name
            for name in subdirs
            if name not in ALWAYS_SKIPPED and os.path.normpath(os.path.join(directory, name)) not in skipped
        )
        for name in sorted(files):
            if name.lower().endswith(".md"):
                yield os.path.join(directory, name)


def problems(root, excluded=()):
    bad = []
    cache = {}

    def anchors_of(path):
        if path not in cache:
            with open(path, encoding="utf-8") as handle:
                cache[path] = anchors(handle.read())
        return cache[path]

    for path in markdown_files(root, excluded):
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
        where = os.path.relpath(path, root)
        for number, target in targets(content):
            target = target.strip("<>").strip()
            if not target or SCHEME.match(target) or target.startswith("/"):
                continue
            target = re.sub(r"\\([^\w\s])", r"\1", target)  # backslash escapes such as \(
            link, _, fragment = target.partition("#")
            link = unquote(link.split("?", 1)[0])
            fragment = unquote(fragment).lower()
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), link)) if link else path
            if not os.path.exists(resolved):
                bad.append("%s:%d: %s does not exist" % (where, number, link))
                continue
            if fragment and os.path.isfile(resolved) and resolved.lower().endswith(".md"):
                if fragment not in anchors_of(resolved):
                    bad.append("%s:%d: #%s is not a heading in %s" % (where, number, fragment, os.path.relpath(resolved, root)))
    return bad


def main(argv):
    root = "."
    excluded = []
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == "--exclude":
            if not args:
                print("::error::--exclude needs a directory")
                return 2
            excluded.append(args.pop(0))
        else:
            root = arg
    try:
        bad = problems(root, excluded)
    except (OSError, UnicodeDecodeError) as exc:
        print("::error::%s" % exc)
        return 1
    for line in bad:
        print("::error::" + line)
    if bad:
        print("%d broken relative link%s" % (len(bad), "" if len(bad) == 1 else "s"))
        return 1
    print("Every relative link in the Markdown files resolves")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
