"""Markov-chain machinery shared by the random-walk based tip selection algorithms."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias

import numpy as np
import numpy.typing as npt

from cats_sim.tangle import Tangle, TxId

FloatArray: TypeAlias = npt.NDArray[np.float64]


def transition_weights(h_current: float, h_approvers: FloatArray, alpha: float) -> FloatArray:
    """Unnormalised transition weights ``exp(-α (H_current - H_approver))`` [Popov 2017]."""
    return np.exp(-alpha * (h_current - h_approvers))


def approver_weights(
    tangle: Tangle, tx_id: TxId, approvers: Sequence[TxId], alpha: float
) -> FloatArray:
    """Transition weights from ``tx_id`` to each of ``approvers``."""
    h_approvers = np.array(
        [tangle.transactions[a].cumulative_weight for a in approvers], dtype=np.float64
    )
    return transition_weights(tangle.transactions[tx_id].cumulative_weight, h_approvers, alpha)


def tip_distribution(
    tangle: Tangle,
    subtangle_ids: Sequence[TxId],
    tip_ids: Sequence[TxId],
    alpha: float,
    *,
    max_iterations: int = 30,
    atol: float = 1e-10,
) -> FloatArray:
    """Tip selection probabilities of a biased random walk over a subtangle.

    The subtangle is converted into an absorbing Markov chain (tips and
    transactions without approvers inside the window are absorbing states);
    the distribution is obtained by power iteration starting from the oldest
    transaction in the window [Guo et al. 2025].

    Note:
        Transition probabilities are *assigned* per approver, not accumulated.
        A transaction approved twice by the same child (every SPC transaction,
        and the duplicated-parent fallback in the simulator) therefore gets a
        row that sums to less than one, and probability mass leaks along such
        edges. This is the behaviour of the original simulator the published
        results were produced with, and it is preserved deliberately.

    Returns:
        Array with one probability per entry of ``tip_ids``; normalised to sum
        to 1 unless all mass leaked away (then all zeros).
    """
    n = len(subtangle_ids)
    if n == 0:
        return np.full(len(tip_ids), 1.0 / max(len(tip_ids), 1), dtype=np.float64)

    id_to_idx = {tx_id: i for i, tx_id in enumerate(subtangle_ids)}
    tip_set = set(tip_ids)

    P = np.zeros((n, n), dtype=np.float64)
    for tx_id in subtangle_ids:
        idx = id_to_idx[tx_id]
        if tx_id in tip_set:
            P[idx, idx] = 1.0  # absorbing state
            continue

        approvers = [a for a in tangle.transactions[tx_id].approved_by if a in id_to_idx]
        if not approvers:
            P[idx, idx] = 1.0  # no forward neighbours in the window: absorbing
            continue

        weights = approver_weights(tangle, tx_id, approvers, alpha)
        cols = [id_to_idx[a] for a in approvers]
        total = weights.sum()
        if total > 0:
            P[idx, cols] = weights / total
        else:
            P[idx, cols] = 1.0 / len(cols)  # uniform fallback

    # Power iteration: π_{k+1} = π_k P, starting from the deepest transaction.
    pi = np.zeros(n, dtype=np.float64)
    pi[0] = 1.0
    for _ in range(max_iterations):
        pi_new = pi @ P
        if np.allclose(pi, pi_new, atol=atol):
            break
        pi = pi_new

    tip_probs = np.array(
        [pi[id_to_idx[t]] if t in id_to_idx else 0.0 for t in tip_ids], dtype=np.float64
    )
    total = tip_probs.sum()
    if total > 0:
        tip_probs /= total
    return tip_probs
