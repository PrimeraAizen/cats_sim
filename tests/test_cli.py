from __future__ import annotations

import csv
import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest

from cats_sim import __version__
from cats_sim.cli import main
from tests.helpers import SMOKE_CONFIG


def _run(tmp_path: Path, *extra: str) -> Path:
    out = tmp_path / "out"
    assert main(["run", str(SMOKE_CONFIG), "-o", str(out), "--runs", "1", *extra]) == 0
    return out


def test_run_writes_tables_and_result_files(tmp_path, capsys):
    out = _run(tmp_path)

    stdout = capsys.readouterr().out
    assert "TABLE II" in stdout
    assert "TABLE III" in stdout
    assert "Detection rate" in stdout

    expected = {
        "results.json",
        "scalability.csv",
        "security.csv",
        "adaptive_runs.csv",
        "alpha_history.csv",
    }
    assert {p.name for p in out.iterdir()} == expected

    data = json.loads((out / "results.json").read_text())
    assert data["metadata"]["cats_sim_version"] == __version__
    assert data["config"]["seed"] == 1
    assert {r["algorithm"] for r in data["scalability"]} == {
        "URTS",
        "MCMC1",
        "S-URTS",
        "G-IOTA",
        "CATS",
    }
    assert data["adaptive"]["num_runs"] == 1

    with (out / "alpha_history.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0]) == ["step", "alpha", "S", "sigma1", "sigma2", "sigma3"]


def test_only_and_seed_options(tmp_path):
    out = _run(tmp_path, "--only", "security", "--seed", "42")
    assert {p.name for p in out.iterdir()} == {"results.json", "security.csv"}
    data = json.loads((out / "results.json").read_text())
    assert data["config"]["seed"] == 42
    assert data["config"]["scalability"] is None


def test_same_seed_gives_identical_results(tmp_path):
    first = json.loads((_run(tmp_path / "a") / "results.json").read_text())
    second = json.loads((_run(tmp_path / "b") / "results.json").read_text())
    del first["metadata"]["created_utc"], second["metadata"]["created_utc"]
    assert first == second


def test_configuration_errors_exit_with_code_2(tmp_path, capsys):
    assert main(["run", str(tmp_path / "missing.toml")]) == 2
    assert "configuration error" in capsys.readouterr().err

    assert main(["run", str(SMOKE_CONFIG), "--runs", "0"]) == 2


def test_disabling_every_experiment_is_an_error(tmp_path, capsys):
    config = tmp_path / "empty.toml"
    config.write_text('[simulation]\nseed = 1\n[algorithms]\nURTS = { kind = "urts" }\n')
    assert main(["run", str(config), "-o", str(tmp_path / "out")]) == 2
    assert "no experiment is enabled" in capsys.readouterr().err


def test_algorithms_command_lists_registered_kinds(capsys):
    assert main(["algorithms"]) == 0
    listed = [line.split()[0] for line in capsys.readouterr().out.splitlines()]
    assert listed == ["cats", "giota", "mcmc", "surts", "urts"]


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_plot_command_reports_missing_results(tmp_path, capsys):
    assert main(["plot", str(tmp_path)]) == 1
    assert "No plottable results" in capsys.readouterr().err


def test_module_entry_point():
    proc = subprocess.run(
        [sys.executable, "-m", "cats_sim", "algorithms"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "cats" in proc.stdout


def test_verbose_flag_only_affects_this_package():
    assert main(["-v", "algorithms"]) == 0
    assert logging.getLogger("cats_sim").level == logging.DEBUG
    assert logging.getLogger("matplotlib").getEffectiveLevel() >= logging.WARNING
    assert main(["algorithms"]) == 0
    assert logging.getLogger("cats_sim").level == logging.INFO
