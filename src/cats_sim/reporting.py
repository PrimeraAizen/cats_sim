"""Human-readable tables and machine-readable result files."""

from __future__ import annotations

import csv
import json
import platform
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from cats_sim import __version__
from cats_sim.config import SuiteConfig
from cats_sim.experiments import (
    AdaptiveSummary,
    ScalabilityResult,
    SecurityResult,
    SuiteResults,
)

RESULTS_JSON = "results.json"
SCALABILITY_CSV = "scalability.csv"
SECURITY_CSV = "security.csv"
ADAPTIVE_RUNS_CSV = "adaptive_runs.csv"
ALPHA_HISTORY_CSV = "alpha_history.csv"


# ------------------------------------------------------------------ tables


def _unique(values: Iterable[Any]) -> list[Any]:
    return list(dict.fromkeys(values))


def format_scalability_table(results: Sequence[ScalabilityResult]) -> str:
    """Table II: mean tip count per algorithm (columns) and λ (rows)."""
    algorithms = _unique(r.algorithm for r in results)
    lambdas = _unique(r.lam for r in results)
    by_key = {(r.lam, r.algorithm): r.mean_tips for r in results}
    lines = [
        "TABLE II: Mean Tip Count (Benign Conditions)",
        f"{'λ':>6}" + "".join(f"  {a:>8}" for a in algorithms),
    ]
    for lam in lambdas:
        cells = "".join(f"  {by_key[(lam, a)]:8.1f}" for a in algorithms)
        lines.append(f"{lam:6g}{cells}")
    return "\n".join(lines)


def format_security_table(results: Sequence[SecurityResult], lam: float, mu: float) -> str:
    """Table III: p₂ per algorithm (columns) and SPC length (rows)."""
    algorithms = _unique(r.algorithm for r in results)
    lengths = _unique(r.spc_length for r in results)
    by_key = {(r.spc_length, r.algorithm): r.mean_p2 for r in results}
    lines = [
        f"TABLE III: SPC Tip Selection Probability p₂ (λ={lam:g}, µ={mu:g})",
        f"{'m':>6}" + "".join(f"  {a:>8}" for a in algorithms),
    ]
    for m in lengths:
        cells = "".join(f"  {by_key[(m, a)]:8.4f}" for a in algorithms)
        lines.append(f"{'m=' + str(m):>6}{cells}")
    return "\n".join(lines)


def format_adaptive_summary(summary: AdaptiveSummary) -> str:
    """Experiment C summary in the format of the original simulator."""
    lines = [
        "CATS Adaptive Response Dynamics",
        f"  Detection rate: {summary.detection_rate * 100:.0f}% "
        f"({summary.detections}/{summary.num_runs} runs)",
    ]
    if summary.latency_mean is not None and summary.latency_std is not None:
        lines.append(
            f"  Detection latency: {summary.latency_mean:.1f} ± {summary.latency_std:.1f} "
            "transactions"
        )
    lines += [
        f"  α̃ peak: {summary.alpha_peak_mean:.5f} ± {summary.alpha_peak_std:.5f}",
        f"  Malicious quarantined: {summary.mal_quarantined_mean:.2f}/1.0",
        f"  Honest false positives: {summary.honest_quarantined_mean:.2f}",
    ]
    return "\n".join(lines)


def format_report(config: SuiteConfig, results: SuiteResults) -> str:
    """All enabled experiment tables, separated by blank lines."""
    parts: list[str] = []
    if results.scalability:
        parts.append(format_scalability_table(results.scalability))
    if results.security and config.security is not None:
        parts.append(
            format_security_table(results.security, config.security.lam, config.security.mu)
        )
    if results.adaptive is not None:
        parts.append(format_adaptive_summary(results.adaptive))
    return "\n\n".join(parts)


# ------------------------------------------------------------------- files


def run_metadata() -> dict[str, str]:
    """Provenance information stored with every result set."""
    return {
        "cats_sim_version": __version__,
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "platform": platform.platform(),
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def _adaptive_to_dict(summary: AdaptiveSummary) -> dict[str, Any]:
    rep = summary.representative
    return {
        "num_runs": summary.num_runs,
        "detections": summary.detections,
        "detection_rate": summary.detection_rate,
        "detection_latency_mean": summary.latency_mean,
        "detection_latency_std": summary.latency_std,
        "alpha_peak_mean": summary.alpha_peak_mean,
        "alpha_peak_std": summary.alpha_peak_std,
        "mal_quarantined_mean": summary.mal_quarantined_mean,
        "honest_quarantined_mean": summary.honest_quarantined_mean,
        "representative_run": {
            "detection_latency": rep.detection_latency,
            "quarantine_size": rep.quarantine_size,
            "mal_quarantined": rep.mal_quarantined,
            "honest_quarantined": rep.honest_quarantined,
            "attach_at_index": rep.attach_at_index,
            "alpha_range": [min(rep.alpha_history), max(rep.alpha_history)],
        },
    }


def results_to_dict(config: SuiteConfig, results: SuiteResults) -> dict[str, Any]:
    """Everything needed to interpret (and re-plot) a result set."""
    return {
        "metadata": run_metadata(),
        "config": config.to_dict(),
        "scalability": [vars(r) | {"per_run": list(r.per_run)} for r in results.scalability],
        "security": [vars(r) | {"per_run": list(r.per_run)} for r in results.security],
        "adaptive": _adaptive_to_dict(results.adaptive) if results.adaptive else None,
    }


def _write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def write_results(output_dir: str | Path, config: SuiteConfig, results: SuiteResults) -> list[Path]:
    """Write ``results.json`` plus one CSV per table; return the written paths."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    json_path = out / RESULTS_JSON
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(results_to_dict(config, results), fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    written = [json_path]

    if results.scalability:
        written.append(
            _write_csv(
                out / SCALABILITY_CSV,
                ["algorithm", "lam", "mean_tips", "std_tips", "num_runs"],
                (
                    (r.algorithm, r.lam, r.mean_tips, r.std_tips, len(r.per_run))
                    for r in results.scalability
                ),
            )
        )

    if results.security:
        written.append(
            _write_csv(
                out / SECURITY_CSV,
                ["algorithm", "spc_length", "mean_p2", "std_p2", "num_runs"],
                (
                    (r.algorithm, r.spc_length, r.mean_p2, r.std_p2, len(r.per_run))
                    for r in results.security
                ),
            )
        )

    if (summary := results.adaptive) is not None:
        written.append(
            _write_csv(
                out / ADAPTIVE_RUNS_CSV,
                [
                    "run",
                    "detected",
                    "detection_latency",
                    "alpha_peak",
                    "quarantine_size",
                    "mal_quarantined",
                    "honest_quarantined",
                ],
                (
                    (
                        i,
                        run.detection_latency is not None,
                        "" if run.detection_latency is None else run.detection_latency,
                        peak,
                        run.quarantine_size,
                        run.mal_quarantined,
                        run.honest_quarantined,
                    )
                    for i, (run, peak) in enumerate(
                        zip(summary.runs, summary.alpha_peaks, strict=True)
                    )
                ),
            )
        )
        rep = summary.representative
        written.append(
            _write_csv(
                out / ALPHA_HISTORY_CSV,
                ["step", "alpha", "S", "sigma1", "sigma2", "sigma3"],
                (
                    (i, alpha, s.S, s.sigma1, s.sigma2, s.sigma3)
                    for i, (alpha, s) in enumerate(
                        zip(rep.alpha_history, rep.signal_history, strict=True)
                    )
                ),
            )
        )

    return written
