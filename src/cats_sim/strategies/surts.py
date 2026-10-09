"""S-URTS: Scalable Uniform Random Tip Selection with anomaly detection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from cats_sim.markov import tip_distribution
from cats_sim.strategies.base import SelectionContext, TipSelectionStrategy
from cats_sim.tangle import Tangle, TxId


class SURTS(TipSelectionStrategy):
    """S-URTS following Guo, Hecker and Dustdar (2025).

    1. Convert the subtangle into an absorbing Markov chain (tips absorb).
    2. Compute the tip distribution via power iteration.
    3. Remove tips whose probability is below the threshold T.
    4. Select uniformly from the remaining tips.

    Thresholds are pre-computed per arrival rate λ; keys may be numbers or
    numeric strings (TOML table keys are strings). For a λ without a
    pre-computed threshold an adaptive one is used:
    ``T = max(0, mean(D) - fallback_kappa * std(D))``.
    """

    name = "S-URTS"

    def __init__(
        self,
        alpha: float = 0.001,
        subtangle_size: int = 500,
        thresholds: Mapping[Any, float] | None = None,
        fallback_kappa: float = 1.5,
    ) -> None:
        if subtangle_size < 1:
            raise ValueError("subtangle_size must be >= 1")
        self.alpha = alpha
        self.subtangle_size = subtangle_size
        self.fallback_kappa = fallback_kappa
        self.thresholds: dict[float, float] = {}
        for lam, threshold in (thresholds or {}).items():
            self.set_threshold(float(lam), threshold)

    def set_threshold(self, lam: float, threshold: float) -> None:
        """Set the pre-computed threshold for arrival rate ``lam``."""
        self.thresholds[float(lam)] = float(threshold)

    def select_tips(self, tangle: Tangle, n_tips: int, ctx: SelectionContext) -> list[TxId]:
        subtangle_ids = tangle.get_subtangle(self.subtangle_size)
        tip_ids = tangle.get_tips_in_subtangle(subtangle_ids)

        if len(tip_ids) <= n_tips:
            return tip_ids if len(tip_ids) >= n_tips else list(tangle.tips)[:n_tips]

        D = tip_distribution(tangle, subtangle_ids, tip_ids, self.alpha)

        T = self.thresholds.get(float(ctx.lam))
        if T is None:
            T = float(np.mean(D) - self.fallback_kappa * np.std(D)) if len(D) > 1 else 0.0
            T = max(T, 0.0)

        eligible = [tip_ids[i] for i in range(len(tip_ids)) if D[i] >= T]
        if len(eligible) < n_tips:
            eligible = tip_ids  # fallback

        chosen = ctx.rng.choice(eligible, size=n_tips, replace=len(eligible) < n_tips)
        return [int(t) for t in chosen]
