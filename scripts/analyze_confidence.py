#!/usr/bin/env python3
"""Failure-risk and calibration analysis of post-answer self-confidence.

OFFLINE given a released confidence table. Eliciting the confidence scores in
the first place REQUIRES model inference and is not part of this package.

Reports parse rate, failure AUROC, ECE, Brier, and mean confidence split by
whether the Baseline answer was correct; optionally scores the self-confidence
gate (keep Baseline if confidence >= 70, else Single).

Sign convention: the positive class is BASELINE FAILURE, and the ranking score
is (100 - confidence)/100. Reversing that flips AUROC around 0.5.
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

import _bootstrap_path  # noqa: F401
from protocol_routing import io
from protocol_routing.bootstrap import DEFAULT_RESAMPLES, format_ci, percentile_bootstrap
from protocol_routing.confidence import (
    SELF_CONFIDENCE_GATE_THRESHOLD,
    auroc,
    confidence_report,
    expected_calibration_error,
    failure_risk_score,
    parse_confidence_series,
    self_confidence_gate,
)
from protocol_routing.protocols import Protocol


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--confidence_csv",
        required=True,
        help="Per-problem confidence table (one row per problem).",
    )
    parser.add_argument("--confidence_column", default="probability", help="Raw confidence column.")
    parser.add_argument(
        "--baseline_correct_column",
        default="baseline_correct",
        help="Binary column: was the Baseline answer correct?",
    )
    parser.add_argument("--output_csv", default=None)
    parser.add_argument("--bootstrap_resamples", type=int, default=DEFAULT_RESAMPLES)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no_bootstrap", action="store_true")
    parser.add_argument(
        "--score_gate",
        action="store_true",
        help=(
            "Also score the self-confidence gate. Needs a 'single_correct' column "
            "to replay the escalation outcome."
        ),
    )
    parser.add_argument(
        "--gate_threshold", type=float, default=SELF_CONFIDENCE_GATE_THRESHOLD
    )
    return parser.parse_args(argv)


def _as_binary(series: pd.Series) -> np.ndarray:
    return series.map(lambda v: 1.0 if str(v).strip().lower() in {"1", "true"} else 0.0).to_numpy()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    frame = io.read_csv(args.confidence_csv)
    for column in (args.confidence_column, args.baseline_correct_column):
        if column not in frame.columns:
            print(f"ERROR: missing column {column!r}. Present: {list(frame.columns)}", file=sys.stderr)
            return 2

    confidence = parse_confidence_series(frame[args.confidence_column].tolist())
    correct = _as_binary(frame[args.baseline_correct_column])
    report = confidence_report(confidence.to_numpy(), correct)

    print(f"n_total:      {int(report['n_total'])}")
    print(f"n_parseable:  {int(report['n_parseable'])}")
    print(f"parse_rate:   {report['parse_rate']:.4f}")
    for key in ("failure_auroc", "ece", "brier", "mean_conf_correct", "mean_conf_wrong"):
        print(f"{key}: {report[key]:.4f}")

    row: dict[str, object] = {k: v for k, v in report.items()}

    if not args.no_bootstrap:
        usable = confidence.notna().to_numpy()
        paired = pd.DataFrame(
            {"conf": confidence.to_numpy()[usable], "correct": correct[usable]}
        )

        def _auroc(sample: pd.DataFrame) -> float:
            return auroc(1.0 - sample["correct"].to_numpy(), failure_risk_score(sample["conf"].to_numpy()))

        def _ece(sample: pd.DataFrame) -> float:
            return expected_calibration_error(sample["correct"].to_numpy(), sample["conf"].to_numpy() / 100.0)

        for name, fn in (("failure_auroc", _auroc), ("ece", _ece)):
            point, low, high = percentile_bootstrap(
                paired, fn, n_resamples=args.bootstrap_resamples, seed=args.seed
            )
            print(f"{name} 95% CI: {format_ci(low, high)}")
            row[f"{name}_ci"] = format_ci(low, high)

    if args.score_gate:
        if "single_correct" not in frame.columns:
            print(
                "ERROR: --score_gate needs a 'single_correct' column to replay the "
                "escalation outcome.",
                file=sys.stderr,
            )
            return 2
        single = _as_binary(frame["single_correct"])
        routes = [self_confidence_gate(c, threshold=args.gate_threshold) for c in confidence.tolist()]
        realised = np.asarray(
            [
                correct[i] if r == Protocol.BASELINE.value else single[i]
                for i, r in enumerate(routes)
            ]
        )
        kept = sum(1 for r in routes if r == Protocol.BASELINE.value)
        print()
        print(f"self-confidence gate (threshold {args.gate_threshold:g})")
        print(f"  kept Baseline:      {kept} / {len(routes)}")
        print(f"  escalated to Single:{len(routes) - kept} / {len(routes)}")
        print(f"  realised solve rate:{realised.mean():.4f}")
        row["gate_threshold"] = args.gate_threshold
        row["gate_kept_baseline"] = kept
        row["gate_solve_rate"] = float(realised.mean())

    if args.output_csv:
        print(f"\nwrote {io.write_frame(args.output_csv, pd.DataFrame([row]))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
