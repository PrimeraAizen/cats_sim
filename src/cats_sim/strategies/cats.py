"""CATS: Context-Aware Adaptive Tip Selection."""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from cats_sim.markov import FloatArray, tip_distribution
from cats_sim.strategies.base import SelectionContext, TipSelectionStrategy
from cats_sim.tangle import Tangle, TxId

DELTA_MAX = 2.0
"""Normalisation constant for the weight-divergence signal σ₂."""

THRESHOLD_FLOOR = 1e-10
"""Lower bound of the detection threshold, so unreachable tips (D = 0) are always caught."""

STRUCTURAL_WALK_NODES = 20
"""Number of ancestors inspected by the structural (chain-likeness) check."""

CHAIN_BRANCHING_THRESHOLD = 1.2
"""Average branching factor at or below which a subgraph counts as chain-like."""


@dataclass(frozen=True)
class CompositeSignal:
    """Module 1 signals recorded at one tip selection."""

    S: float
    sigma1: float  # tip saturation
    sigma2: float  # weight divergence
    sigma3: float  # anomaly density


@dataclass
class QuarantineEntry:
    """State of a quarantined tip."""

    age: int
    strong: bool  # strong anomalies (chain-like) are never released
    detection_tx: int  # CATS transaction counter at first detection


class CATS(TipSelectionStrategy):
    """Context-Aware Adaptive Tip Selection.

    * Module 1 — dynamic α-adaptation via the composite signal S(t);
    * Module 2 — adaptive anomaly detection via an absorbing Markov chain;
    * Module 3 — fairness-preserving tip reintegration.

    The defaults are the reference configuration from the paper.
    """

    name = "CATS"

    def __init__(
        self,
        alpha_min: float = 0.001,
        alpha_max: float = 0.05,
        w1: float = 0.3,
        w2: float = 0.4,
        w3: float = 0.3,
        gamma: float = 0.15,
        kappa: float = 1.5,
        rho_max: float = 3.0,
        reintegration_interval: int = 50,
        max_quarantine_age: int = 200,
        subtangle_size: int = 500,
    ) -> None:
        if not 0 <= alpha_min <= alpha_max:
            raise ValueError("require 0 <= alpha_min <= alpha_max")
        if not 0 < gamma <= 1:
            raise ValueError("gamma must be in (0, 1]")
        if rho_max <= 1:
            raise ValueError("rho_max must be > 1")
        if reintegration_interval < 1 or subtangle_size < 1:
            raise ValueError("reintegration_interval and subtangle_size must be >= 1")

        # Module 1 parameters
        self.alpha_min = alpha_min
        self.alpha_max = alpha_max
        self.w1 = w1
        self.w2 = w2
        self.w3 = w3
        self.gamma = gamma
        self.rho_max = rho_max

        # Module 2 parameters
        self.kappa = kappa
        self.subtangle_size = subtangle_size

        # Module 3 parameters
        self.reintegration_interval = reintegration_interval
        self.max_quarantine_age = max_quarantine_age

        # Internal state
        self.alpha_smooth = alpha_min  # α̃(t)
        self.quarantine: dict[TxId, QuarantineEntry] = {}
        self.tx_counter = 0  # tip selections so far; drives reintegration timing

        # History for analysis
        self.alpha_history: list[float] = []
        self.signal_history: list[CompositeSignal] = []

    # ------------------------------------------------------------------ hooks

    def prepare(self, tangle: Tangle, ctx: SelectionContext) -> None:
        """Pre-scan: if the tangle was modified externally (e.g. an SPC was
        injected), run one selection cycle so the quarantine is up to date
        before honest transactions select tips."""
        if tangle.num_transactions > 1:
            self.select_tips(tangle, 2, ctx)

    def excluded_tips(self) -> frozenset[TxId]:
        return frozenset(self.quarantine)

    # -------------------------------------------------------------- selection

    def select_tips(self, tangle: Tangle, n_tips: int, ctx: SelectionContext) -> list[TxId]:
        self.tx_counter += 1

        self._adapt_alpha(tangle, ctx)

        # ── Module 2: adaptive anomaly detection ──
        subtangle_ids = tangle.get_subtangle(self.subtangle_size)
        tip_ids = tangle.get_tips_in_subtangle(subtangle_ids)
        D = tip_distribution(tangle, subtangle_ids, tip_ids, self.alpha_smooth)

        # Adaptive threshold: T = μ_D - κ σ_D, floored so that tips with
        # D = 0 (unreachable) are always caught.
        if len(D) > 1:
            T = max(float(np.mean(D) - self.kappa * np.std(D)), THRESHOLD_FLOOR)
        else:
            T = THRESHOLD_FLOOR

        for i, tip_id in enumerate(tip_ids):
            if D[i] < T and tip_id not in self.quarantine:
                self.quarantine[tip_id] = QuarantineEntry(
                    age=0,
                    strong=self._check_structural_anomaly(tangle, tip_id),
                    detection_tx=self.tx_counter,
                )

        for entry in self.quarantine.values():
            entry.age += 1

        # ── Module 3: fairness-preserving reintegration ──
        if self.tx_counter % self.reintegration_interval == 0:
            self._reintegrate_tips(tangle, tip_ids, D, T)

        # Eligible tip set: L'(t) = L(t) \ Q(t)
        eligible = [t for t in tangle.tips if t not in self.quarantine]
        if len(eligible) < n_tips:
            eligible = list(tangle.tips)  # quarantine too aggressive

        chosen = ctx.rng.choice(eligible, size=n_tips, replace=len(eligible) < n_tips)
        return [int(t) for t in chosen]

    def _adapt_alpha(self, tangle: Tangle, ctx: SelectionContext) -> None:
        """Module 1: update α̃(t) from the composite signal S(t)."""
        L_star = 2 * ctx.lam * ctx.h  # theoretical URTS steady state
        num_tips = len(tangle.tips)

        # σ₁: tip saturation
        rho = num_tips / max(L_star, 1)
        sigma1 = float(np.clip((rho - 1) / (self.rho_max - 1), 0.0, 1.0))

        # σ₂: weight divergence (coefficient of variation of tip weights)
        tip_weights = [tangle.transactions[t].cumulative_weight for t in tangle.tips]
        if len(tip_weights) > 1:
            delta = float(np.std(tip_weights)) / max(float(np.mean(tip_weights)), 1e-10)
            sigma2 = min(1.0, delta / DELTA_MAX)
        else:
            sigma2 = 0.0

        # σ₃: anomaly density
        sigma3 = min(1.0, len(self.quarantine) / max(num_tips, 1))

        S = self.w1 * sigma1 + self.w2 * sigma2 + self.w3 * sigma3

        # α-adaptation with EMA smoothing
        alpha_raw = self.alpha_min + S * (self.alpha_max - self.alpha_min)
        self.alpha_smooth = self.gamma * alpha_raw + (1 - self.gamma) * self.alpha_smooth

        self.alpha_history.append(self.alpha_smooth)
        self.signal_history.append(CompositeSignal(S, sigma1, sigma2, sigma3))

    def _check_structural_anomaly(self, tangle: Tangle, tip_id: TxId) -> bool:
        """Chain-like subgraph behind the tip = strong anomaly.

        Walks back from the tip over at most ``STRUCTURAL_WALK_NODES``
        transactions and computes the average number of approvers per node.
        """
        visited: set[TxId] = set()
        queue: deque[TxId] = deque([tip_id])
        total_children = 0
        total_nodes = 0

        while queue and total_nodes < STRUCTURAL_WALK_NODES:
            node_id = queue.popleft()
            if node_id in visited:
                continue
            visited.add(node_id)
            total_nodes += 1

            tx = tangle.transactions[node_id]
            total_children += len(tx.approved_by)
            queue.extend(p for p in tx.approves if p not in visited)

        avg_branching = total_children / max(total_nodes, 1)
        return avg_branching <= CHAIN_BRANCHING_THRESHOLD

    def _reintegrate_tips(
        self, tangle: Tangle, tip_ids: Sequence[TxId], D: FloatArray, T: float
    ) -> None:
        """Re-evaluate weakly anomalous tips for potential reintegration."""
        tip_id_to_idx = {tid: i for i, tid in enumerate(tip_ids)}

        for tx_id, entry in list(self.quarantine.items()):
            if entry.strong:
                continue  # strong anomalies are never released

            if tx_id not in tangle.tips:
                del self.quarantine[tx_id]  # no longer a tip
                continue

            idx = tip_id_to_idx.get(tx_id)
            if idx is not None and D[idx] >= T:
                del self.quarantine[tx_id]  # selection probability recovered
                continue

            if entry.age >= self.max_quarantine_age:
                del self.quarantine[tx_id]  # maximum quarantine age reached
