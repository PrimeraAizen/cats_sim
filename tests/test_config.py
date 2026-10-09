from __future__ import annotations

import copy
import json
import tomllib
from pathlib import Path
from typing import Any

import pytest

from cats_sim.config import ConfigError, SuiteConfig, load_config, parse_config
from cats_sim.strategies import CATS, MCMC, SURTS
from tests.helpers import CONFIG_DIR, SMOKE_CONFIG


def _smoke() -> dict[str, Any]:
    with SMOKE_CONFIG.open("rb") as fh:
        return tomllib.load(fh)


@pytest.mark.parametrize("path", sorted(CONFIG_DIR.glob("*.toml")), ids=lambda p: p.name)
def test_shipped_configs_are_valid(path: Path):
    config = load_config(path)
    assert config.enabled_experiments == ["scalability", "security", "adaptive"]
    for spec in config.algorithms.values():
        spec.create()


def test_paper_config_matches_the_original_experiment_setup():
    config = load_config(CONFIG_DIR / "paper.toml")
    assert config.h == 1.0
    assert config.scalability is not None
    assert config.scalability.lambdas == (5.0, 10.0, 15.0, 20.0)
    assert config.scalability.algorithms == ("URTS", "MCMC1", "MCMC5", "S-URTS", "G-IOTA", "CATS")
    assert (config.scalability.num_transactions, config.scalability.warmup) == (2000, 200)
    assert config.security is not None
    assert config.security.algorithms == ("URTS", "MCMC1", "S-URTS", "CATS")
    assert (config.security.lam, config.security.mu) == (15.0, 5.0)
    assert config.security.spc_lengths == (10, 30, 50)
    assert (config.security.base_transactions, config.security.n_samples) == (500, 1000)
    assert config.adaptive is not None
    assert (config.adaptive.attach_at, config.adaptive.num_transactions) == (250, 1000)
    assert {e: getattr(config, e).num_runs for e in config.enabled_experiments} == {
        "scalability": 100,
        "security": 100,
        "adaptive": 100,
    }

    surts = config.algorithms["S-URTS"].create()
    assert isinstance(surts, SURTS)
    assert surts.thresholds == {5.0: 0.035, 10.0: 0.015, 15.0: 0.01, 20.0: 0.007}
    mcmc = config.algorithms["MCMC5"].create()
    assert isinstance(mcmc, MCMC)
    assert mcmc.alpha == 0.05
    assert isinstance(config.algorithms["CATS"].create(), CATS)


def test_disabled_and_missing_experiments_are_none():
    data = _smoke()
    data["experiments"]["security"]["enabled"] = False
    del data["experiments"]["adaptive"]
    config = parse_config(data)
    assert config.enabled_experiments == ["scalability"]
    assert config.security is None
    assert config.adaptive is None


def test_defaults_fill_omitted_keys():
    data = {
        "simulation": {"seed": 3},
        "algorithms": {"CATS": {"kind": "cats"}},
        "experiments": {"adaptive": {}},
    }
    config = parse_config(data)
    assert config.h == 1.0
    assert config.adaptive is not None
    assert (config.adaptive.lam, config.adaptive.num_runs) == (15.0, 100)


def _mutated(path: list[str], value: Any) -> dict[str, Any]:
    data = copy.deepcopy(_smoke())
    node = data
    for key in path[:-1]:
        node = node[key]
    if value is _DELETE:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return data


_DELETE = object()


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (["simulation", "seed"], _DELETE, "missing required key 'simulation.seed'"),
        (["simulation", "seed"], -1, "must be >= 0"),
        (["simulation", "h"], 0, "must be > 0"),
        (["simulation", "h"], "fast", "expected a number"),
        (["simulation", "typo"], 1, r"unknown keys in \[simulation\]"),
        (["experiments", "scalability", "num_run"], 5, "unknown keys"),
        (["experiments", "scalability", "num_runs"], 0, "must be >= 1"),
        (["experiments", "scalability", "num_runs"], True, "expected an integer"),
        (["experiments", "scalability", "lambdas"], [], "non-empty list"),
        (["experiments", "scalability", "lambdas"], [5, -1], r"lambdas\[1\]"),
        (["experiments", "scalability", "algorithms"], ["NOPE"], "unknown algorithms"),
        (["experiments", "scalability", "algorithms"], [1], "list of strings"),
        (["experiments", "scalability", "enabled"], "yes", "expected true/false"),
        (["experiments", "security", "spc_lengths"], [0], "must be >= 1"),
        (["experiments", "adaptive", "algorithm"], "URTS", "must refer to a CATS"),
        (["experiments", "adaptive", "algorithm"], "NOPE", "unknown algorithm"),
        (["experiments", "adaptive", "algorithm"], 5, "expected a string"),
        (["experiments", "adaptive", "attach_at"], 500, "attach_at must be <"),
        (["experiments", "security"], "x", "expected a table"),
        (["algorithms", "URTS", "kind"], "nope", "algorithms.URTS.kind"),
        (["algorithms", "MCMC1", "alpha"], _DELETE, "algorithms.MCMC1"),
        (["algorithms", "CATS", "gamma"], 2.0, "gamma"),
        (["algorithms", "URTS"], "urts", "expected a table"),
        (["algorithms"], {}, "at least one algorithm"),
        (["typo"], {}, "unknown keys"),
    ],
)
def test_invalid_configs_are_rejected_with_a_helpful_message(path, value, message):
    with pytest.raises(ConfigError, match=message):
        parse_config(_mutated(path, value))


def test_load_config_reports_missing_and_malformed_files(tmp_path: Path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.toml")
    bad = tmp_path / "bad.toml"
    bad.write_text("this is = = not toml")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(bad)


def test_overrides_return_modified_copies():
    config = load_config(SMOKE_CONFIG)
    only = config.restricted_to(["adaptive"])
    assert only.enabled_experiments == ["adaptive"]
    assert config.enabled_experiments == ["scalability", "security", "adaptive"]

    runs = config.with_num_runs(7)
    assert all(getattr(runs, e).num_runs == 7 for e in runs.enabled_experiments)
    assert config.with_seed(99).seed == 99

    with pytest.raises(ConfigError):
        config.restricted_to(["nope"])
    with pytest.raises(ConfigError):
        config.with_num_runs(0)
    with pytest.raises(ConfigError):
        config.with_seed(-5)


def test_config_is_json_serialisable():
    config: SuiteConfig = load_config(CONFIG_DIR / "paper.toml")
    data = json.loads(json.dumps(config.to_dict()))
    assert data["seed"] == config.seed
    assert data["algorithms"]["S-URTS"]["params"]["thresholds"]["5"] == 0.035
