# ci-baseline state

**Updated:** 2026-11-03
**Branch:** `docs/v1-plan`, which holds the spec and the plan. Implementation goes on this branch or a feature branch cut from it.

## Position

- Design approved by the owner on 2026-11-03: `docs/superpowers/specs/2026-11-03-ci-baseline-design.md`.
- v1.0.0 plan written and accepted: `docs/superpowers/plans/2026-11-03-ci-baseline-v1.md`, 11 tasks.
- Execution method chosen by the owner: **subagent-driven** (superpowers:subagent-driven-development).
- Next step: Task 1, scaffold, pinned-binary installer and self-test skeleton.

## Inputs the next step needs

- The plan's "Plan decisions not in the spec" section records the choices made while planning: the `baseline-ref` input, the fifth fixture `dotnet-nowarn-package`, per-TFM evaluation, the vulnerable package `Microsoft.Rest.ClientRuntime 2.3.24`, Linux-only coverage-gate, and fixtures ignored by Renovate.
- Self-test results only come from GitHub Actions runs on pushed branches. Actions must be enabled on this repo; check before Task 2.
- Owner-gated: pushing to `MarcelRoozekrans/renovate-config` (Task 10), every Task 11 item, releases, tags and repo settings.

## Commit rules

Conventional commits. No Co-Authored-By trailer and no session link. No nested parentheses in commit bodies, because release-please drops such commits.
