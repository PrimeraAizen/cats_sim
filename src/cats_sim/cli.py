"""Command-line interface: ``cats-sim run | plot | algorithms``."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from cats_sim import __version__
from cats_sim.config import EXPERIMENTS, ConfigError, load_config
from cats_sim.strategies import REGISTRY

logger = logging.getLogger("cats_sim")


def _cmd_run(args: argparse.Namespace) -> int:
    from cats_sim.experiments import run_suite
    from cats_sim.reporting import format_report, write_results

    config = load_config(args.config)
    if args.only:
        config = config.restricted_to(args.only)
    if args.seed is not None:
        config = config.with_seed(args.seed)
    if args.runs is not None:
        config = config.with_num_runs(args.runs)
    if not config.enabled_experiments:
        raise ConfigError("no experiment is enabled")

    logger.info(
        "Running %s (seed=%d) from %s",
        ", ".join(config.enabled_experiments),
        config.seed,
        args.config,
    )
    results = run_suite(config)
    print(format_report(config, results))

    paths = write_results(args.output_dir, config, results)
    print(f"\nResults written to {Path(args.output_dir).resolve()}:")
    for path in paths:
        print(f"  {path.name}")
    return 0


def _cmd_plot(args: argparse.Namespace) -> int:
    from cats_sim.plotting import plot_results

    paths = plot_results(args.results_dir, fmt=args.format)
    if not paths:
        print(f"No plottable results found in {args.results_dir}", file=sys.stderr)
        return 1
    for path in paths:
        print(path)
    return 0


def _cmd_algorithms(_: argparse.Namespace) -> int:
    for kind, cls in sorted(REGISTRY.items()):
        summary = (cls.__doc__ or "").strip().splitlines()[0]
        print(f"{kind:<6} {cls.__name__:<6} {summary}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cats-sim",
        description="Simulate tip selection algorithms on an IOTA-style Tangle.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug log output")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the experiments defined in a TOML config")
    run.add_argument("config", type=Path, help="path to a TOML configuration (see configs/)")
    run.add_argument(
        "--only",
        nargs="+",
        choices=EXPERIMENTS,
        metavar="EXPERIMENT",
        help=f"run only these experiments ({', '.join(EXPERIMENTS)})",
    )
    run.add_argument("--seed", type=int, help="override the configured root seed")
    run.add_argument("--runs", type=int, help="override num_runs of every experiment")
    run.add_argument(
        "-o", "--output-dir", type=Path, default=Path("results"), help="default: ./results"
    )
    run.set_defaults(func=_cmd_run)

    plot = sub.add_parser("plot", help="draw figures from a results directory")
    plot.add_argument("results_dir", type=Path, help="directory written by `cats-sim run`")
    plot.add_argument("--format", choices=("png", "pdf", "svg"), default="png")
    plot.set_defaults(func=_cmd_plot)

    algos = sub.add_parser("algorithms", help="list the available tip selection algorithms")
    algos.set_defaults(func=_cmd_algorithms)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Progress messages of this package only (default INFO, -v DEBUG); third-party
    # libraries keep their default WARNING level.
    logging.basicConfig(format="%(message)s", stream=sys.stderr)
    logger.setLevel(logging.DEBUG if args.verbose else logging.INFO)

    try:
        return int(args.func(args))
    except ConfigError as exc:
        print(f"cats-sim: configuration error: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(f"cats-sim: {exc}", file=sys.stderr)
        return 3
