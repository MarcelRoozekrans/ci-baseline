#!/usr/bin/env node
// Parse every commit in a range with the parser release-please uses, @conventional-commits/parser.
// release-please drops a commit it cannot parse from the changelog while its workflow succeeds, so a
// parse error here is the only warning. A body line that starts with a word followed by "(" is read
// as a type and scope, and a nested "(" inside it throws; a fenced code block does not protect it.
//
// Usage: node check_release_parse.mjs --from SHA --to SHA [--repo DIR]
// Exit code 1 lists every commit that does not parse; 2 means git could not read the range.
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(join(dirname(fileURLToPath(import.meta.url)), 'commitlint', 'package.json'));
const { parser } = require('@conventional-commits/parser');

/** The first line of the parser's error for a message, or null when it parses. */
export function parseError(message) {
  try {
    parser(message);
    return null;
  } catch (error) {
    return String(error.message).split('\n')[0];
  }
}

/** [sha, message] for every commit in from..to, oldest first. */
export function commits(repo, from, to) {
  const out = execFileSync('git', ['-C', repo, 'log', '--reverse', '--format=%H%x00%B%x01', `${from}..${to}`], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  return out
    .split('\x01')
    .map((chunk) => chunk.replace(/^\n+/, ''))
    .filter((chunk) => chunk.length > 0)
    .map((chunk) => {
      const at = chunk.indexOf('\x00');
      return [chunk.slice(0, at), chunk.slice(at + 1)];
    });
}

export function main(argv, log = console.log) {
  const args = { '--repo': '.' };
  for (let i = 0; i < argv.length; i += 2) {
    if (!['--from', '--to', '--repo'].includes(argv[i]) || i + 1 >= argv.length) {
      log('::error::usage: check_release_parse.mjs --from SHA --to SHA [--repo DIR]');
      return 2;
    }
    args[argv[i]] = argv[i + 1];
  }
  if (!args['--from'] || !args['--to']) {
    log('::error::--from and --to are required');
    return 2;
  }
  let found;
  try {
    found = commits(args['--repo'], args['--from'], args['--to']);
  } catch (error) {
    log(`::error::git could not read ${args['--from']}..${args['--to']}: ${String(error.stderr ?? error.message).trim()}`);
    return 2;
  }
  let bad = 0;
  for (const [sha, message] of found) {
    const error = parseError(message);
    if (error !== null) {
      bad += 1;
      log(`::error::${sha.slice(0, 7)}: release-please cannot parse this commit and would drop it from the changelog: ${error}`);
    }
  }
  if (bad > 0) return 1;
  log(`release parse: ${found.length} commit${found.length === 1 ? '' : 's'} parse`);
  return 0;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  process.exit(main(process.argv.slice(2)));
}
