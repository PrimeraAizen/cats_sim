from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest

from cats_sim.attacks import attach_parasite_chain


def test_parasite_chain_topology(honest_tangle):
    before = honest_tangle.num_transactions
    attach = 100
    ids = attach_parasite_chain(
        honest_tangle, attach, 10, mu=5, start_time=honest_tangle.time, rng=np.random.default_rng(0)
    )

    assert ids == list(range(before, before + 10))
    assert honest_tangle.transactions[ids[0]].approves == [attach, attach]
    for prev, cur in pairwise(ids):
        assert honest_tangle.transactions[cur].approves == [prev, prev]
        assert honest_tangle.transactions[prev].approved_by == [cur, cur]
    assert all(honest_tangle.transactions[i].is_malicious for i in ids)
    # Only the chain end is a new tip.
    assert set(ids) & honest_tangle.tips == {ids[-1]}


def test_parasite_chain_timestamps_increase(honest_tangle):
    start = honest_tangle.time
    ids = attach_parasite_chain(honest_tangle, 50, 20, 5, start, np.random.default_rng(1))
    times = [honest_tangle.transactions[i].time for i in ids]
    assert times[0] > start
    assert all(b > a for a, b in pairwise(times))


def test_non_positive_rate_uses_unit_inter_arrival(honest_tangle):
    start = honest_tangle.time
    ids = attach_parasite_chain(honest_tangle, 50, 3, 0, start, np.random.default_rng(1))
    assert [honest_tangle.transactions[i].time for i in ids] == [start + 1, start + 2, start + 3]


def test_sybil_identities_are_assigned_round_robin(honest_tangle):
    ids = attach_parasite_chain(
        honest_tangle, 50, 5, 5, 0.0, np.random.default_rng(1), sybil_ids=["a", "b"]
    )
    assert [honest_tangle.transactions[i].identity for i in ids] == ["a", "b", "a", "b", "a"]


@pytest.mark.parametrize(
    ("length", "sybil_ids", "message"),
    [(-1, None, "chain_length"), (3, [], "sybil_ids")],
)
def test_invalid_arguments_are_rejected(honest_tangle, length, sybil_ids, message):
    with pytest.raises(ValueError, match=message):
        attach_parasite_chain(
            honest_tangle, 0, length, 5, 0.0, np.random.default_rng(0), sybil_ids=sybil_ids
        )


def test_chain_is_reproducible(tangle_factory):
    a, b = tangle_factory(), tangle_factory()
    ids_a = attach_parasite_chain(a, 10, 5, 5, a.time, np.random.default_rng(3))
    ids_b = attach_parasite_chain(b, 10, 5, 5, b.time, np.random.default_rng(3))
    assert ids_a == ids_b
    assert [a.transactions[i].time for i in ids_a] == [b.transactions[i].time for i in ids_b]
