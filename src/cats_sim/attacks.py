"""Attack models injected into a :class:`~cats_sim.tangle.Tangle`.

Kept separate from the DAG data structure: the Tangle knows how to store
transactions, the attack module knows how an adversary builds them.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from cats_sim.tangle import Tangle, TxId


def attach_parasite_chain(
    tangle: Tangle,
    attach_point: TxId,
    chain_length: int,
    mu: float,
    start_time: float,
    rng: np.random.Generator,
    sybil_ids: Sequence[str] | None = None,
) -> list[TxId]:
    """Attach a Simple Parasite Chain (SPC) to the tangle.

    Following Cullen et al. and Guo et al.: the SPC is a linear chain where
    ONLY the first transaction connects to the main DAG at the attach point.
    Each subsequent transaction approves only the previous one in the chain
    (branching factor ≈ 1.0). Every SPC transaction approves its single parent
    twice, mirroring the two-approval rule of honest transactions.

    Args:
        tangle: the tangle to attack (modified in place).
        attach_point: transaction where the SPC connects to the main DAG.
        chain_length: number of transactions in the SPC (m).
        mu: attacker transaction rate; inter-arrival times are Exp(1/mu).
            With ``mu <= 0`` a fixed inter-arrival time of 1.0 is used.
        start_time: time when the attacker starts building.
        rng: random number generator.
        sybil_ids: fake identity labels assigned round-robin
            (Sybil-augmented SPC).

    Returns:
        IDs of the malicious transactions, in chain order.
    """
    if chain_length < 0:
        raise ValueError("chain_length must be >= 0")
    if sybil_ids is not None and len(sybil_ids) == 0:
        raise ValueError("sybil_ids must not be empty when given")

    malicious_ids: list[TxId] = []
    prev_id = attach_point
    current_time = start_time

    for i in range(chain_length):
        current_time += float(rng.exponential(1.0 / mu)) if mu > 0 else 1.0
        identity = sybil_ids[i % len(sybil_ids)] if sybil_ids is not None else None

        # The first transaction approves the attach point (the only link to the
        # main DAG); every later one approves the previous chain transaction.
        tx_id = tangle.add_transaction(
            [prev_id, prev_id], current_time, is_malicious=True, identity=identity
        )
        malicious_ids.append(tx_id)
        prev_id = tx_id

    return malicious_ids
