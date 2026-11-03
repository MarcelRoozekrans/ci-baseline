# ci-baseline state

**Updated:** 2026-11-03
**Branch:** `feat/v1`, draft PR #1 to `main`.

## Position

v1 is implemented on `feat/v1`: all 11 plan tasks of `docs/superpowers/plans/2026-11-03-ci-baseline-v1.md` and the fixes from the final review are in, and the self-test runs on the draft PR. The release steps wait on the owner: granting the release bot App write access to workflows on its installation, merging the PR, the first release-please release as `v1.0.0`, and the `renovate-config` change.

## Commit rules

Conventional commits. No Co-Authored-By trailer and no session link. No nested parentheses in commit bodies, because release-please drops such commits.
