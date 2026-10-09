"""Markov Chain Monte Carlo tip selection (biased random walk)."""

from __future__ import annotations

import numpy as np

from cats_sim.markov import approver_weights
from cats_sim.strategies.base import SelectionContext, TipSelectionStrategy
from cats_sim.tangle import Tangle, TxId


class MCMC(TipSelectionStrategy):
    """Biased random walk parameterised by α.

    Following Popov (2017) and Cullen et al.:

    * start the walk deep in the DAG (100λ–200λ transactions back);
    * transition probability ``p_jk ∝ exp(-α (H_j - H_k))``;
    * walk forward until reaching a tip.
    """

    def __init__(self, alpha: float) -> None:
        if alpha < 0:
            raise ValueError("alpha must be >= 0")
        self.alpha = alpha
        self.name = f"MCMC(α={alpha})"

    def select_tips(self, tangle: Tangle, n_tips: int, ctx: SelectionContext) -> list[TxId]:
        return [self._random_walk(tangle, ctx) for _ in range(n_tips)]

    def _start_point(self, n: int, lam: float, rng: np.random.Generator) -> TxId:
        """Pick a start transaction between 100λ and 200λ transactions back.

        Falls back to the first half of the tangle when it is still small.
        IDs are contiguous, so the i-th oldest transaction has ID i.
        """
        deep = n > int(200 * lam)
        depth_low = min(int(100 * lam) if deep else 0, n - 1)
        depth_high = min(int(200 * lam) if deep else max(1, n // 2), n - 1)

        if depth_low >= depth_high:
            return max(0, n - depth_high - 1)
        start_pos = int(rng.integers(depth_low, depth_high + 1))
        return max(0, n - start_pos - 1)

    def _random_walk(self, tangle: Tangle, ctx: SelectionContext) -> TxId:
        """Perform a single biased random walk from a deep start point to a tip."""
        rng = ctx.rng
        n = tangle.num_transactions
        current = self._start_point(n, ctx.lam, rng)

        for _ in range(n):  # bounded to prevent infinite loops
            if current in tangle.tips:
                return current

            approvers = tangle.transactions[current].approved_by
            if not approvers:
                return current  # dead end = de facto tip

            weights = approver_weights(tangle, current, approvers, self.alpha)
            total = weights.sum()
            if total == 0 or np.isnan(total):
                current = approvers[int(rng.integers(len(approvers)))]  # uniform fallback
            else:
                current = approvers[int(rng.choice(len(approvers), p=weights / total))]

        # Fallback: return a random tip if the walk did not converge
        tips = list(tangle.tips)
        return tips[int(rng.integers(len(tips)))]
