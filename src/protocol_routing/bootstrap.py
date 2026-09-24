"""Problem-level percentile bootstrap.

What the interval means
-----------------------
The resampling unit is the PROBLEM.  A bootstrap replicate draws ``n`` problems
with replacement from the evaluated problem set and recomputes the statistic on
that replicate.  The resulting interval therefore quantifies **benchmark-problem
sampling uncertainty**: how much the number would move if we had drawn a
different sample of problems from the same pool.

It is NOT repeated-run uncertainty.  Each protocol was executed once per
problem; re-running the same protocol on the same problem at nonzero
temperature would move the outcome, and this interval says nothing about that.
Do not describe these CIs as run-to-run variability.

Defaults follow the paper: 2000 resamples, 95% percentile interval.
"""

from __future__ import annotations

from typing import Callable, Mapping, Sequence

import numpy as np
import pandas as pd

DEFAULT_RESAMPLES = 2000
DEFAULT_ALPHA = 0.05


def percentile_bootstrap(
    values: pd.DataFrame | pd.Series | np.ndarray,
    statistic: Callable[[pd.DataFrame | pd.Series | np.ndarray], float],
    *,
    n_resamples: int = DEFAULT_RESAMPLES,
    seed: int = 42,
    alpha: float = DEFAULT_ALPHA,
) -> tuple[float, float, float]:
    """Return ``(point_estimate, ci_low, ci_high)`` for one statistic.

    ``statistic`` is applied to the full sample for the point estimate and to
    each resample for the interval.  The RNG is seeded, so the same
    ``(values, seed, n_resamples)`` always yields the same interval.
    """
    n = len(values)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    point = float(statistic(values))
    draws = np.empty(n_resamples, dtype=float)
    index = np.arange(n)
    for i in range(n_resamples):
        take = rng.choice(index, size=n, replace=True)
        if isinstance(values, pd.DataFrame):
            sample: object = values.iloc[take]
        elif isinstance(values, pd.Series):
            sample = values.iloc[take]
        else:
            sample = np.asarray(values)[take]
        draws[i] = float(statistic(sample))
    lo, hi = np.percentile(draws, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return point, float(lo), float(hi)


def bootstrap_metrics(
    per_example: pd.DataFrame,
    summarize: Callable[[pd.DataFrame], Mapping[str, float]],
    *,
    n_resamples: int = DEFAULT_RESAMPLES,
    seed: int = 42,
    alpha: float = DEFAULT_ALPHA,
) -> dict[str, tuple[float, float, float]]:
    """Bootstrap a whole metric dict at once, resampling rows jointly.

    Resampling once per replicate and recomputing every metric on that same
    replicate preserves the correlation between metrics, which per-metric
    bootstraps would destroy.
    """
    n = len(per_example)
    if n == 0:
        return {}
    point = dict(summarize(per_example))
    keys = list(point)
    draws = {key: np.empty(n_resamples, dtype=float) for key in keys}
    rng = np.random.default_rng(seed)
    index = np.arange(n)
    for i in range(n_resamples):
        sample = per_example.iloc[rng.choice(index, size=n, replace=True)].reset_index(drop=True)
        stats = summarize(sample)
        for key in keys:
            draws[key][i] = float(stats.get(key, np.nan))
    out: dict[str, tuple[float, float, float]] = {}
    for key in keys:
        column = draws[key]
        finite = column[np.isfinite(column)]
        if finite.size == 0:
            out[key] = (float(point[key]), float("nan"), float("nan"))
            continue
        lo, hi = np.percentile(finite, [100 * alpha / 2, 100 * (1 - alpha / 2)])
        out[key] = (float(point[key]), float(lo), float(hi))
    return out


def paired_difference(
    values_a: Sequence[float],
    values_b: Sequence[float],
    *,
    n_resamples: int = DEFAULT_RESAMPLES,
    seed: int = 42,
    alpha: float = DEFAULT_ALPHA,
) -> tuple[float, float, float]:
    """Bootstrap the paired mean difference ``mean(a) - mean(b)``.

    Both arms must be evaluated on the SAME problems in the SAME order; a
    replicate resamples problem indices once and applies them to both arms, so
    the pairing is preserved.  Unpaired resampling here would inflate the
    interval and is the usual way a paired comparison gets misreported.
    """
    a = np.asarray(values_a, dtype=float)
    b = np.asarray(values_b, dtype=float)
    if a.shape != b.shape:
        raise ValueError(f"Paired arms must align: {a.shape} vs {b.shape}")
    n = a.size
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    point = float(a.mean() - b.mean())
    index = np.arange(n)
    draws = np.empty(n_resamples, dtype=float)
    for i in range(n_resamples):
        take = rng.choice(index, size=n, replace=True)
        draws[i] = float(a[take].mean() - b[take].mean())
    lo, hi = np.percentile(draws, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return point, float(lo), float(hi)


def format_ci(low: float, high: float, *, decimals: int = 4) -> str:
    """Render an interval the way the camera-ready CSVs do: ``[lo,hi]``."""
    return f"[{low:.{decimals}f},{high:.{decimals}f}]"
