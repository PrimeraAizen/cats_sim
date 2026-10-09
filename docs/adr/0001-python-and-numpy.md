# 1. Keep Python + NumPy as the implementation language

Status: Accepted (2026-10-09)

## Context

The simulator already existed as a validated Python/NumPy script (`legacy/test3.py`)
that produced the published results. Turning it into a maintainable project raised
the question of whether to keep the language.

What matters for this project, in order:

1. **Correctness and trust**: results feed a paper, so reviewers must be able to read
   and check the algorithms against their equations.
2. **Continuity**: the numbers already reported must remain reproducible with the new
   code base (see ADR 0010).
3. **Ecosystem**: linear algebra (Markov-chain power iteration), random number
   generation, statistics and plotting.
4. **Performance**: good enough for 100 runs per data point. The dense 500×500 matrix
   power iteration is the dominant cost and already runs in NumPy's compiled kernels.

## Decision

Keep **Python (≥ 3.11)** with **NumPy** as the only runtime dependency.

- Python 3.11 is the floor: it brings `tomllib` (ADR 0006), `datetime.UTC` and faster
  CPython, and it is still within its security-support window. CI tests 3.11–3.14.
- NumPy ≥ 2.0 for the `Generator` API (ADR 0005) and typed arrays.

## Alternatives considered

| Option | Why not |
|---|---|
| Rewrite in C++/Rust | Much faster pure-Python loops, but a rewrite would re-introduce bugs into validated logic and make the code harder for most researchers to review. The heavy numerical part is already compiled NumPy code. |
| Julia | Good for simulations, but smaller ecosystem and audience; same rewrite risk. |
| Python + a DES framework (SimPy) | The model is a batched Poisson process with a fixed PoW window, not a general event queue; a framework adds a dependency without simplifying the code. |
| Python + NetworkX for the DAG | Convenient, but much slower for incremental weight updates and adds a dependency; the hand-written adjacency lists are tiny and fully tested. |
| Python + SciPy sparse matrices | Could speed up the Markov chain, but changes floating-point summation order relative to the published code. Kept as a possible optimisation (it would need its own ADR). |

## Consequences

- No rewrite risk: the package is a restructuring of the original code, verified
  against it (ADR 0010).
- Pure-Python loops (random walks, BFS) limit speed. Independent seeded runs
  (ADR 0005) make process-level parallelism a straightforward later step if needed.
