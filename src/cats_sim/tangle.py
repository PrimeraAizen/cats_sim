"""DAG data structure for the IOTA Tangle model.

The Tangle grows by appending transactions that each approve existing tips
(typically two). Cumulative weights are updated after each attachment
[Popov 2017].
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field

TxId = int
"""Transaction identifier. IDs are assigned contiguously starting at 0 (genesis)."""

GENESIS_ID: TxId = 0


@dataclass(slots=True, eq=False)
class Transaction:
    """Single transaction (vertex) in the Tangle DAG."""

    id: TxId
    time: float
    is_malicious: bool = False
    identity: str | None = None  # for Sybil analysis
    approves: list[TxId] = field(default_factory=list)  # edges OUT: parents
    approved_by: list[TxId] = field(default_factory=list)  # edges IN: children
    cumulative_weight: int = 1
    is_tip: bool = True


class Tangle:
    """DAG-based distributed ledger.

    Invariants (checked by the property-based tests):

    * transaction IDs are ``0 .. num_transactions - 1`` and are never removed;
    * every transaction only approves transactions with a smaller ID (acyclic);
    * ``tips`` is exactly the set of transactions nobody approves yet;
    * ``cumulative_weight`` of a transaction is ``1 + number of its descendants``.
    """

    def __init__(self) -> None:
        genesis = Transaction(GENESIS_ID, 0.0)
        self.transactions: dict[TxId, Transaction] = {GENESIS_ID: genesis}
        self.tips: set[TxId] = {GENESIS_ID}
        self.next_id: TxId = GENESIS_ID + 1
        self.time: float = 0.0

    @property
    def num_transactions(self) -> int:
        return len(self.transactions)

    @property
    def num_tips(self) -> int:
        return len(self.tips)

    def get_tips(self) -> set[TxId]:
        """Return a copy of the current tip IDs."""
        return set(self.tips)

    def add_transaction(
        self,
        approved_ids: Sequence[TxId],
        arrival_time: float,
        *,
        is_malicious: bool = False,
        identity: str | None = None,
    ) -> TxId:
        """Add a new transaction that approves the given transactions.

        Args:
            approved_ids: IDs of the transactions to approve (typically 2).
                The same parent may appear more than once.
            arrival_time: arrival time of the new transaction.
            is_malicious: whether this is an attacker transaction.
            identity: optional identity label (for Sybil analysis).

        Returns:
            The ID of the new transaction.
        """
        unknown = [p for p in approved_ids if p not in self.transactions]
        if unknown:
            raise ValueError(f"cannot approve unknown transactions: {unknown}")

        tx_id = self.next_id
        self.next_id += 1
        self.time = arrival_time

        tx = Transaction(tx_id, arrival_time, is_malicious=is_malicious, identity=identity)
        tx.approves = list(approved_ids)
        self.transactions[tx_id] = tx

        # Update edges and tip status
        for parent_id in approved_ids:
            parent = self.transactions[parent_id]
            parent.approved_by.append(tx_id)
            if parent_id in self.tips:
                parent.is_tip = False
                self.tips.discard(parent_id)

        tx.is_tip = True
        self.tips.add(tx_id)

        self._update_weights(tx_id)
        return tx_id

    def _update_weights(self, new_tx_id: TxId) -> None:
        """Increment the cumulative weight of every ancestor of ``new_tx_id`` by 1.

        Uses BFS to traverse the approval graph backwards; each ancestor is
        counted once even if it is reachable over several paths.
        """
        visited: set[TxId] = set()
        queue: deque[TxId] = deque()

        for parent_id in self.transactions[new_tx_id].approves:
            if parent_id not in visited:
                visited.add(parent_id)
                queue.append(parent_id)

        while queue:
            node_id = queue.popleft()
            self.transactions[node_id].cumulative_weight += 1
            for grandparent_id in self.transactions[node_id].approves:
                if grandparent_id not in visited:
                    visited.add(grandparent_id)
                    queue.append(grandparent_id)

    def get_subtangle(self, window_size: int = 500) -> list[TxId]:
        """Return the IDs of the most recent ``window_size`` transactions, oldest first.

        Used to limit the computation scope of Markov chain operations.
        """
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        # IDs are contiguous and never removed, so the newest window is a plain range.
        n = self.num_transactions
        return list(range(max(0, n - window_size), n))

    def get_tips_in_subtangle(self, subtangle_ids: Sequence[TxId]) -> list[TxId]:
        """Return the transactions of a subtangle that have no approvers inside it."""
        subtangle_set = set(subtangle_ids)
        return [
            tx_id
            for tx_id in subtangle_ids
            if not any(a in subtangle_set for a in self.transactions[tx_id].approved_by)
        ]
