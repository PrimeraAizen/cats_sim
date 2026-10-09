"""Tangle generation: the context that runs a tip selection strategy."""

from __future__ import annotations

import numpy as np

from cats_sim.strategies.base import SelectionContext, TipSelectionStrategy
from cats_sim.tangle import Tangle, TxId


def generate_tangle(
    tangle: Tangle,
    strategy: TipSelectionStrategy,
    num_transactions: int,
    ctx: SelectionContext,
) -> list[int]:
    """Grow ``tangle`` by ``num_transactions`` honest transactions.

    Transactions arrive as a Poisson process with rate λ. Because of the PoW
    delay h, transactions arriving within the same window ``[t, t + h)`` see
    the same DAG state: they all select tips from the same snapshot and are
    attached together before the next window. This creates the
    characteristic DAG width proportional to λh.

    Args:
        tangle: tangle to grow (modified in place; continuations are allowed).
        strategy: tip selection algorithm.
        num_transactions: number of honest transactions to add.
        ctx: arrival rate, PoW duration and random generator.

    Returns:
        Number of tips after each added transaction.
    """
    if num_transactions < 0:
        raise ValueError("num_transactions must be >= 0")
    if ctx.lam <= 0 or ctx.h <= 0:
        raise ValueError("lam and h must be > 0")

    rng = ctx.rng
    n_approvals = strategy.n_approvals
    tip_counts: list[int] = []

    # Arrival times are generated upfront and offset by the current tangle time.
    arrival_times = np.cumsum(rng.exponential(1.0 / ctx.lam, size=num_transactions)) + tangle.time

    # Let the strategy observe external modifications (e.g. an injected SPC).
    strategy.prepare(tangle, ctx)

    window_start = float(arrival_times[0]) if num_transactions > 0 else 0.0
    tx_idx = 0

    while tx_idx < num_transactions:
        window_end = window_start + ctx.h

        batch_times: list[float] = []
        while tx_idx < num_transactions and arrival_times[tx_idx] < window_end:
            batch_times.append(float(arrival_times[tx_idx]))
            tx_idx += 1

        if not batch_times:
            window_start = window_end
            continue

        # Snapshot of the tip set seen by every transaction of this batch,
        # without the tips the strategy refuses to approve.
        excluded = strategy.excluded_tips()
        snapshot_tips = [t for t in tangle.tips if t not in excluded]
        if not snapshot_tips:
            snapshot_tips = list(tangle.tips)

        batch_selections: list[tuple[float, list[TxId]]] = []
        for t_arrival in batch_times:
            if len(snapshot_tips) >= n_approvals:
                selected = strategy.select_tips(tangle, n_approvals, ctx)
            else:
                # Too few tips: take all of them and pad with random repeats.
                selected = list(snapshot_tips)
                while len(selected) < n_approvals:
                    selected.append(snapshot_tips[int(rng.integers(len(snapshot_tips)))])

            # Ensure at least 2 distinct parents when possible
            distinct = list(set(selected))
            if len(distinct) < 2 and len(snapshot_tips) >= 2:
                remaining = [t for t in snapshot_tips if t not in distinct]
                if remaining:
                    distinct.append(remaining[int(rng.integers(len(remaining)))])
            selected = distinct[:n_approvals]
            if len(selected) < 2:
                selected = selected * 2  # minimum 2 approvals

            batch_selections.append((t_arrival, selected))

        for t_arrival, selected in batch_selections:
            tangle.add_transaction(selected, t_arrival)
            tip_counts.append(len(tangle.tips))

        window_start = window_end

    return tip_counts
