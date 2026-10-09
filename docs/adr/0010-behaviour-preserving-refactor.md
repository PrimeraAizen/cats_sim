# 10. Behaviour-preserving refactor, verified against the original

Status: Accepted (2026-10-09)

## Context

Published numbers come from `legacy/test3.py`. Restructuring the code must not
change what the simulator computes. Otherwise the project and the paper would
silently diverge. At the same time the random number streams had to change
(ADR 0005), so outputs cannot be compared run by run.

## Decision

1. **Port the logic line for line.** Every formula, constant and control-flow branch
   is kept:
   - δ_max = 2.0; branching threshold 1.2 over 20 nodes; 30 power iterations with
     atol 1e-10; threshold floor 1e-10;
   - S-URTS thresholds and fallback κ = 1.5; warm-up 200; attach points at the
     midpoint;
   - the PoW batch model; the CATS pre-scan and quarantine filtering of snapshots;
   - p₂ measured with 1,000 *real* selections.

   Constants that were magic numbers now have names (`DELTA_MAX`, `THRESHOLD_FLOOR`, …)
   or configuration keys with the original values as defaults.

2. **Changes allowed only where they cannot alter results:**
   - the injected `Generator` instead of global state;
   - removal of parameters that were never read (`T_DS`, `num_transactions` in the
     security experiment, `lam` of the SPC builder);
   - O(1) subtangle windows instead of sorting all IDs (IDs are contiguous, so the
     output is identical);
   - vectorised exponentials (equal to the loop version within 1e-12 relative, tested);
   - a fresh strategy per run instead of `reset()`.

3. **Verify:**
   - **Exactly**: `tests/test_legacy_equivalence.py` runs in CI. It loads the original
     script and compares, on identical random DAGs that include duplicate-parent
     (SPC-like) attachments:
     - cumulative weights, tips, windows and window tips;
     - the Markov tip distribution for several α (relative tolerance 1e-12);
     - the structural anomaly check;
     - the *entire* CATS state trajectory: α̃(t), S(t), σ₁–σ₃, the quarantine
       contents, ages, strong/weak flags and detection counters. CATS's state does
       not depend on the random tip draws, so it can be compared step by step.
   - **Statistically**: `scripts/verify_against_legacy.py` runs both
     implementations on the same experiment settings and checks every metric within
     3 combined standard errors. Covered metrics: tips per algorithm and λ, p₂ per
     algorithm and chain length, CATS detection rate, α̃ peak, and quarantine counts.

## Inherited behaviour, documented but deliberately not changed

These behaviours affect the published numbers. Changing any of them is a
*methodological* decision for the authors, not a refactoring decision. Each is
pinned by a characterisation test, so it cannot change by accident.

1. **Duplicate approvals leak probability mass in the Markov chain.** A transition
   probability is *assigned* per approver entry, not accumulated. Every SPC
   transaction approves its parent twice, so each chain step loses half of the
   walk's mass. This is the main reason S-URTS and CATS find SPC tips "unreachable".
   (`markov.tip_distribution`; `tests/test_markov.py::test_duplicate_approvals_leak_probability_mass`)
2. **SPCs are never classified as *strong* anomalies.** The structural check counts
   `approved_by` entries including duplicates, so a chain has branching ≈ 2 > 1.2.
   Quarantined SPC tips are therefore *weak* and can be released by Module 3.
   (`tests/test_cats.py::test_parasite_chains_are_not_classified_as_strong`)
3. **p₂ sampling mutates CATS.** Each of the 1,000 samples is a real selection that
   advances α̃, the quarantine ages and the reintegration counter.
4. URTS returns `tips * n_tips` (more than `n_tips` items) when fewer tips than
   requested exist. G-IOTA returns two tips when fewer than two exist. The
   simulator normalises both cases afterwards.
5. The adaptive experiment stores the α̃ history of the *first* run with a detection,
   or the last run if none detected.
6. The original module docstring mentions a "slow-build" attack; it was never
   implemented and is not claimed by this project.

## Consequences

- Any future change to the model shows up as a failing equivalence or
  characterisation test. That forces a conscious decision, recorded in a new ADR and
  the changelog.
- The legacy script stays in the repository (`legacy/`, excluded from tooling) as the
  reference implementation.
