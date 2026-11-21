import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { main, parseError } from '../lib/check_release_parse.mjs';

test('a body line that starts with a word and nests a parenthesis does not parse', () => {
  assert.match(parseError('fix: x\n\nTypeof(Foo(1)) is used.\n'), /unexpected token/);
  assert.match(parseError('fix: x\n\n[Singleton(As = typeof(IDetector))]\n'), /unexpected token/);
});

test('a fenced code block does not protect a nested parenthesis', () => {
  assert.match(parseError('fix: x\n\n```\nfoo(bar(1))\n```\n'), /unexpected token/);
});

test('nested parentheses later in a line, and single levels, parse', () => {
  assert.equal(parseError('fix: x\n\nCall foo(bar(1)) now.\n'), null);
  assert.equal(parseError('fix(core): x\n\nA note (one level) here.\n'), null);
});

test('main checks a git range', () => {
  const repo = mkdtempSync(join(tmpdir(), 'release-parse-'));
  try {
    const git = (...args) =>
      execFileSync('git', ['-C', repo, '-c', 'user.name=t', '-c', 'user.email=t@example.com', ...args], { encoding: 'utf8' }).trim();
    git('init', '-q');
    git('commit', '-q', '--allow-empty', '-m', 'chore: base');
    const base = git('rev-parse', 'HEAD');
    git('commit', '-q', '--allow-empty', '-m', 'feat: good', '-m', 'Call foo(bar(1)) now.');
    const good = git('rev-parse', 'HEAD');
    git('commit', '-q', '--allow-empty', '-m', 'fix: bad', '-m', 'Foo(Bar(1)) breaks it.');
    const bad = git('rev-parse', 'HEAD');
    const lines = [];
    assert.equal(main(['--repo', repo, '--from', base, '--to', good], (l) => lines.push(l)), 0);
    assert.equal(main(['--repo', repo, '--from', base, '--to', bad], (l) => lines.push(l)), 1);
    assert.ok(lines.some((l) => l.startsWith(`::error::${bad.slice(0, 7)}: release-please cannot parse`)));
    assert.equal(main(['--repo', repo, '--from', '0'.repeat(40), '--to', bad], () => {}), 2);
    assert.equal(main(['--from'], () => {}), 2);
  } finally {
    rmSync(repo, { recursive: true, force: true });
  }
});
