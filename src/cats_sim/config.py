"""Experiment-suite configuration: TOML files validated into frozen dataclasses.

Validation is strict on purpose: an unknown key is almost always a typo, and
a typo in a research configuration silently produces wrong results.
"""

from __future__ import annotations

import dataclasses
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cats_sim.strategies import REGISTRY, TipSelectionStrategy, create_strategy
from cats_sim.strategies.cats import CATS

EXPERIMENTS: tuple[str, ...] = ("scalability", "security", "adaptive")


class ConfigError(ValueError):
    """Raised when a configuration file is invalid."""


@dataclass(frozen=True)
class AlgorithmSpec:
    """A configured tip selection algorithm (``kind`` + constructor parameters)."""

    label: str
    kind: str
    params: dict[str, Any] = field(default_factory=dict)

    def create(self) -> TipSelectionStrategy:
        """Build a fresh strategy instance (one per simulation run)."""
        return create_strategy(self.kind, **self.params)


@dataclass(frozen=True)
class ScalabilityConfig:
    """Experiment A: mean tip count under benign conditions."""

    algorithms: tuple[str, ...]
    lambdas: tuple[float, ...] = (5.0, 10.0, 15.0, 20.0)
    num_transactions: int = 2000
    num_runs: int = 100
    warmup: int = 200  # transactions skipped before measuring the steady state


@dataclass(frozen=True)
class SecurityConfig:
    """Experiment B: probability p₂ of selecting a parasite-chain tip."""

    algorithms: tuple[str, ...]
    lam: float = 15.0
    mu: float = 5.0
    spc_lengths: tuple[int, ...] = (10, 30, 50)
    base_transactions: int = 500  # honest tangle size before the attack
    n_samples: int = 1000  # tip selections used to estimate p₂
    num_runs: int = 100


@dataclass(frozen=True)
class AdaptiveConfig:
    """Experiment C: CATS α̃(t) response and detection latency."""

    algorithm: str = "CATS"
    lam: float = 15.0
    mu: float = 5.0
    spc_length: int = 30
    num_transactions: int = 1000
    attach_at: int = 250  # honest transactions before the SPC is attached
    num_runs: int = 100
    peak_window: int = 50  # selections after the attack searched for the α̃ peak


@dataclass(frozen=True)
class SuiteConfig:
    """A complete, validated experiment suite."""

    seed: int
    h: float
    algorithms: dict[str, AlgorithmSpec]
    scalability: ScalabilityConfig | None = None
    security: SecurityConfig | None = None
    adaptive: AdaptiveConfig | None = None

    @property
    def enabled_experiments(self) -> list[str]:
        return [name for name in EXPERIMENTS if getattr(self, name) is not None]

    def restricted_to(self, names: Iterable[str]) -> SuiteConfig:
        """Return a copy with only the given experiments enabled."""
        keep = set(names)
        unknown = keep - set(EXPERIMENTS)
        if unknown:
            raise ConfigError(f"unknown experiments: {sorted(unknown)}")
        changes: dict[str, Any] = {name: None for name in EXPERIMENTS if name not in keep}
        return dataclasses.replace(self, **changes)

    def with_num_runs(self, num_runs: int) -> SuiteConfig:
        """Return a copy where every enabled experiment uses ``num_runs`` runs."""
        if num_runs < 1:
            raise ConfigError("num_runs must be >= 1")
        changes = {
            name: dataclasses.replace(getattr(self, name), num_runs=num_runs)
            for name in self.enabled_experiments
        }
        return dataclasses.replace(self, **changes)

    def with_seed(self, seed: int) -> SuiteConfig:
        if seed < 0:
            raise ConfigError("seed must be >= 0")
        return dataclasses.replace(self, seed=seed)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation (stored next to the results)."""
        return dataclasses.asdict(self)


# --------------------------------------------------------------------- loading


def load_config(path: str | Path) -> SuiteConfig:
    """Read and validate a TOML configuration file."""
    path = Path(path)
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        raise ConfigError(f"configuration file not found: {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: invalid TOML: {exc}") from None
    return parse_config(data)


def parse_config(data: Mapping[str, Any]) -> SuiteConfig:
    """Validate an already-parsed configuration mapping."""
    root = _Reader(data, "")
    sim = _Reader(root.table("simulation"), "simulation")
    seed = sim.get_int("seed", minimum=0)
    h = sim.get_float("h", 1.0, positive=True)
    sim.finish()

    algorithms = _parse_algorithms(root.table("algorithms"))
    experiments = _Reader(root.table("experiments", {}), "experiments")
    root.finish()

    scalability = security = adaptive = None

    table = experiments.optional_table("scalability")
    if table is not None and _enabled(table, "experiments.scalability"):
        r = _Reader(table, "experiments.scalability")
        r.get_bool("enabled", True)
        scalability = ScalabilityConfig(
            algorithms=_algorithm_refs(r, algorithms),
            lambdas=r.get_float_list("lambdas", ScalabilityConfig.lambdas),
            num_transactions=r.get_int(
                "num_transactions", ScalabilityConfig.num_transactions, minimum=1
            ),
            num_runs=r.get_int("num_runs", ScalabilityConfig.num_runs, minimum=1),
            warmup=r.get_int("warmup", ScalabilityConfig.warmup, minimum=0),
        )
        r.finish()

    table = experiments.optional_table("security")
    if table is not None and _enabled(table, "experiments.security"):
        r = _Reader(table, "experiments.security")
        r.get_bool("enabled", True)
        security = SecurityConfig(
            algorithms=_algorithm_refs(r, algorithms),
            lam=r.get_float("lam", SecurityConfig.lam, positive=True),
            mu=r.get_float("mu", SecurityConfig.mu, minimum=0.0),
            spc_lengths=r.get_int_list("spc_lengths", SecurityConfig.spc_lengths, minimum=1),
            base_transactions=r.get_int(
                "base_transactions", SecurityConfig.base_transactions, minimum=1
            ),
            n_samples=r.get_int("n_samples", SecurityConfig.n_samples, minimum=1),
            num_runs=r.get_int("num_runs", SecurityConfig.num_runs, minimum=1),
        )
        r.finish()

    table = experiments.optional_table("adaptive")
    if table is not None and _enabled(table, "experiments.adaptive"):
        r = _Reader(table, "experiments.adaptive")
        r.get_bool("enabled", True)
        label = r.get_str("algorithm", AdaptiveConfig.algorithm)
        spec = algorithms.get(label)
        if spec is None:
            raise ConfigError(f"experiments.adaptive.algorithm: unknown algorithm {label!r}")
        if not issubclass(REGISTRY[spec.kind], CATS):
            raise ConfigError("experiments.adaptive.algorithm must refer to a CATS algorithm")
        adaptive = AdaptiveConfig(
            algorithm=label,
            lam=r.get_float("lam", AdaptiveConfig.lam, positive=True),
            mu=r.get_float("mu", AdaptiveConfig.mu, minimum=0.0),
            spc_length=r.get_int("spc_length", AdaptiveConfig.spc_length, minimum=1),
            num_transactions=r.get_int(
                "num_transactions", AdaptiveConfig.num_transactions, minimum=1
            ),
            attach_at=r.get_int("attach_at", AdaptiveConfig.attach_at, minimum=1),
            num_runs=r.get_int("num_runs", AdaptiveConfig.num_runs, minimum=1),
            peak_window=r.get_int("peak_window", AdaptiveConfig.peak_window, minimum=1),
        )
        r.finish()
        if adaptive.attach_at >= adaptive.num_transactions:
            raise ConfigError("experiments.adaptive: attach_at must be < num_transactions")

    experiments.finish()
    return SuiteConfig(seed, h, algorithms, scalability, security, adaptive)


def _parse_algorithms(table: Mapping[str, Any]) -> dict[str, AlgorithmSpec]:
    if not table:
        raise ConfigError("[algorithms] must define at least one algorithm")
    specs: dict[str, AlgorithmSpec] = {}
    for label, raw in table.items():
        where = f"algorithms.{label}"
        if not isinstance(raw, Mapping):
            raise ConfigError(f"{where}: expected a table like {{ kind = 'urts' }}")
        params = dict(raw)
        kind = params.pop("kind", None)
        if kind not in REGISTRY:
            raise ConfigError(f"{where}.kind: expected one of {sorted(REGISTRY)}, got {kind!r}")
        spec = AlgorithmSpec(label=label, kind=kind, params=params)
        try:
            spec.create()  # validate parameters early
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{where}: {exc}") from None
        specs[label] = spec
    return specs


def _algorithm_refs(r: _Reader, algorithms: Mapping[str, AlgorithmSpec]) -> tuple[str, ...]:
    labels = r.get_str_list("algorithms", tuple(algorithms))
    unknown = [label for label in labels if label not in algorithms]
    if unknown:
        raise ConfigError(f"{r.where}.algorithms: unknown algorithms {unknown}")
    if not labels:
        raise ConfigError(f"{r.where}.algorithms must not be empty")
    return labels


def _enabled(table: Mapping[str, Any], where: str) -> bool:
    value = table.get("enabled", True)
    if not isinstance(value, bool):
        raise ConfigError(f"{where}.enabled: expected true/false")
    return value


_MISSING: Any = object()


class _Reader:
    """Typed access to one TOML table that remembers which keys were used."""

    def __init__(self, table: Mapping[str, Any], where: str) -> None:
        self._table = table
        self._used: set[str] = set()
        self.where = where

    def _key(self, key: str) -> str:
        return f"{self.where}.{key}" if self.where else key

    def _get(self, key: str, default: Any) -> Any:
        self._used.add(key)
        if key in self._table:
            return self._table[key]
        if default is _MISSING:
            raise ConfigError(f"missing required key {self._key(key)!r}")
        return default

    def optional_table(self, key: str) -> Mapping[str, Any] | None:
        """A sub-table, or ``None`` when absent (an empty table means "use defaults")."""
        return self.table(key) if key in self._table else self._get(key, None)

    def table(self, key: str, default: Any = _MISSING) -> Mapping[str, Any]:
        value = self._get(key, default)
        if not isinstance(value, Mapping):
            raise ConfigError(f"{self._key(key)}: expected a table")
        return value

    def get_bool(self, key: str, default: Any = _MISSING) -> bool:
        value = self._get(key, default)
        if not isinstance(value, bool):
            raise ConfigError(f"{self._key(key)}: expected true/false, got {value!r}")
        return value

    def get_str(self, key: str, default: Any = _MISSING) -> str:
        value = self._get(key, default)
        if not isinstance(value, str):
            raise ConfigError(f"{self._key(key)}: expected a string, got {value!r}")
        return value

    def get_int(self, key: str, default: Any = _MISSING, *, minimum: int | None = None) -> int:
        return self._check_int(self._key(key), self._get(key, default), minimum)

    def get_float(
        self,
        key: str,
        default: Any = _MISSING,
        *,
        minimum: float | None = None,
        positive: bool = False,
    ) -> float:
        return self._check_float(self._key(key), self._get(key, default), minimum, positive)

    def get_int_list(
        self, key: str, default: Any = _MISSING, *, minimum: int | None = None
    ) -> tuple[int, ...]:
        values = self._list(key, default)
        return tuple(
            self._check_int(f"{self._key(key)}[{i}]", v, minimum) for i, v in enumerate(values)
        )

    def get_float_list(self, key: str, default: Any = _MISSING) -> tuple[float, ...]:
        values = self._list(key, default)
        return tuple(
            self._check_float(f"{self._key(key)}[{i}]", v, None, True) for i, v in enumerate(values)
        )

    def get_str_list(self, key: str, default: Any = _MISSING) -> tuple[str, ...]:
        values = self._list(key, default)
        if not all(isinstance(v, str) for v in values):
            raise ConfigError(f"{self._key(key)}: expected a list of strings")
        return tuple(values)

    def finish(self) -> None:
        unknown = sorted(set(self._table) - self._used)
        if unknown:
            where = f" in [{self.where}]" if self.where else ""
            raise ConfigError(f"unknown keys{where}: {unknown}")

    def _list(self, key: str, default: Any) -> list[Any]:
        value = self._get(key, default)
        if not isinstance(value, (list, tuple)) or not value:
            raise ConfigError(f"{self._key(key)}: expected a non-empty list")
        return list(value)

    @staticmethod
    def _check_int(where: str, value: Any, minimum: int | None) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{where}: expected an integer, got {value!r}")
        if minimum is not None and value < minimum:
            raise ConfigError(f"{where}: must be >= {minimum}, got {value}")
        return value

    @staticmethod
    def _check_float(where: str, value: Any, minimum: float | None, positive: bool) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{where}: expected a number, got {value!r}")
        number = float(value)
        if positive and number <= 0:
            raise ConfigError(f"{where}: must be > 0, got {number}")
        if minimum is not None and number < minimum:
            raise ConfigError(f"{where}: must be >= {minimum}, got {number}")
        return number
