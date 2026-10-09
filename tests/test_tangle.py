from __future__ import annotations

import pytest

from cats_sim.tangle import GENESIS_ID, Tangle
from tests.helpers import build_tangle


def test_new_tangle_contains_only_genesis():
    tangle = Tangle()
    assert tangle.num_transactions == 1
    assert tangle.tips == {GENESIS_ID}
    assert tangle.transactions[GENESIS_ID].cumulative_weight == 1
    assert tangle.time == 0.0


def test_add_transaction_links_parents_and_moves_tips():
    tangle = Tangle()
    a = tangle.add_transaction([0], 1.0)
    b = tangle.add_transaction([0], 2.0)
    c = tangle.add_transaction([a, b], 3.0, is_malicious=True, identity="sybil-1")

    assert (a, b, c) == (1, 2, 3)
    assert tangle.tips == {c}
    assert tangle.transactions[c].approves == [a, b]
    assert tangle.transactions[a].approved_by == [c]
    assert not tangle.transactions[a].is_tip
    assert tangle.transactions[c].is_tip
    assert tangle.transactions[c].is_malicious
    assert tangle.transactions[c].identity == "sybil-1"
    assert tangle.time == 3.0


def test_cumulative_weights_on_diamond():
    #   0 <- 1 <- 3
    #   0 <- 2 <- 3
    tangle = build_tangle([[0], [0], [1, 2]])
    weights = {i: tx.cumulative_weight for i, tx in tangle.transactions.items()}
    assert weights == {0: 4, 1: 2, 2: 2, 3: 1}


def test_duplicate_parent_is_counted_once_for_weights_but_twice_as_edge():
    tangle = build_tangle([[0, 0]])
    assert tangle.transactions[0].cumulative_weight == 2
    assert tangle.transactions[0].approved_by == [1, 1]


def test_unknown_parent_is_rejected():
    tangle = Tangle()
    with pytest.raises(ValueError, match="unknown"):
        tangle.add_transaction([5], 1.0)
    assert tangle.num_transactions == 1


def test_get_tips_returns_a_copy():
    tangle = Tangle()
    tips = tangle.get_tips()
    tips.add(99)
    assert tangle.tips == {0}
    assert tangle.num_tips == 1


def test_subtangle_is_the_newest_window():
    tangle = build_tangle([[i] for i in range(10)])
    assert tangle.get_subtangle(4) == [7, 8, 9, 10]
    assert tangle.get_subtangle(500) == list(range(11))


def test_subtangle_rejects_empty_window():
    with pytest.raises(ValueError, match="window_size"):
        Tangle().get_subtangle(0)


def test_tips_in_subtangle_ignore_approvers_outside_the_window():
    # chain 0 <- 1 <- 2 and a side branch 0 <- 3
    tangle = build_tangle([[0], [1], [0]])
    assert tangle.get_tips_in_subtangle([1, 2, 3]) == [2, 3]
    # In window [0, 1] nobody inside approves 1, so it is a tip of that window.
    assert tangle.get_tips_in_subtangle([0, 1]) == [1]
