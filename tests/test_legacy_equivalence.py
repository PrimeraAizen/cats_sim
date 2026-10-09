"""Behaviour preservation: compare the package against the original simulator.

``legacy/test3.py`` is the code the published results were produced with.
Random draws differ (global ``np.random`` vs. an injected ``Generator``), so
stochastic behaviour is compared statistically by
``scripts/verify_against_legacy.py``. Everything *deterministic* is compared
here exactly, on identical DAGs:

* cumulative weights, tips, subtangle windows and window tips;
* the absorbing-Markov-chain tip distribution (S-URTS / CATS module 2);
* the CATS structural anomaly check;
* the complete CATS state evolution (α̃, signals, quarantine), which does not
  depend on the random draws used to pick the returned tips.
"""

from __future__ import annotations

import importlib.util
import sys
from typing import Any

import numpy as np
import pytest

from cats_sim import CATS, Tangle
from cats_sim.markov import tip_distribution
from tests.helpers import ROOT, make_ctx

LEGACY_PATH = ROOT / "legacy" / "test3.py"


@pytest.fixture(scope="module")
def legacy() -> Any:
    if not LEGACY_PATH.is_file():
        pytest.skip("legacy/test3.py is not available")
    spec = importlib.util.spec_from_file_location("legacy_test3", LEGACY_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode, previous = True, sys.dont_write_bytecode
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def _random_edges(seed: int, n: int) -> list[list[int]]:
    """Random DAG with honest-looking and SPC-like (duplicate-parent) attachments."""
    rng = np.random.default_rng(seed)
    edges: list[list[int]] = []
    for i in range(1, n + 1):
        recent = max(0, i - 15)  # keep the DAG narrow, like a real tangle
        if rng.random() < 0.15:
            parent = int(rng.integers(recent, i))
            edges.append([parent, parent])
        else:
            edges.append([int(p) for p in rng.integers(recent, i, size=2)])
    return edges


def _both(legacy: Any, edges: list[list[int]]) -> tuple[Any, Tangle]:
    old, new = legacy.Tangle(), Tangle()
    for i, parents in enumerate(edges, start=1):
        old.add_transaction(parents, float(i))
        new.add_transaction(parents, float(i))
    return old, new


@pytest.mark.parametrize("seed", range(5))
def test_dag_bookkeeping_is_identical(legacy, seed):
    old, new = _both(legacy, _random_edges(seed, 300))
    assert old.tips == new.tips
    for tx_id, tx in new.transactions.items():
        assert old.transactions[tx_id].cumulative_weight == tx.cumulative_weight
        assert old.transactions[tx_id].approved_by == tx.approved_by
    for window in (1, 50, 299, 1000):
        ids = new.get_subtangle(window)
        assert old.get_subtangle(window) == ids
        assert old.get_tips_in_subtangle(ids) == new.get_tips_in_subtangle(ids)


@pytest.mark.parametrize("seed", range(5))
@pytest.mark.parametrize("alpha", [0.0, 0.001, 0.05, 0.5])
def test_tip_distribution_is_identical(legacy, seed, alpha):
    old, new = _both(legacy, _random_edges(seed, 300))
    for window in (50, 200):
        ids = new.get_subtangle(window)
        tips = new.get_tips_in_subtangle(ids)
        expected = legacy.SURTS(alpha=alpha)._compute_stationary_distribution(old, ids, tips)
        np.testing.assert_allclose(tip_distribution(new, ids, tips, alpha), expected, rtol=1e-12)


@pytest.mark.parametrize("seed", range(5))
def test_structural_check_is_identical(legacy, seed):
    old, new = _both(legacy, _random_edges(seed, 200))
    old_cats, new_cats = legacy.CATS(), CATS()
    for tx_id in new.transactions:
        assert old_cats._check_structural_anomaly(old, tx_id) == new_cats._check_structural_anomaly(
            new, tx_id
        )


@pytest.mark.parametrize("seed", range(3))
def test_cats_state_evolution_is_identical(legacy, seed):
    """Feed both CATS implementations the same growing DAG and compare state."""
    edges = _random_edges(seed, 400)
    old, new = legacy.Tangle(), Tangle()
    old_cats, new_cats = legacy.CATS(subtangle_size=120), CATS(subtangle_size=120)
    ctx = make_ctx(lam=5.0, h=1.0, seed=seed)

    for i, parents in enumerate(edges, start=1):
        old.add_transaction(parents, float(i))
        new.add_transaction(parents, float(i))
        if i % 2 == 0:  # a selection every other transaction
            old_cats.select_tips(old, n_tips=2, lam=ctx.lam, h=ctx.h)
            new_cats.select_tips(new, 2, ctx)

            assert new_cats.alpha_smooth == pytest.approx(old_cats.alpha_smooth, rel=1e-12)
            assert set(new_cats.quarantine) == set(old_cats.quarantine)
            for tx_id, entry in new_cats.quarantine.items():
                ref = old_cats.quarantine[tx_id]
                assert (entry.age, entry.strong, entry.detection_tx) == (
                    ref["age"],
                    ref["strong"],
                    ref["detection_tx"],
                )

    assert new_cats.tx_counter == old_cats.tx_counter
    assert len(new_cats.quarantine) > 0  # the scenario actually exercised detection
    np.testing.assert_allclose(new_cats.alpha_history, old_cats.alpha_history, rtol=1e-12)
    for s_new, s_old in zip(new_cats.signal_history, old_cats.signal_history, strict=True):
        assert (s_new.S, s_new.sigma1, s_new.sigma2, s_new.sigma3) == pytest.approx(
            (s_old["S"], s_old["sigma1"], s_old["sigma2"], s_old["sigma3"]), rel=1e-12
        )
