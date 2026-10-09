"""Experiment runners reproducing the evaluation of the CATS paper.

* A — scalability: mean tip count under benign conditions;
* B — security: probability p₂ that a TSA selects a parasite-chain tip;
* C — adaptive response: CATS α̃(t) dynamics and detection latency.

Every run builds a fresh strategy instance and gets its own random stream
(:func:`cats_sim.seeding.derive_rng`), so runs are independent and
reproducible.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

from cats_sim.attacks import attach_parasite_chain
from cats_sim.config import SuiteConfig
from cats_sim.seeding import derive_rng
from cats_sim.simulation import generate_tangle
from cats_sim.strategies import TipSelectionStrategy
from cats_sim.strategies.base import SelectionContext
from cats_sim.strategies.cats import CATS, CompositeSignal
from cats_sim.tangle import Tangle, TxId

logger = logging.getLogger(__name__)

StrategyFactory = Callable[[], TipSelectionStrategy]
CatsFactory = Callable[[], CATS]


# ---------------------------------------------------------------- results


@dataclass(frozen=True)
class ScalabilityResult:
    algorithm: str
    lam: float
    mean_tips: float
    std_tips: float
    per_run: tuple[float, ...]


@dataclass(frozen=True)
class SecurityResult:
    algorithm: str
    spc_length: int
    mean_p2: float
    std_p2: float
    per_run: tuple[float, ...]


@dataclass(frozen=True)
class AdaptiveRunResult:
    alpha_history: tuple[float, ...]
    signal_history: tuple[CompositeSignal, ...]
    detection_latency: int | None  # tip selections between attack and first detection
    quarantine_size: int
    mal_quarantined: int
    honest_quarantined: int
    attach_at_index: int  # index into alpha_history at which the SPC was attached

    def alpha_peak(self, window: int) -> float:
        """Maximum α̃ within ``window`` selections after the attack (0 if none)."""
        post = self.alpha_history[self.attach_at_index : self.attach_at_index + window]
        return max(post) if post else 0.0


@dataclass(frozen=True)
class AdaptiveSummary:
    num_runs: int
    detections: int
    latency_mean: float | None
    latency_std: float | None
    alpha_peak_mean: float
    alpha_peak_std: float
    mal_quarantined_mean: float
    honest_quarantined_mean: float
    representative: AdaptiveRunResult  # first run with a detection (else the last run)
    runs: tuple[AdaptiveRunResult, ...] = field(repr=False)
    alpha_peaks: tuple[float, ...] = field(repr=False)

    @property
    def detection_rate(self) -> float:
        return self.detections / self.num_runs


@dataclass(frozen=True)
class SuiteResults:
    scalability: tuple[ScalabilityResult, ...] = ()
    security: tuple[SecurityResult, ...] = ()
    adaptive: AdaptiveSummary | None = None


# ----------------------------------------------------------- experiment A


def run_scalability(
    factory: StrategyFactory,
    *,
    label: str,
    lam: float,
    num_transactions: int,
    num_runs: int,
    warmup: int,
    h: float,
    seed: int,
) -> ScalabilityResult:
    """Mean steady-state tip count of one algorithm at arrival rate ``lam``."""
    per_run: list[float] = []
    for run in range(num_runs):
        ctx = SelectionContext(lam, h, derive_rng(seed, "scalability", label, lam, run))
        tip_counts = generate_tangle(Tangle(), factory(), num_transactions, ctx)
        steady = tip_counts[warmup:] if len(tip_counts) > warmup else tip_counts
        per_run.append(float(np.mean(steady)))

    return ScalabilityResult(
        algorithm=label,
        lam=lam,
        mean_tips=float(np.mean(per_run)),
        std_tips=float(np.std(per_run)),
        per_run=tuple(per_run),
    )


# ----------------------------------------------------------- experiment B


def _attach_point(tangle: Tangle, preferred: TxId) -> TxId:
    return preferred if preferred in tangle.transactions else tangle.num_transactions // 2


def measure_p2(
    tangle: Tangle,
    strategy: TipSelectionStrategy,
    malicious_ids: Sequence[TxId],
    n_samples: int,
    ctx: SelectionContext,
) -> float:
    """Fraction of ``n_samples`` two-tip selections that pick an active SPC tip.

    Note: for stateful strategies (CATS) every sample is a real selection and
    updates the strategy's state, exactly as in the original simulator.
    """
    active_malicious_tips = set(malicious_ids) & tangle.tips
    malicious = total = 0
    for _ in range(n_samples):
        for tip in strategy.select_tips(tangle, 2, ctx):
            total += 1
            if tip in active_malicious_tips:
                malicious += 1
    return malicious / max(total, 1)


def run_security(
    factory: StrategyFactory,
    *,
    label: str,
    lam: float,
    mu: float,
    spc_lengths: Sequence[int],
    base_transactions: int,
    n_samples: int,
    num_runs: int,
    h: float,
    seed: int,
) -> list[SecurityResult]:
    """p₂ of one algorithm for each parasite-chain length.

    Following Guo et al. (2025): build an honest tangle, attach an SPC at its
    midpoint, add one PoW window of honest transactions so the TSA "sees" the
    SPC before it is buried, then estimate p₂ by repeated tip selection.
    """
    results: list[SecurityResult] = []
    for m in spc_lengths:
        p2_values: list[float] = []
        for run in range(num_runs):
            ctx = SelectionContext(lam, h, derive_rng(seed, "security", label, m, run))
            tangle = Tangle()
            strategy = factory()

            # Phase 1: honest tangle
            generate_tangle(tangle, strategy, base_transactions, ctx)

            # Phase 2: parasite chain at the midpoint
            malicious_ids = attach_parasite_chain(
                tangle,
                attach_point=_attach_point(tangle, base_transactions // 2),
                chain_length=m,
                mu=mu,
                start_time=tangle.time,
                rng=ctx.rng,
            )

            # Phase 3: one PoW window of honest transactions
            generate_tangle(tangle, strategy, max(int(lam * h), 5), ctx)

            p2_values.append(measure_p2(tangle, strategy, malicious_ids, n_samples, ctx))

        results.append(
            SecurityResult(
                algorithm=label,
                spc_length=m,
                mean_p2=float(np.mean(p2_values)),
                std_p2=float(np.std(p2_values)),
                per_run=tuple(p2_values),
            )
        )
    return results


# ----------------------------------------------------------- experiment C


def run_adaptive_once(
    factory: CatsFactory,
    *,
    lam: float,
    mu: float,
    spc_length: int,
    num_transactions: int,
    attach_at: int,
    h: float,
    rng: np.random.Generator,
) -> AdaptiveRunResult:
    """Track CATS α̃(t) when an SPC is attached mid-experiment (one run)."""
    cats = factory()
    tangle = Tangle()
    ctx = SelectionContext(lam, h, rng)

    # Phase 1: honest tangle up to the attack
    generate_tangle(tangle, cats, attach_at, ctx)
    attach_at_index = len(cats.alpha_history)
    counter_at_attach = cats.tx_counter

    # Phase 2: parasite chain
    malicious_set = set(
        attach_parasite_chain(
            tangle,
            attach_point=_attach_point(tangle, attach_at // 2),
            chain_length=spc_length,
            mu=mu,
            start_time=tangle.time,
            rng=rng,
        )
    )

    # Phase 3: continue the honest tangle
    generate_tangle(tangle, cats, num_transactions - attach_at, ctx)

    latencies = [
        entry.detection_tx - counter_at_attach
        for tx_id, entry in cats.quarantine.items()
        if tx_id in malicious_set
    ]
    mal_quarantined = sum(1 for tx_id in cats.quarantine if tx_id in malicious_set)

    return AdaptiveRunResult(
        alpha_history=tuple(cats.alpha_history),
        signal_history=tuple(cats.signal_history),
        detection_latency=min(latencies) if latencies else None,
        quarantine_size=len(cats.quarantine),
        mal_quarantined=mal_quarantined,
        honest_quarantined=len(cats.quarantine) - mal_quarantined,
        attach_at_index=attach_at_index,
    )


def run_adaptive(
    factory: CatsFactory,
    *,
    lam: float,
    mu: float,
    spc_length: int,
    num_transactions: int,
    attach_at: int,
    num_runs: int,
    peak_window: int,
    h: float,
    seed: int,
) -> AdaptiveSummary:
    """Repeat :func:`run_adaptive_once` and aggregate detection statistics."""
    runs = tuple(
        run_adaptive_once(
            factory,
            lam=lam,
            mu=mu,
            spc_length=spc_length,
            num_transactions=num_transactions,
            attach_at=attach_at,
            h=h,
            rng=derive_rng(seed, "adaptive", run),
        )
        for run in range(num_runs)
    )
    latencies = [r.detection_latency for r in runs if r.detection_latency is not None]
    peaks = tuple(r.alpha_peak(peak_window) for r in runs)
    representative = next((r for r in runs if r.detection_latency is not None), runs[-1])

    return AdaptiveSummary(
        num_runs=num_runs,
        detections=len(latencies),
        latency_mean=float(np.mean(latencies)) if latencies else None,
        latency_std=float(np.std(latencies)) if latencies else None,
        alpha_peak_mean=float(np.mean(peaks)),
        alpha_peak_std=float(np.std(peaks)),
        mal_quarantined_mean=float(np.mean([r.mal_quarantined for r in runs])),
        honest_quarantined_mean=float(np.mean([r.honest_quarantined for r in runs])),
        representative=representative,
        runs=runs,
        alpha_peaks=peaks,
    )


# ------------------------------------------------------------------ suite


def run_suite(config: SuiteConfig) -> SuiteResults:
    """Run every enabled experiment of ``config``."""
    algos = config.algorithms
    scalability: list[ScalabilityResult] = []
    security: list[SecurityResult] = []
    adaptive: AdaptiveSummary | None = None

    if (sc := config.scalability) is not None:
        logger.info("Experiment A: scalability (benign conditions)")
        for lam in sc.lambdas:
            for label in sc.algorithms:
                t0 = time.perf_counter()
                result = run_scalability(
                    algos[label].create,
                    label=label,
                    lam=lam,
                    num_transactions=sc.num_transactions,
                    num_runs=sc.num_runs,
                    warmup=sc.warmup,
                    h=config.h,
                    seed=config.seed,
                )
                scalability.append(result)
                logger.info(
                    "  λ=%-5g %-8s mean tips = %6.1f ± %5.2f  (%.1fs)",
                    lam, label, result.mean_tips, result.std_tips, time.perf_counter() - t0,
                )  # fmt: skip

    if (se := config.security) is not None:
        logger.info("Experiment B: security (parasite chain), λ=%g, µ=%g", se.lam, se.mu)
        for label in se.algorithms:
            t0 = time.perf_counter()
            results = run_security(
                algos[label].create,
                label=label,
                lam=se.lam,
                mu=se.mu,
                spc_lengths=se.spc_lengths,
                base_transactions=se.base_transactions,
                n_samples=se.n_samples,
                num_runs=se.num_runs,
                h=config.h,
                seed=config.seed,
            )
            security.extend(results)
            logger.info("  %-8s (%.1fs)", label, time.perf_counter() - t0)
            for r in results:
                logger.info("    m=%3d: p₂ = %.4f ± %.4f", r.spc_length, r.mean_p2, r.std_p2)

    if (ad := config.adaptive) is not None:
        logger.info("Experiment C: CATS adaptive response dynamics")
        spec = algos[ad.algorithm]

        def cats_factory() -> CATS:
            strategy = spec.create()
            assert isinstance(strategy, CATS)  # guaranteed by config validation
            return strategy

        t0 = time.perf_counter()
        adaptive = run_adaptive(
            cats_factory,
            lam=ad.lam,
            mu=ad.mu,
            spc_length=ad.spc_length,
            num_transactions=ad.num_transactions,
            attach_at=ad.attach_at,
            num_runs=ad.num_runs,
            peak_window=ad.peak_window,
            h=config.h,
            seed=config.seed,
        )
        logger.info("  %d runs (%.1fs)", ad.num_runs, time.perf_counter() - t0)

    return SuiteResults(tuple(scalability), tuple(security), adaptive)
