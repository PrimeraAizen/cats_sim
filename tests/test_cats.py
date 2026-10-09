from __future__ import annotations

import numpy as np
import pytest

from cats_sim import CATS, Tangle, attach_parasite_chain, generate_tangle
from cats_sim.strategies.cats import QuarantineEntry
from tests.helpers import build_tangle, make_ctx


def test_defaults_are_the_paper_reference_configuration():
    cats = CATS()
    assert (cats.alpha_min, cats.alpha_max) == (0.001, 0.05)
    assert (cats.w1, cats.w2, cats.w3) == (0.3, 0.4, 0.3)
    assert (cats.gamma, cats.kappa, cats.rho_max) == (0.15, 1.5, 3.0)
    assert (cats.reintegration_interval, cats.max_quarantine_age) == (50, 200)
    assert cats.subtangle_size == 500
    assert cats.alpha_smooth == cats.alpha_min


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"alpha_min": 0.1, "alpha_max": 0.05}, "alpha_min"),
        ({"gamma": 0.0}, "gamma"),
        ({"rho_max": 1.0}, "rho_max"),
        ({"reintegration_interval": 0}, "reintegration_interval"),
    ],
)
def test_invalid_parameters_are_rejected(params, message):
    with pytest.raises(ValueError, match=message):
        CATS(**params)


def test_alpha_stays_within_bounds_and_history_is_recorded():
    cats = CATS()
    generate_tangle(Tangle(), cats, 300, make_ctx(lam=10, seed=1))
    assert len(cats.alpha_history) == cats.tx_counter == len(cats.signal_history)
    assert all(cats.alpha_min <= a <= cats.alpha_max for a in cats.alpha_history)
    assert all(0 <= s.S <= 1 for s in cats.signal_history)


def test_prepare_does_nothing_on_a_fresh_tangle(ctx):
    cats = CATS()
    cats.prepare(Tangle(), ctx)
    assert cats.tx_counter == 0


def test_detects_and_excludes_a_parasite_chain_tip():
    # Detection is probabilistic (see the adaptive experiment for rates), so a
    # fixed set of seeds is used: the outcome is deterministic, not flaky.
    detected = 0
    for seed in range(10):
        ctx = make_ctx(lam=10, seed=seed)
        tangle, cats = Tangle(), CATS()
        generate_tangle(tangle, cats, 300, ctx)
        spc = attach_parasite_chain(tangle, 150, 10, 5, tangle.time, ctx.rng)

        cats.prepare(tangle, ctx)  # the pre-scan that runs before honest traffic resumes

        assert cats.excluded_tips() == frozenset(cats.quarantine)
        if spc[-1] in cats.quarantine:
            detected += 1
            picks = {t for _ in range(50) for t in cats.select_tips(tangle, 2, ctx)}
            assert spc[-1] not in picks
    assert detected >= 3


def test_structural_check_flags_single_parent_chains():
    chain = build_tangle([[0], [1], [2], [3]])
    assert CATS()._check_structural_anomaly(chain, 4)


def test_structural_check_accepts_wide_regions():
    fan = build_tangle([[0]] * 30)
    assert not CATS()._check_structural_anomaly(fan, 1)


def test_parasite_chains_are_not_classified_as_strong():
    """Characterisation test for behaviour inherited from the original simulator.

    SPC transactions approve their parent twice, so every chain node lists its
    child twice in ``approved_by``: the measured branching factor is ~2 and an
    SPC never counts as a *strong* (chain-like) anomaly.
    """
    tangle = build_tangle([[0]] * 30)
    spc = attach_parasite_chain(tangle, 5, 10, 5, tangle.time, np.random.default_rng(0))
    assert not CATS()._check_structural_anomaly(tangle, spc[-1])


def test_reintegration_rules():
    tangle = build_tangle([[0], [0], [0], [0], [1]])  # tips 2, 3, 4, 5
    cats = CATS(max_quarantine_age=10)
    cats.quarantine = {
        1: QuarantineEntry(age=1, strong=False, detection_tx=0),  # no longer a tip
        2: QuarantineEntry(age=1, strong=True, detection_tx=0),  # strong: kept
        3: QuarantineEntry(age=1, strong=False, detection_tx=0),  # recovered: released
        4: QuarantineEntry(age=10, strong=False, detection_tx=0),  # too old: released
        5: QuarantineEntry(age=1, strong=False, detection_tx=0),  # still anomalous: kept
    }
    tip_ids = [2, 3, 4, 5]
    D = np.array([0.0, 0.5, 0.0, 0.0])
    cats._reintegrate_tips(tangle, tip_ids, D, T=0.1)
    assert set(cats.quarantine) == {2, 5}
