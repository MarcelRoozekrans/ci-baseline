# ci-baseline state

**Updated:** 2026-11-03
**Branch:** `feat/v1`, draft PR #1 to `main`.

## Position

v1 is implemented on `feat/v1`. Tasks 1 to 10 of `docs/superpowers/plans/2026-11-03-ci-baseline-v1.md` are done, and so are the fixes from the final whole-branch review. Self-test is green on draft PR #1, all 20 checks. Task 11, the release, waits on the owner.

## Next steps, in order

1. Owner: install the release bot App on this repo with Contents, Pull requests and Workflows write. Set `RELEASE_BOT_CLIENT_ID` and `RELEASE_BOT_PRIVATE_KEY`. Add a `main` ruleset that requires the self-test checks. Confirm that no tag ruleset blocks the App from moving `v1`.
2. Owner: mark PR #1 ready and squash-merge it with its title. Keep the PR body unchanged until release-please has run; its `BEGIN_COMMIT_OVERRIDE` block is the v1.0.0 changelog.
3. Verify the push run on `main`: `baseline / gitleaks` reports "Not a pull request" and passes.
4. release-please opens a release PR for `1.0.0`, and the owner merges it. Then `git ls-remote --tags origin` shows `v1.0.0` and `v1` at the same SHA, and `move-major-tag` reports "Moved v1".
5. Owner merges MarcelRoozekrans/renovate-config#3.
6. In `architecture-governance-engine`, update `docs/planning/STATE.md`: Phase 1.4 is unblocked.

Open follow-ups: #2, Renovate for the pinned binaries, which needs a decision on the approach; #3, removing the actionlint ignore once actionlint ships `job.workflow_*` support.

## Commit rules

Conventional commits. No Co-Authored-By trailer and no session link. No nested parentheses in commit bodies, because release-please drops such commits.
