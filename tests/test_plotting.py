from __future__ import annotations

import builtins
from pathlib import Path

import pytest

from cats_sim import plotting
from cats_sim.cli import main
from tests.helpers import SMOKE_CONFIG

pytest.importorskip("matplotlib")


@pytest.fixture(scope="module")
def results_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("results")
    assert main(["run", str(SMOKE_CONFIG), "-o", str(out), "--runs", "1"]) == 0
    return out


@pytest.mark.parametrize("fmt", ["png", "pdf", "svg"])
def test_plot_results_writes_every_figure(results_dir, fmt):
    paths = plotting.plot_results(results_dir, fmt=fmt)
    assert [p.name for p in paths] == [
        f"fig_scalability.{fmt}",
        f"fig_security.{fmt}",
        f"fig_alpha.{fmt}",
    ]
    assert all(p.stat().st_size > 1000 for p in paths)


def test_plot_command(results_dir, capsys):
    assert main(["plot", str(results_dir)]) == 0
    assert "fig_alpha.png" in capsys.readouterr().out


def test_plot_results_without_results_returns_nothing(tmp_path):
    assert plotting.plot_results(tmp_path) == []


def test_algorithm_colors_follow_the_palette_order_and_never_cycle():
    colors = plotting.algorithm_colors([f"A{i}" for i in range(10)])
    assert list(colors.values())[:8] == list(plotting.PALETTE)
    assert colors["A8"] == colors["A9"] == plotting.MUTED


def test_missing_matplotlib_gives_install_hint(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "matplotlib":
            raise ImportError("No module named 'matplotlib'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ImportError, match=r"cats-sim\[plot\]"):
        plotting._matplotlib()
