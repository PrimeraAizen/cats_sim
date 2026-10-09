from __future__ import annotations

import numpy as np
import pytest

from cats_sim.markov import tip_distribution, transition_weights
from tests.helpers import build_tangle


def _distribution(tangle, alpha=0.0):
    ids = tangle.get_subtangle(500)
    tips = tangle.get_tips_in_subtangle(ids)
    return tips, tip_distribution(tangle, ids, tips, alpha)


def test_transition_weights_decay_with_weight_difference():
    w = transition_weights(10.0, np.array([10.0, 9.0, 5.0]), alpha=0.5)
    assert w[0] == pytest.approx(1.0)
    assert w[0] > w[1] > w[2]


def test_distribution_is_a_probability_vector(honest_tangle):
    _, d = _distribution(honest_tangle, alpha=0.01)
    assert np.all(d >= 0)
    assert d.sum() == pytest.approx(1.0)


def test_single_chain_puts_all_mass_on_its_tip():
    tips, d = _distribution(build_tangle([[0], [1], [2]]))
    assert tips == [3]
    np.testing.assert_allclose(d, [1.0])


def test_symmetric_fork_with_zero_alpha_is_uniform():
    tips, d = _distribution(build_tangle([[0], [0]]))
    assert tips == [1, 2]
    np.testing.assert_allclose(d, [0.5, 0.5])


def test_higher_alpha_moves_mass_to_the_heavier_branch():
    #   0 <- 1 <- {3, 4}      (heavy branch)
    #   0 <- 2                (light branch, a tip)
    tangle = build_tangle([[0], [0], [1], [1]])
    tips, uniform = _distribution(tangle, alpha=0.0)
    _, biased = _distribution(tangle, alpha=1.0)
    assert tips == [2, 3, 4]
    np.testing.assert_allclose(uniform, [0.5, 0.25, 0.25])
    # From genesis (H=5): heavy child H=3, light child H=1 -> p(light) = 1 / (1 + e^2)
    assert biased[0] == pytest.approx(1 / (1 + np.e**2))
    assert biased[1] == pytest.approx(biased[2])


def test_duplicate_approvals_leak_probability_mass():
    """Characterisation test for behaviour inherited from the original simulator.

    Transition probabilities are assigned per approver entry, so a parent
    approved twice by the same child gets a row summing to < 1. Here tx 1 is
    approved twice by tx 2 (chain-like, as in an SPC) while tx 3 approves the
    genesis directly.
    """
    tangle = build_tangle([[0, 0], [1, 1], [0]])
    tips, d = _distribution(tangle, alpha=0.0)
    assert tips == [2, 3]
    # With accumulation it would be [2/3, 1/3]; the original yields [1/3, 2/3].
    np.testing.assert_allclose(d, [1 / 3, 2 / 3])


def test_empty_subtangle_gives_uniform_distribution(honest_tangle):
    d = tip_distribution(honest_tangle, [], [1, 2, 3, 4], alpha=0.1)
    np.testing.assert_allclose(d, [0.25] * 4)
