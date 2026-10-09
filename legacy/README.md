# Legacy scripts (provenance record)

These files are the original single-file versions of the simulator, kept **byte for
byte** as they were before the project was packaged. They are not part of the
package, are not linted, and pre-commit never rewrites them.

| File | Role |
|---|---|
| `test3.py` | **Final version**: the code the published results were produced with. It is the reference implementation the package is tested against. |
| `test2.py` | Earlier iteration (security experiment also ran MCMC5 and G-IOTA; adaptive experiment without the PoW batch model). |
| `test.py` | First iteration. |

How the package is kept equivalent to `test3.py`:

- `tests/test_legacy_equivalence.py` loads `test3.py` and checks that every
  deterministic component gives identical results on identical DAGs: weights, tips,
  windows, the Markov-chain tip distribution, the structural check, and the full CATS
  state evolution. This runs in CI.
- `scripts/verify_against_legacy.py` runs both implementations on the same
  experiments and checks that every metric agrees within sampling error. This is
  needed because the random number streams differ.

SHA-1 checksums at the time of packaging:

```
d33eea0b8db7b7303c5626615442681f71c90156  test.py
98aba25e0a32f785b19ef4513121566ef12a37db  test2.py
6a7ba90f0f1b0c7bfdc08a2ae2a0cb663ea599df  test3.py
```
