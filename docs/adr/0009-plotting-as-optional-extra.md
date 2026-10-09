# 9. Plotting as an optional extra

Status: Accepted (2026-10-09)

## Context

The paper needs figures for the three experiments. Plotting libraries are large, and
most uses of the simulator, such as CI, servers and batch runs, do not need them.

## Decision

- matplotlib is an **optional dependency**: `pip install "cats-sim[plot]"` or
  `uv sync --extra plot`. Nothing else imports it, and `cats-sim plot` prints an
  install hint if it is missing.
- `cats-sim plot RESULTS_DIR` works **from the result files on disk**, so old result
  sets can be re-drawn without re-running hours of simulation.
- matplotlib's object-oriented `Figure` API is used instead of `pyplot`. It needs no
  global backend or state, so it runs headless in CI and inside other programs.
- Visual rules:
  - a fixed categorical palette validated for colour-vision deficiency (worst adjacent
    pair ΔE ≥ 9 under simulated CVD), assigned per algorithm in configuration order,
    so an algorithm keeps its colour across figures;
  - one y-axis per panel and hairline grids;
  - value labels on the p₂ columns so that a zero-height bar reads as "0", not
    "missing";
  - CSV files alongside as the table view of the same data.
- PNG (200 dpi), PDF and SVG output; fonts are embedded as TrueType (`pdf.fonttype 42`)
  so text stays editable and searchable in the paper.

## Alternatives considered

- **matplotlib as a hard dependency**: simpler install, but it pulls in a large set
  of transitive packages for every user.
- **Plotly / Bokeh**: interactive HTML is nice for exploration, but the target is
  static figures for a paper.
- **seaborn**: a convenience layer over matplotlib that is not needed for three
  charts; an extra dependency.

## Consequences

- The CI smoke job installs the extra and draws every figure, so plotting cannot rot.
- Tests for plotting are skipped automatically if matplotlib is absent.
