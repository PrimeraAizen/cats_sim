"""Figures drawn from a results directory written by ``cats-sim run``.

Requires the optional ``plot`` extra (matplotlib). Plotting works from the
files on disk, so old result sets can be re-plotted without re-running the
simulation. The object-oriented :class:`matplotlib.figure.Figure` API is used
instead of ``pyplot`` so no global backend or state is touched.

Visual conventions: a fixed, colour-vision-deficiency-validated categorical
palette assigned per algorithm in configuration order (an algorithm keeps its
colour across figures), thin marks, hairline grid, one y-axis per panel. The
CSV files next to the figures are the table view of the same data.
"""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cats_sim.reporting import ALPHA_HISTORY_CSV, RESULTS_JSON

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

logger = logging.getLogger(__name__)

# Categorical slots in fixed order (validated: adjacent CVD ΔE ≥ 9.1, normal-vision ΔE ≥ 19.6).
PALETTE = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
SURFACE = "#ffffff"

LINE_WIDTH = 1.75
MARKER_SIZE = 6.5

_RC = {
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "axes.edgecolor": BASELINE,
    "axes.linewidth": 0.8,
    "axes.labelcolor": INK_SECONDARY,
    "axes.titlecolor": INK,
    "axes.titlesize": 11,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
    "axes.labelsize": 9.5,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "axes.axisbelow": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "grid.linestyle": "-",
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelcolor": INK_SECONDARY,
    "ytick.labelcolor": INK_SECONDARY,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.frameon": False,
    "legend.fontsize": 9,
    "legend.labelcolor": INK_SECONDARY,
    "font.family": "sans-serif",
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
}


def _matplotlib() -> Any:
    try:
        import matplotlib
    except ImportError as exc:
        raise ImportError(
            "plotting requires matplotlib; install it with "
            "`uv sync --extra plot` or `pip install 'cats-sim[plot]'`"
        ) from exc
    return matplotlib


@contextmanager
def _style() -> Iterator[None]:
    with _matplotlib().rc_context(_RC):
        yield


def algorithm_colors(labels: Sequence[str]) -> dict[str, str]:
    """Assign palette slots to algorithm labels in order (colour follows the entity)."""
    if len(labels) > len(PALETTE):
        logger.warning("more than %d algorithms: extra ones are drawn in grey", len(PALETTE))
    return {label: PALETTE[i] if i < len(PALETTE) else MUTED for i, label in enumerate(labels)}


def _new_figure(width: float, height: float, rows: int = 1) -> tuple[Figure, list[Axes]]:
    from matplotlib.figure import Figure

    fig = Figure(figsize=(width, height), layout="constrained")
    axes = fig.subplots(rows, 1, sharex=True, squeeze=False)[:, 0]
    return fig, list(axes)


def _legend(fig: Figure, ax: Axes) -> None:
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside right center", handlelength=1.6)


# ----------------------------------------------------------------- figures


def figure_scalability(records: Sequence[Mapping[str, Any]], colors: Mapping[str, str]) -> Figure:
    """Mean tip count against λ, one line per algorithm, ±1 std whiskers."""
    with _style():
        fig, (ax,) = _new_figure(6.4, 3.6)
        for label, color in colors.items():
            rows = sorted((r for r in records if r["algorithm"] == label), key=lambda r: r["lam"])
            if not rows:
                continue
            lam = [r["lam"] for r in rows]
            mean = [r["mean_tips"] for r in rows]
            std = [r["std_tips"] for r in rows]
            ax.errorbar(lam, mean, yerr=std, fmt="none", ecolor=color, elinewidth=1, alpha=0.6)
            ax.plot(
                lam,
                mean,
                color=color,
                linewidth=LINE_WIDTH,
                marker="o",
                markersize=MARKER_SIZE,
                markeredgecolor=SURFACE,
                markeredgewidth=1.5,
                solid_capstyle="round",
                label=label,
            )
        ax.set_title("Mean tip count under benign conditions")
        ax.set_xlabel("Arrival rate λ (transactions per time unit)")
        ax.set_ylabel("Mean number of tips")
        ax.set_xticks(sorted({r["lam"] for r in records}))
        ax.set_ylim(bottom=0)
        _legend(fig, ax)
    return fig


def figure_security(
    records: Sequence[Mapping[str, Any]], colors: Mapping[str, str], lam: float, mu: float
) -> Figure:
    """p₂ per parasite-chain length, grouped columns per algorithm, ±1 std whiskers."""
    with _style():
        fig, (ax,) = _new_figure(6.4, 3.6)
        lengths = sorted({r["spc_length"] for r in records})
        present = [label for label in colors if any(r["algorithm"] == label for r in records)]
        slot = min(0.8 / max(len(present), 1), 0.16)  # keep columns thin when few algorithms
        top = max((r["mean_p2"] + r["std_p2"] for r in records), default=0.0) or 1.0
        for i, label in enumerate(present):
            by_m = {r["spc_length"]: r for r in records if r["algorithm"] == label}
            offset = (i - (len(present) - 1) / 2) * slot
            xs = [j + offset for j, m in enumerate(lengths) if m in by_m]
            values = [by_m[m]["mean_p2"] for m in lengths if m in by_m]
            errors = [by_m[m]["std_p2"] for m in lengths if m in by_m]
            # the gap between adjacent columns is left as surface (no outline strokes)
            ax.bar(xs, values, width=slot * 0.85, color=colors[label], label=label, linewidth=0)
            ax.errorbar(xs, values, yerr=errors, fmt="none", ecolor=MUTED, elinewidth=0.9)
            # value at the tip, so a zero-height column still reads as "0" rather than missing
            for x, v, e in zip(xs, values, errors, strict=True):
                ax.annotate(
                    f"{v:.3f}",
                    xy=(x, v + e + 0.025 * top),
                    ha="center",
                    va="bottom",
                    fontsize=7,
                    color=INK_SECONDARY,
                )
        ax.set_xticks(range(len(lengths)), [f"m = {m}" for m in lengths])
        ax.tick_params(axis="x", length=0)
        ax.set_title(f"Probability p₂ of selecting a parasite-chain tip (λ = {lam:g}, µ = {mu:g})")
        ax.set_xlabel("Parasite chain length")
        ax.set_ylabel("p₂")
        ax.set_ylim(bottom=0)
        _legend(fig, ax)
    return fig


def figure_alpha(
    rows: Sequence[Mapping[str, float]], attach_at_index: int | None, color: str = PALETTE[0]
) -> Figure:
    """CATS α̃(t) and composite signal S(t) for the representative adaptive run."""
    with _style():
        fig, (ax_alpha, ax_signal) = _new_figure(6.4, 4.4, rows=2)
        steps = [r["step"] for r in rows]
        panels = [
            (ax_alpha, "alpha", "α̃(t)", "CATS adaptive response to a parasite chain"),
            (ax_signal, "S", "S(t)", "Composite threat signal"),
        ]
        for ax, key, ylabel, title in panels:
            ax.plot(steps, [r[key] for r in rows], color=color, linewidth=LINE_WIDTH)
            ax.set_ylabel(ylabel)
            ax.set_title(title)
            if attach_at_index is not None:
                ax.axvline(attach_at_index, color=INK_SECONDARY, linewidth=0.9)
        if attach_at_index is not None:
            ax_alpha.annotate(
                "SPC attached",
                xy=(attach_at_index, 1),
                xycoords=("data", "axes fraction"),
                xytext=(4, -2),
                textcoords="offset points",
                va="top",
                fontsize=8.5,
                color=INK_SECONDARY,
            )
        ax_signal.set_xlabel("Tip selection (CATS invocation)")
        ax_signal.set_ylim(0, 1)
    return fig


# --------------------------------------------------------------- entry point


def _read_alpha_history(path: Path) -> list[dict[str, float]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [{k: float(v) for k, v in row.items()} for row in csv.DictReader(fh)]


def plot_results(results_dir: str | Path, fmt: str = "png") -> list[Path]:
    """Draw every figure the results in ``results_dir`` allow; return the written paths."""
    directory = Path(results_dir)
    results_path = directory / RESULTS_JSON
    if not results_path.is_file():
        return []
    _matplotlib()  # fail early with a helpful message if the extra is missing

    data = json.loads(results_path.read_text(encoding="utf-8"))
    colors = algorithm_colors(list(data["config"]["algorithms"]))
    save_kwargs: dict[str, Any] = {"dpi": 200} if fmt == "png" else {}

    figures: list[tuple[str, Figure]] = []
    if data.get("scalability"):
        figures.append(("fig_scalability", figure_scalability(data["scalability"], colors)))
    if data.get("security"):
        sec = data["config"]["security"]
        figures.append(
            ("fig_security", figure_security(data["security"], colors, sec["lam"], sec["mu"]))
        )
    alpha_path = directory / ALPHA_HISTORY_CSV
    if data.get("adaptive") and alpha_path.is_file():
        attach = data["adaptive"]["representative_run"]["attach_at_index"]
        label = data["config"]["adaptive"]["algorithm"]
        figures.append(
            (
                "fig_alpha",
                figure_alpha(
                    _read_alpha_history(alpha_path), attach, colors.get(label, PALETTE[0])
                ),
            )
        )

    written: list[Path] = []
    for name, fig in figures:
        path = directory / f"{name}.{fmt}"
        fig.savefig(path, **save_kwargs)
        written.append(path)
    return written
