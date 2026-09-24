#!/usr/bin/env python3
"""Validate matched-outcome tables and emit the per-setting aggregates.

OFFLINE. No model calls.

Validates the schema of every per-problem matched-label CSV, recomputes the
fixed-order oracle label, and writes the coverage / oracle-distribution /
PER-vs-Broadcast interaction tables.

To check the regenerated tables against the camera-ready CSVs, use
``reproduce_paper_tables.py --reference_dir ...`` instead.
"""

from __future__ import annotations

import argparse
import sys

import _bootstrap_path  # noqa: F401
from protocol_routing import io
from protocol_routing.matched import (
    coverage_table,
    load_matched_dir,
    oracle_distribution_table,
    per_broadcast_interaction_table,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--matched_dir", required=True, help="Directory of matched-label CSVs.")
    parser.add_argument("--output_dir", required=True, help="Where to write the aggregate tables.")
    parser.add_argument(
        "--allow_non_paper_settings",
        action="store_true",
        help=(
            "Include settings outside the 10 paper settings. Off by default, "
            "because some source extracts also carry settings that the paper "
            "excludes (one for a NonCommercial licence and no matched Gemma run, "
            "one an appendix-only tier-sampled slice). Those are not paper "
            "settings and are excluded from the release."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        tables = load_matched_dir(args.matched_dir, strict=not args.allow_non_paper_settings)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    out = io.ensure_dir(args.output_dir)
    print(f"Validated {len(tables)} setting(s):")
    for table in tables:
        counts = table.frame["oracle_label"].value_counts().to_dict()
        print(f"  {table.setting:<52} n={table.n:<5} oracle={counts}")

    for name, frame in (
        ("matched_protocol_coverage.csv", coverage_table(tables)),
        ("oracle_label_distribution.csv", oracle_distribution_table(tables)),
        ("per_broadcast_interaction.csv", per_broadcast_interaction_table(tables)),
    ):
        print(f"wrote {io.write_frame(out / name, frame)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
