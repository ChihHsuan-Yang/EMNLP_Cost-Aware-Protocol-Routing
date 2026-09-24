#!/usr/bin/env python3
"""PER vs Broadcast outcomes on the problems where cheap protocols failed.

OFFLINE. No model calls.

Conditions on Baseline AND Single both failing, then compares PER and Broadcast
on exactly those problems. Because every protocol ran on every problem, the
comparison is PAIRED: the bootstrap resamples problem indices once and applies
them to both arms.

Restricting to the both-failed subset is the point, not a convenience. On the
full set the two expensive protocols mostly agree because the easy problems are
already solved; the disagreement lives where escalation is actually being paid
for. The subset is defined by a condition on the CHEAP protocols, not on PER or
Broadcast, so it does not select on the outcome being compared.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import _bootstrap_path  # noqa: F401
from protocol_routing import io
from protocol_routing.bootstrap import DEFAULT_RESAMPLES, format_ci, paired_difference
from protocol_routing.matched import load_matched_dir, per_broadcast_interaction_table


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--matched_dir", required=True)
    parser.add_argument("--output_csv", default=None)
    parser.add_argument("--bootstrap_resamples", type=int, default=DEFAULT_RESAMPLES)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no_bootstrap", action="store_true")
    parser.add_argument("--allow_non_paper_settings", action="store_true")
    return parser.parse_args(argv)


def _bool_col(frame: pd.DataFrame, column: str) -> np.ndarray:
    return frame[column].map(lambda v: str(v).strip().lower() in {"1", "true"}).to_numpy()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tables = load_matched_dir(args.matched_dir, strict=not args.allow_non_paper_settings)
    summary = per_broadcast_interaction_table(tables)

    if not args.no_bootstrap:
        cis = []
        for table in tables:
            frame = table.frame
            subset = frame[(~_bool_col(frame, "baseline_correct")) & (~_bool_col(frame, "single_correct"))]
            if subset.empty:
                cis.append("")
                continue
            per = _bool_col(subset, "per_correct").astype(float)
            bro = _bool_col(subset, "broadcast_correct").astype(float)
            _, low, high = paired_difference(
                bro, per, n_resamples=args.bootstrap_resamples, seed=args.seed
            )
            cis.append(format_ci(100 * low, 100 * high, decimals=1))
        # Reindex to the order per_broadcast_interaction_table used.
        order = {(t.solver, t.setting_label): c for t, c in zip(tables, cis)}
        summary["broadcast_minus_per_ci_points"] = [
            order.get((r["solver"], r["setting"]), "") for _, r in summary.iterrows()
        ]

    print(summary.to_string(index=False))
    print()
    print("Subset = problems where BOTH Baseline and Single failed.")
    print("Positive broadcast_minus_per_points favours Broadcast.")
    if args.output_csv:
        print(f"\nwrote {io.write_frame(args.output_csv, summary)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
