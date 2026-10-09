from __future__ import annotations

from collections import Counter

import numpy as np
import pytest

from cats_sim.strategies import (
    GIOTA,
    MCMC,
    REGISTRY,
    SURTS,
    URTS,
    TipSelectionStrategy,
    available_strategies,
    create_strategy,
)
from cats_sim.tangle import Tangle
from tests.helpers import build_tangle, make_ctx

# Minimal constructor parameters for every registered strategy. A new strategy
# must be added here, which makes the generic contract tests below cover it.
DEFAULT_PARAMS: dict[str, dict[str, float]] = {
    "urts": {},
    "mcmc": {"alpha": 0.001},
    "surts": {},
    "giota": {},
    "cats": {},
}


def test_every_registered_strategy_is_covered_by_the_contract_tests():
    assert set(DEFAULT_PARAMS) == set(REGISTRY)


@pytest.fixture(params=sorted(DEFAULT_PARAMS))
def strategy(request: pytest.FixtureRequest) -> TipSelectionStrategy:
    return create_strategy(request.param, **DEFAULT_PARAMS[request.param])


# ------------------------------------------------------------ generic contract


@pytest.mark.parametrize("n_tips", [1, 2, 3])
def test_selects_current_tips(strategy, honest_tangle, n_tips):
    selected = strategy.select_tips(honest_tangle, n_tips, make_ctx(seed=1))
    assert len(selected) == n_tips
    assert set(selected) <= honest_tangle.tips
    assert all(type(t) is int for t in selected)


def test_selection_is_reproducible_for_a_seed(honest_tangle):
    for kind, params in DEFAULT_PARAMS.items():
        picks = [
            create_strategy(kind, **params).select_tips(honest_tangle, 2, make_ctx(seed=3))
            for _ in range(2)
        ]
        assert picks[0] == picks[1], kind


def test_strategy_has_a_name_and_repr(strategy):
    assert strategy.name
    assert strategy.name in repr(strategy)


def test_default_hooks_are_no_ops(honest_tangle, ctx):
    urts = URTS()
    urts.prepare(honest_tangle, ctx)
    assert urts.excluded_tips() == frozenset()
    assert urts.n_approvals == 2


# -------------------------------------------------------------------- registry


def test_available_strategies_lists_registry_keys():
    assert available_strategies() == ["cats", "giota", "mcmc", "surts", "urts"]


def test_unknown_kind_raises_helpful_error():
    with pytest.raises(KeyError, match="available: cats"):
        create_strategy("does-not-exist")


def test_bad_parameters_raise():
    with pytest.raises(TypeError):
        create_strategy("urts", alpha=1.0)
    with pytest.raises(TypeError):
        create_strategy("mcmc")  # alpha is required


# ------------------------------------------------------------------------ URTS


def test_urts_repeats_tips_when_there_are_too_few():
    assert URTS().select_tips(Tangle(), 2, make_ctx()) == [0, 0]


def test_urts_is_roughly_uniform():
    tangle = build_tangle([[0]] * 4)  # four tips: 1..4
    rng_ctx = make_ctx(seed=5)
    counts = Counter(t for _ in range(2000) for t in URTS().select_tips(tangle, 1, rng_ctx))
    assert set(counts) == {1, 2, 3, 4}
    assert all(400 < c < 600 for c in counts.values())


# ------------------------------------------------------------------------ MCMC


def test_mcmc_rejects_negative_alpha():
    with pytest.raises(ValueError, match="alpha"):
        MCMC(alpha=-0.1)


def test_mcmc_name_contains_alpha():
    assert MCMC(0.05).name == "MCMC(α=0.05)"


def _walk_endpoints(alpha: float, monkeypatch: pytest.MonkeyPatch) -> Counter[int]:
    #   0 <- 1 <- 3 <- 4 <- 5 <- 6     heavy branch (tip 6)
    #   0 <- 2                         light branch (tip 2)
    tangle = build_tangle([[0], [0], [1], [3], [4], [5]])
    mcmc = MCMC(alpha)
    monkeypatch.setattr(mcmc, "_start_point", lambda n, lam, rng: 0)  # start at genesis
    ctx = make_ctx(seed=11)
    return Counter(mcmc.select_tips(tangle, 1, ctx)[0] for _ in range(400))


def test_mcmc_walk_is_unbiased_with_zero_alpha(monkeypatch):
    ends = _walk_endpoints(0.0, monkeypatch)
    assert set(ends) == {2, 6}
    assert 150 < ends[2] < 250


def test_mcmc_walk_follows_weight_with_large_alpha(monkeypatch):
    assert _walk_endpoints(5.0, monkeypatch) == Counter({6: 400})


def test_mcmc_start_point_is_100_to_200_lambda_deep():
    mcmc, rng = MCMC(0.001), np.random.default_rng(0)
    starts = {mcmc._start_point(5000, 10, rng) for _ in range(500)}
    assert min(starts) >= 5000 - 2001
    assert max(starts) <= 5000 - 1001


def test_mcmc_start_point_in_small_tangle_is_in_the_older_half():
    mcmc, rng = MCMC(0.001), np.random.default_rng(0)
    starts = {mcmc._start_point(100, 10, rng) for _ in range(500)}
    assert min(starts) >= 49
    assert max(starts) <= 99


# ---------------------------------------------------------------------- S-URTS


def _fork():
    #   0 <- 1 <- {3, 4};  0 <- 2   ->  α=0 distribution over tips [2, 3, 4] is [.5, .25, .25]
    return build_tangle([[0], [0], [1], [1]])


def test_surts_threshold_removes_unlikely_tips():
    surts = SURTS(alpha=0.0, thresholds={"1": 0.3})  # TOML keys arrive as strings
    ctx = make_ctx(lam=1.0, seed=2)
    assert {surts.select_tips(_fork(), 1, ctx)[0] for _ in range(50)} == {2}


def test_surts_uses_adaptive_threshold_for_unknown_lambda():
    surts = SURTS(alpha=0.0, thresholds={1.0: 0.3})
    ctx = make_ctx(lam=7.0, seed=2)  # no threshold for λ=7 -> mean - 1.5 std keeps all
    assert {surts.select_tips(_fork(), 1, ctx)[0] for _ in range(100)} == {2, 3, 4}


def test_surts_falls_back_to_all_tips_when_too_few_are_eligible():
    surts = SURTS(alpha=0.0, thresholds={1.0: 0.3})
    ctx = make_ctx(lam=1.0)
    picks = {t for _ in range(50) for t in surts.select_tips(_fork(), 2, ctx)}
    assert picks == {2, 3, 4}


def test_surts_returns_window_tips_when_there_are_few():
    tangle = build_tangle([[0], [0]])
    assert SURTS().select_tips(tangle, 2, make_ctx()) == [1, 2]
    assert SURTS().select_tips(Tangle(), 2, make_ctx()) == [0]


def test_surts_validates_window():
    with pytest.raises(ValueError, match="subtangle_size"):
        SURTS(subtangle_size=0)


# ---------------------------------------------------------------------- G-IOTA


def test_giota_approves_three_tips():
    assert GIOTA.n_approvals == 3


def test_giota_prefers_older_tips():
    tangle = build_tangle([[0]] * 10)  # tips 1..10 arrive at t = 1..10
    ctx = make_ctx(seed=4)
    picked = [GIOTA().select_tips(tangle, 1, ctx)[0] for _ in range(3000)]
    # uniform mean would be 5.5; linear weights n..1 give (n + 2) / 3 = 4
    assert np.mean(picked) == pytest.approx(4.0, abs=0.2)


def test_giota_with_few_tips():
    assert GIOTA().select_tips(Tangle(), 3, make_ctx()) == [0, 0]
    assert sorted(GIOTA().select_tips(build_tangle([[0], [0]]), 3, make_ctx())) == [1, 2]
