# ci-baseline state

**Updated:** 2026-11-16
**Branch:** `main`.

## Position

v1.0.0 is released. `v1` and `v1.0.0` pointed at the same release commit after the release PR merged, and `move-major-tag` moves `v1` on later releases.

## Next steps

1. In `architecture-governance-engine`, update `docs/planning/STATE.md`: Phase 1.4 is unblocked.

Open follow-ups: #2, Renovate for the pinned binaries, which needs a decision on the approach; #3, removing the actionlint ignore once actionlint ships `job.workflow_*` support.

## Commit rules

Conventional commits. No Co-Authored-By trailer and no session link. No nested parentheses in commit bodies, because release-please drops such commits.
