"""CATS Tangle Simulator.

Discrete-event simulator for evaluating tip selection algorithms on DAG-based
distributed ledgers (IOTA Tangle model): URTS, MCMC, S-URTS, G-IOTA and CATS
under benign conditions and parasite-chain attacks.
"""

from importlib.metadata import PackageNotFoundError, version

from cats_sim.attacks import attach_parasite_chain
from cats_sim.simulation import generate_tangle
from cats_sim.strategies import (
    CATS,
    GIOTA,
    MCMC,
    SURTS,
    URTS,
    SelectionContext,
    TipSelectionStrategy,
    available_strategies,
    create_strategy,
)
from cats_sim.tangle import Tangle, Transaction, TxId

try:
    __version__ = version("cats-sim")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0+unknown"

__all__ = [
    "CATS",
    "GIOTA",
    "MCMC",
    "SURTS",
    "URTS",
    "SelectionContext",
    "Tangle",
    "TipSelectionStrategy",
    "Transaction",
    "TxId",
    "__version__",
    "attach_parasite_chain",
    "available_strategies",
    "create_strategy",
    "generate_tangle",
]
