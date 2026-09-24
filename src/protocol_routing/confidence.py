"""Post-answer self-confidence: parsing, the gate policy, calibration metrics.

Confidence is elicited AFTER the Baseline answer is produced and BEFORE any
collaboration.  The model reports an integer 0-100.  Two policies use it:

Self-confidence gate (main paper)
    A single binary rule: keep Baseline if confidence >= 70, else escalate to
    Single.  That is the whole policy.  It never routes to PER or Broadcast.

Two-threshold cascade (appendix ablation)
    A separate, three-way rule: Baseline when confidence is high (>= 70),
    Single in the middle band, Tier-majority when confidence is very low
    (< 10).  This is an ablation, not the headline policy; do not conflate the
    two.

All parsing here is deterministic and offline.  Eliciting the confidence score
in the first place requires model inference and is NOT part of this package.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from protocol_routing.protocols import Protocol

#: The main-paper gate threshold.
SELF_CONFIDENCE_GATE_THRESHOLD = 70.0

#: Appendix two-threshold cascade.
CASCADE_TAU_HIGH = 70.0
CASCADE_TAU_LOW = 10.0

_KEYED = re.compile(r"""["']?(?P<key>[A-Za-z_][A-Za-z0-9_ ]*)["']?\s*:\s*(?P<value>\d{1,3})""")
_BARE = re.compile(r"^\s*(\d{1,3})\s*$")
_FIRST_INT = re.compile(r"\b([0-9]{1,3})\b")


def parse_confidence(text: object, *, key: str = "PROBABILITY") -> float | None:
    """Parse a 0-100 integer confidence out of a raw model response.

    Deterministic, in this order:

    1. JSON object with ``key`` -> that value.
    2. ``KEY: <int>`` anywhere in the text (case-insensitive).
    3. The whole string is a bare integer.
    4. The first standalone integer in 0-100.

    Returns ``None`` when nothing parseable is found.  ``None`` means
    *unparseable*, which is a distinct state from a low score: an unparseable
    response has no confidence, and counting it as 0 would fabricate a
    confident-wrong prediction.  Values are clipped to [0, 100].
    """
    if text is None:
        return None
    if isinstance(text, (int, np.integer)) and not isinstance(text, bool):
        return float(min(100, max(0, int(text))))
    if isinstance(text, float) and text == text:  # not NaN
        return float(min(100.0, max(0.0, float(text))))
    raw = str(text).strip()
    if not raw or raw.lower() in {"nan", "none", "null"}:
        return None

    try:
        payload = json.loads(raw)
    except Exception:
        payload = None
    if isinstance(payload, dict):
        for candidate_key in (key, key.lower(), key.upper()):
            if candidate_key in payload:
                try:
                    return float(min(100, max(0, int(payload[candidate_key]))))
                except Exception:
                    break

    keyed = re.search(
        rf"""["']?{re.escape(key)}["']?\s*:\s*(\d{{1,3}})""", raw, re.IGNORECASE
    )
    if keyed:
        return float(min(100, max(0, int(keyed.group(1)))))

    bare = _BARE.match(raw)
    if bare:
        return float(min(100, max(0, int(bare.group(1)))))

    for match in _FIRST_INT.finditer(raw):
        value = int(match.group(1))
        if 0 <= value <= 100:
            return float(value)
    return None


def parse_confidence_series(values: Sequence[object], *, key: str = "PROBABILITY") -> pd.Series:
    """Vectorised :func:`parse_confidence`; unparseable rows become ``NaN``."""
    return pd.Series([parse_confidence(v, key=key) for v in values], dtype=float)


def self_confidence_gate(
    confidence: float | None,
    *,
    threshold: float = SELF_CONFIDENCE_GATE_THRESHOLD,
) -> str:
    """The main-paper self-confidence gate.

    ``confidence >= threshold`` keeps Baseline; anything else (including an
    unparseable score) escalates to Single.  Escalating on unparseable is the
    conservative direction: it spends more, never less.
    """
    if confidence is None or (isinstance(confidence, float) and confidence != confidence):
        return Protocol.SINGLE.value
    return Protocol.BASELINE.value if float(confidence) >= threshold else Protocol.SINGLE.value


def two_threshold_cascade(
    confidence: float | None,
    tier_majority_label: str,
    *,
    tau_high: float = CASCADE_TAU_HIGH,
    tau_low: float = CASCADE_TAU_LOW,
) -> str:
    """Appendix ablation: Baseline high / Single mid / Tier-majority very low.

    An unparseable confidence falls back to the tier-majority label, matching
    the ablation as run.
    """
    if confidence is None or (isinstance(confidence, float) and confidence != confidence):
        return tier_majority_label
    value = float(confidence)
    if value >= tau_high:
        return Protocol.BASELINE.value
    if value >= tau_low:
        return Protocol.SINGLE.value
    return tier_majority_label


# ---------------------------------------------------------------------------
# Failure-risk metrics
# ---------------------------------------------------------------------------
#
# Convention: the POSITIVE class is *Baseline failure*.  The score used to rank
# problems is therefore (100 - confidence) / 100, i.e. self-reported failure
# risk.  Getting this direction wrong flips AUROC around 0.5 and is the easiest
# mistake to make here, so the direction is fixed in one place.


def failure_risk_score(confidence: Sequence[float]) -> np.ndarray:
    """Convert 0-100 confidence into a 0-1 failure-risk score."""
    values = np.asarray(confidence, dtype=float)
    return (100.0 - values) / 100.0


def auroc(labels: Sequence[int], scores: Sequence[float]) -> float:
    """AUROC with the positive class = 1.  Returns NaN if a class is absent."""
    from sklearn.metrics import roc_auc_score

    y = np.asarray(labels, dtype=float)
    s = np.asarray(scores, dtype=float)
    if len(np.unique(y)) < 2:
        return float("nan")
    return float(roc_auc_score(y, s))


def auprc(labels: Sequence[int], scores: Sequence[float]) -> float:
    """Average precision with the positive class = 1."""
    from sklearn.metrics import average_precision_score

    y = np.asarray(labels, dtype=float)
    s = np.asarray(scores, dtype=float)
    if len(np.unique(y)) < 2:
        return float("nan")
    return float(average_precision_score(y, s))


def brier(labels: Sequence[int], probabilities: Sequence[float]) -> float:
    """Brier score between 0-1 probabilities and 0/1 labels."""
    y = np.asarray(labels, dtype=float)
    p = np.asarray(probabilities, dtype=float)
    if y.size == 0:
        return float("nan")
    return float(np.mean((p - y) ** 2))


@dataclass(frozen=True)
class ReliabilityBin:
    lower: float
    upper: float
    n: int
    mean_probability: float
    empirical_rate: float

    @property
    def abs_gap(self) -> float:
        return abs(self.mean_probability - self.empirical_rate)


def reliability_bins(
    labels: Sequence[int],
    probabilities: Sequence[float],
    *,
    n_bins: int = 10,
) -> list[ReliabilityBin]:
    """Equal-width reliability bins over [0, 1].  Empty bins are dropped."""
    y = np.asarray(labels, dtype=float)
    p = np.asarray(probabilities, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    out: list[ReliabilityBin] = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p > lo) & (p <= hi) if i > 0 else (p >= lo) & (p <= hi)
        if not mask.any():
            continue
        out.append(
            ReliabilityBin(
                lower=float(lo),
                upper=float(hi),
                n=int(mask.sum()),
                mean_probability=float(p[mask].mean()),
                empirical_rate=float(y[mask].mean()),
            )
        )
    return out


def expected_calibration_error(
    labels: Sequence[int],
    probabilities: Sequence[float],
    *,
    n_bins: int = 10,
) -> float:
    """Sample-weighted ECE over equal-width bins, on the 0-1 scale."""
    bins = reliability_bins(labels, probabilities, n_bins=n_bins)
    if not bins:
        return float("nan")
    weights = np.asarray([b.n for b in bins], dtype=float)
    gaps = np.asarray([b.abs_gap for b in bins], dtype=float)
    return float(np.sum(weights * gaps) / weights.sum())


def confidence_report(
    confidence: Sequence[float],
    baseline_correct: Sequence[int],
    *,
    n_bins: int = 10,
) -> Mapping[str, float]:
    """Failure-risk AUROC + calibration summary over parseable rows only.

    ``parse_rate`` reports what fraction of rows were usable, so a small
    denominator can never be mistaken for a full one.
    """
    conf = np.asarray(confidence, dtype=float)
    correct = np.asarray(baseline_correct, dtype=float)
    usable = np.isfinite(conf)
    n_total = int(conf.size)
    if usable.sum() == 0:
        return {"n_total": float(n_total), "n_parseable": 0.0, "parse_rate": 0.0}
    c = conf[usable]
    y_correct = correct[usable]
    y_failure = 1.0 - y_correct
    p_correct = c / 100.0
    return {
        "n_total": float(n_total),
        "n_parseable": float(usable.sum()),
        "parse_rate": float(usable.sum() / n_total),
        "failure_auroc": auroc(y_failure, failure_risk_score(c)),
        "ece": expected_calibration_error(y_correct, p_correct, n_bins=n_bins),
        "brier": brier(y_correct, p_correct),
        "mean_conf_correct": float(np.mean(p_correct[y_correct == 1.0])) if (y_correct == 1.0).any() else float("nan"),
        "mean_conf_wrong": float(np.mean(p_correct[y_correct == 0.0])) if (y_correct == 0.0).any() else float("nan"),
    }
