# AGENTS.md: ci-baseline

Reusable GitHub Actions workflows and composite actions that give .NET repos one shared security and
quality baseline: gitleaks, CodeQL, NuGetAudit, optional Trivy, a coverage floor and a release SBOM.
Other repos call them as `MarcelRoozekrans/ci-baseline/...@v1`. Nothing here is compiled or packaged;
what ships is the YAML on the `v1` tag, plus a few Python and shell helpers under `lib/`.

## Layout

- `.github/workflows/baseline.yml`, `conventions.yml` and `history-scan.yml` are the public reusable
  workflows.
  `release-please.yml` and `self-test.yml` run on this repo only.
- `actions/*` are composite actions. `coverage-gate` and `sbom` are public. `commitlint`, `gitleaks`,
  `markdown-links`, `nuget-audit`, `semgrep` and `trivy` are internal: the workflows call them, and they may change in any release.
- `lib/` holds the logic the actions call: `coverage_gate.py`, `baseline_lib.py`, `check_links.py`,
  `install-pinned.sh` and `check_readme.py`, and `lib/commitlint/` the pinned commitlint with its
  lockfile and the house config, and `lib/semgrep/` the hashed requirements for Semgrep. `tests/`
  are the unit tests.
- `fixtures/` are inputs for the self-test, not examples. Most of them are broken on purpose
  (`dotnet-vulnerable`, `dotnet-nowarn*`, `dotnet-lowcov`, `iac-misconfig`, `markdown-broken`,
  `gha-injection`). Do not fix them. Renovate
  ignores them.
- `.github/actionlint.yaml` ignores `job.workflow_sha` and `workflow_repository` errors until
  actionlint supports them; see issue #3.

## Build and test

There is no build. Python 3 and PyYAML are enough; fixtures need the .NET 10 SDK, and the
`coverage-gate` CI job also installs .NET 9.

Commands from `.github/workflows/self-test.yml`:

```sh
# job unit
python3 -m unittest discover -s tests -t .
# job lint, also run by hand: checks the README tables, the codecov block and the heading links
python3 lib/check_readme.py
# job coverage-gate: the fixtures the gate is then run against
dotnet test fixtures/dotnet-clean --collect:"XPlat Code Coverage"
dotnet test fixtures/dotnet-lowcov --collect:"XPlat Code Coverage"
```

The rest of `self-test.yml` runs only on GitHub: actionlint (job lint), calls of `baseline.yml` on
`fixtures/dotnet-clean`, and each internal action on a fixture that must fail it. Those jobs check
the outcome of steps that are expected to fail, so a red step inside them can be correct; read the
`Assert outcomes` step. actionlint is not installed here and its call is not reproduced.

## Conventions and gotchas

- **The `v1` tag is the product.** release-please keeps a release PR open; merging it creates
  `vX.Y.Z` and the `move-major-tag` job in `release-please.yml` force-moves `vMAJOR` to the release
  commit. Only a merged release PR changes what callers get. Every later `feat` or `fix` on `main`
  waits for the next release PR, and merging that one changes every caller's CI at once.
- **A breaking change must be a major release.** README "Versioning": a higher coverage floor, a new
  required check, a lower audit level, a removed or renamed input, output, job name or action input all
  turn existing callers red. Mark such a commit `feat!` or with a `BREAKING CHANGE:` footer so
  release-please cuts `v2`. A tightening committed as plain `feat` or `fix` ships to every `@v1`
  caller. The workflow job names (`gitleaks`, `codeql (csharp)`, `nuget-audit`) are the required status
  check names in callers' rulesets, so renaming one is breaking too.
- **Workflows and internal actions release together.** `baseline.yml` and `history-scan.yml` check
  out this repo at `job.workflow_sha` and call `.ci-baseline/actions/...`. Never point them at an
  `@v1` or `@main` reference of their own actions.
- **README is checked against the YAML.** Change an input in a workflow or action, the matching
  README table and `fixtures/dotnet-clean/codecov.yml` together, then run `lib/check_readme.py`.
  Links from workflows to README headings must keep resolving.
- **Third-party actions are pinned by commit SHA** with a version comment. Downloaded binaries go
  through `lib/install-pinned.sh url sha256 dest`, which verifies the checksum. Keep that when
  adding a tool.
- **`pull_request_target` is refused** by `baseline.yml`; do not weaken that.
- **Moving `v1` by hand** when `move-major-tag` failed: the README section "Moving `v1` by hand"
  has the commands. Set `TAG` to the tag of the release whose job failed; do not assume that is the
  latest release, and leave `v1` alone if it already points at a newer release.

<!-- org-core:start sha256=08a88996bc9165f888fc0260607cfd0670cae128c323e16707c6b452ee66222d (generated from docker-nuc scripts/agents-md/org-core-personal.md; do not edit here) -->
## Org rules

These rules hold in every public MarcelRoozekrans repo.

### Commits and releases

- Conventional Commits. release-please reads them on the default branch, and the changelog sections
  in `release-please-config.json` decide which types count. The standard: `feat`, `fix`, `perf`,
  `deps` and `revert` open or update the release PR; `docs`, `test`, `refactor`, `build`, `ci`,
  `chore` and `style` do not, unless the commit is breaking or has a `Release-As:` footer. The
  release happens when that PR merges. A breaking change needs `!` or a `BREAKING CHANGE:` footer.
- A commit body never contains nested parentheses. release-please cannot parse them and silently
  drops the whole commit from the changelog, while the workflow still reports success.
- After merging a commit that should release, check that it appears in the release-please PR.

### Branches and pull requests

- Every change goes through a branch and a pull request. Never push to the default branch directly.
- A PR body says what the diff does, and nothing the diff does not do.
- Fix review findings in the PR under review, including small ones. File an issue only for a finding
  that belongs to other code, needs a design decision, is its own piece of work, or waits on
  something external.

### CI

- The .NET repos call the shared workflows of `MarcelRoozekrans/ci-baseline`, pinned to `@v1`, never
  `@main`.
- Its coverage gate fails the build when line coverage drops below the floor of 80%, and Codecov
  fails a PR that lowers project coverage by more than 1 percentage point. New code comes with
  tests.
- A repo with a lower floor documents the reason and links the issue that raises it.
<!-- org-core:end -->
