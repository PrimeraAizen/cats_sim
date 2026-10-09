from __future__ import annotations

import os
import subprocess
import sys

import pytest

from cats_sim.seeding import derive_rng


def test_same_keys_give_the_same_stream():
    a = derive_rng(1, "security", "CATS", 30, 4).random(5)
    b = derive_rng(1, "security", "CATS", 30, 4).random(5)
    assert a.tolist() == b.tolist()


@pytest.mark.parametrize(
    "keys",
    [
        (2, "security", "CATS", 30, 4),
        (1, "security", "URTS", 30, 4),
        (1, "security", "CATS", 30, 5),
    ],
)
def test_any_different_key_gives_a_different_stream(keys):
    reference = derive_rng(1, "security", "CATS", 30, 4).random(5)
    assert derive_rng(*keys).random(5).tolist() != reference.tolist()


def test_streams_are_stable_across_interpreter_processes():
    """String keys must not depend on Python's per-process hash randomisation."""
    code = (
        "from cats_sim.seeding import derive_rng;"
        "print(derive_rng(7, 'adaptive', 1.5).integers(1 << 30))"
    )
    outputs = {
        subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": str(seed)},
        ).stdout
        for seed in (1, 2)
    }
    assert len(outputs) == 1


def test_invalid_seeds_and_keys_are_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        derive_rng(-1)
    with pytest.raises(TypeError, match="bool"):
        derive_rng(1, True)
