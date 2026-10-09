"""Deterministic derivation of independent random streams.

Every simulation run gets its own :class:`numpy.random.Generator` derived from
the root seed and a tuple of keys (experiment, algorithm, parameter, run
index). Consequences:

* a run is reproducible from ``(seed, keys)`` alone;
* results of one experiment do not depend on which other experiments,
  algorithms or runs were executed before it;
* runs are statistically independent and could be executed in parallel.
"""

from __future__ import annotations

import zlib

import numpy as np

SeedKey = str | int | float


def _as_entropy(key: SeedKey) -> int:
    if isinstance(key, bool):
        raise TypeError("bool is not a valid seed key")
    if isinstance(key, int) and key >= 0:
        return key
    # crc32 instead of hash(): str hashing is randomised per interpreter process.
    return zlib.crc32(repr(key).encode())


def derive_rng(seed: int, *keys: SeedKey) -> np.random.Generator:
    """Return a generator for the stream identified by ``seed`` and ``keys``."""
    if seed < 0:
        raise ValueError("seed must be non-negative")
    entropy = [seed, *(_as_entropy(k) for k in keys)]
    return np.random.default_rng(np.random.SeedSequence(entropy))
