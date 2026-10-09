# 6. TOML configuration files and a standard-library CLI

Status: Accepted (2026-10-09)

## Context

Experiment parameters (λ values, runs, SPC lengths, algorithm parameters, S-URTS
thresholds) were hard-coded in `main()`. Experiments were selected by commenting
blocks in and out, which is error-prone and leaves no record of what was run.

## Decision

- **Declarative TOML configuration** (`configs/paper.toml`, `quick.toml`,
  `smoke.toml`), parsed with the standard-library `tomllib`.
- **Strict validation into frozen dataclasses** (`config.py`): unknown keys, wrong
  types, out-of-range values and references to undefined algorithms fail with a
  message naming the offending key. A typo such as `num_run = 10` must not silently
  fall back to a default of 100 runs.
- Algorithm parameters are validated at load time by constructing the strategy once.
- The resolved configuration is written into `results.json` next to the results.
- **`argparse` CLI** with three sub-commands:
  - `run CONFIG [--only …] [--seed] [--runs] [-o DIR]`
  - `plot RESULTS_DIR`
  - `algorithms`
  `main(argv) -> int` is directly callable from tests. Exit codes: 0 ok,
  1 nothing to plot, 2 configuration error, 3 missing optional dependency.
- Progress goes to `logging` (stderr); result tables go to stdout.

## Alternatives considered

| Option | Why not |
|---|---|
| YAML | Needs a third-party parser; implicit typing pitfalls (`no` → `False`, `1e3` as a string). TOML is the Python standard (`pyproject.toml`). |
| JSON | No comments, which are essential to explain parameters in a research config. |
| Pydantic / attrs for validation | Excellent, but a runtime dependency for ~10 fields. The hand-written reader is ~100 lines and fully tested. |
| Hydra / OmegaConf | Powerful sweeps, but heavy and opinionated (working-directory changes, YAML). |
| Click / Typer CLI | Nicer help output, but a dependency for three sub-commands; `argparse` is sufficient and always available. |

## Consequences

- NumPy remains the only runtime dependency.
- An experiment is fully described by a version-controlled file, a seed and the
  package version, all of which are recorded in the output.
