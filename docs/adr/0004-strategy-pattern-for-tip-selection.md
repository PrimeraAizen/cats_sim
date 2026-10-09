# 4. Strategy pattern + registry for tip selection algorithms

Status: Accepted (2026-10-09)

## Context

The core research question is a comparison of interchangeable tip selection
algorithms (TSAs): URTS, MCMC(α), S-URTS, G-IOTA and CATS run in the same simulator
and the same experiments. In the original script:

- the simulator and experiments branched on concrete classes:
  `isinstance(tsa, GIOTA)` for three approvals, `isinstance(tsa, CATS)` for the
  pre-scan, quarantine filtering and `reset()`;
- `select_tips(**kwargs)` had a different signature in every class;
- CATS called the private method `SURTS._compute_stationary_distribution` through an
  embedded S-URTS instance.

Every new algorithm would therefore have meant editing the simulator and the
experiments: the Open/Closed principle was violated.

## Decision

Apply the **Strategy pattern**. The simulator (`simulation.generate_tangle`) is the
*context*; each TSA is a *concrete strategy* behind one abstract interface:

```python
class TipSelectionStrategy(ABC):
    name: str
    n_approvals: int = 2  # G-IOTA: 3

    @abstractmethod
    def select_tips(self, tangle, n_tips, ctx) -> list[TxId]: ...
    def prepare(self, tangle, ctx) -> None: ...  # hook, default no-op
    def excluded_tips(self) -> frozenset[TxId]: ...  # hook, default empty
```

- **Variation as data and hooks instead of type checks.** `n_approvals` replaces the
  G-IOTA check. `prepare()` replaces the CATS pre-scan check. `excluded_tips()`
  replaces reading `tsa.quarantine` from outside.
- **A parameter object** (`SelectionContext(lam, h, rng)`) gives all strategies the same
  signature instead of `**kwargs`.
- **Composition for shared maths.** The absorbing-chain computation lives in
  `markov.py` and is used by both S-URTS and CATS.
- **A registry** (`strategies.REGISTRY`, a simple factory) maps the `kind` used in
  configuration files to the class. Adding an algorithm means one new class plus one
  dictionary entry.
- **One instance per run.** Experiments receive a *factory* and build a fresh strategy
  for every run, replacing `reset()`. No state can leak between runs, and runs are
  independent (parallelisable).
- An **abstract base class** (not a `typing.Protocol`) because the hooks need shared
  default implementations, and instantiating an incomplete strategy should fail
  immediately.

The three *experiments* are plain functions selected by name. In Python a function
already is a strategy, and a class hierarchy for three fixed experiments would add
ceremony without benefit.

## Alternatives considered

- **Keep `isinstance` branches**: simplest today, but every new TSA touches the
  simulator; it is the coupling this refactor removes.
- **`typing.Protocol`**: structural typing is great for *consuming* third-party
  objects, but cannot provide default hooks.
- **Decorator-based auto-registration** (`@register("cats")`): less explicit. An
  import-order side effect decides what is registered, and the registry is harder to
  find by grepping.
- **Template Method** for the whole selection: the algorithms share almost no common
  skeleton (walk vs. uniform vs. Markov chain), so a fixed skeleton would be forced.

## Consequences

- The simulator and experiments contain no algorithm names. A contract test
  (`tests/test_strategies.py`) runs every registered strategy through the same checks
  and fails if a new strategy is registered without test parameters.
- New algorithms can be evaluated from a TOML file without code changes to the runner.
