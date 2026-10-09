"""Tip selection strategies and the registry used to build them from configuration.

Adding a new algorithm = one new :class:`TipSelectionStrategy` subclass plus
one entry in :data:`REGISTRY`; nothing else in the simulator changes.
"""

from __future__ import annotations

from typing import Any

from cats_sim.strategies.base import SelectionContext, TipSelectionStrategy
from cats_sim.strategies.cats import CATS
from cats_sim.strategies.giota import GIOTA
from cats_sim.strategies.mcmc import MCMC
from cats_sim.strategies.surts import SURTS
from cats_sim.strategies.urts import URTS

REGISTRY: dict[str, type[TipSelectionStrategy]] = {
    "urts": URTS,
    "mcmc": MCMC,
    "surts": SURTS,
    "giota": GIOTA,
    "cats": CATS,
}
"""Maps the ``kind`` used in configuration files to the strategy class."""


def available_strategies() -> list[str]:
    """Return the registered strategy kinds."""
    return sorted(REGISTRY)


def create_strategy(kind: str, **params: Any) -> TipSelectionStrategy:
    """Instantiate the strategy registered under ``kind`` with ``params``.

    Raises:
        KeyError: if ``kind`` is not registered.
        TypeError, ValueError: if ``params`` do not fit the strategy.
    """
    try:
        cls = REGISTRY[kind]
    except KeyError:
        raise KeyError(
            f"unknown strategy kind {kind!r}; available: {', '.join(available_strategies())}"
        ) from None
    return cls(**params)


__all__ = [
    "CATS",
    "GIOTA",
    "MCMC",
    "REGISTRY",
    "SURTS",
    "URTS",
    "SelectionContext",
    "TipSelectionStrategy",
    "available_strategies",
    "create_strategy",
]
