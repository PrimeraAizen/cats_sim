"""Statistical equivalence check: cats_sim vs. the original simulator.

The package draws random numbers from an injected ``numpy.random.Generator``,
the original (``legacy/test3.py``) from the global legacy ``np.random`` state,
so individual runs cannot match. This script runs both implementations
independently on the same experiment settings and checks that every metric
agrees within sampling error:

    |mean_new - mean_legacy| < 3 * sqrt(se_new² + se_legacy²)

Deterministic components are compared exactly by
``tests/test_legacy_equivalence.py``.

Usage::

    uv run python scripts/verify_against_legacy.py            # ~15 minutes
    uv run python scripts/verify_against_legacy.py --runs 10  # ~7 minutes, less power

With 20 comparisons at a 3-sigma threshold there is roughly a 5% chance that
one comparison fails by chance; re-run with another ``--seed`` before
concluding there is a real difference.
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np

from cats_sim.experiments import run_adaptive, run_scalability, run_security
from cats_sim.strategies import CATS, GIOTA, MCMC, SURTS, URTS, TipSelectionStrategy

ROOT = Path(__file__).resolve().parents[1]
SURTS_THRESHOLDS = {5: 0.035, 10: 0.015, 15: 0.01, 20: 0.007}
Z_LIMIT = 3.0


def load_legacy() -> ModuleType:
    path = ROOT / "legacy" / "test3.py"
    spec = importlib.util.spec_from_file_location("legacy_test3", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    return module


@dataclass
class Comparison:
    metric: str
    legacy: Sequence[float]
    new: Sequence[float]

    @staticmethod
    def _stats(values: Sequence[float]) -> tuple[float, float]:
        arr = np.asarray(values, dtype=np.float64)
        se = float(arr.std(ddof=1) / math.sqrt(len(arr))) if len(arr) > 1 else 0.0
        return float(arr.mean()), se

    @property
    def z(self) -> float:
        (m1, s1), (m2, s2) = self._stats(self.legacy), self._stats(self.new)
        se = math.hypot(s1, s2)
        if se == 0:
            return 0.0 if m1 == m2 else math.inf
        return (m2 - m1) / se

    @property
    def passed(self) -> bool:
        return abs(self.z) < Z_LIMIT

    def row(self) -> str:
        (m1, s1), (m2, s2) = self._stats(self.legacy), self._stats(self.new)
        verdict = "ok" if self.passed else "DIFFERENT"
        return (
            f"{self.metric:<34} {m1:>9.4f} ± {s1:<7.4f} {m2:>9.4f} ± {s2:<7.4f}"
            f" {self.z:>+6.2f}  {verdict}"
        )


def legacy_algorithms(legacy: ModuleType) -> dict[str, Callable[[], Any]]:
    def surts() -> Any:
        s = legacy.SURTS(alpha=0.001, subtangle_size=500)
        for lam, t in SURTS_THRESHOLDS.items():
            s.set_threshold(lam, t)
        return s

    return {
        "URTS": legacy.URTS,
        "MCMC1": lambda: legacy.MCMC(alpha=0.001),
        "S-URTS": surts,
        "G-IOTA": legacy.GIOTA,
        "CATS": legacy.CATS,
    }


NEW_ALGORITHMS: dict[str, Callable[[], TipSelectionStrategy]] = {
    "URTS": URTS,
    "MCMC1": lambda: MCMC(alpha=0.001),
    "S-URTS": lambda: SURTS(alpha=0.001, subtangle_size=500, thresholds=SURTS_THRESHOLDS),
    "G-IOTA": GIOTA,
    "CATS": CATS,
}


def compare_scalability(
    legacy: ModuleType, runs: int, seed: int, lambdas: Sequence[float], n: int
) -> list[Comparison]:
    out = []
    for lam in lambdas:
        for label, make_legacy in legacy_algorithms(legacy).items():
            np.random.seed(seed)  # noqa: NPY002 - the legacy code uses the global state
            old = legacy.run_scalability_experiment(
                make_legacy(), int(lam), num_transactions=n, num_runs=runs
            )
            new = run_scalability(
                NEW_ALGORITHMS[label],
                label=label,
                lam=lam,
                num_transactions=n,
                num_runs=runs,
                warmup=200,
                h=1.0,
                seed=seed,
            )
            out.append(Comparison(f"tips  λ={lam:g} {label}", old["all_runs"], new.per_run))
            print(f"  {out[-1].row()}", flush=True)
    return out


def compare_security(
    legacy: ModuleType, runs: int, seed: int, labels: Sequence[str], lengths: Sequence[int]
) -> list[Comparison]:
    out = []
    for label in labels:
        np.random.seed(seed)  # noqa: NPY002
        old = legacy.run_security_experiment(
            legacy_algorithms(legacy)[label](), 15, spc_lengths=list(lengths), num_runs=runs
        )
        new = run_security(
            NEW_ALGORITHMS[label],
            label=label,
            lam=15.0,
            mu=5.0,
            spc_lengths=lengths,
            base_transactions=500,
            n_samples=1000,
            num_runs=runs,
            h=1.0,
            seed=seed,
        )
        for result in new:
            m = result.spc_length
            out.append(Comparison(f"p2    m={m} {label}", old[m]["all_runs"], result.per_run))
            print(f"  {out[-1].row()}", flush=True)
    return out


def compare_adaptive(legacy: ModuleType, runs: int, seed: int) -> list[Comparison]:
    np.random.seed(seed)  # noqa: NPY002
    old = [
        legacy.run_adaptive_response_experiment(lam=15, mu=5, spc_length=30, num_transactions=1000)
        for _ in range(runs)
    ]
    new = run_adaptive(
        CATS,
        lam=15.0,
        mu=5.0,
        spc_length=30,
        num_transactions=1000,
        attach_at=250,
        num_runs=runs,
        peak_window=50,
        h=1.0,
        seed=seed,
    )

    def peak(r: dict[str, Any]) -> float:
        post = r["alpha_history"][r["attach_at_index"] : r["attach_at_index"] + 50]
        return max(post) if post else 0.0

    out = [
        Comparison(
            "CATS detected (rate)",
            [float(r["detection_latency"] is not None) for r in old],
            [float(r.detection_latency is not None) for r in new.runs],
        ),
        Comparison("CATS α̃ peak", [peak(r) for r in old], list(new.alpha_peaks)),
        Comparison(
            "CATS malicious quarantined",
            [r["mal_quarantined"] for r in old],
            [r.mal_quarantined for r in new.runs],
        ),
        Comparison(
            "CATS honest quarantined",
            [r["honest_quarantined"] for r in old],
            [r.honest_quarantined for r in new.runs],
        ),
    ]
    for c in out:
        print(f"  {c.row()}", flush=True)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--runs", type=int, default=20, help="runs per metric (default 20)")
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--transactions", type=int, default=1000, help="tangle size, experiment A")
    args = parser.parse_args(argv)

    legacy = load_legacy()
    header = f"{'metric':<34} {'legacy mean ± se':>19} {'new mean ± se':>19} {'z':>6}"
    print(header)
    print("-" * len(header))
    t0 = time.perf_counter()

    comparisons = compare_scalability(legacy, args.runs, args.seed, (5.0, 15.0), args.transactions)
    comparisons += compare_security(
        legacy, args.runs, args.seed, ("URTS", "S-URTS", "CATS"), (10, 30)
    )
    comparisons += compare_adaptive(legacy, args.runs, args.seed)

    failed = [c for c in comparisons if not c.passed]
    print("-" * len(header))
    print(
        f"{len(comparisons) - len(failed)}/{len(comparisons)} metrics agree within "
        f"{Z_LIMIT:g}σ ({args.runs} runs each, {time.perf_counter() - t0:.0f}s)"
    )
    for c in failed:
        print(f"  differs: {c.metric} (z = {c.z:+.2f})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
