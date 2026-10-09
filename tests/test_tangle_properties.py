"""Property-based tests: DAG invariants must hold for any attachment sequence."""

from __future__ import annotations

from collections import Counter, deque

from hypothesis import given, settings
from hypothesis import strategies as st

from cats_sim.tangle import Tangle, TxId


@st.composite
def tangles(draw: st.DrawFn, max_size: int = 40) -> Tangle:
    n = draw(st.integers(min_value=0, max_value=max_size))
    tangle = Tangle()
    for i in range(1, n + 1):
        parents = draw(st.lists(st.integers(0, i - 1), min_size=1, max_size=3))
        tangle.add_transaction(parents, float(i))
    return tangle


def descendants(tangle: Tangle, tx_id: TxId) -> set[TxId]:
    seen: set[TxId] = set()
    queue = deque(tangle.transactions[tx_id].approved_by)
    while queue:
        node = queue.popleft()
        if node not in seen:
            seen.add(node)
            queue.extend(tangle.transactions[node].approved_by)
    return seen


@settings(max_examples=150, deadline=None)
@given(tangles())
def test_ids_are_contiguous_and_edges_point_backwards(tangle: Tangle):
    assert sorted(tangle.transactions) == list(range(tangle.num_transactions))
    for tx_id, tx in tangle.transactions.items():
        assert all(parent < tx_id for parent in tx.approves)


@settings(max_examples=150, deadline=None)
@given(tangles())
def test_approval_edges_are_symmetric(tangle: Tangle):
    forward = Counter((p, c) for c, tx in tangle.transactions.items() for p in tx.approves)
    backward = Counter((p, c) for p, tx in tangle.transactions.items() for c in tx.approved_by)
    assert forward == backward


@settings(max_examples=150, deadline=None)
@given(tangles())
def test_tips_are_exactly_the_unapproved_transactions(tangle: Tangle):
    unapproved = {i for i, tx in tangle.transactions.items() if not tx.approved_by}
    assert tangle.tips == unapproved
    assert all(tx.is_tip == (i in unapproved) for i, tx in tangle.transactions.items())
    all_ids = list(tangle.transactions)
    assert set(tangle.get_tips_in_subtangle(all_ids)) == unapproved


@settings(max_examples=150, deadline=None)
@given(tangles())
def test_cumulative_weight_is_one_plus_number_of_descendants(tangle: Tangle):
    for tx_id, tx in tangle.transactions.items():
        assert tx.cumulative_weight == 1 + len(descendants(tangle, tx_id))
