"""Strategy interface for tip selection algorithms (TSAs)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

from cats_sim.tangle import Tangle, TxId


@dataclass(frozen=True)
class SelectionContext:
    """Environment of a tip selection call.

    Attributes:
        lam: honest transaction arrival rate λ (txns per time unit).
        h: proof-of-work duration.
        rng: random number generator owned by the current simulation run.
    """

    lam: float
    h: float
    rng: np.random.Generator


class TipSelectionStrategy(ABC):
    """A tip selection algorithm.

    The simulator (:func:`cats_sim.simulation.generate_tangle`) only talks to
    this interface, so algorithms are interchangeable without the simulator
    knowing which one it runs. Stateless algorithms implement
    :meth:`select_tips` only; stateful ones (CATS) also override the hooks.

    One instance is used for exactly one simulation run; experiments create a
    fresh instance per run, so no state can leak between runs.
    """

    name: str
    """Human-readable name used in logs and reports."""

    n_approvals: int = 2
    """How many tips each new honest transaction approves."""

    @abstractmethod
    def select_tips(self, tangle: Tangle, n_tips: int, ctx: SelectionContext) -> list[TxId]:
        """Select ``n_tips`` transactions for a new transaction to approve."""

    def prepare(self, tangle: Tangle, ctx: SelectionContext) -> None:  # noqa: B027
        """Hook called once before a batch of honest transactions is generated.

        Lets a strategy observe changes made to the tangle from outside the
        simulator (e.g. an injected parasite chain). Default: do nothing.
        """

    def excluded_tips(self) -> frozenset[TxId]:
        """Tips the strategy currently refuses to approve. Default: none."""
        return frozenset()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name!r}>"
