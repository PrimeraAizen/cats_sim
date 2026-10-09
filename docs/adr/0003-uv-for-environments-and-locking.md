# 3. uv for environments and dependency locking

Status: Accepted (2026-10-09)

## Context

Research results must be reproducible months later on other machines. That requires
pinning the *exact* versions of every package, including transitive ones (NumPy's
random streams and floating-point kernels can change between releases). The previous
setup was an unpinned virtualenv shared with other projects.

## Decision

Use **[uv](https://docs.astral.sh/uv/)** for environment management, with a committed
**`uv.lock`**:

- `uv sync` creates `.venv` with exactly the locked versions; `uv run <cmd>` runs inside it.
- The lock is *universal*: one file covers all supported Python versions and
  platforms. For example, it locks NumPy 2.4.x for Python 3.11 and 2.5.x for ≥ 3.12.
- Development tools live in a PEP 735 `[dependency-groups] dev` group. Users of the
  package do not install them.
- `.python-version` pins the default interpreter for development.
- CI uses `uv sync --locked`, which fails if `uv.lock` is out of date with
  `pyproject.toml`.

## Alternatives considered

| Option | Why not |
|---|---|
| pip + `requirements.txt` | No lock of transitive dependencies unless pip-tools is added; separate files per purpose; no Python version management. |
| pip-tools | Locks well, but per-platform/per-Python lock files and a separate venv tool. |
| Poetry | Mature lockfile, but its own non-standard dependency groups (historically) and a slower resolver. It also owns the build backend (see ADR 0002). |
| conda | Useful for non-Python binaries, which this project does not need; slower, and the environment files are not lock files by default. |

## Consequences

- One tool for Python install, venv, locking and running. It is fast enough for CI
  (with caching) and for quick local re-syncs.
- Standard metadata only: `pip install -e .` still works for anyone not using uv.
  The lock file is uv-specific, but the dependency *ranges* stay in `pyproject.toml`.
- Dependabot keeps the lock file current (ADR 0008).
