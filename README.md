# ci-baseline

Reusable GitHub Actions workflows and composite actions that give .NET repositories one shared security and quality baseline. A repo calls them instead of copying the jobs, so every repo gets the same checks and a change to the baseline is a versioned release.

## What it checks

| Check | Where it runs | What fails it |
| --- | --- | --- |
| gitleaks | pull requests | a secret in a commit the pull request adds |
| CodeQL | `baseline.yml` | a CodeQL error, or a refused SARIF upload |
| NuGetAudit | `baseline.yml` | a package advisory at or above `nuget-audit-level`, or a `NoWarn` that mutes an audit code |
| Coverage gate | your test job | line coverage below the floor of 80 percent, or a `codecov.yml` that does not enforce the project status |
| Drop in coverage | codecov | a pull request that lowers project coverage by more than 1 percentage point |
| SBOM | your release job | a failed CycloneDX run, or a failed upload to the release |
| Full-history gitleaks | by hand, before a repo goes public | a secret anywhere in any ref |
| Trivy | `baseline.yml`, off by default | a HIGH or CRITICAL finding in the files or in one image |

## Versioning

Callers pin `@v1`. A stricter default is a major release: a higher floor, a new required check or an audit level that fails on more severities becomes `v2`, and Renovate offers it as a pull request. Fixes and additions that do not tighten anything reach callers through the moving `v1` tag without a pull request. Do not call it with `@main`: a change on `main` would turn every caller red at once.

A full commit SHA of a release works as a pin too, for example `@<sha> # v1.2.0`. The workflows check out their internal actions from the commit that the caller's `uses:` resolved to, so a caller on a SHA or on a tag gets the actions from that same commit.

## Adopt it in a .NET repo

The steps fit in one pull request.

### 1. Add the baseline job

Put this in `ci.yml` or in a new `baseline-checks.yml`. Name the job `baseline`: the required check names in step 6 start with the job name.

```yaml
name: baseline-checks

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  baseline:
    permissions:
      contents: read
      security-events: write
      actions: read
    uses: MarcelRoozekrans/ci-baseline/.github/workflows/baseline.yml@v1
    with:
      solution: MyRepo.slnx # empty means the single solution file in the repo root
```

Grant all three permissions even with `codeql: false`. A reusable workflow cannot widen the permissions its caller grants, and GitHub rejects the call at startup when the nested CodeQL job asks for permissions the caller did not give.

The input tables below list everything `baseline.yml` accepts.

### 2. Add the coverage gate and the codecov config

Run the gate right after the test step that collects coverage, in a job on a Linux runner. The test projects need the `coverlet.collector` package. Without it no `coverage.cobertura.xml` is written and the gate fails with `no-reports`.

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: actions/setup-dotnet@0f4a354dd5547a28c70b7853dbd95d5b67886e73 # v6.1.0
        with:
          dotnet-version: 10.0.x
      - run: dotnet test MyRepo.slnx --collect:"XPlat Code Coverage"
      - uses: MarcelRoozekrans/ci-baseline/actions/coverage-gate@v1
      # Upload the reports to codecov here, as you do today. The upload stays in your job.
```

The gate does two things. It merges the Cobertura reports and fails when line coverage is below the floor, and it reads your `codecov.yml` and fails when that file would let the drop check pass quietly. The drop check itself runs in codecov, because it needs the base commit's number.

Set `codecov.yml` in the repo root to exactly this:

```yaml
coverage:
  status:
    project:
      default:
        target: auto
        threshold: 1%
ignore:
  - "tests/**"
  - "benchmarks/**"
  - "samples/**"
  - "**/obj/**"
  - "**/*.g.cs"
```

`lib/check_readme.py` compares this block with `fixtures/dotnet-clean/codecov.yml` on every pull request in this repo, so the two cannot drift apart.

The gate refuses a `codecov.yml` where `coverage.status.project.default`:
- is missing or off;
- sets `informational: true`;
- sets a `target` other than `auto`;
- has no `threshold`, or one above `max-drop`;
- has `paths` or `flags`, which narrow the project status so the drop check no longer covers the whole project.

A top-level `ignore` is allowed.

#### What the gate measures

The gate measures production code only. It leaves out:
- assemblies whose name contains `Tests`, `Benchmarks`, `Samples` or `AotSmoke`;
- files under a `tests`, `benchmarks`, `samples` or `obj` directory, and `*.g.cs` files.

This is a naming rule. A production assembly with one of those words in its name, such as `Contoso.Samples.Core`, is not measured. Name test projects `<Name>.Tests`, and keep production code out of directories called `tests`, `benchmarks` or `samples`. ReportGenerator, which does the merging, ignores case in these filters.

The gate runs on Linux runners only in v1, because it needs PyYAML to read `codecov.yml`. On another OS it fails and says so. A repo that tests on Windows runs the gate in its Linux job.

### 3. Add the SBOM to the release job

The job needs `contents: write` to attach the file to the release, and the release must already exist when the step runs.

```yaml
jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: actions/setup-dotnet@0f4a354dd5547a28c70b7853dbd95d5b67886e73 # v6.1.0
        with:
          dotnet-version: 10.0.x
      - run: dotnet build MyRepo.slnx --configuration Release
      - uses: MarcelRoozekrans/ci-baseline/actions/sbom@v1
        with:
          solution: MyRepo.slnx
          tag: ${{ github.ref_name }} # the release tag
```

`github.ref_name` is the release tag only when the job runs on a tag or release event. A job that runs on `main` in a release-please flow passes release-please's `tag_name` output instead.

The SBOM is CycloneDX JSON, with transitive packages and without test projects. With `upload: false` it only writes the file and reports its path in the `path` output.

### 4. Add the history-scan caller

This workflow scans every ref and all history for secrets. Run it once before a repo goes public.

```yaml
name: history-scan

on: workflow_dispatch

permissions:
  contents: read

jobs:
  history-scan:
    uses: MarcelRoozekrans/ci-baseline/.github/workflows/history-scan.yml@v1
    secrets:
      GITLEAKS_CONFIG: ${{ secrets.GITLEAKS_CONFIG }}
```

`GITLEAKS_CONFIG` is optional. It holds the TOML of a custom gitleaks config, for example extra rules for hostnames or internal addresses. Those patterns describe your private setup, so never commit that config to a repo that is public or will be. Keep it only as a secret. The report is uploaded as an artifact for 7 days, with the secrets redacted.

### 5. Set the audit properties locally

Optional, but a local restore then shows the same findings as CI. In `Directory.Build.props`:

```xml
<Project>
  <PropertyGroup>
    <NuGetAudit>true</NuGetAudit>
    <NuGetAuditMode>all</NuGetAuditMode>
    <NuGetAuditLevel>moderate</NuGetAuditLevel>
  </PropertyGroup>
</Project>
```

CI sets these itself, with the reporting level at `low`, so every advisory shows up in the job summary. `nuget-audit-level` only decides which ones fail the job.

### 6. Require the checks in the `main` ruleset

Add these as required status checks:

- `baseline / gitleaks`
- `baseline / codeql (csharp)`
- `baseline / nuget-audit`
- the name of your own job that runs `coverage-gate`, for example `build`
- `codecov/project`

With another value in `languages` the CodeQL check is named `baseline / codeql (<language>)`, one per language.

Do not require `baseline / prepare` or `baseline / trivy`. `prepare` only builds the CodeQL language list. `trivy` always reports, and says in its summary when it is off.

A required check must report on every pull request. That is why the gitleaks job passes with a note on events that are not pull requests, and why a disabled check still runs and writes the reason into its summary.

### 7. Remove Dependabot

Delete `.github/dependabot.yml` if there is one. Renovate does the dependency updates. It also picks up the `@v1` references.

## Inputs

### baseline.yml inputs

| Input | Default | What it does |
| --- | --- | --- |
| `languages` | `csharp` | Comma-separated CodeQL languages. One `codeql` check per language. |
| `dotnet-version` | `10.0.x` | .NET SDK for the audit. `global-json` uses the repo's `global.json`. |
| `solution` | empty | The `.sln` or `.slnx` to audit. Empty means the single solution file in the repo root, and the job fails if there are several. |
| `dotnet` | `true` | Run NuGetAudit. Set `false` for a repo without .NET code. |
| `nuget-audit-level` | `moderate` | Lowest severity that fails: `low`, `moderate`, `high` or `critical`. |
| `codeql` | `true` | Run CodeQL. With `false` the job still runs and writes "CodeQL disabled by caller input" into its summary. |
| `trivy` | `false` | Run Trivy on the files, and on `trivy-image` when set. Fails on HIGH and CRITICAL. |
| `trivy-path` | `.` | Path that `trivy fs` scans. |
| `trivy-image` | empty | Container image that Trivy also scans. Empty means no image scan. |

### history-scan.yml

`history-scan.yml` takes no inputs. It takes the optional secret `GITLEAKS_CONFIG`, described in step 4.

### coverage-gate inputs

| Input | Default | What it does |
| --- | --- | --- |
| `reports` | `**/coverage.cobertura.xml` | Space-separated globs of Cobertura reports, relative to `working-directory`. Several reports are merged. A glob that matches nothing fails the run. |
| `floor` | `80` | Minimum line coverage in percent. Below 80 needs `floor-override-reason`. |
| `floor-override-reason` | empty | Why the floor is below 80. Printed in the step summary. |
| `max-drop` | `1` | Largest `threshold`, in percentage points, that `codecov.yml` may allow. |
| `working-directory` | `.` | Directory where `codecov.yml` is looked up and the `reports` globs are expanded. |

The action sets the output `result` (`pass`, `below-floor`, `no-reports`, `policy`, `invalid-floor`, `unsupported-os` or `error`) before it fails, so a later step can tell why.

### sbom inputs

| Input | Default | What it does |
| --- | --- | --- |
| `solution` | required | The `.sln`, `.slnx` or project file to describe. It is restored first. |
| `tag` | empty | Release tag to attach the SBOM to. Required when `upload` is `true`. |
| `output-name` | empty | File name of the SBOM. Empty means `<repo>-<tag>.cdx.json`, or `<repo>.cdx.json` without a tag. |
| `upload` | `true` | Attach the file to the release with `gh release upload --clobber`. Needs `contents: write` on the job. |

The gitleaks, nuget-audit and trivy actions in `actions/` are internal. `baseline.yml` and `history-scan.yml` call them, and they can change in any release. Call the workflows instead.

## Overrides

Every override is an explicit line in your own workflow or project files, so it shows up in a diff. None of them lowers a check quietly.

### A floor below 80

A repo that adopts the baseline below 80 percent coverage sets the floor to its current number and gives a reason. Open an issue in that repo to raise it.

```yaml
- uses: MarcelRoozekrans/ci-baseline/actions/coverage-gate@v1
  with:
    floor: 62
    floor-override-reason: "Coverage is 62.4 percent today. Raise it: https://github.com/OWNER/REPO/issues/123"
```

The reason is printed in the job summary. An empty reason with a floor below 80 fails the step.

### NuGetAuditSuppress

An advisory with no fixed version yet blocks every pull request. Suppress that one advisory by its URL, with a comment that gives the reason and links an issue. Do not lower `nuget-audit-level` and do not use `NoWarn`.

```xml
<ItemGroup>
  <!-- GHSA-xxxx-xxxx-xxxx in Some.Package: no fixed version yet. Remove when one ships. https://github.com/OWNER/REPO/issues/456 -->
  <NuGetAuditSuppress Include="https://github.com/advisories/GHSA-xxxx-xxxx-xxxx" />
</ItemGroup>
```

Put it in the project that references the package, or in `Directory.Build.props`. The suppression is visible in the diff, applies to one advisory, and is easy to find and remove once a fix exists.

### Why NoWarn on NU190x is refused

`NoWarn` removes the audit warning, so the restore passes and nobody sees the advisory. The nuget-audit job reads `NoWarn` and `WarningsNotAsErrors` for every project in the solution, for every target framework, and fails when one contains a code that fails at your `nuget-audit-level`. At the default `moderate` those are `NU1902`, `NU1903` and `NU1904`. A `NoWarn` attribute on a `PackageReference` counts too: it silences the audit the same way as a project-wide `NoWarn`.

The guard only checks projects in the solution. A project that is reached only through a `ProjectReference` and is not listed in the solution is not guarded, so keep every project in the solution.

`NU1905` means a package source gave no vulnerability data, so the packages from that source were not checked. It shows up as a warning and in the job summary. It does not fail the job, because that would block every repo with a feed that has no vulnerability data.

### CodeQL off

A private repo without GitHub Code Security cannot upload CodeQL results. Set `codeql: false` in the `with:` block of the baseline job. The job keeps its name and passes, and its summary says CodeQL is off. Keep the three permissions from step 1 anyway.

## Private repos

On the free plan a private repo can neither enforce a ruleset nor upload CodeQL results. Adopt the baseline anyway, with `codeql: false`.

- Runs and goes red on failure: gitleaks on pull requests, NuGetAudit, the coverage gate and the SBOM.
- Runs and says it is off: CodeQL, through the summary line from `codeql: false`.
- Does not block: nothing. Without a ruleset a red check does not stop a merge.

If the repo goes public, add the `main` ruleset from step 6 and remove `codeql: false`. Turn off CodeQL default setup first; see below.

## Troubleshooting

### CodeQL upload refused

The `codeql` job fails when the analysis or the upload fails, with a message that links here. The usual reason is that GitHub refused the SARIF upload, for one of two causes.

1. **CodeQL default setup is on.** It refuses uploads from a workflow. In the repository settings under Code security, switch CodeQL analysis from default setup to off. This baseline runs CodeQL itself.
2. **A private repo without GitHub Code Security.** Code scanning needs it. Either enable Code Security for the repo, or set `codeql: false`.

The workflow cannot tell these apart in advance, because the caller's `GITHUB_TOKEN` cannot read the repo's Code Security settings.

### Moving `v1` by hand

The release workflow moves the `v1` tag to the release commit. When that job fails, callers stay on the old commit. Move the tag yourself:

```sh
git tag -f v1 <sha> && git push -f origin refs/tags/v1
```

`<sha>` is the commit of the release, as shown on the release page. The push needs a token that is allowed to write tags in this repo.

### `codecov/project` never reports

The status needs a coverage upload from your job, and with `target: auto` it compares with the base commit, so the base branch needs an upload too. Check that the upload step ran and succeeded. Re-run the job that uploads. If the status still does not appear, push an empty commit with `git commit --allow-empty -m "ci: retrigger codecov"`. The absolute floor does not depend on codecov, so the gate still checks that part.

### `coverage-gate` fails on a Windows or macOS runner

The gate runs on Linux only in v1. Run it in a Linux job.

## Checks on this repo

`self-test.yml` runs on every pull request. It runs actionlint, calls `baseline.yml` on `fixtures/dotnet-clean`, and runs each internal action on a fixture that must fail it. `python3 -m unittest discover -s tests -t .` runs the unit tests, including `lib/check_readme.py`. That script fails when a table in this README lists different inputs than the YAML, when the codecov block above differs from its fixture, or when a link from a workflow or action points to a heading this README does not have.
