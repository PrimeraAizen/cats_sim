from __future__ import annotations

from typing import Any

import pytest

from cats_sim import CATS, URTS, Tangle, attach_parasite_chain, generate_tangle
from cats_sim.config import load_config
from cats_sim.experiments import (
    AdaptiveRunResult,
    measure_p2,
    run_adaptive,
    run_scalability,
    run_security,
    run_suite,
)
from tests.helpers import SMOKE_CONFIG, make_ctx


def _scalability(seed: int = 0, **overrides: Any):
    kwargs: dict[str, Any] = {
        "label": "URTS",
        "lam": 5.0,
        "num_transactions": 120,
        "num_runs": 3,
        "warmup": 20,
        "h": 1.0,
        "seed": seed,
    }
    return run_scalability(URTS, **(kwargs | overrides))


def test_scalability_result_aggregates_runs():
    result = _scalability()
    assert result.algorithm == "URTS"
    assert len(result.per_run) == 3
    assert result.mean_tips == pytest.approx(sum(result.per_run) / 3)
    assert result.std_tips >= 0


def test_scalability_is_reproducible_and_seed_dependent():
    assert _scalability(seed=1) == _scalability(seed=1)
    assert _scalability(seed=1).per_run != _scalability(seed=2).per_run


def test_scalability_short_runs_use_all_samples():
    result = _scalability(num_transactions=10, warmup=50, num_runs=1)
    assert result.mean_tips > 0


def test_security_reports_p2_per_chain_length():
    results = run_security(
        URTS,
        label="URTS",
        lam=5.0,
        mu=5.0,
        spc_lengths=(5, 10),
        base_transactions=60,
        n_samples=50,
        num_runs=2,
        h=1.0,
        seed=0,
    )
    assert [r.spc_length for r in results] == [5, 10]
    for r in results:
        assert len(r.per_run) == 2
        assert all(0.0 <= p <= 1.0 for p in r.per_run)


def test_measure_p2_counts_active_chain_tips():
    tangle = Tangle()
    ctx = make_ctx(lam=5, seed=0)
    generate_tangle(tangle, URTS(), 60, ctx)
    spc = attach_parasite_chain(tangle, 30, 5, 5, tangle.time, ctx.rng)
    p2 = measure_p2(tangle, URTS(), spc, 500, ctx)
    # URTS picks uniformly: the SPC end is one of the current tips.
    assert p2 == pytest.approx(1 / tangle.num_tips, abs=0.05)
    # Buried chain transactions are not tips and never count.
    assert measure_p2(tangle, URTS(), spc[:-1], 100, ctx) == 0.0


def test_adaptive_runs_track_alpha_and_detection():
    summary = run_adaptive(
        CATS,
        lam=10.0,
        mu=5.0,
        spc_length=10,
        num_transactions=300,
        attach_at=150,
        num_runs=3,
        peak_window=50,
        h=1.0,
        seed=0,
    )
    assert summary.num_runs == len(summary.runs) == len(summary.alpha_peaks) == 3
    assert 0.0 <= summary.detection_rate <= 1.0
    for run in summary.runs:
        assert 0 < run.attach_at_index < len(run.alpha_history)
        assert run.mal_quarantined + run.honest_quarantined == run.quarantine_size
    if summary.detections:
        assert summary.representative.detection_latency is not None
        assert summary.latency_mean is not None
    else:
        assert summary.representative is summary.runs[-1]


def test_alpha_peak_window():
    run = AdaptiveRunResult(
        alpha_history=(0.1, 0.2, 0.9, 0.3, 0.5),
        signal_history=(),
        detection_latency=None,
        quarantine_size=0,
        mal_quarantined=0,
        honest_quarantined=0,
        attach_at_index=3,
    )
    assert run.alpha_peak(1) == 0.3
    assert run.alpha_peak(10) == 0.5
    assert AdaptiveRunResult((0.1,), (), None, 0, 0, 0, attach_at_index=5).alpha_peak(3) == 0.0


def test_suite_runs_every_enabled_experiment():
    config = load_config(SMOKE_CONFIG).with_num_runs(1)
    results = run_suite(config)
    assert config.scalability is not None
    assert config.security is not None
    expected_scalability = len(config.scalability.lambdas) * len(config.scalability.algorithms)
    assert len(results.scalability) == expected_scalability
    assert len(results.security) == len(config.security.algorithms)
    assert results.adaptive is not None


def test_experiment_results_do_not_depend_on_other_experiments():
    config = load_config(SMOKE_CONFIG).with_num_runs(1)
    full = run_suite(config)
    only_security = run_suite(config.restricted_to(["security"]))
    assert only_security.security == full.security
    assert only_security.scalability == ()
    assert only_security.adaptive is None
