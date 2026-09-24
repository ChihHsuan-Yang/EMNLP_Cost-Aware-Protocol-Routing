#!/usr/bin/env python3
"""Score router predictions against the fixed-order oracle, with bootstrap CIs.

OFFLINE. Replays already-observed outcomes; no model calls.

Takes a predictions CSV (one row per held-out problem, with a predicted
protocol) and the matched outcome table, then reports realised solve rate,
oracle-label accuracy, macro-F1, escalation rates, and 2000-resample
problem-level percentile intervals.

The interval is BENCHMARK-PROBLEM sampling uncertainty. Each protocol was
executed once per problem, so it says nothing about run-to-run variability.
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

import _bootstrap_path  # noqa: F401
from protocol_routing import io
from protocol_routing.bootstrap import DEFAULT_RESAMPLES, bootstrap_metrics, format_ci
from protocol_routing.matched import load_matched_table
from protocol_routing.metrics import realized_outcomes, summarize_routing
from protocol_routing.protocols import CORRECTNESS_COLUMNS


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--matched_csv", required=True, help="Matched-label table for this setting.")
    parser.add_argument(
        "--predictions_csv",
        required=True,
        help="Predictions with columns <id_column> and predicted_label.",
    )
    parser.add_argument("--id_column", default="problem_uid")
    parser.add_argument("--output_csv", default=None, help="Optional metrics CSV to write.")
    parser.add_argument("--bootstrap_resamples", type=int, default=DEFAULT_RESAMPLES)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--no_bootstrap", action="store_true", help="Point estimates only (fast)."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    table = load_matched_table(args.matched_csv)
    predictions = io.read_csv(args.predictions_csv)
    if "predicted_label" not in predictions.columns:
        print("ERROR: predictions CSV needs a 'predicted_label' column", file=sys.stderr)
        return 2

    merged = table.frame.merge(
        predictions[[args.id_column, "predicted_label"]], on=args.id_column, how="inner"
    )
    if merged.empty:
        print(
            f"ERROR: no rows joined on {args.id_column!r}. "
            "Check that the predictions cover this setting.",
            file=sys.stderr,
        )
        return 2
    if len(merged) < len(predictions):
        print(
            f"WARNING: {len(predictions) - len(merged)} prediction row(s) did not join "
            "to the matched table and are excluded."
        )

    per_example = realized_outcomes(
        merged, merged["predicted_label"].tolist(), success_columns=CORRECTNESS_COLUMNS
    )
    point = summarize_routing(per_example)
    print(f"setting: {table.setting}")
    print(f"n evaluated: {len(per_example)}")

    if args.no_bootstrap:
        for key, value in point.items():
            print(f"{key}: {value:.6f}")
        rows = [{"setting": table.setting, **point}]
    else:
        intervals = bootstrap_metrics(
            per_example,
            summarize_routing,
            n_resamples=args.bootstrap_resamples,
            seed=args.seed,
        )
        row: dict[str, object] = {"setting": table.setting}
        for key, (value, low, high) in intervals.items():
            print(f"{key}: {value:.6f}  95% CI {format_ci(low, high)}")
            row[key] = value
            row[f"{key}_ci"] = format_ci(low, high)
        rows = [row]

    if args.output_csv:
        print(f"\nwrote {io.write_frame(args.output_csv, pd.DataFrame(rows))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
