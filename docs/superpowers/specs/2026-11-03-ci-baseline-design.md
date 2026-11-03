# CI Baseline Design: shared security and quality workflows

**Date:** 2026-11-03
**Repository:** `MarcelRoozekrans/ci-baseline` (working name, public, new)
**First adopter:** `MarcelRoozekrans/architecture-governance-engine`, becoming `Ariadne.NET`, in its Phase 1.4

## Intent

The owner keeps repos under three owners: the personal account `MarcelRoozekrans`, and the orgs `ZeroAlloc-Net` and `lucent-org`. On 2026-11-03 the owner decided that every repo gets the same CI security and quality baseline. Copying the same jobs into dozens of repos means they drift apart: one repo has a floor of 70%, another skips audit of transitive packages, a third never got gitleaks. This repo holds the baseline once. Repos call it, and a change to the baseline is a versioned release that Renovate rolls out.

The baseline, as decided on 2026-11-03:
- gitleaks on every pull request, plus a one-time full-history scan before a repo goes public
- NuGetAudit with `NuGetAuditMode=all` for .NET repos, so transitive packages are audited at restore
- CodeQL for the repo's languages
- a CycloneDX SBOM attached to each release
- a codecov coverage floor
- Renovate stays the dependency updater, not Dependabot
- Trivy only for repos that ship container images or IaC

## Goals

- One public repo that hosts the baseline as reusable workflows and composite actions, callable by any repo of all three owners, private or public, without cross-repo access settings.
- Versioned releases: callers pin `@v1`; a stricter baseline is a major release that Renovate offers as a PR.
- Each adopting repo makes the baseline checks required through its own `main` ruleset.
- v1 covers .NET repos completely. gitleaks and CodeQL take the language as input and work for any repo, so later non-.NET adoption needs no redesign.
- Ariadne.NET adopts it in its Phase 1.4, then the rollout below.
- An adoption guide in the README that a repo can follow in one PR.

## Non-goals

- Non-.NET stacks in v1 (Astro, TypeScript, Python, private repos with container images or infrastructure code). They follow in a later round. The Trivy job is designed in, but nothing in v1 calls it.
- Org-level enforcement: org rulesets with required workflows. Decided 2026-11-03: opt-in plus a per-repo ruleset, the same mechanism under all three owners. Personal accounts have no org rulesets anyway.
- Moving the existing reusable workflows in `ZeroAlloc-Net/.github` (`api-compat.yml`, `publish.yml`, `release-tracking.yml`, `ship-release-tracking.yml`, `benchmark-smoke.yml`). They stay where they are. Only the baseline checks come from here.
- Build, test, pack and publish. Each repo keeps its own `ci.yml`. The baseline adds checks to it but does not replace it.
- Replacing Renovate or the shared preset `MarcelRoozekrans/renovate-config`. At most that preset gains a rule for this repo's tags.

## Anti-goals

- A baseline change that turns every repo red at once with no PR in between. That is why callers never use `@main`.
- A check that "passes" because it skipped itself silently. When a check cannot run, for example CodeQL on a private repo without Code Security, the job says so in its summary and the README tells the owner. It does not report a pass it never ran.
- A coverage floor or audit level that a repo lowers quietly. Lowering one needs an explicit, visible input in the repo's workflow file.
- Secrets in this repo, and any job that needs more than `contents: read` plus the one permission it needs.
- Private details of the owner's setup, such as hostnames or home paths, in this public repo, its examples or its issues.

## Decisions

Decided with the owner on 2026-11-03:

- **Host:** a new public repo under the personal account, next to `renovate-config`, and not the org's `.github` repo. It stays neutral across the three owners, has its own releases, and the ZeroAlloc org planning docs stay separate. The name `ci-baseline` is a working name; the owner confirms it when the repo is created.
- **Versioning:** release-please cuts `vX.Y.Z` and moves a major tag `vX`. Callers use `@v1`; a repo that wants a full SHA pin may use one. A stricter default, such as a higher floor, a new required check or a lower audit level, is a major release.
- **Enforcement:** opt-in. Each repo calls the baseline, and its own `main` ruleset requires the baseline checks.
- **Scope of v1:** .NET repos, Ariadne.NET first.
- **Coverage floor:** 80% line coverage over the whole project, and a PR may not lower project coverage by more than 1 percentage point.
- **NuGetAudit:** `NuGetAuditMode=all`, `NuGetAuditLevel=moderate`. Moderate, high and critical advisories fail the build; low ones are reported.
- **Org settings, checked 2026-11-03:** ZeroAlloc-Net and lucent-org are on the free plan, allow all actions and reusable workflows, and do not require SHA pinning, so `@v1` from a personal repo works there.
- **Private repos, decided 2026-11-03:** on the free plan a private repo cannot enforce a ruleset or upload CodeQL results. Private .NET repos adopt the baseline anyway, with `codeql: false`, which the job summary shows. gitleaks, NuGetAudit, the coverage gate and the SBOM still run and go red, but nothing blocks a merge. They come after the public repos in the rollout. If a repo goes public, it gets its ruleset and CodeQL then.
- **Rollout order:** Ariadne.NET → the family (Minos.NET, Rag.NET, Mnemosyne.NET, Thalos.NET, Daedalus.NET) → the personal tools (AI.Sentinel, roslyn-codelens-mcp, memorylens-mcp, then the other personal .NET repos) → the ZeroAlloc-Net repos.
- **Structure:** approach C below.

## Approaches

The constraint behind the choice: the coverage floor and the SBOM need data from the repo's own jobs, namely its test results and its release build. A reusable workflow always runs as separate jobs.

- **A: One umbrella reusable workflow.** A single `uses:` per repo, with inputs that turn parts on and off. Coverage and the SBOM need an artifact contract: the repo uploads its Cobertura file or release build, and the baseline downloads it. That contract fails in ways that are easy to miss, such as a wrong artifact name or an SBOM built from something other than what ships.
- **B: One reusable workflow per check.** The most flexible, but five `uses:` blocks per repo, job names chosen per repo, and messier rulesets. It has the same artifact problem as A.
- **C: Hybrid (chosen).** One umbrella reusable workflow, `baseline.yml`, for the checks that stand alone (gitleaks, CodeQL, NuGetAudit). Composite actions for the steps that belong inside the repo's own jobs: `coverage-gate` after the test step, `sbom` in the release job. The full-history scan is its own reusable workflow, started by hand. The coverage gate reads the real test output, and the SBOM describes exactly what ships. The cost is two adoption steps per repo instead of one.

## Design

### Repository layout

```
.github/workflows/
  baseline.yml          reusable: gitleaks (PR), codeql, nuget-audit, trivy (off by default)
  history-scan.yml      reusable: gitleaks over all refs and all history, workflow_dispatch in callers
  self-test.yml         this repo's CI: actionlint + calls its own workflows and actions on fixtures
  release-please.yml    releases this repo, moves the major tag
actions/
  coverage-gate/action.yml   public: used in the caller's test job
  sbom/action.yml            public: used in the caller's release job
  gitleaks/action.yml        internal: the logic baseline.yml and history-scan.yml wrap
  nuget-audit/action.yml     internal: the logic baseline.yml wraps
fixtures/
  dotnet-clean/         small solution: passes every check, coverage above 80%
  dotnet-vulnerable/    restores a package with a known moderate-or-higher advisory, transitively
  dotnet-lowcov/        coverage below 80%
  dotnet-nowarn/        silences NU1902 through NoWarn, which the audit must refuse
docs/superpowers/specs/ this document
README.md               adoption guide, inputs, required-check names, how to override
```

### `baseline.yml` (reusable workflow)

Trigger: `workflow_call`. Inputs (defaults in brackets):
- `languages` [`csharp`]: CodeQL languages, comma-separated.
- `dotnet-version` [`10.0.x`]: also accepts `global-json` to use the repo's `global.json`.
- `solution` [empty]: path to the `.sln`/`.slnx` to restore. Empty means the single one at the root, and the job fails if there are several.
- `dotnet` [`true`]: whether the NuGetAudit job runs. Non-.NET callers set it to `false`.
- `nuget-audit-level` [`moderate`].
- `codeql` [`true`]: private repos without Code Security set it to `false`; see the codeql job.
- `trivy` [`false`]: v1 has no callers.

Default permissions `contents: read`. Each job widens only what it needs (`security-events: write` for CodeQL).

Jobs, which give the stable check names `baseline / gitleaks`, `baseline / codeql (csharp)` and `baseline / nuget-audit` when the caller's job is named `baseline`:
The check logic lives in the internal composite actions, so `self-test` can run each one on a fixture as a normal step and assert a failure (see Self-test). The reusable workflow only wraps them.

The caller's job must grant the permissions: a reusable workflow cannot widen what the caller grants. The adoption guide's snippet sets `contents: read`, `security-events: write`, and `actions: read`, which CodeQL needs on private repos.

- **gitleaks:** on `pull_request` events only, it scans the commits the PR adds, with `--redact`. It runs the gitleaks binary pinned by version and checksum, not `gitleaks/gitleaks-action`, because that action requires a paid license key for repos owned by an organization, and ZeroAlloc-Net and lucent-org are organizations. On other events it reports "not a pull request" in the job summary and succeeds, because a required check must report on every PR, and on push the history scan covers the history.
- **codeql:** a matrix over `languages`, using `github/codeql-action` init and analyze with `build-mode: none` for C#, so it does not depend on the repo's build. The caller's `GITHUB_TOKEN` cannot read whether Code Security is enabled, so the job does not try to detect it beforehand. When the SARIF upload is refused, on a private repo without Code Security or a repo with CodeQL default setup still on, the job fails and its summary names both causes and points to the README. The README tells the owner to turn off default setup, and on a private repo either enable Code Security or set the explicit `codeql: false`. With `codeql: false` the job still runs and writes "CodeQL disabled by caller input" in its summary, so the check name exists and the choice shows. A silent skip is not allowed; see the anti-goals.
- **nuget-audit:** `setup-dotnet`, then `dotnet restore <solution> -p:NuGetAudit=true -p:NuGetAuditMode=all -p:NuGetAuditLevel=low -p:WarningsAsErrors=<codes>`. `NuGetAuditLevel` sets what is *reported*, so it stays at `low`, and every advisory shows up. The input `nuget-audit-level` sets what *fails*, through `WarningsAsErrors`: moderate means `NU1902;NU1903;NU1904`, NU1901 being low. Findings go into the job summary. Before restoring, the job reads `NoWarn` and `WarningsNotAsErrors` for every project (`dotnet msbuild -getProperty`) and fails if any of them contains a failing `NU190x` code, because such a code would silence the audit unseen. An advisory that has no fixed version yet goes through `NuGetAuditSuppress` per advisory URL, which is visible in the diff; see Risks. This works whether or not the repo already sets the properties in `Directory.Build.props`. The README still recommends setting them there, so a local restore shows the same findings.
- **trivy:** only if `trivy: true`. Filesystem and config scan, and an image scan when an `image` input is given. It fails on HIGH and CRITICAL. It is not exercised in v1 beyond its self-test fixture.

### `history-scan.yml` (reusable workflow)

Checks out with `fetch-depth: 0` and all refs, then runs gitleaks over the whole history. The report is uploaded as an artifact with 7-day retention and summarised, with `--redact`, because artifacts of a public repo can be downloaded by anyone. A caller wires it to `workflow_dispatch`. The adoption guide makes it the step that must pass before a repo goes public. For Ariadne.NET it is the history check in its Phase 1.4 step 2, which also covers the owner's private-detail patterns (hostnames, internal IPs, home paths) through a custom gitleaks config. Those patterns are private details themselves, so the config is never committed to a repo that is or will be public. The caller passes it as a secret (`GITLEAKS_CONFIG`, the TOML contents), and the workflow writes it to a temp file for the run *(Claude's call)*.

### `actions/coverage-gate` (composite action)

Used right after the repo's own test step. Inputs: `reports` (glob of Cobertura files) [`**/coverage.cobertura.xml`], `floor` [`80`], `max-drop` [`1`].
- **Scope:** production code only. The gate excludes test projects, benchmarks, samples, generated files (`*.g.cs`, `obj/`) and the AotSmoke-style executable test projects, the same as the `ignore` list in Minos.NET's `codecov.yml`. The README's `codecov.yml` block carries the same `ignore` list, so both count the same lines *(Claude's call)*.
- **The floor is local and authoritative:** it merges the reports with ReportGenerator, pinned, into a single summary and fails if line coverage is below `floor`. It writes the number to the job summary.
- **The drop check runs through codecov,** because it needs the base commit's number: the README's `codecov.yml` block sets `coverage.status.project.default` to `target: auto` and `threshold: 1%`, not informational. The ruleset requires the `codecov/project` status. The gate reads the repo's `codecov.yml` and fails if project status is informational, has a fixed target, or has a threshold above `max-drop`. That way a repo cannot weaken the drop rule by editing `codecov.yml` alone.
- A floor below 80 is accepted only together with an input `floor-override-reason` that is non-empty. That reason is printed in the summary. This is the visible, explicit override from the anti-goals.

The upload to codecov stays in the repo's own job (OIDC, as Minos.NET does), because the token setup differs per repo.

### `actions/sbom` (composite action)

Used in the repo's release or publish job, after the release build. Inputs: `solution`, `tag`, `output-name` [`<repo>-<tag>.cdx.json`], and `upload` [`true`].
- It installs the `CycloneDX` dotnet tool, pinned, and generates a CycloneDX JSON SBOM for the solution with transitive dependencies and without test projects. With `upload: true` it attaches the SBOM to the GitHub release for `tag` using `gh release upload --clobber`, so a resumed publish run does not fail on the existing asset. That needs `contents: write`, which the caller's job grants.
- For Ariadne.NET it goes into `publish-nuget` in `ci.yml`, next to the step that attaches the `.nupkg` files.

### Versioning and releases of this repo

- release-please, `release-type: simple`, with `bump-minor-pre-major` off. The first release is `v1.0.0`, because callers pin a major tag from day one.
- After a release, a step moves the major tag (`v1`) to the release commit. The release workflow runs on a token from the owner's release bot GitHub App, as in the family repos, not on `GITHUB_TOKEN`.
- Renovate's `github-actions` manager picks up `uses: MarcelRoozekrans/ci-baseline/...@v1` references. On a major tag, Renovate offers `v2` as a major-update PR, which stays manual as `renovate-config` already keeps all majors. `renovate-config` extends `config:recommended` without `helpers:pinGitHubActionDigests`, so `v1.x` releases reach callers through the moving tag and open no PRs. A rule added to `renovate-config` groups the baseline's references (workflow and actions) into one PR per repo, and excludes them from digest pinning, so a later change to that preset doesn't start a stream of digest PRs.

### Self-test

`self-test.yml` runs on every push and PR in this repo:
- `actionlint` on all workflows, and a check on action metadata.
- **Pass path:** it calls `baseline.yml` from the local ref on `dotnet-clean` as a real reusable-workflow call, which must pass. That proves the wrapping, inputs, permissions and check names.
- **Fail paths:** a reusable-workflow call that fails turns the run red whatever comes after it, so the expected failures run on the composite actions directly, as steps with an `id`. The step after each one asserts `steps.<id>.outcome == 'failure'` and fails the job otherwise. `dotnet-vulnerable` must fail `nuget-audit`, `dotnet-nowarn` must fail `nuget-audit`, and `dotnet-lowcov` must fail `coverage-gate`. For gitleaks, the test generates a fake secret at run time into a throwaway git repo in `$RUNNER_TEMP` and must fail the scan. No secret-like string is ever committed here, so this repo's own gitleaks and history scan stay clean.
- `sbom` runs with `upload: false` on `dotnet-clean`, and the produced file is validated against the CycloneDX schema.

### Adoption in a .NET repo (README content)

1. In `ci.yml`, or a new `baseline-checks.yml`, add a job `baseline: uses: MarcelRoozekrans/ci-baseline/.github/workflows/baseline.yml@v1` with `pull_request` and `push` triggers on `main`. The job grants `contents: read`, `security-events: write` and `actions: read`, and passes the `GITLEAKS_CONFIG` secret only to the history-scan caller.
2. Add `- uses: MarcelRoozekrans/ci-baseline/actions/coverage-gate@v1` after the test step, and set `codecov.yml` to the given block.
3. Add `- uses: MarcelRoozekrans/ci-baseline/actions/sbom@v1` to the release job.
4. Add a `history-scan.yml` caller on `workflow_dispatch`. Run it once before going public.
5. Recommended: set `NuGetAudit`, `NuGetAuditMode=all` and `NuGetAuditLevel=moderate` in `Directory.Build.props` for local parity.
6. In the `main` ruleset, require `baseline / gitleaks`, `baseline / codeql (csharp)`, `baseline / nuget-audit`, the repo's build job that runs `coverage-gate`, and `codecov/project`.
7. Remove Dependabot config if present. Renovate covers dependency updates.

### Rollout

1. **Ariadne.NET** in its Phase 1.4. Its design already lists the baseline as a goal. The plan for Phase 1.4 calls this repo instead of inlining the jobs, so its own `ci.yml` stays smaller. Ariadne's 1.4 is blocked on `ci-baseline` `v1.0.0`; if that slips, Ariadne waits rather than inlining a copy that later has to be removed.
2. **Family:** Minos.NET, Rag.NET, Mnemosyne.NET, Thalos.NET, Daedalus.NET. One PR each.
3. **Personal tools:** AI.Sentinel, roslyn-codelens-mcp, memorylens-mcp, then the remaining personal .NET repos (AdoNet.Async, MailPeek, Owasp.Analyzers, BlazorNative and others).
4. **ZeroAlloc-Net repos**, last and the most numerous. Their existing `@main` workflows in `ZeroAlloc-Net/.github` stay as they are.
5. **Private .NET repos**, without enforcement, as decided above.

A repo below 80% coverage on adoption gets the explicit `floor-override-reason` with its current number, and an issue in that repo to raise it. It does not get a silent lower floor.

## Constraints

- The repo is public, so any repo, private or in another org, can call it.
- GitHub Code Security is needed for CodeQL uploads on private repos.
- gitleaks runs as a pinned binary, not the licensed action.
- Every third-party action is pinned to a full SHA with a version comment, and Renovate keeps those pins current.
- No secrets in this repo. The release bot App credentials are this repo's own Actions secret and variable, set by the owner.

## Settings only the owner can make

- Confirm the repo name, and approve creating `MarcelRoozekrans/ci-baseline` as a public repo.
- Install the release bot GitHub App on it, and set `RELEASE_BOT_CLIENT_ID` and `RELEASE_BOT_PRIVATE_KEY`.
- Per adopting public repo: turn off CodeQL default setup if it is on, and add the `main` ruleset.

## Left to the builder

- **Plan boundary:** the plan covers this repo up to `v1.0.0` and the change to `renovate-config`. Ariadne.NET's adoption is part of its own Phase 1.4 plan, and each later repo is its own PR from the adoption guide *(Claude's call)*.
- Exact versions and SHAs of gitleaks, ReportGenerator, CycloneDX, actionlint and the actions, current at build time.
- The vulnerable package for the `dotnet-vulnerable` fixture: one with a published moderate-or-higher advisory, pulled in transitively.
- Wording of the job summaries and the README.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| A major tag move fails after a release | Callers stay on the old `v1` commit | The release workflow fails visibly; the README documents moving it by hand. |
| A baseline update breaks repos at the same time | Many red PRs | Breaking changes are major releases only; `self-test` must pass before a release. |
| codecov reports late or not at all | `codecov/project` never reports, PR blocked | The absolute floor is local; codecov outages are rare and visible. The README explains how to retrigger. |
| A private repo lacks Code Security | CodeQL job fails | Clear failure message plus the explicit `codeql: false`, decided per repo by the owner. |
| NuGetAudit flags an advisory with no fixed version | PR blocked | The README documents `NuGetAuditSuppress` per advisory in the repo, with a reason and an issue. It is visible in the diff, not a lower level. |
