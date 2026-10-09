from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest

from cats_sim import GIOTA, URTS, SelectionContext, Tangle, TipSelectionStrategy, generate_tangle
from cats_sim.tangle import TxId
from tests.helpers import make_ctx


class RecordingStrategy(TipSelectionStrategy):
    """Test double: URTS that records hook calls and refuses some tips."""

    name = "recording"

    def __init__(self, excluded: frozenset[TxId] = frozenset()) -> None:
        self.prepare_calls = 0
        self.selections = 0
        self._excluded = excluded

    def select_tips(self, tangle: Tangle, n_tips: int, ctx: SelectionContext) -> list[TxId]:
        self.selections += 1
        return URTS().select_tips(tangle, n_tips, ctx)

    def prepare(self, tangle: Tangle, ctx: SelectionContext) -> None:
        self.prepare_calls += 1

    def excluded_tips(self) -> frozenset[TxId]:
        return self._excluded


def test_adds_exactly_the_requested_transactions():
    tangle = Tangle()
    counts = generate_tangle(tangle, URTS(), 250, make_ctx())
    assert tangle.num_transactions == 251
    assert len(counts) == 250
    assert counts[-1] == tangle.num_tips


def test_arrival_times_increase_and_continue_from_tangle_time():
    tangle = Tangle()
    generate_tangle(tangle, URTS(), 100, make_ctx(seed=1))
    t_mid = tangle.time
    generate_tangle(tangle, URTS(), 100, make_ctx(seed=2))
    times = [tangle.transactions[i].time for i in range(1, tangle.num_transactions)]
    assert all(b >= a for a, b in pairwise(times))
    assert tangle.transactions[101].time > t_mid


def test_honest_transactions_approve_two_distinct_parents():
    tangle = Tangle()
    generate_tangle(tangle, URTS(), 200, make_ctx())
    for tx_id in range(2, tangle.num_transactions):
        parents = tangle.transactions[tx_id].approves
        assert len(parents) == 2
        if tangle.transactions[parents[0]].time > 0:
            assert parents[0] != parents[1]


def test_giota_transactions_approve_up_to_three_parents():
    tangle = Tangle()
    generate_tangle(tangle, GIOTA(), 200, make_ctx())
    sizes = {len(tangle.transactions[i].approves) for i in range(1, tangle.num_transactions)}
    assert 3 in sizes
    assert sizes <= {2, 3}


def test_first_transaction_approves_genesis_twice_without_consulting_strategy():
    strategy = RecordingStrategy()
    tangle = Tangle()
    generate_tangle(tangle, strategy, 1, make_ctx())
    assert tangle.transactions[1].approves == [0, 0]
    assert strategy.selections == 0


def test_prepare_hook_runs_once_per_call():
    strategy = RecordingStrategy()
    tangle = Tangle()
    generate_tangle(tangle, strategy, 50, make_ctx())
    generate_tangle(tangle, strategy, 50, make_ctx())
    assert strategy.prepare_calls == 2
    assert strategy.selections > 0


def test_excluding_all_tips_falls_back_to_the_full_tip_set():
    tangle = Tangle()
    generate_tangle(tangle, URTS(), 50, make_ctx())
    strategy = RecordingStrategy(excluded=frozenset(tangle.tips))
    generate_tangle(tangle, strategy, 20, make_ctx(seed=3))
    assert tangle.num_transactions == 71


def test_zero_transactions_is_a_no_op():
    tangle = Tangle()
    assert generate_tangle(tangle, URTS(), 0, make_ctx()) == []
    assert tangle.num_transactions == 1


@pytest.mark.parametrize(
    ("n", "lam", "h", "message"),
    [
        (-1, 10.0, 1.0, "num_transactions"),
        (10, 0.0, 1.0, "lam and h"),
        (10, 10.0, 0.0, "lam and h"),
    ],
)
def test_invalid_arguments_are_rejected(n, lam, h, message):
    with pytest.raises(ValueError, match=message):
        generate_tangle(Tangle(), URTS(), n, make_ctx(lam=lam, h=h))


def test_generation_is_reproducible():
    a, b = Tangle(), Tangle()
    counts_a = generate_tangle(a, URTS(), 300, make_ctx(seed=9))
    counts_b = generate_tangle(b, URTS(), 300, make_ctx(seed=9))
    assert counts_a == counts_b
    assert [t.approves for t in a.transactions.values()] == [
        t.approves for t in b.transactions.values()
    ]


def test_tip_count_grows_with_arrival_rate():
    """Scientific sanity check: the DAG width scales with λh."""

    def mean_tips(lam: float) -> float:
        counts = generate_tangle(Tangle(), URTS(), 600, make_ctx(lam=lam, seed=1))
        return float(np.mean(counts[200:]))

    low, high = mean_tips(5), mean_tips(20)
    assert high > 2.5 * low
