# 8. CI/CD with GitHub Actions

Status: Accepted (2026-10-09)

## Context

The repository is hosted on GitHub. Checks must run on every change. Releases and
long experiment runs should not depend on one person's laptop.

## Decision

Three workflows in `.github/workflows/` plus Dependabot:

**`ci.yml`: continuous integration** (push to `main`, pull requests, manual):

| Job | What it guarantees |
|---|---|
| `quality` | Ruff lint, Ruff format check, mypy strict |
| `test` | pytest + coverage gate on Ubuntu × Python 3.11, 3.12, 3.13, 3.14, plus macOS / 3.14 (the development platform); coverage summary and `coverage.xml` artifact |
| `smoke` | `cats-sim run configs/smoke.toml` + `cats-sim plot`: the deliverable works end to end; output uploaded as an artifact |
| `build` | `uv build`, then the wheel is installed into a clean venv and executed. This catches packaging mistakes that the src-layout tests cannot see. Runs only after the other jobs pass. |

**`release.yml`: continuous delivery** on a `vX.Y.Z` tag. It checks that the tag
equals the version in `pyproject.toml`, runs the tests, builds, and creates a GitHub
Release with the sdist and wheel attached (`gh release create`, no third-party
release action).

**`experiments.yml`: research delivery**, started manually with a config, a seed and
an optional experiment subset. It runs the simulation in a clean, locked environment
and uploads results and figures (PNG + PDF) as an artifact kept for 90 days. The
artifact is tied to the exact commit, which makes paper figures traceable.

Practices applied in all workflows:

- least-privilege `permissions: contents: read`; write access only in the release job;
- `concurrency` cancels superseded runs;
- `uv sync --locked` (the CI environment equals the lock file);
- uv cache enabled;
- `fail-fast: false` so one failing Python version does not hide the others;
- user inputs are passed through environment variables, never interpolated into
  shell code (avoids script injection);
- validated with `actionlint`.

**Dependabot** opens grouped weekly PRs for GitHub Actions and the uv lock file. CI
then checks every update.

## Alternatives considered

- **GitLab CI / Jenkins**: fine tools, but the code is on GitHub. Native integration
  (checks on PRs, artifacts, releases, Dependabot) wins.
- **Publishing to PyPI**: not needed for a research artifact; GitHub Releases are
  enough and avoid managing PyPI credentials. Adding a trusted-publishing step later
  would be a few lines.
- **Pinning actions to commit SHAs**: the strongest supply-chain protection, but less
  readable. Major-version tags plus Dependabot updates are a reasonable trade-off for
  a repository without secrets. Switch to SHAs if secrets are ever added.
- **Running the full paper suite on every push**: hours of compute per commit. The
  smoke run covers the code paths; full runs are triggered on demand.

## Consequences

- A change can only reach `main` green (once branch protection requires the CI
  checks; enable it in the repository settings).
- A release is one `git tag` + `git push --tags`.
