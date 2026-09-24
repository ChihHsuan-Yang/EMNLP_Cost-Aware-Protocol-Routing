#!/usr/bin/env python3
"""Train a routing model on already-observed protocol outcomes.

OFFLINE. Trains a small sklearn model on a laptop in seconds. No model
endpoint, no GPU, no HPC.

The router predicts the fixed-order oracle label from the problem statement
and its metadata. Outcome columns are structurally barred from the feature
matrix by ``protocol_routing.features``, which raises ``LeakageError`` on
contact with any of them.

Splits follow the paper: hyperparameters are chosen on DEV only, the model is
refit on train+dev, and the untouched test split is scored once.
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

import _bootstrap_path  # noqa: F401
from protocol_routing import io
from protocol_routing.matched import load_matched_table
from protocol_routing.metrics import accuracy, escalation_rates, macro_f1
from protocol_routing.router import (
    MetadataOnlyRouter,
    SplitConfig,
    TextMetadataRouter,
    TierMajorityRouter,
    fit_refit_evaluate,
    make_splits,
)

ROUTERS = {
    "text_metadata_logreg": TextMetadataRouter,
    "metadata_logreg": MetadataOnlyRouter,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input_csv", required=True, help="Per-problem table with outcomes and metadata.")
    parser.add_argument("--output_dir", required=True, help="Where to write predictions and metrics.")
    parser.add_argument(
        "--router",
        choices=sorted(ROUTERS) + ["tier_majority"],
        default="text_metadata_logreg",
        help="Which router to train (default: the main text+metadata router).",
    )
    parser.add_argument(
        "--split",
        choices=["primary", "six_setting"],
        default="primary",
        help="primary = stratified 80/10/10 seed 42; six_setting = 70/15/15 seed 20260712.",
    )
    parser.add_argument("--id_column", default="problem_uid")
    parser.add_argument(
        "--split_csv",
        default=None,
        help="Optional precomputed split assignment (columns: <id_column>, split).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        table = load_matched_table(args.input_csv)
        frame = table.frame
    except Exception:
        # Not a matched-label table; accept any frame that already has labels.
        frame = io.read_csv(args.input_csv)
        if "oracle_label" not in frame.columns:
            print(
                "ERROR: input must be a matched-label table or already carry an "
                "'oracle_label' column.",
                file=sys.stderr,
            )
            return 2

    if args.id_column not in frame.columns:
        print(f"ERROR: missing id column {args.id_column!r}", file=sys.stderr)
        return 2

    config = SplitConfig.primary() if args.split == "primary" else SplitConfig.six_setting()
    if args.split_csv:
        assignment = io.read_csv(args.split_csv)
        frame = frame.merge(assignment[[args.id_column, "split"]], on=args.id_column, how="inner")
    else:
        frame = frame.copy()
        frame["split"] = make_splits(frame, config=config, id_column=args.id_column)

    counts = frame["split"].value_counts().to_dict()
    print(f"Split: {config.name}  ->  {counts}")

    out = io.ensure_dir(args.output_dir)

    if args.router == "tier_majority":
        train = frame[frame["split"].isin(["train", "dev"])]
        test = frame[frame["split"] == "test"]
        router = TierMajorityRouter().fit(train, train["oracle_label"].tolist())
        predictions = pd.DataFrame(
            {
                args.id_column: test[args.id_column].tolist(),
                "oracle_label": test["oracle_label"].tolist(),
                "predicted_label": router.predict(test),
            }
        )
        best: dict[str, object] = {
            "global_majority": router.global_majority,
            "n_tiers": len(router.tier_majority),
        }
        search_log: list[dict[str, object]] = []
    else:
        _, best, search_log, predictions = fit_refit_evaluate(
            ROUTERS[args.router], frame, label_column="oracle_label"
        )
        predictions = predictions.rename(columns={"problem_uid": args.id_column})

    golds = predictions["oracle_label"].tolist()
    preds = predictions["predicted_label"].tolist()
    metrics = {
        "router": args.router,
        "split": config.name,
        "n_test": len(predictions),
        "oracle_label_accuracy": round(accuracy(golds, preds), 6),
        "macro_f1": round(macro_f1(golds, preds), 6),
        **{k: round(v, 6) for k, v in escalation_rates(golds, preds).items()},
    }
    print("\n".join(f"{k}: {v}" for k, v in metrics.items()))

    io.write_frame(out / "test_predictions.csv", predictions)
    io.write_frame(out / "metrics.csv", pd.DataFrame([metrics]))
    io.write_json(out / "selected_config.json", {"selected": dict(best), "dev_search": search_log})
    print(f"\nWrote router artifacts to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
