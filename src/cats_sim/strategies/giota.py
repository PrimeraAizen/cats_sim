"""G-IOTA: fair and confidence-aware tangle."""

from __future__ import annotations

import numpy as np

from cats_sim.strategies.base import SelectionContext, TipSelectionStrategy
from cats_sim.tangle import Tangle, TxId


class GIOTA(TipSelectionStrategy):
    """G-IOTA following Bu, Gürcan and Potop-Butucaru (2019).

    Each new transaction approves three tips instead of two, preferring tips
    that have been waiting longest (fairness mechanism).
    """

    name = "G-IOTA"
    n_approvals = 3

    def select_tips(self, tangle: Tangle, n_tips: int, ctx: SelectionContext) -> list[TxId]:
        tips = list(tangle.tips)

        if len(tips) <= n_tips:
            return tips if len(tips) >= 2 else [tips[0], tips[0]]

        # Fairness: order by arrival time (oldest first) and weight linearly
        # so that older tips are more likely to be selected.
        tip_times = sorted(((t, tangle.transactions[t].time) for t in tips), key=lambda x: x[1])
        n = len(tip_times)
        weights = np.arange(n, 0, -1, dtype=np.float64)
        weights /= weights.sum()

        selected = ctx.rng.choice(n, size=min(n_tips, n), replace=False, p=weights)
        return [tip_times[int(i)][0] for i in selected]
