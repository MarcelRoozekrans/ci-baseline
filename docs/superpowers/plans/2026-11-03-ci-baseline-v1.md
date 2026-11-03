# CI Baseline v1.0.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `MarcelRoozekrans/ci-baseline` `v1.0.0`: the reusable workflows and composite actions that give every .NET repo gitleaks, CodeQL, NuGetAudit, a coverage floor and a release SBOM, plus the Renovate rule that rolls baseline releases out.

**Architecture:** Approach C from the spec. `baseline.yml` is an umbrella reusable workflow for the stand-alone checks; it checks out this repo at `baseline-ref` and runs the internal composite actions from that checkout. `coverage-gate` and `sbom` are public composite actions that run inside the caller's own jobs. All decision logic that can be unit-tested lives in stdlib-only Python under `lib/`, and the action YAML only wires inputs to it. `self-test.yml` proves the pass path through a real reusable-workflow call and every fail path through the composite actions on fixtures.

**Tech Stack:** GitHub Actions (reusable workflows, composite actions), bash, Python 3 stdlib plus PyYAML (preinstalled on `ubuntu-latest`), .NET 10 SDK, gitleaks, Trivy, ReportGenerator, CycloneDX for .NET, cyclonedx-cli, actionlint, release-please, Renovate.

**Spec:** `docs/superpowers/specs/2026-11-03-ci-baseline-design.md`

## Global Constraints

- Public repo. No secrets, no hostnames, home paths, internal IPs or other private details in any file, example, fixture or commit.
- Every third-party action pinned to a full commit SHA with a version comment: `uses: actions/checkout@<sha> # v7.0.0`.
- Every downloaded binary (gitleaks, Trivy, actionlint, cyclonedx-cli) pinned by version **and** SHA-256, installed through `lib/install-pinned.sh`. Never `gitleaks/gitleaks-action` (paid licence for orgs), never `aquasecurity/trivy-action`.
- Every dotnet tool (ReportGenerator, CycloneDX) installed with an exact `--version`.
- Versions are the latest stable at build time. Record each pin once, as an `env:` value in the action that uses it.
- Workflow default permissions `contents: read`. A job widens only what it needs: `security-events: write` for CodeQL, `contents: write` only in the release workflow.
- Check names when the caller job is named `baseline`: `baseline / gitleaks`, `baseline / codeql (csharp)`, `baseline / nuget-audit`. These strings are API from v1.0.0 on.
- No silent skip: a check that is turned off or not applicable still runs and writes why into `$GITHUB_STEP_SUMMARY`.
- Coverage: floor `80` line coverage, `max-drop` `1` percentage point. A floor below 80 needs a non-empty `floor-override-reason`.
- NuGetAudit: `NuGetAuditMode=all`, reporting level `low`, failing level from `nuget-audit-level` [`moderate`]: low → `NU1901;NU1902;NU1903;NU1904`, moderate → `NU1902;NU1903;NU1904`, high → `NU1903;NU1904`, critical → `NU1904`.
- release-please `release-type: simple`, `bump-minor-pre-major: false`, first release `v1.0.0`.
- Commits: conventional commits, no `Co-Authored-By` trailer, no session link, no nested parentheses in commit bodies (release-please drops the commit).
- Do not push to `renovate-config`, create releases, tags or change repo settings without the owner's confirmation.

## Plan decisions not in the spec

Made while planning; each is small and reversible, and the README documents the visible ones.

1. **`baseline-ref` input.** A reusable workflow cannot address its own repo's files by relative path: `./actions/x` resolves against the caller's workspace. `baseline.yml` therefore checks out `MarcelRoozekrans/ci-baseline` at input `baseline-ref` [`v1`] into `.ci-baseline/` and calls `./.ci-baseline/actions/<name>`. Self-test passes its own commit SHA. A self-test check keeps the default `v<major>` equal to the major in the release manifest, so a v2 release that forgets to bump it fails its release PR.
2. **Fifth fixture `dotnet-nowarn-package`.** Probed on 2026-11-03 with SDK 10.0.403: `NoWarn="NU1903"` on a direct `PackageReference` to the vulnerable package silences the audit, the same as a project `NoWarn`. The spec's guard reads only properties, so it also reads `PackageReference` item metadata. `NoWarn` on the *parent* of a transitive package does not silence it.
3. **Per-TFM evaluation.** `dotnet msbuild -getProperty` on a multi-targeted project evaluates the outer build only, so a `NoWarn` under a `TargetFramework` condition is invisible there. The guard evaluates each TFM in `TargetFrameworks` with `-p:TargetFramework=<tfm>`.
4. **Vulnerable package.** .NET 10 prunes framework-provided packages from the graph, so the classic `System.Net.Http 4.3.0` via `NETStandard.Library 1.6.1` reports **nothing** under SDK 10. Verified instead: `Microsoft.Rest.ClientRuntime 2.3.24` pulls `Newtonsoft.Json 10.0.3` transitively, which raises `NU1903` (GHSA-5crp-9r3c-p9vr, high).
5. **`actions/trivy`** is an internal composite action like gitleaks and nuget-audit, so its fail path can be self-tested, with a fixture `fixtures/iac-misconfig/`.
6. **`coverage-gate` runs on Linux runners only in v1.** It needs PyYAML to read `codecov.yml`. On another OS it fails with a message that says so. A repo that tests on Windows runs the gate in its Linux job.
7. **This repo's `renovate.json` ignores `fixtures/**`.** Renovate must never "fix" the vulnerable fixture or move fixture test packages.
8. **A `prepare` job** in `baseline.yml` turns the comma-separated `languages` into a JSON matrix, because workflow expressions have no string split. Its check name, `baseline / prepare`, is not meant to be required.

## Review Focus

1. **The audit silenced by a direct `PackageReference NoWarn` or a TFM-conditioned `NoWarn`.** Both are real per the 2026-11-03 probe. The guard must refuse both. Pinned in Task 3 by `dotnet-nowarn-package` and the multi-target `dotnet-nowarn`.
2. **`coverage-gate` finding no report**, because the test step collected nothing or the glob is wrong. That must fail with "no coverage reports matched", never pass on zero files. Pinned in Task 5 by a unit test and a self-test step on an empty directory.
3. **A `codecov.yml` the gate misreads:** missing; under `.github/`; `project: off`; `threshold: "5%"` as a string; `target: 70%`; `informational: true`. Each must give the right verdict. Pinned in Task 5 unit tests.
4. **The gitleaks PR range.** Only the PR's commits are scanned. A secret already in the base must not fail a PR, which the history scan covers, and a secret in a head commit must fail it. Pinned in Task 2 by the two-commit throwaway-repo test.
5. **The solution input:** empty with two solutions at the root, a `.slnx`, or a path that does not exist. Each gives a clear failure or the right file. Pinned in Task 3 unit tests for `resolve_solution`.

---

## File structure

```
.github/workflows/baseline.yml        Task 7
.github/workflows/history-scan.yml    Task 2
.github/workflows/self-test.yml       Task 1, grown by every task
.github/workflows/release-please.yml  Task 8
actions/gitleaks/action.yml           Task 2  (internal)
actions/nuget-audit/action.yml        Task 3  (internal)
actions/trivy/action.yml              Task 4  (internal)
actions/coverage-gate/action.yml      Task 5  (public)
actions/sbom/action.yml               Task 6  (public)
lib/install-pinned.sh                 Task 1
lib/baseline_lib.py                   Tasks 3, 7: resolve_solution, failing_codes, split_languages, nowarn_violations
lib/coverage_gate.py                  Task 5
lib/check_baseline_ref.py             Task 8
tests/test_*.py                       unit tests, stdlib unittest
fixtures/dotnet-clean/                Task 3, gains tests in Task 5
fixtures/dotnet-vulnerable/           Task 3
fixtures/dotnet-nowarn/               Task 3
fixtures/dotnet-nowarn-package/       Task 3
fixtures/dotnet-lowcov/               Task 5
fixtures/iac-misconfig/               Task 4
release-please-config.json, .release-please-manifest.json   Task 8
renovate.json, .gitignore             Task 1
README.md                             Task 9
```

Unit tests run with `python3 -m unittest discover -s tests -t .` from the repo root. Each test file puts `lib/` on `sys.path`.

---

### Task 1: Scaffold, pinned-binary installer, self-test skeleton

**Files:**
- Create: `lib/install-pinned.sh`, `.github/workflows/self-test.yml`, `renovate.json`, `.gitignore`, `README.md` (one-paragraph stub; Task 9 writes it)

**Interfaces:**
- Produces: `lib/install-pinned.sh <url> <sha256> <dest-dir>`. It downloads to a temp file, verifies with `sha256sum -c` (exit 1 with `::error::checksum mismatch for <url>` on mismatch), extracts `.tar.gz` or `.zip` into `<dest-dir>` or copies a bare binary, `chmod +x`, and appends `<dest-dir>` to `$GITHUB_PATH`. `set -euo pipefail`.
- Produces: `self-test.yml` with jobs `lint` and `unit`, on `push` to `main`, `pull_request` and `workflow_dispatch`, `permissions: contents: read`. Later tasks add jobs.

- [ ] **Step 1:** Write `self-test.yml` job `lint`: checkout, install actionlint through `lib/install-pinned.sh`, run `actionlint` on all workflows, and a step that loads every `actions/*/action.yml` with PyYAML and fails unless each has `name`, `description`, and `runs.using == 'composite'`. Add a step `installer-rejects-bad-checksum` with `id: badsum`, `continue-on-error: true`, that calls the installer with the actionlint URL and 64 zeros, then `if: steps.badsum.outcome != 'failure'` → `exit 1`.
- [ ] **Step 2:** Job `unit`: `python3 -m unittest discover -s tests -t .`. Add `tests/__init__.py` and a placeholder `tests/test_smoke.py` asserting `lib/` is importable, so the job has something to run.
- [ ] **Step 3:** Write `lib/install-pinned.sh` as specified.
- [ ] **Step 4:** `renovate.json`: `{"extends": ["github>MarcelRoozekrans/renovate-config"], "ignorePaths": ["fixtures/**"]}` plus `$schema`. `.gitignore`: `bin/ obj/ TestResults/ *.cdx.json .ci-baseline/`.
- [ ] **Step 5: Verify locally:** `bash -n lib/install-pinned.sh`; run the installer once against the real actionlint release URL into `/tmp/al` with `GITHUB_PATH=/dev/null` and run `/tmp/al/actionlint .github/workflows/*.yml`. Expected: no findings. Run it again with a wrong checksum. Expected: exit 1 and the error line.
- [ ] **Step 6: Commit:** `ci: add self-test skeleton and pinned binary installer`

### Task 2: gitleaks action and history scan

**Files:**
- Create: `actions/gitleaks/action.yml`, `.github/workflows/history-scan.yml`
- Modify: `.github/workflows/self-test.yml` adds job `gitleaks`

**Interfaces:**
- Consumes: `lib/install-pinned.sh` (Task 1), through `${{ github.action_path }}/../../lib/install-pinned.sh`.
- Produces: `actions/gitleaks` with inputs `mode` (`range` | `history`), `source` [`.`], `log-opts` [empty], `config` [empty: path to a TOML; empty means gitleaks' own default plus the repo's `.gitleaks.toml` if present], `report-path` [empty]. It runs `gitleaks git <source> --redact --no-banner --exit-code 1`, plus `--log-opts` for `range` and `--log-opts=--all` for `history`, `--config` when given and `--report-path` when given. It writes a summary line with the number of findings, never the secrets.
- Produces: `history-scan.yml`, a `workflow_call` with optional secret `GITLEAKS_CONFIG` and job `history-scan`. It checks out with `fetch-depth: 0` and `fetch-tags: true`, then runs `git fetch origin '+refs/heads/*:refs/remotes/origin/*'`. When the secret is non-empty it writes it to `$RUNNER_TEMP/gitleaks.toml` with `umask 077`. It runs the action in `history` mode with a JSON report and uploads it with `if: always()` and `retention-days: 7`.

- [ ] **Step 1: Write the fail-path and range tests in `self-test.yml` job `gitleaks`.** In `$RUNNER_TEMP/leakrepo`, `git init`, then commit A, a clean file. Commit B adds `token.txt` holding `ghp_` plus 36 random alphanumerics from `/dev/urandom`, generated at run time. Commit C is clean. Steps:
  - `range-with-leak`: the action with `mode: range`, `source: $RUNNER_TEMP/leakrepo`, `log-opts: A..C`, `id: leak`, `continue-on-error: true`. Assert `steps.leak.outcome == 'failure'`.
  - `range-without-leak`: `log-opts: B..C`, so the leak sits in the base. Must succeed.
  - `history`: `mode: history` on the same repo, `id: hist`, `continue-on-error: true`. Assert failure.
  - `history-clean`: call `history-scan.yml` as a separate self-test job on this repo. It must pass.
- [ ] **Step 2: Push the branch and run self-test.** Expected: the gitleaks job fails because the action does not exist yet.
- [ ] **Step 3:** Implement `actions/gitleaks/action.yml` and `history-scan.yml` as in Interfaces.
- [ ] **Step 4: Run self-test.** Expected: `gitleaks` and `history-scan` jobs green, all three assertions hold, and the logs show `REDACTED`, never `ghp_`.
- [ ] **Step 5: Commit:** `feat: add gitleaks action and history scan workflow`

### Task 3: nuget-audit action, guard and .NET fixtures

**Files:**
- Create: `lib/baseline_lib.py`, `tests/test_baseline_lib.py`, `actions/nuget-audit/action.yml`
- Create: `fixtures/dotnet-clean/` holding `DotnetClean.slnx`, `src/Clean/Clean.csproj` (net10.0, one small class, no packages), no `global.json`
- Create: `fixtures/dotnet-vulnerable/` holding `DotnetVulnerable.slnx` and a project referencing `Microsoft.Rest.ClientRuntime` `2.3.24`
- Create: `fixtures/dotnet-nowarn/` holding a solution and a project with `<TargetFrameworks>net10.0;net9.0</TargetFrameworks>`, the same vulnerable reference, and in `Directory.Build.props` `<NoWarn>$(NoWarn);NU1903</NoWarn>` under `Condition="'$(TargetFramework)' == 'net9.0'"`
- Create: `fixtures/dotnet-nowarn-package/` holding a solution and a project with a direct `<PackageReference Include="Newtonsoft.Json" Version="12.0.3" NoWarn="NU1903" />`
- Modify: `self-test.yml` adds job `nuget-audit`

**Interfaces:**
- Produces in `lib/baseline_lib.py`:
  - `resolve_solution(root: str, solution: str) -> str`. With an empty `solution`: the single `*.sln`/`*.slnx` directly in `root`. Raises `BaselineError` naming the files when there are 0 or more than 1. With a non-empty `solution`: that path, or `BaselineError("solution not found: <path>")`.
  - `failing_codes(level: str) -> list[str]`. Case-insensitive mapping per Global Constraints. Raises `BaselineError` listing the valid levels for anything else.
  - `nowarn_violations(evaluations: list[dict], codes: list[str]) -> list[str]`. Each dict is one `dotnet msbuild -getProperty:NoWarn -getProperty:WarningsNotAsErrors -getItem:PackageReference` JSON result, plus keys `project` and `tfm`. Returns one human-readable line per hit: `<project> [<tfm>]: NoWarn contains NU1903`, or `... PackageReference Newtonsoft.Json NoWarn contains NU1903`. Splits on `;` and `,`, trims, compares case-insensitively.
  - `class BaselineError(Exception)` and a `main()` CLI with subcommands `resolve-solution`, `failing-codes`, `nowarn-check`. The CLI prints `::error::<message>` and exits 1 on `BaselineError`.
- Produces: `actions/nuget-audit` with inputs `solution` [empty], `nuget-audit-level` [`moderate`], `working-directory` [`.`]. It does not run `setup-dotnet`; the caller does that.

- [ ] **Step 1: Write the failing unit tests** in `tests/test_baseline_lib.py`:
  - `test_resolve_single_slnx`, `test_resolve_two_solutions_raises` (message names both files), `test_resolve_none_raises`, `test_resolve_explicit_missing_raises`, `test_resolve_explicit_ok`
  - `test_failing_codes_moderate == ["NU1902","NU1903","NU1904"]`, `test_failing_codes_case_insensitive("High") == ["NU1903","NU1904"]`, `test_failing_codes_low` gives four codes, `test_failing_codes_invalid_raises("medium")`
  - `test_nowarn_property_hit`, `test_warnings_not_as_errors_hit`, `test_package_reference_nowarn_hit`, `test_nowarn_low_code_ignored_at_moderate` (NU1901 in NoWarn at moderate is not a violation), `test_nowarn_comma_and_spaces`, `test_clean_evaluation_returns_empty`
- [ ] **Step 2:** Run `python3 -m unittest tests.test_baseline_lib -v`. Expected: ImportError.
- [ ] **Step 3:** Implement `lib/baseline_lib.py`.
- [ ] **Step 4:** Run the tests. Expected: all pass.
- [ ] **Step 5: Implement `actions/nuget-audit/action.yml`.** Steps:
  1. resolve the solution;
  2. compute the codes;
  3. guard: for each project from `dotnet sln <sln> list`, read `TargetFrameworks`/`TargetFramework`, run the msbuild query once per TFM with `-p:TargetFramework=<tfm>`, collect the JSON and pipe it to `nowarn-check`. On violations, fail with the list and a pointer to the README section on `NuGetAuditSuppress`;
  4. `dotnet restore "$sln" --force -p:NuGetAudit=true -p:NuGetAuditMode=all -p:NuGetAuditLevel=low "-p:WarningsAsErrors=\"$codes\""`, `tee` to a log;
  5. `if: always()`: grep the `NU190x` lines from the log into the step summary as a table of code, package, version and advisory URL, or "No advisories."
- [ ] **Step 6: Self-test job `nuget-audit`:** `setup-dotnet` 10.0.x, plus 9.0.x for the nowarn fixture. `fixtures/dotnet-clean` must pass. `dotnet-vulnerable`, `dotnet-nowarn` and `dotnet-nowarn-package` each run with an `id` and `continue-on-error: true` and are asserted `failure`. A last assertion checks that the nowarn runs failed in the guard step, not in restore: the action writes `guard: violations found` to the summary and the assertion greps it, because a pass through the restore error would prove nothing.
- [ ] **Step 7: Verify locally** in each fixture: `dotnet restore -p:NuGetAudit=true -p:NuGetAuditMode=all -p:NuGetAuditLevel=low` on `dotnet-vulnerable` shows `NU1903` for `Newtonsoft.Json 10.0.3`, and on `dotnet-clean` shows none. Then push and run self-test. Expected: job green, all assertions hold.
- [ ] **Step 8: Commit:** `feat: add nuget-audit action with NoWarn guard and fixtures`

### Task 4: trivy action

**Files:**
- Create: `actions/trivy/action.yml`, `fixtures/iac-misconfig/Dockerfile`
- Modify: `self-test.yml` adds job `trivy`

**Interfaces:**
- Consumes: `lib/install-pinned.sh`.
- Produces: `actions/trivy` with inputs `path` [`.`], `image` [empty]. It runs `trivy fs --scanners vuln,secret,misconfig --severity HIGH,CRITICAL --exit-code 1 <path>`, and `trivy image --severity HIGH,CRITICAL --exit-code 1 <image>` when `image` is set. The table output goes to the step summary.

- [ ] **Step 1:** Fixture: a `Dockerfile` `FROM alpine:3.20` with no `USER` line, and `RUN apk add curl`. That raises Trivy misconfiguration `DS002`, "image user should not be root", HIGH. Self-test job `trivy`: the action on `fixtures/iac-misconfig`, with an `id` and `continue-on-error`, asserted `failure`. The action on `fixtures/dotnet-clean` must pass.
- [ ] **Step 2:** Push and run. Expected: fails, because the action is missing.
- [ ] **Step 3:** Implement the action.
- [ ] **Step 4:** Run self-test. Expected: green. If DS002 is not HIGH in the pinned Trivy version, pick another HIGH Dockerfile check from `trivy` output, name it in the fixture's comment, and re-run.
- [ ] **Step 5: Commit:** `feat: add trivy action`

### Task 5: coverage-gate action

**Files:**
- Create: `lib/coverage_gate.py`, `tests/test_coverage_gate.py`, `actions/coverage-gate/action.yml`
- Create: `fixtures/dotnet-clean/tests/Clean.Tests/` (xunit and coverlet.collector, testing the class fully); `fixtures/dotnet-lowcov/` (solution, a `src` project with several methods, a test project that covers under 50%, and a `codecov.yml` that is the README block)
- Create: `fixtures/dotnet-clean/codecov.yml`, the README block
- Modify: `self-test.yml` adds job `coverage-gate`

**Interfaces:**
- Produces in `lib/coverage_gate.py`:
  - `validate_floor(floor: str, reason: str) -> float`. Parses to a float in `[0, 100]`, otherwise `GateError`. Below 80 with an empty or whitespace-only reason: `GateError("floor <f> is below 80; set floor-override-reason")`.
  - `find_codecov_config(root: str) -> str`. The first existing of `codecov.yml`, `.codecov.yml`, `.github/codecov.yml`, `.github/.codecov.yml`, `dev/codecov.yml`, `dev/.codecov.yml`. Otherwise `GateError("no codecov.yml found")`.
  - `codecov_policy_errors(cfg: dict | None, max_drop: float) -> list[str]`. Reads `coverage.status.project.default`. An error each for: project status missing, `false` or `off`; `informational: true`; `target` present and not `auto`; `threshold` missing, or above `max_drop` once a trailing `%` is stripped.
  - `line_coverage(summary: dict) -> float`. Reads ReportGenerator `JsonSummary` `summary.linecoverage`.
  - `main()` CLI: `validate-floor`, `check-codecov <root> <max-drop>`, `check-floor <summary.json> <floor>`. It prints `::error::` and exits 1 on failure, and writes `Line coverage: <x>% (floor <f>%)` and any override reason to `$GITHUB_STEP_SUMMARY`.
- Produces: `actions/coverage-gate` with inputs `reports` [`**/coverage.cobertura.xml`], `floor` [`80`], `floor-override-reason` [empty], `max-drop` [`1`], `working-directory` [`.`].

- [ ] **Step 1: Write the failing unit tests:**
  - `test_floor_default_ok`, `test_floor_below_80_without_reason_raises`, `test_floor_below_80_whitespace_reason_raises`, `test_floor_below_80_with_reason_ok`, `test_floor_non_numeric_raises`, `test_floor_above_100_raises`
  - `test_find_config_in_dot_github`, `test_find_config_missing_raises`
  - `test_policy_readme_block_ok` (`target: auto`, `threshold: 1%`), `test_policy_threshold_string_5pct`, `test_policy_threshold_number_1_ok`, `test_policy_fixed_target_70pct`, `test_policy_informational`, `test_policy_project_off`, `test_policy_threshold_missing`, `test_policy_empty_file`
  - `test_line_coverage_reads_summary == 83.3`, `test_line_coverage_missing_key_raises`
- [ ] **Step 2:** Run them. Expected: ImportError.
- [ ] **Step 3:** Implement `lib/coverage_gate.py`.
- [ ] **Step 4:** Run them. Expected: all pass.
- [ ] **Step 5: Implement `actions/coverage-gate/action.yml`.** Steps:
  1. if `runner.os != 'Linux'`, fail: "coverage-gate supports Linux runners in v1";
  2. `validate-floor`;
  3. `check-codecov`;
  4. expand `reports` with `shopt -s globstar nullglob` in `working-directory`; zero matches fails with "no coverage reports matched '<glob>'";
  5. install ReportGenerator at a pinned version into `$RUNNER_TEMP/rg` and run `-reports:<joined;list> -targetdir:$RUNNER_TEMP/covsum -reporttypes:JsonSummary -assemblyfilters:-*.Tests;-*Benchmarks*;-*Samples*;-*AotSmoke* -filefilters:-*/tests/*;-*/benchmarks/*;-*/samples/*;-*/obj/*;-*.g.cs`;
  6. `check-floor`.
- [ ] **Step 6: Self-test job `coverage-gate`:** run `dotnet test --collect:"XPlat Code Coverage"` in each fixture. `dotnet-clean` with defaults must pass. `dotnet-lowcov` must fail, with an `id` and an assertion. `dotnet-lowcov` with `floor: 40` and an empty reason must fail at `validate-floor`. With `floor: 40` and a reason, it passes and the summary contains the reason. `reports: nothing/**/*.xml` must fail, the empty-glob case.
- [ ] **Step 7:** Push and run. Expected: green, all assertions hold.
- [ ] **Step 8: Commit:** `feat: add coverage-gate action`

### Task 6: sbom action

**Files:**
- Create: `actions/sbom/action.yml`
- Modify: `self-test.yml` adds job `sbom`

**Interfaces:**
- Produces: `actions/sbom` with inputs `solution` (required), `tag` [empty], `output-name` [empty; empty means `<repo>-<tag>.cdx.json`, or `<repo>.cdx.json` without a tag, where `<repo>` is `github.event.repository.name`], `upload` [`true`]. Output `path`, the SBOM file. `upload: true` with an empty `tag` fails. It runs `gh release upload "$tag" "$path" --clobber` with `GH_TOKEN: ${{ github.token }}`.

- [ ] **Step 1: Self-test job `sbom`:** run the action on `fixtures/dotnet-vulnerable` with `upload: false`. That fixture has a transitive dependency, so it proves transitive output. Validate the file with pinned `cyclonedx-cli validate --input-format json --fail-on-errors`. Assert with `jq` that `components[].name` contains `Newtonsoft.Json`, the transitive package, and contains no project whose name ends in `.Tests`. A second run with `upload: true` and an empty tag must fail, asserted.
- [ ] **Step 2:** Push and run. Expected: fails, because the action is missing.
- [ ] **Step 3:** Implement. Install the `CycloneDX` dotnet tool at a pinned version into `$RUNNER_TEMP/cdx`. Use its flags for JSON output, file name, output directory and test-project exclusion from `--help` of the pinned version; it includes transitive packages by default. Run `dotnet restore` first.
- [ ] **Step 4:** Run self-test. Expected: green.
- [ ] **Step 5: Commit:** `feat: add sbom action`

### Task 7: baseline.yml and the pass path

**Files:**
- Create: `.github/workflows/baseline.yml`
- Modify: `lib/baseline_lib.py` adds `split_languages`; `tests/test_baseline_lib.py`; `self-test.yml` adds job `baseline`

**Interfaces:**
- Consumes: `actions/gitleaks`, `actions/nuget-audit`, `actions/trivy`, and `baseline_lib.py resolve-solution`.
- Produces: `split_languages(value: str) -> list[str]`. Splits on `,`, trims, drops empties, deduplicates while keeping order. An empty result raises `BaselineError`. CLI subcommand `split-languages` prints compact JSON.
- Produces: `baseline.yml` on `workflow_call` with inputs `languages` [`csharp`], `dotnet-version` [`10.0.x`; `global-json` means `global-json-file: global.json`], `solution` [`''`], `dotnet` [`true`], `nuget-audit-level` [`moderate`], `codeql` [`true`], `trivy` [`false`], `trivy-image` [`''`], `baseline-ref` [`v1`]. Top-level `permissions: contents: read`. Each job's first steps: checkout of the caller; checkout of `MarcelRoozekrans/ci-baseline` at `inputs.baseline-ref` into `.ci-baseline`. Jobs:
  - `prepare`: outputs `languages` JSON.
  - `gitleaks`: `name: gitleaks`, checkout with `fetch-depth: 0`. On `pull_request`/`pull_request_target` it runs the action with `log-opts: <base.sha>..<head.sha>`, and fails clearly if `git cat-file -e <base.sha>` fails. Otherwise it writes "Not a pull request: the PR scan runs on pull requests, history-scan.yml covers history." and exits 0.
  - `codeql`: `name: codeql (${{ matrix.language }})`, `needs: prepare`, `permissions: contents: read, security-events: write, actions: read`. With `inputs.codeql == false` it writes "CodeQL disabled by caller input" and exits 0. Otherwise init with `build-mode: none` for `csharp` (codeql's default for others), and analyze with `id: analyze`, `continue-on-error: true`. A following step `if: steps.analyze.outcome == 'failure'` writes a summary naming the two causes, a private repo without Code Security and CodeQL default setup still on, with the README anchor `#codeql-upload-refused`, and exits 1.
  - `nuget-audit`: `name: nuget-audit`. `dotnet == false` writes "NuGetAudit disabled by caller input: not a .NET repo". Otherwise `setup-dotnet`, then the action.
  - `trivy`: `name: trivy`. `trivy == false` writes "Trivy disabled by caller input", otherwise the action.

- [ ] **Step 1:** Unit tests `test_split_languages_trims`, `test_split_languages_dedup`, `test_split_languages_empty_raises`. Run them: they fail. Implement. Run them: they pass.
- [ ] **Step 2: Self-test job `baseline`:** `uses: ./.github/workflows/baseline.yml` with `solution: fixtures/dotnet-clean/DotnetClean.slnx`, `baseline-ref: ${{ github.event.pull_request.head.sha || github.sha }}`, `trivy: true`, and job permissions `contents: read`, `security-events: write`, `actions: read`. The job is named `baseline`, so the check names match the README.
- [ ] **Step 3:** Implement `baseline.yml`.
- [ ] **Step 4:** Run actionlint locally, then push and run self-test on a PR. Expected: checks named exactly `self-test / baseline / gitleaks`, `.../codeql (csharp)`, `.../nuget-audit`, `.../trivy`, all green, and code scanning on this repo shows an analysis from the run. Then run `workflow_dispatch` once and check that gitleaks reports "Not a pull request" in its summary and passes.
- [ ] **Step 5: Commit:** `feat: add baseline reusable workflow`

### Task 8: Releases and the major tag

**Files:**
- Create: `release-please-config.json`, `.release-please-manifest.json`, `.github/workflows/release-please.yml`, `lib/check_baseline_ref.py`, `tests/test_check_baseline_ref.py`
- Modify: `self-test.yml` job `lint` runs `check_baseline_ref.py`

**Interfaces:**
- Produces: `check_baseline_ref.py`, which exits 1 unless the `baseline-ref` default in `baseline.yml` equals `v<major>`. `<major>` comes from `.release-please-manifest.json` `"."`, or, when that key is absent, from `initial-version` in the config. Function `expected_ref(manifest: dict, config: dict) -> str`.
- Config: `release-type: simple`, `bump-minor-pre-major: false`, `include-component-in-tag: false`, `initial-version: "1.0.0"`, and Minos.NET's `changelog-sections`. Manifest `{}`.
- Workflow: on push to `main`, with `permissions: contents: write, pull-requests: write`, `concurrency: release-please`. It mints a release bot App token from `vars.RELEASE_BOT_CLIENT_ID` and `secrets.RELEASE_BOT_PRIVATE_KEY`, as in Minos.NET's `release-please.yml`, then runs `googleapis/release-please-action` with that token. Job `move-major-tag`, `if: release_created`: a checkout with the App token, then `git tag -f "v$MAJOR" "$SHA"` and `git push -f origin "refs/tags/v$MAJOR"`, where `MAJOR` and `SHA` come from the action outputs `major` and `sha`, and a summary line. Its failure is visible; the README covers moving the tag by hand.

- [ ] **Step 1:** Tests `test_expected_ref_from_manifest` (`{".":"2.3.0"}` gives `v2`), `test_expected_ref_initial_version` (`{}` with `initial-version` `1.0.0` gives `v1`), and `test_mismatch_exits_1`, against a temp `baseline.yml` with `default: v2`. Run: fail. Implement. Run: pass.
- [ ] **Step 2:** Write the config, manifest and workflow. Run actionlint. Validate the config against the release-please schema: `npx --yes ajv-cli validate` with the schema from the `$schema` URL.
- [ ] **Step 3: Commit:** `ci: add release-please with major tag move`

### Task 9: README, the adoption guide

**Files:**
- Modify: `README.md`

Content, from spec sections "Adoption in a .NET repo" and Risks, with no private details:
- What the baseline checks, and the `@v1` versioning promise: a stricter default is a major release, and Renovate offers it as a PR.
- The seven adoption steps, each with a copy-paste snippet: the `baseline` caller job with its three permissions; coverage-gate after `dotnet test --collect:"XPlat Code Coverage"`; the `codecov.yml` block with `target: auto`, `threshold: 1%` and the `ignore` list `tests/**`, `benchmarks/**`, `samples/**`, `**/obj/**`, `**/*.g.cs`; sbom in the release job with `contents: write`; the history-scan caller with the `GITLEAKS_CONFIG` secret and "never commit that config"; the `Directory.Build.props` audit properties; the ruleset's required checks by exact name, including `codecov/project`; removing Dependabot.
- An inputs table for `baseline.yml`, `coverage-gate` and `sbom`. `baseline-ref` is marked "self-test only, do not set".
- Overrides: `floor-override-reason` with an example; `NuGetAuditSuppress` per advisory URL with a reason and an issue; `codeql: false` for private repos; why `NoWarn` on NU190x is refused, including the per-package form.
- Troubleshooting anchors: `#codeql-upload-refused` covers turning off default setup and Code Security; also moving `v1` by hand (`git tag -f v1 <sha> && git push -f origin refs/tags/v1`), retriggering codecov, and Linux-only coverage-gate.
- Private repos: what runs, what does not block.

- [ ] **Step 1:** Write the README.
- [ ] **Step 2: Verify:** every input in the inputs table matches an `inputs:` key in the YAML. Run a script that diffs the key sets. Every anchor the workflows reference exists. `grep -nE 'roozekrans\.nl|/home/|192\.168\.|10\.[0-9]+\.' -r .` finds nothing.
- [ ] **Step 3: Commit:** `docs: add adoption guide`

### Task 10: Renovate rule in renovate-config

**Repo:** `MarcelRoozekrans/renovate-config`, branch `feat/ci-baseline-group`. **Pushing and opening the PR need the owner's confirmation at that point.**

**Files:**
- Modify: `default.json` adds one `packageRules` entry

- [ ] **Step 1:** Add the rule:

```json
{
  "description": "Roll out MarcelRoozekrans/ci-baseline as one PR per repo: its reusable workflow and composite actions share one version. No digest pins, so v1.x releases reach callers through the moving v1 tag without PRs, and only a new major opens one. Majors stay manual through the automerge rule above.",
  "matchManagers": ["github-actions"],
  "matchPackageNames": ["MarcelRoozekrans/ci-baseline"],
  "groupName": "ci-baseline",
  "pinDigests": false
}
```

- [ ] **Step 2: Validate:** `npx --yes --package renovate renovate-config-validator default.json`. Expected: `Config validated successfully`.
- [ ] **Step 3: Prove the match:** create a scratch git repo with a workflow that uses `MarcelRoozekrans/ci-baseline/.github/workflows/baseline.yml@v1` and `MarcelRoozekrans/ci-baseline/actions/coverage-gate@v1`. Run `npx --yes renovate --platform=local --dry-run=lookup` with `LOG_LEVEL=debug` and the edited preset inlined as `RENOVATE_CONFIG_FILE`. Expected: both deps are listed with `packageName: MarcelRoozekrans/ci-baseline`, `groupName: ci-baseline`, `pinDigests: false`. If the packageName differs, for example with the path included, change the matcher to fit and record why in the description.
- [ ] **Step 4: Commit:** `feat: group ci-baseline references and skip digest pins`. Ask the owner before pushing and opening the PR.

### Task 11: Release v1.0.0 (owner-gated)

Each item needs the owner; the implementer prepares and asks, and does not act alone.

- [ ] Owner: install the release bot App on `ci-baseline`, set variable `RELEASE_BOT_CLIENT_ID` and secret `RELEASE_BOT_PRIVATE_KEY`, add a `main` ruleset requiring the `self-test` jobs, and confirm that no tag ruleset blocks the App from force-pushing `v1`.
- [ ] Merge the implementation PR. release-please opens `chore(main): release 1.0.0`, and self-test runs on it because of the App token. Owner merges it.
- [ ] **Verify:** `git ls-remote --tags origin` shows `v1.0.0` and `v1` at the same SHA; the GitHub release `v1.0.0` exists; the `move-major-tag` summary names `v1`.
- [ ] Update `docs/planning/STATE.md` in `architecture-governance-engine`: Phase 1.4 is unblocked.
