# Architecture Decision Records

Each file records one significant decision: the context, the choice, the
alternatives that were considered, and the consequences. The format follows
Michael Nygard's [ADR template](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
ADRs are immutable once accepted. A later change of mind gets a new ADR that
*supersedes* the old one, so the reasoning history stays readable.

| # | Decision | Status |
|---|---|---|
| [0001](0001-python-and-numpy.md) | Keep Python + NumPy as the implementation language | Accepted |
| [0002](0002-package-layout-and-packaging.md) | src layout, `pyproject.toml` (PEP 621) and hatchling | Accepted |
| [0003](0003-uv-for-environments-and-locking.md) | uv for environments and dependency locking | Accepted |
| [0004](0004-strategy-pattern-for-tip-selection.md) | Strategy pattern + registry for tip selection algorithms | Accepted |
| [0005](0005-explicit-seeded-randomness.md) | Explicit, seeded random number generation | Accepted |
| [0006](0006-toml-configuration-and-cli.md) | TOML configuration files and a standard-library CLI | Accepted |
| [0007](0007-quality-toolchain.md) | Ruff, mypy, pytest, Hypothesis, coverage, pre-commit | Accepted |
| [0008](0008-ci-cd-github-actions.md) | CI/CD with GitHub Actions | Accepted |
| [0009](0009-plotting-as-optional-extra.md) | Plotting as an optional extra | Accepted |
| [0010](0010-behaviour-preserving-refactor.md) | Behaviour-preserving refactor, verified against the original | Accepted |

New ADR: copy the structure of an existing one, take the next number, add it to the table.
