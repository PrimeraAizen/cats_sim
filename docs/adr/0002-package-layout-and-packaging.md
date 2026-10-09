# 2. src layout, `pyproject.toml` (PEP 621) and hatchling

Status: Accepted (2026-10-09)

## Context

A 1,200-line script mixed the data structure, five algorithms, the experiment runner
and the result output, with experiments switched on and off by commenting code out.
The project needed a structure that is installable, importable from tests and
notebooks, and divided into units that can be tested independently.

## Decision

- **Installable package `cats_sim` in a `src/` layout**, one module per concern:

  | Module | Responsibility |
  |---|---|
  | `tangle.py` | DAG data structure only |
  | `markov.py` | transition weights, absorbing-chain tip distribution (shared by S-URTS and CATS) |
  | `attacks.py` | adversary models (parasite chain); moved out of `Tangle` (single responsibility) |
  | `strategies/` | one module per tip selection algorithm + the interface (ADR 0004) |
  | `simulation.py` | Poisson/PoW-batch tangle growth (the Strategy *context*) |
  | `experiments.py` | the three experiments and their result types |
  | `config.py`, `cli.py`, `reporting.py`, `plotting.py` | I/O edges, kept apart from the model |

- **`pyproject.toml` as the single configuration file** (PEP 621 metadata; PEP 517
  build; PEP 735 dependency groups; PEP 639 license expression). It also holds the
  Ruff, mypy, pytest and coverage settings.
- **hatchling** as build backend.
- **`py.typed`** marker (PEP 561) so downstream code type-checks against the package.
- Console entry point `cats-sim` plus `python -m cats_sim`.

## Alternatives considered

- **Flat layout** (`cats_sim/` at the root): tests can then import the package from the
  working tree even when packaging is broken. The src layout makes tests run against
  the *installed* package, which catches missing files and wrong metadata. The PyPA
  packaging guide recommends it for this reason.
- **setuptools + `setup.py`**: works, but imperative configuration is deprecated in
  favour of declarative `pyproject.toml`; more legacy surface.
- **Poetry / PDM as backend**: tie the build to a specific front-end tool. hatchling
  is a small PyPA-maintained backend that any front end (pip, uv, build) can drive.
- **Keeping a single script**: impossible to unit-test parts in isolation, and every
  experiment variant needs code edits.

## Consequences

- `pip install .` / `uv sync` give a working `cats-sim` command; the package is
  importable from notebooks without `sys.path` hacks.
- Dependencies point one way: model ← simulation ← experiments ← reporting/CLI. The
  model never imports I/O code.
