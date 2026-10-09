"""Helpers shared by the test modules."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from cats_sim import SelectionContext, Tangle

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"
SMOKE_CONFIG = CONFIG_DIR / "smoke.toml"


def make_ctx(lam: float = 10.0, h: float = 1.0, seed: int = 0) -> SelectionContext:
    return SelectionContext(lam=lam, h=h, rng=np.random.default_rng(seed))


def build_tangle(edges: list[list[int]]) -> Tangle:
    """Tangle whose i-th added transaction (ID i + 1) approves ``edges[i]``."""
    tangle = Tangle()
    for i, parents in enumerate(edges, start=1):
        tangle.add_transaction(parents, float(i))
    return tangle
