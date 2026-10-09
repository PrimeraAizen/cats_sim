# 5. Explicit, seeded random number generation

Status: Accepted (2026-10-09)

## Context

The original script drew every random number from NumPy's *global legacy* state
(`np.random.exponential`, `np.random.choice`, …) and never seeded it. Consequences:

- no run could be reproduced, including the published ones;
- tests could not assert anything about stochastic code;
- results of one experiment depended on how many random numbers earlier experiments
  had consumed.

## Decision

- Every random draw uses an explicitly passed **`numpy.random.Generator`** (PCG64),
  as NumPy's [NEP 19](https://numpy.org/neps/nep-0019-rng-policy.html) recommends for
  new code. The generator travels in `SelectionContext.rng`; no module touches global
  random state. Ruff's `NPY002` rule enforces this.
- Every simulation run gets its **own stream** derived from the configured root seed
  and the run's identity:
  `derive_rng(seed, experiment, algorithm, parameter, run_index)`, built on
  `numpy.random.SeedSequence` with an entropy list. String keys are mapped with CRC-32,
  not Python's `hash()`, which is salted per process for strings.
- The seed is part of the configuration and is written into `results.json`.

## Alternatives considered

- **Seed the global state once** (`np.random.seed(42)`): reproducible only if the
  exact same sequence of calls happens. Enabling or disabling one experiment changes
  every later number, and it is not safe for parallel runs.
- **Pass `RandomState` objects**: bit-compatible with the old global functions, but
  `RandomState` is frozen legacy API with a weaker generator (MT19937). Bit-compatibility
  is worthless here because the original runs were unseeded.
- **One generator per experiment, shared by its runs**: run *k* would still depend on
  runs 0…k-1; per-run streams make every run independently reproducible.

## Consequences

- `cats-sim run cfg.toml --seed N` is fully reproducible: CI checks that two runs
  produce identical results. Running one experiment alone gives exactly the numbers
  it produces inside the full suite (tested).
- Individual runs differ from what the original script would produce, as the
  original's would on every invocation anyway. Equivalence is shown statistically
  (ADR 0010).
