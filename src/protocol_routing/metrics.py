"""Routing and classification metrics shared by every evaluation path."""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from protocol_routing.oracle import escalation_direction
from protocol_routing.protocols import PROTOCOL_ORDER, Protocol, canonical_protocol


def per_class_prf(golds: Sequence[str], preds: Sequence[str], label: str) -> tuple[float, float, float]:
    """Precision, recall, F1 for one label (0.0 when the denominator is 0)."""
    g = np.asarray([canonical_protocol(x).value for x in golds])
    p = np.asarray([canonical_protocol(x).value for x in preds])
    target = canonical_protocol(label).value
    tp = int(np.sum((g == target) & (p == target)))
    fp = int(np.sum((g != target) & (p == target)))
    fn = int(np.sum((g == target) & (p != target)))
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def macro_f1(golds: Sequence[str], preds: Sequence[str], *, labels: Sequence[str] | None = None) -> float:
    """Macro-F1 over the five oracle labels.

    The average is over ALL five labels by default, including labels that never
    occur in ``golds``.  That is the paper convention: a router that never
    predicts ``broadcast`` should be penalised for it, and letting the label set
    shrink to whatever happens to appear would hide that.
    """
    names = [canonical_protocol(x).value for x in (labels if labels is not None else [p.value for p in PROTOCOL_ORDER])]
    return float(np.mean([per_class_prf(golds, preds, name)[2] for name in names]))


def accuracy(golds: Sequence[str], preds: Sequence[str]) -> float:
    g = [canonical_protocol(x).value for x in golds]
    p = [canonical_protocol(x).value for x in preds]
    if not g:
        return 0.0
    return float(np.mean([a == b for a, b in zip(g, p)]))


def escalation_rates(golds: Sequence[str], preds: Sequence[str]) -> dict[str, float]:
    """Over-/under-escalation and match rates."""
    if not len(golds):
        return {"over_escalation_rate": 0.0, "under_escalation_rate": 0.0, "match_rate": 0.0}
    directions = [escalation_direction(p, g) for g, p in zip(golds, preds)]
    n = len(directions)
    return {
        "over_escalation_rate": directions.count("over") / n,
        "under_escalation_rate": directions.count("under") / n,
        "match_rate": directions.count("match") / n,
    }


def realized_outcomes(
    frame: pd.DataFrame,
    predictions: Sequence[str],
    *,
    success_columns: Mapping[str, str],
    cost_columns: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Per-problem realised outcome of following ``predictions``.

    For each problem, the routed protocol's ALREADY-OBSERVED outcome is looked
    up.  Nothing is executed and nothing is modelled: this is a replay over the
    matched table.  Routing to ``none`` realises no success and no cost.

    Parameters
    ----------
    success_columns
        protocol identifier -> boolean column in ``frame``.
    cost_columns
        Optional protocol identifier -> numeric token-cost column.  When
        omitted, cost columns are all reported as ``NaN`` rather than 0, so a
        missing cost table can never be mistaken for a free router.
    """
    golds = frame["oracle_label"].tolist() if "oracle_label" in frame.columns else None
    rows = []
    records = frame.to_dict("records")
    if len(records) != len(predictions):
        raise ValueError(f"{len(predictions)} predictions for {len(records)} rows")
    for i, (record, raw_pred) in enumerate(zip(records, predictions)):
        pred = canonical_protocol(raw_pred).value
        if pred == Protocol.NONE.value:
            success, cost = 0.0, 0.0
        else:
            column = success_columns[pred]
            success = 1.0 if str(record[column]).strip().lower() in {"1", "true"} else 0.0
            if cost_columns and pred in cost_columns and cost_columns[pred] in frame.columns:
                cost = float(record[cost_columns[pred]])
            else:
                cost = float("nan")
        gold = canonical_protocol(golds[i]).value if golds is not None else None
        if gold is None:
            oracle_cost = float("nan")
        elif gold == Protocol.NONE.value:
            oracle_cost = 0.0
        elif cost_columns and gold in cost_columns and cost_columns[gold] in frame.columns:
            oracle_cost = float(record[cost_columns[gold]])
        else:
            oracle_cost = float("nan")
        rows.append(
            {
                "problem_uid": record.get("problem_uid", record.get("problem_id", i)),
                "predicted_label": pred,
                "oracle_label": gold,
                "success": success,
                "tokens": cost,
                "excess_tokens_vs_oracle": max(cost - oracle_cost, 0.0) if cost == cost and oracle_cost == oracle_cost else float("nan"),
                "mode_correct": float(gold == pred) if gold is not None else float("nan"),
                "solvable": float(gold != Protocol.NONE.value) if gold is not None else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def summarize_routing(per_example: pd.DataFrame) -> dict[str, float]:
    """Headline routing metrics from a :func:`realized_outcomes` frame."""
    n = len(per_example)
    if n == 0:
        return {}
    solvable = float(per_example["solvable"].sum())
    missed = float(((per_example["solvable"] == 1.0) & (per_example["success"] == 0.0)).sum())
    out = {
        "n_examples": float(n),
        "solve_rate": float(per_example["success"].mean()),
        "mode_accuracy": float(per_example["mode_correct"].mean()),
        "macro_f1": macro_f1(per_example["oracle_label"].tolist(), per_example["predicted_label"].tolist()),
        "missed_success_rate": missed / solvable if solvable else 0.0,
    }
    out.update(
        escalation_rates(per_example["oracle_label"].tolist(), per_example["predicted_label"].tolist())
    )
    if per_example["tokens"].notna().all():
        out["avg_tokens"] = float(per_example["tokens"].mean())
        out["avg_excess_tokens_vs_oracle"] = float(per_example["excess_tokens_vs_oracle"].mean())
    return out
