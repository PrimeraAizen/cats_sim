# 7. Quality toolchain: Ruff, mypy, pytest, Hypothesis, coverage, pre-commit

Status: Accepted (2026-10-09)

## Context

The simulator's output is a scientific claim, so defects are costly: a silent bug
changes the paper's numbers. The project needs automatic checks that are fast enough
to run on every commit and identical locally and in CI.

## Decision

| Concern | Tool | Configuration |
|---|---|---|
| Lint + import order + modernisation | **Ruff** | rule sets E, W, F, I, B, UP, SIM, C4, N, NPY, PT, RUF |
| Formatting | **Ruff formatter** | 100 columns |
| Static types | **mypy**, `strict = true` | src, tests (relaxed: untyped test functions allowed), scripts |
| Tests | **pytest** | `--strict-markers`, `--strict-config`, warnings are errors |
| Property-based tests | **Hypothesis** | DAG invariants over random attachment sequences |
| Coverage | **pytest-cov / coverage.py** | branch coverage, CI fails below 85% |
| Commit-time checks | **pre-commit** | whitespace/YAML/TOML hygiene, Ruff, mypy |

Test layers in `tests/`:

1. **Unit tests** per module, against hand-built DAGs with known answers. For example,
   the cumulative weights of a diamond DAG, or the analytic walk probability
   1/(1+e²).
2. **Property-based tests** (`test_tangle_properties.py`): for *any* attachment
   sequence, weights equal 1 + number of descendants, tips are exactly the unapproved
   transactions, edges are symmetric and point backwards.
3. **Contract tests**: every registered strategy passes the same interface checks
   (ADR 0004).
4. **Characterisation tests** pin inherited behaviour that is surprising but
   affects published results (ADR 0010).
5. **Equivalence tests** against the original script (ADR 0010).
6. **Integration/CLI tests**: complete runs with the smoke config, reproducibility,
   experiment independence, output files, figures.

## Alternatives considered

- **flake8 + isort + black + pyupgrade**: four tools, four configurations, slower.
  Ruff implements these rules in one tool.
- **pyright** instead of mypy: faster, and it is used in many editors. mypy is the
  reference implementation, and `mypy --strict` is the more common CI gate. Either
  would do.
- **unittest**: no fixtures or parametrisation, and noisier assertions. pytest is the
  de-facto standard.
- **A higher coverage gate (95–100%)**: actual coverage is ~97%, but a gate at 100%
  rewards testing trivial branches. 85% guards against untested new modules without
  that pressure.

## Consequences

- `uv run pre-commit run --all-files` runs locally the same checks CI runs; the tool
  versions are pinned by `uv.lock` and `.pre-commit-config.yaml`.
- Type annotations document units and shapes (`FloatArray`, `TxId`) and catch
  interface mismatches between strategies at check time.
