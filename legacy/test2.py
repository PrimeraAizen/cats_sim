"""
CATS Tangle Simulator
=====================
Discrete-event simulator for evaluating tip selection algorithms
on DAG-based distributed ledgers (IOTA Tangle model).

Implements: URTS, MCMC (α=0.001, α=0.05), S-URTS, G-IOTA, CATS
Attack model: Simple Parasite Chain (SPC), slow-build, Sybil-augmented

References:
  [Popov 2017]   S. Popov, "The Tangle," ver. 1.3
  [Cullen et al.] "On the resilience of DAG-based distributed ledgers"
  [Guo et al. 2025] "A scalable and secure TSA for DAG-based blockchain"
  [Fan 2019]     "Performance analysis of an IoT-friendly DAG-based DL system"
"""

import numpy as np
from collections import defaultdict, deque
import time
import json
import os

# ============================================================
# 1. DAG DATA STRUCTURE
# ============================================================

class Transaction:
    """Single transaction (vertex) in the Tangle DAG."""
    __slots__ = ['id', 'time', 'approves', 'approved_by',
                 'cumulative_weight', 'is_tip', 'is_malicious', 'identity']

    def __init__(self, tx_id, arrival_time, is_malicious=False, identity=None):
        self.id = tx_id
        self.time = arrival_time
        self.approves = []        # edges OUT: transactions this tx approves (parents)
        self.approved_by = []     # edges IN:  transactions that approve this tx (children)
        self.cumulative_weight = 1
        self.is_tip = True
        self.is_malicious = is_malicious
        self.identity = identity  # for Sybil detection


class Tangle:
    """
    DAG-based distributed ledger simulator.

    The Tangle grows by appending transactions that each approve m=2
    existing tips. Cumulative weights are updated after each attachment.
    """

    def __init__(self):
        # Genesis transaction
        genesis = Transaction(0, 0.0)
        genesis.is_tip = True
        genesis.cumulative_weight = 1

        self.transactions = {0: genesis}
        self.tips = {0}
        self.next_id = 1
        self.time = 0.0

    @property
    def num_transactions(self):
        return len(self.transactions)

    @property
    def num_tips(self):
        return len(self.tips)

    def get_tips(self):
        """Return set of current tip IDs."""
        return set(self.tips)

    def add_transaction(self, approved_ids, arrival_time,
                        is_malicious=False, identity=None):
        """
        Add a new transaction that approves the given tips.

        Args:
            approved_ids: list of transaction IDs to approve (typically 2)
            arrival_time: float, arrival time
            is_malicious: bool, whether this is an attacker transaction
            identity: optional identity label (for Sybil analysis)

        Returns:
            int: ID of the new transaction
        """
        tx_id = self.next_id
        self.next_id += 1
        self.time = arrival_time

        tx = Transaction(tx_id, arrival_time, is_malicious, identity)
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

        # Update cumulative weights for all ancestors
        self._update_weights(tx_id)

        return tx_id

    def _update_weights(self, new_tx_id):
        """
        Increment cumulative weight of all ancestors of new_tx_id by 1.
        Uses BFS to traverse the approval graph backwards.
        """
        visited = set()
        queue = deque()

        # Start from the parents of the new transaction
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

    def get_subtangle(self, window_size=500):
        """
        Return the most recent `window_size` transactions as a subtangle.
        Used to limit computation scope for Markov chain operations.

        Returns:
            list of transaction IDs in the subtangle (sorted by ID)
        """
        all_ids = sorted(self.transactions.keys())
        if len(all_ids) <= window_size:
            return all_ids
        return all_ids[-window_size:]

    def get_tips_in_subtangle(self, subtangle_ids):
        """Return tip IDs within a given subtangle."""
        subtangle_set = set(subtangle_ids)
        tips = []
        for tx_id in subtangle_ids:
            tx = self.transactions[tx_id]
            # A tip in the subtangle: no approvers within the subtangle
            approvers_in_sub = [a for a in tx.approved_by if a in subtangle_set]
            if len(approvers_in_sub) == 0:
                tips.append(tx_id)
        return tips

    def attach_parasite_chain(self, attach_point, chain_length, mu,
                              lam, start_time, sybil_ids=None):
        """
        Attach a Simple Parasite Chain (SPC) to the tangle.

        Following Cullen et al. and Guo et al.: the SPC is a linear chain
        where ONLY the first transaction connects to the main DAG at the
        attach point. Each subsequent transaction approves only the previous
        one in the chain (forming a chain-like topology with branching
        factor ≈ 1.0).

        Args:
            attach_point: tx_id where the SPC connects to the main DAG
            chain_length: number of transactions in the SPC (m)
            mu: attacker transaction rate
            lam: honest transaction rate (for reference)
            start_time: time when attacker starts building
            sybil_ids: list of fake identity labels (for Sybil-augmented SPC)

        Returns:
            list of malicious tx_ids
        """
        malicious_ids = []
        prev_id = attach_point
        current_time = start_time

        for i in range(chain_length):
            # Inter-arrival time for attacker
            dt = np.random.exponential(1.0 / mu) if mu > 0 else 1.0
            current_time += dt

            identity = None
            if sybil_ids is not None:
                identity = sybil_ids[i % len(sybil_ids)]

            if i == 0:
                # First SPC transaction: approves the attach point (2x)
                # This is the only link between SPC and main DAG
                approved = [attach_point, attach_point]
            else:
                # All subsequent SPC transactions: approve only previous
                # in the chain (2x the same, forming a linear chain)
                approved = [prev_id, prev_id]

            tx_id = self.add_transaction(
                approved[:2], current_time,
                is_malicious=True, identity=identity
            )
            malicious_ids.append(tx_id)
            prev_id = tx_id

        return malicious_ids


# ============================================================
# 2. TIP SELECTION ALGORITHMS
# ============================================================

class URTS:
    """Uniform Random Tip Selection — baseline."""
    name = "URTS"

    def select_tips(self, tangle, n_tips=2, **kwargs):
        tips = list(tangle.tips)
        if len(tips) < n_tips:
            return tips * n_tips  # edge case: not enough tips
        return list(np.random.choice(tips, size=n_tips, replace=False))


class MCMC:
    """
    Markov Chain Monte Carlo tip selection (Biased Random Walk).
    Parameterized by alpha.

    Following Popov (2017) and Cullen et al.:
    - Start walk deep in the DAG (100λ-200λ transactions back)
    - Transition probability: p_jk ∝ exp(-α * (H_j - H_k))
    - Walk forward until reaching a tip
    """
    def __init__(self, alpha):
        self.alpha = alpha
        self.name = f"MCMC(α={alpha})"

    def select_tips(self, tangle, n_tips=2, lam=10, **kwargs):
        tips = []
        for _ in range(n_tips):
            tip = self._random_walk(tangle, lam)
            tips.append(tip)
        return tips

    def _random_walk(self, tangle, lam):
        """Perform a single biased random walk from a deep start point to a tip."""
        all_ids = sorted(tangle.transactions.keys())
        n = len(all_ids)

        # Start point: between 100λ and 200λ transactions back
        # (or genesis if tangle is small)
        depth_low = int(100 * lam) if n > int(200 * lam) else 0
        depth_high = int(200 * lam) if n > int(200 * lam) else max(1, n // 2)
        depth_low = min(depth_low, n - 1)
        depth_high = min(depth_high, n - 1)

        if depth_low >= depth_high:
            start_idx = max(0, n - depth_high - 1)
        else:
            start_pos = np.random.randint(depth_low, depth_high + 1)
            start_idx = max(0, n - start_pos - 1)

        current = all_ids[start_idx]

        # Walk forward (toward tips) with max steps to prevent infinite loops
        max_steps = n
        for _ in range(max_steps):
            tx = tangle.transactions[current]
            if tx.is_tip or current in tangle.tips:
                return current

            # Forward neighbors: transactions that approve current
            approvers = tx.approved_by
            if not approvers:
                return current  # dead end = de facto tip

            # Compute transition probabilities
            h_current = tx.cumulative_weight
            weights = []
            for approver_id in approvers:
                h_approver = tangle.transactions[approver_id].cumulative_weight
                w = np.exp(-self.alpha * (h_current - h_approver))
                weights.append(w)

            weights = np.array(weights, dtype=np.float64)
            total = weights.sum()
            if total == 0 or np.isnan(total):
                # Fallback to uniform
                current = approvers[np.random.randint(len(approvers))]
            else:
                probs = weights / total
                current = approvers[np.random.choice(len(approvers), p=probs)]

        # Fallback: return random tip if walk didn't converge
        return list(tangle.tips)[np.random.randint(len(tangle.tips))]


class SURTS:
    """
    S-URTS: Scalable Uniform Random Tip Selection with anomaly detection.
    Following Guo, Hecker, Dustdar (2025).

    1. Convert subtangle to absorbing Markov chain (tips = absorbing states)
    2. Compute stationary distribution via power iteration
    3. Remove tips below threshold T
    4. Select uniformly from remaining tips
    """
    name = "S-URTS"

    def __init__(self, alpha=0.001, subtangle_size=500):
        self.alpha = alpha
        self.subtangle_size = subtangle_size
        self.threshold_cache = {}  # λ -> T

    def set_threshold(self, lam, threshold):
        """Set pre-computed threshold for a given λ."""
        self.threshold_cache[lam] = threshold

    def select_tips(self, tangle, n_tips=2, lam=10, **kwargs):
        subtangle_ids = tangle.get_subtangle(self.subtangle_size)
        tip_ids = tangle.get_tips_in_subtangle(subtangle_ids)

        if len(tip_ids) <= n_tips:
            return tip_ids if len(tip_ids) >= n_tips else list(tangle.tips)[:n_tips]

        # Compute selection probability distribution
        D = self._compute_stationary_distribution(tangle, subtangle_ids, tip_ids)

        # Get threshold
        T = self.threshold_cache.get(lam, None)
        if T is None:
            # Adaptive threshold: mean - 1.5 * std of distribution
            T = np.mean(D) - 1.5 * np.std(D) if len(D) > 1 else 0.0
            T = max(T, 0.0)

        # Filter tips above threshold
        eligible = [tip_ids[i] for i in range(len(tip_ids)) if D[i] >= T]

        if len(eligible) < n_tips:
            eligible = tip_ids  # fallback

        selected = list(np.random.choice(eligible, size=n_tips,
                                         replace=(len(eligible) < n_tips)))
        return selected

    def _compute_stationary_distribution(self, tangle, subtangle_ids, tip_ids):
        """
        Build absorbing Markov chain and compute stationary distribution
        via power iteration. Tips are absorbing states.

        Returns:
            numpy array of selection probabilities for each tip
        """
        n = len(subtangle_ids)
        if n == 0:
            return np.array([1.0 / max(len(tip_ids), 1)] * len(tip_ids))

        id_to_idx = {tx_id: i for i, tx_id in enumerate(subtangle_ids)}
        tip_set = set(tip_ids)

        # Build transition matrix
        P = np.zeros((n, n), dtype=np.float64)

        for tx_id in subtangle_ids:
            idx = id_to_idx[tx_id]
            tx = tangle.transactions[tx_id]

            if tx_id in tip_set:
                # Absorbing state: stays at itself
                P[idx, idx] = 1.0
                continue

            # Forward neighbors (approvers) within subtangle
            approvers = [a for a in tx.approved_by if a in id_to_idx]

            if not approvers:
                # No forward neighbors in subtangle = treat as absorbing
                P[idx, idx] = 1.0
                continue

            # Transition probabilities: exp(-α * (H_j - H_k))
            h_current = tx.cumulative_weight
            weights = []
            approver_idxs = []
            for a_id in approvers:
                a_idx = id_to_idx[a_id]
                h_a = tangle.transactions[a_id].cumulative_weight
                w = np.exp(-self.alpha * (h_current - h_a))
                weights.append(w)
                approver_idxs.append(a_idx)

            total = sum(weights)
            if total > 0:
                for w, a_idx in zip(weights, approver_idxs):
                    P[idx, a_idx] = w / total
            else:
                # Uniform fallback
                for a_idx in approver_idxs:
                    P[idx, a_idx] = 1.0 / len(approver_idxs)

        # Power iteration: π = π₀ * P^k
        # Start from the oldest transaction in subtangle
        pi = np.zeros(n, dtype=np.float64)
        pi[0] = 1.0  # start from the deepest transaction

        # Iterate until convergence
        for k in range(30):
            pi_new = pi @ P
            if np.allclose(pi, pi_new, atol=1e-10):
                break
            pi = pi_new

        # Extract tip probabilities
        tip_probs = []
        for tip_id in tip_ids:
            if tip_id in id_to_idx:
                tip_probs.append(pi[id_to_idx[tip_id]])
            else:
                tip_probs.append(0.0)

        tip_probs = np.array(tip_probs, dtype=np.float64)
        total = tip_probs.sum()
        if total > 0:
            tip_probs /= total

        return tip_probs

    def compute_tip_distribution(self, tangle, subtangle_ids=None):
        """Public method to get raw tip distribution (used by CATS Module 2)."""
        if subtangle_ids is None:
            subtangle_ids = tangle.get_subtangle(self.subtangle_size)
        tip_ids = tangle.get_tips_in_subtangle(subtangle_ids)
        D = self._compute_stationary_distribution(tangle, subtangle_ids, tip_ids)
        return tip_ids, D


class GIOTA:
    """
    G-IOTA: Fair and confidence-aware tangle.
    Following Bu, Gürcan, Potop-Butucaru (2019).

    Key difference: each new transaction approves 3 tips instead of 2,
    prioritizing tips that have been waiting longest (fairness mechanism).
    """
    name = "G-IOTA"

    def select_tips(self, tangle, n_tips=3, **kwargs):
        """Select 3 tips with fairness priority (oldest tips preferred)."""
        tips = list(tangle.tips)

        if len(tips) <= n_tips:
            return tips if len(tips) >= 2 else [tips[0], tips[0]]

        # Fairness: sort by arrival time (oldest first), then sample
        # with bias toward older tips
        tip_times = [(t, tangle.transactions[t].time) for t in tips]
        tip_times.sort(key=lambda x: x[1])  # oldest first

        # Give higher weight to older tips
        n = len(tip_times)
        weights = np.array([n - i for i in range(n)], dtype=np.float64)
        weights /= weights.sum()

        selected_indices = np.random.choice(n, size=min(n_tips, n),
                                            replace=False, p=weights)
        return [tip_times[i][0] for i in selected_indices]


class CATS:
    """
    Context-Aware Adaptive Tip Selection (CATS) algorithm.

    Module 1: Dynamic α-adaptation via composite signal S(t)
    Module 2: Adaptive anomaly detection via absorbing Markov chain
    Module 3: Fairness-preserving tip reintegration

    Parameters (reference configuration from the paper):
        alpha_min = 0.001
        alpha_max = 0.05
        w1, w2, w3 = 0.3, 0.4, 0.3  (signal weights)
        gamma = 0.15                  (EMA smoothing)
        kappa = 1.5                   (detection sensitivity)
        rho_max = 3.0                 (anomaly tip ratio)
        reintegration_interval = 50   (txns between re-evaluations)
        max_quarantine_age = 200      (max quarantine duration in txns)
    """
    name = "CATS"

    def __init__(self, alpha_min=0.001, alpha_max=0.05,
                 w1=0.3, w2=0.4, w3=0.3,
                 gamma=0.15, kappa=1.5, rho_max=3.0,
                 reintegration_interval=50, max_quarantine_age=200,
                 subtangle_size=500):
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
        self.quarantine = {}           # tx_id -> {'age': int, 'strong': bool}
        self.tx_counter = 0            # counts transactions for reintegration timing
        self.s_urts_engine = SURTS(alpha=alpha_min, subtangle_size=subtangle_size)

        # History for analysis
        self.alpha_history = []
        self.signal_history = []

    def reset(self):
        """Reset internal state for a new experiment run."""
        self.alpha_smooth = self.alpha_min
        self.quarantine = {}
        self.tx_counter = 0
        self.alpha_history = []
        self.signal_history = []

    def select_tips(self, tangle, n_tips=2, lam=10, h=1.0, **kwargs):
        """
        Full CATS tip selection procedure.

        Args:
            tangle: Tangle object
            n_tips: number of tips to select (default 2)
            lam: honest transaction arrival rate
            h: PoW duration (for L* computation)
        """
        self.tx_counter += 1

        # ── Module 1: Dynamic α-Adaptation ──
        L_star = 2 * lam * h  # theoretical URTS steady state
        num_tips = len(tangle.tips)

        # Signal σ₁: tip saturation
        rho = num_tips / max(L_star, 1)
        sigma1 = np.clip((rho - 1) / (self.rho_max - 1), 0.0, 1.0)

        # Signal σ₂: weight divergence (CV of cumulative weights across tips)
        tip_weights = [tangle.transactions[t].cumulative_weight
                       for t in tangle.tips]
        if len(tip_weights) > 1:
            mu_c = np.mean(tip_weights)
            sigma_c = np.std(tip_weights)
            delta = sigma_c / max(mu_c, 1e-10)
            delta_max = 2.0  # normalization constant
            sigma2 = min(1.0, delta / delta_max)
        else:
            sigma2 = 0.0

        # Signal σ₃: anomaly density
        sigma3 = len(self.quarantine) / max(num_tips, 1)
        sigma3 = min(1.0, sigma3)

        # Composite signal
        S = self.w1 * sigma1 + self.w2 * sigma2 + self.w3 * sigma3

        # α-adaptation with EMA smoothing
        alpha_raw = self.alpha_min + S * (self.alpha_max - self.alpha_min)
        self.alpha_smooth = (self.gamma * alpha_raw +
                             (1 - self.gamma) * self.alpha_smooth)

        self.alpha_history.append(self.alpha_smooth)
        self.signal_history.append({
            'S': S, 'sigma1': sigma1, 'sigma2': sigma2, 'sigma3': sigma3
        })

        # ── Module 2: Adaptive Anomaly Detection ──
        subtangle_ids = tangle.get_subtangle(self.subtangle_size)
        tip_ids = tangle.get_tips_in_subtangle(subtangle_ids)

        # Update the S-URTS engine's alpha to current smoothed value
        self.s_urts_engine.alpha = self.alpha_smooth

        # Compute tip distribution
        D = self.s_urts_engine._compute_stationary_distribution(
            tangle, subtangle_ids, tip_ids
        )

        # Adaptive threshold: T = μ_D - κ * σ_D
        if len(D) > 1:
            mu_D = np.mean(D)
            sigma_D = np.std(D)
            T = mu_D - self.kappa * sigma_D
            # Floor: T should be at least a small positive value
            # so that tips with D=0.0 (unreachable) are always caught
            T = max(T, 1e-10)
        else:
            T = 1e-10

        # Detect anomalous tips
        for i, tip_id in enumerate(tip_ids):
            if D[i] < T and tip_id not in self.quarantine:
                # Classify: strong vs weak anomaly
                is_strong = self._check_structural_anomaly(tangle, tip_id)
                self.quarantine[tip_id] = {
                    'age': 0,
                    'strong': is_strong,
                    'detection_tx': self.tx_counter
                }

        # Age all quarantined tips
        for tx_id in list(self.quarantine.keys()):
            self.quarantine[tx_id]['age'] += 1

        # ── Module 3: Fairness-Preserving Reintegration ──
        if self.tx_counter % self.reintegration_interval == 0:
            self._reintegrate_tips(tangle, subtangle_ids, tip_ids, D, T)

        # Build eligible tip set: L'(t) = L(t) \ Q(t)
        quarantined_ids = set(self.quarantine.keys())
        eligible = [t for t in tangle.tips if t not in quarantined_ids]

        if len(eligible) < n_tips:
            # Fallback: use all tips if quarantine too aggressive
            eligible = list(tangle.tips)

        selected = list(np.random.choice(eligible, size=n_tips,
                                         replace=(len(eligible) < n_tips)))
        return selected

    def _check_structural_anomaly(self, tangle, tip_id):
        """
        Structural check: chain-like subgraph = strong anomaly.
        Compute average branching factor of the subgraph rooted at this tip.
        Branching factor ≤ 1.2 → chain-like → strong anomaly.
        """
        visited = set()
        queue = deque([tip_id])
        total_children = 0
        total_nodes = 0

        # Walk backwards from tip through its approvals (max 20 steps)
        while queue and total_nodes < 20:
            node_id = queue.popleft()
            if node_id in visited:
                continue
            visited.add(node_id)
            total_nodes += 1

            tx = tangle.transactions[node_id]
            children_count = len(tx.approved_by)
            total_children += children_count

            for parent_id in tx.approves:
                if parent_id not in visited:
                    queue.append(parent_id)

        avg_branching = total_children / max(total_nodes, 1)
        return avg_branching <= 1.2

    def _reintegrate_tips(self, tangle, subtangle_ids, tip_ids, D, T):
        """Re-evaluate weakly anomalous tips for potential reintegration."""
        tip_id_to_idx = {tid: i for i, tid in enumerate(tip_ids)}

        for tx_id in list(self.quarantine.keys()):
            info = self.quarantine[tx_id]

            # Strong anomalies: never release
            if info['strong']:
                continue

            # Check if tip still exists
            if tx_id not in tangle.tips:
                del self.quarantine[tx_id]
                continue

            # Re-evaluate: has selection probability recovered?
            if tx_id in tip_id_to_idx:
                idx = tip_id_to_idx[tx_id]
                if D[idx] >= T:
                    del self.quarantine[tx_id]
                    continue

            # Max age release (with reduced priority — here just release)
            if info['age'] >= self.max_quarantine_age:
                del self.quarantine[tx_id]


# ============================================================
# 3. EXPERIMENT RUNNER
# ============================================================

def generate_tangle(tangle, tsa, num_transactions, lam, h=1.0, **tsa_kwargs):
    """
    Generate a tangle with proper concurrent arrival modeling.

    Transactions arrive as a Poisson process with rate λ.
    Due to PoW delay h, transactions that arrive within the same
    time window see the same DAG state (same tip set). This creates
    the characteristic DAG width proportional to λ·h.

    The simulator processes transactions in batches: all transactions
    arriving within one PoW window [t, t+h) select tips from the
    same snapshot, then are all added before the next batch.

    Args:
        tangle: Tangle object (should contain genesis)
        tsa: tip selection algorithm instance
        num_transactions: total transactions to add
        lam: Poisson arrival rate (txns/sec)
        h: PoW duration (seconds)
        tsa_kwargs: extra args passed to tsa.select_tips()

    Returns:
        list of tip counts at each step
    """
    tip_counts = []
    current_time = 0.0
    added = 0

    # For G-IOTA, use 3 approvals; for others, 2
    n_approvals = 3 if isinstance(tsa, GIOTA) else 2

    # Generate all arrival times upfront (Poisson process)
    inter_arrivals = np.random.exponential(1.0 / lam, size=num_transactions)
    arrival_times = np.cumsum(inter_arrivals)
    # Offset by current tangle time so continuations work properly
    arrival_times += tangle.time

    # CATS pre-scan: if the tangle was modified externally (e.g., SPC injected),
    # run one tip selection cycle to update CATS internal state (quarantine)
    # before any honest transactions select tips
    if isinstance(tsa, CATS) and tangle.num_transactions > 1:
        tsa.select_tips(tangle, n_tips=2, lam=lam, h=h, **tsa_kwargs)

    # Process in PoW windows of duration h
    window_start = arrival_times[0] if len(arrival_times) > 0 else 0.0
    tx_idx = 0

    while tx_idx < num_transactions:
        window_end = window_start + h

        # Collect all transactions arriving in [window_start, window_end)
        batch_times = []
        while tx_idx < num_transactions and arrival_times[tx_idx] < window_end:
            batch_times.append(arrival_times[tx_idx])
            tx_idx += 1

        if not batch_times:
            window_start = window_end
            continue

        # All transactions in this batch see the SAME tip set (snapshot)
        # They select tips independently from this snapshot
        # For CATS: exclude quarantined tips from the snapshot
        snapshot_tips = list(tangle.tips)
        if isinstance(tsa, CATS):
            quarantined = set(tsa.quarantine.keys())
            snapshot_tips = [t for t in snapshot_tips if t not in quarantined]
            if not snapshot_tips:
                snapshot_tips = list(tangle.tips)  # fallback
        batch_selections = []

        for t_arrival in batch_times:
            if len(snapshot_tips) >= n_approvals:
                selected = tsa.select_tips(tangle, n_tips=n_approvals,
                                           lam=lam, h=h, **tsa_kwargs)
            elif len(snapshot_tips) >= 1:
                selected = list(snapshot_tips)
                # Pad to n_approvals by repeating
                while len(selected) < n_approvals:
                    selected.append(snapshot_tips[
                        np.random.randint(len(snapshot_tips))])
            else:
                selected = [0]  # genesis fallback

            # Ensure at least 2 distinct tips if possible
            selected_set = list(set(selected))
            if len(selected_set) < 2 and len(snapshot_tips) >= 2:
                remaining = [t for t in snapshot_tips if t not in selected_set]
                if remaining:
                    selected_set.append(remaining[
                        np.random.randint(len(remaining))])
            selected = selected_set[:n_approvals]
            if len(selected) < 2:
                selected = selected * 2  # minimum 2 approvals

            batch_selections.append((t_arrival, selected))

        # Now add all transactions in this batch to the tangle
        for t_arrival, selected in batch_selections:
            tangle.add_transaction(selected, t_arrival)
            tip_counts.append(len(tangle.tips))

        window_start = window_end

    return tip_counts


def run_scalability_experiment(tsa, lam, num_transactions=2000,
                               h=1.0, num_runs=100):
    """
    Scalability experiment: benign conditions, measure tip counts.

    Returns:
        dict with mean_tips, std_tips, tip_history (from last run)
    """
    all_mean_tips = []

    for run in range(num_runs):
        tangle = Tangle()
        if isinstance(tsa, CATS):
            tsa.reset()

        tip_counts = generate_tangle(tangle, tsa, num_transactions, lam, h)
        # Mean tip count in steady state (skip first 200 for warmup)
        steady = tip_counts[200:] if len(tip_counts) > 200 else tip_counts
        all_mean_tips.append(np.mean(steady))

    return {
        'mean_tips': np.mean(all_mean_tips),
        'std_tips': np.std(all_mean_tips),
        'all_runs': all_mean_tips
    }


def run_security_experiment(tsa, lam, num_transactions=2000,
                            spc_lengths=None, mu=5, T_DS=120,
                            subtangle_attach=500, h=1.0, num_runs=100):
    """
    Security experiment: attach SPC at midpoint, measure p₂.

    Following Guo et al. (2025) methodology: generate tangle of size N,
    attach SPC at fixed site in subtangle, then measure the tip selection
    probability distribution over the resulting tangle (including SPC).
    p₂ is the probability that the TSA selects an SPC tip.

    Args:
        tsa: tip selection algorithm
        lam: honest arrival rate
        spc_lengths: list of SPC chain lengths to test
        mu: attacker rate
        T_DS: broadcast delay
        subtangle_attach: transaction count for the base tangle
        num_runs: number of independent runs

    Returns:
        dict mapping spc_length -> {mean_p2, std_p2}
    """
    if spc_lengths is None:
        spc_lengths = [10, 30, 50]

    results = {}

    for m in spc_lengths:
        p2_values = []

        for run in range(num_runs):
            tangle = Tangle()
            if isinstance(tsa, CATS):
                tsa.reset()

            # Phase 1: Build honest tangle
            generate_tangle(tangle, tsa, subtangle_attach, lam, h)

            # Phase 2: Attach parasite chain at midpoint of the tangle
            # Following Guo et al.: attach at the point with maximum
            # distance in the subtangle (we use midpoint as approximation)
            attach_point = subtangle_attach // 2
            if attach_point not in tangle.transactions:
                all_ids = sorted(tangle.transactions.keys())
                attach_point = all_ids[len(all_ids) // 2]

            current_time = tangle.time
            malicious_ids = tangle.attach_parasite_chain(
                attach_point=attach_point,
                chain_length=m,
                mu=mu,
                lam=lam,
                start_time=current_time
            )
            malicious_set = set(malicious_ids)

            # Phase 3: Add a small number of honest txns (one PoW window)
            # so the TSA can "see" the SPC but it hasn't been buried yet
            small_batch = max(int(lam * h), 5)
            generate_tangle(tangle, tsa, small_batch, lam, h)

            # Measure p₂: run many tip selections on the current tangle
            # and count how often an SPC tip is selected
            n_samples = 1000
            malicious_selections = 0
            total_selections = 0

            # Only count SPC tips that are still tips
            active_mal_tips = malicious_set & tangle.tips

            for _ in range(n_samples):
                test_tips = tsa.select_tips(tangle, n_tips=2, lam=lam, h=h)
                for t in test_tips:
                    total_selections += 1
                    if t in active_mal_tips:
                        malicious_selections += 1

            p2 = malicious_selections / max(total_selections, 1)
            p2_values.append(p2)

        results[m] = {
            'mean_p2': np.mean(p2_values),
            'std_p2': np.std(p2_values),
            'all_runs': p2_values
        }

    return results


def run_adaptive_response_experiment(lam=15, mu=5, spc_length=30,
                                     num_transactions=1000, h=1.0):
    """
    Track CATS α̃(t) evolution when an SPC is attached mid-experiment.
    Single run for detailed analysis.

    Returns:
        dict with alpha_history, signal_history, detection_latency
    """
    cats = CATS()
    cats.reset()
    tangle = Tangle()

    attach_at = 250  # attach SPC after 250 transactions
    current_time = 0.0

    for i in range(num_transactions):
        dt = np.random.exponential(1.0 / lam)
        current_time += dt

        # Attach SPC at the specified point
        if i == attach_at:
            attach_point = attach_at // 2
            if attach_point not in tangle.transactions:
                attach_point = max(tangle.transactions.keys()) // 2
            tangle.attach_parasite_chain(
                attach_point=attach_point,
                chain_length=spc_length,
                mu=mu,
                lam=lam,
                start_time=current_time
            )

        selected = cats.select_tips(tangle, n_tips=2, lam=lam, h=h)
        selected = list(set(selected))
        if len(selected) < 2 and len(tangle.tips) >= 2:
            remaining = [t for t in tangle.tips if t not in selected]
            if remaining:
                selected.append(np.random.choice(remaining))
        tangle.add_transaction(selected, current_time)

    # Find detection latency: first quarantine after attach_at
    detection_latency = None
    for tx_id, info in cats.quarantine.items():
        if tangle.transactions[tx_id].is_malicious:
            latency = info.get('detection_tx', 0) - attach_at
            if detection_latency is None or latency < detection_latency:
                detection_latency = latency

    return {
        'alpha_history': cats.alpha_history,
        'signal_history': cats.signal_history,
        'detection_latency': detection_latency,
        'quarantine_size': len(cats.quarantine),
        'attach_at': attach_at
    }


# ============================================================
# 4. MAIN EXPERIMENT SCRIPT
# ============================================================

def main():
    """Run the complete experiment suite from the CATS paper."""

    print("=" * 70)
    print("CATS Tangle Simulator — Experiment Suite")
    print("=" * 70)

    # Configuration
    lambdas = [5, 10, 15, 20]
    num_transactions = 2000
    num_runs = 100          # Use 10 for quick testing; paper uses 100
    spc_lengths = [10, 30, 50]
    mu = 5
    h = 1.0

    # Pre-computed thresholds for S-URTS (from Guo et al. 2025)
    surts_thresholds = {5: 0.035, 10: 0.015, 15: 0.01, 20: 0.007}

    # Initialize algorithms
    algorithms = {
        'URTS': URTS(),
        'MCMC1': MCMC(alpha=0.001),
        'MCMC5': MCMC(alpha=0.05),
        'S-URTS': SURTS(alpha=0.001, subtangle_size=500),
        'G-IOTA': GIOTA(),
        'CATS': CATS(),
    }

    # Set S-URTS thresholds
    for lam_val, thresh in surts_thresholds.items():
        algorithms['S-URTS'].set_threshold(lam_val, thresh)

    results_dir = "./results/"
    os.makedirs(results_dir, exist_ok=True)

    # ── Experiment A: Scalability (benign conditions) ──
    print("\n" + "─" * 70)
    print("EXPERIMENT A: SCALABILITY (Benign Conditions)")
    print("─" * 70)

    scalability_results = {}

    for lam in lambdas:
        print(f"\n  λ = {lam} txn/s")
        scalability_results[lam] = {}

        for alg_name, tsa in algorithms.items():
            t0 = time.time()
            result = run_scalability_experiment(
                tsa, lam, num_transactions, h, num_runs
            )
            elapsed = time.time() - t0
            scalability_results[lam][alg_name] = result
            print(f"    {alg_name:10s}: mean tips = {result['mean_tips']:6.1f} "
                  f"± {result['std_tips']:5.2f}  ({elapsed:.1f}s)")

    # ── Experiment B: Security (Parasite Chain Attack) ──
    print("\n" + "─" * 70)
    print("EXPERIMENT B: SECURITY (Parasite Chain Attack)")
    print(f"  λ = 15, µ = {mu}, SPC lengths = {spc_lengths}")
    print("─" * 70)

    security_algorithms = {
        'URTS': algorithms['URTS'],
        'MCMC1': algorithms['MCMC1'],
        'MCMC5': algorithms['MCMC5'],
        'S-URTS': algorithms['S-URTS'],
        'G-IOTA': algorithms['G-IOTA'],
        'CATS': algorithms['CATS'],
    }

    security_results = {}
    for alg_name, tsa in security_algorithms.items():
        t0 = time.time()
        result = run_security_experiment(
            tsa, lam=15, num_transactions=num_transactions,
            spc_lengths=spc_lengths, mu=mu, h=h, num_runs=num_runs
        )
        elapsed = time.time() - t0
        security_results[alg_name] = result
        print(f"\n  {alg_name}:  ({elapsed:.1f}s)")
        for m in spc_lengths:
            r = result[m]
            print(f"    m={m:3d}: p₂ = {r['mean_p2']:.4f} ± {r['std_p2']:.4f}")

    # ── Experiment C: Adaptive Response Dynamics ──
    print("\n" + "─" * 70)
    print("EXPERIMENT C: CATS Adaptive Response Dynamics")
    print("─" * 70)

    adaptive_result = run_adaptive_response_experiment(
        lam=15, mu=5, spc_length=30, num_transactions=1000, h=h
    )
    print(f"  Detection latency: {adaptive_result['detection_latency']} transactions")
    print(f"  Final quarantine size: {adaptive_result['quarantine_size']}")
    print(f"  α̃ range: [{min(adaptive_result['alpha_history']):.4f}, "
          f"{max(adaptive_result['alpha_history']):.4f}]")

    # ── Save Results ──
    print("\n" + "─" * 70)
    print("SAVING RESULTS")
    print("─" * 70)

    # Format scalability table (Table II from paper)
    print("\n  TABLE II: Mean Tip Count (Benign Conditions, N=2000)")
    print(f"  {'λ':>4s}", end="")
    for alg in ['URTS', 'MCMC1', 'MCMC5', 'S-URTS', 'G-IOTA', 'CATS']:
        print(f"  {alg:>8s}", end="")
    print()
    for lam in lambdas:
        print(f"  {lam:4d}", end="")
        for alg in ['URTS', 'MCMC1', 'MCMC5', 'S-URTS', 'G-IOTA', 'CATS']:
            val = scalability_results[lam][alg]['mean_tips']
            print(f"  {val:8.1f}", end="")
        print()

    # Format security table (Table III from paper)
    print("\n  TABLE III: SPC Tip Selection Probability p₂ (λ=15, µ=5)")
    print(f"  {'m':>6s}", end="")
    for alg in ['URTS', 'MCMC1', 'MCMC5', 'S-URTS', 'G-IOTA', 'CATS']:
        print(f"  {alg:>8s}", end="")
    print()
    for m in spc_lengths:
        print(f"  m={m:3d}", end="")
        for alg in ['URTS', 'MCMC1', 'MCMC5', 'S-URTS', 'G-IOTA', 'CATS']:
            val = security_results[alg][m]['mean_p2']
            print(f"  {val:8.4f}", end="")
        print()

    # Save raw results as JSON
    save_data = {
        'config': {
            'lambdas': lambdas,
            'num_transactions': num_transactions,
            'num_runs': num_runs,
            'spc_lengths': spc_lengths,
            'mu': mu, 'h': h
        },
        'scalability': {
            str(lam): {
                alg: {'mean': r['mean_tips'], 'std': r['std_tips']}
                for alg, r in alg_results.items()
            }
            for lam, alg_results in scalability_results.items()
        },
        'security': {
            alg: {
                str(m): {'mean_p2': r['mean_p2'], 'std_p2': r['std_p2']}
                for m, r in alg_results.items()
            }
            for alg, alg_results in security_results.items()
        },
        'adaptive': {
            'detection_latency': adaptive_result['detection_latency'],
            'quarantine_size': adaptive_result['quarantine_size'],
            'alpha_range': [
                min(adaptive_result['alpha_history']),
                max(adaptive_result['alpha_history'])
            ]
        }
    }

    with open(f"{results_dir}/experiment_results.json", 'w') as f:
        json.dump(save_data, f, indent=2)

    # Save alpha history for plotting
    np.savetxt(f"{results_dir}/alpha_history.csv",
               adaptive_result['alpha_history'], delimiter=',')

    print(f"\n  Results saved to {results_dir}/")
    print("=" * 70)
    print("EXPERIMENT SUITE COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
