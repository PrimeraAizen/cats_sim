"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from cats_sim import URTS, SelectionContext, Tangle, generate_tangle
from tests.helpers import make_ctx


@pytest.fixture
def ctx() -> SelectionContext:
    return make_ctx()


@pytest.fixture
def tangle_factory() -> Callable[..., Tangle]:
    """Build an honest tangle grown with URTS."""

    def factory(n: int = 200, lam: float = 10.0, seed: int = 7) -> Tangle:
        tangle = Tangle()
        generate_tangle(tangle, URTS(), n, make_ctx(lam=lam, seed=seed))
        return tangle

    return factory


@pytest.fixture
def honest_tangle(tangle_factory: Callable[..., Tangle]) -> Tangle:
    """A 200-transaction tangle grown with URTS at λ = 10."""
    return tangle_factory()
