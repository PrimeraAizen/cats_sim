"""Uniform Random Tip Selection (baseline)."""

from __future__ import annotations

from cats_sim.strategies.base import SelectionContext, TipSelectionStrategy
from cats_sim.tangle import Tangle, TxId


class URTS(TipSelectionStrategy):
    """Uniform Random Tip Selection — baseline."""

    name = "URTS"

    def select_tips(self, tangle: Tangle, n_tips: int, ctx: SelectionContext) -> list[TxId]:
        tips = list(tangle.tips)
        if len(tips) < n_tips:
            return tips * n_tips  # edge case: not enough tips
        return [int(t) for t in ctx.rng.choice(tips, size=n_tips, replace=False)]
