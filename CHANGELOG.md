# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-10-09

First packaged release of the simulator used for the CATS paper
(previously the single script `legacy/test3.py`).

### Added
- `cats_sim` package (src layout) with one module per concern: DAG, Markov chain,
  attacks, strategies, simulation, experiments, configuration, reporting, plotting.
- Strategy pattern for tip selection algorithms with a registry, so a new algorithm
  is one class plus one registry entry.
- `cats-sim` command line: `run`, `plot`, `algorithms`.
- TOML experiment configurations: `configs/paper.toml`, `configs/quick.toml`,
  `configs/smoke.toml`.
- Reproducible runs: every run derives its own seeded random stream.
- Result files with provenance metadata (`results.json`) plus CSV tables.
- Figures for the three experiments (optional `plot` extra, matplotlib).
- Test-suite (unit, property-based, integration, exact equivalence with the original
  code) and `scripts/verify_against_legacy.py` for statistical equivalence.
- Tooling: uv lockfile, Ruff, mypy (strict), pytest + coverage gate, pre-commit.
- GitHub Actions: CI (lint, types, test matrix, smoke run, build), tagged releases,
  manually triggered experiment runs, Dependabot.
- Documentation: README and architecture decision records in `docs/adr/`.

### Changed
- Experiments are selected through configuration or `--only` instead of commenting
  code out. All experiment parameters that were hard-coded are now configurable, with
  the original values as defaults.
- `alpha_history.csv` now has a header and also contains the composite signal S(t)
  and its components.

### Removed
- Unused parameters of the original functions: `T_DS` and `num_transactions` of the
  security experiment, `lam` of the parasite-chain builder.

The simulation logic itself is unchanged; see
[ADR 0010](docs/adr/0010-behaviour-preserving-refactor.md).

[Unreleased]: https://github.com/OWNER/REPO/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/OWNER/REPO/releases/tag/v1.0.0
