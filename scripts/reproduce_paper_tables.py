#!/usr/bin/env python3
"""Regenerate the camera-ready aggregate tables and diff them against the paper.

OFFLINE. Reads only the released per-problem matched-outcome tables; calls no
model, needs no GPU, finishes in seconds.

What it does
------------
1. Loads the 10 paper settings' matched-label tables.
2. Recomputes the fixed-order oracle label for every problem from the four
   observed outcomes (it does NOT trust any stored label column).
3. Rebuilds ``matched_protocol_coverage.csv`` and
   ``oracle_label_distribution.csv``.
4. Diffs each cell against the camera-ready ancillary CSVs, prints a per-row
   PASS/FAIL, and exits nonzero on any mismatch.

Exit codes: 0 = every row matched; 1 = at least one mismatch; 2 = input problem.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

import _bootstrap_path  # noqa: F401  (sys.path setup for source checkouts)
from protocol_routing import io
from protocol_routing.matched import (
    coverage_table,
    load_matched_dir,
    oracle_distribution_table,
    per_broadcast_interaction_table,
)

TABLES = {
    "matched_protocol_coverage.csv": coverage_table,
    "oracle_label_distribution.csv": oracle_distribution_table,
}

OPTIONAL_TABLES = {
    # Reproducible point estimates; the reference file also carries a bootstrap
    # CI column, which this script does not attempt to match cell-for-cell.
    "per_broadcast_interaction.csv": per_broadcast_interaction_table,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--matched_dir",
        required=True,
        help="Directory of per-problem matched-label CSVs (one per setting).",
    )
    parser.add_argument(
        "--reference_dir",
        default=None,
        help=(
            "Directory of camera-ready ancillary CSVs to diff against. "
            "Omit to regenerate without checking."
        ),
    )
    parser.add_argument(
        "--output_dir",
        default=None,
        help="Where to write the regenerated tables. Omit to skip writing.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.0,
        help="Absolute tolerance for numeric cells (default 0.0: exact match).",
    )
    parser.add_argument(
        "--include_optional",
        action="store_true",
        help="Also rebuild per_broadcast_interaction.csv (point estimates only).",
    )
    return parser.parse_args(argv)


def _compare(produced: pd.DataFrame, reference: pd.DataFrame, *, tolerance: float) -> list[tuple[str, bool, str]]:
    """Row-by-row comparison. Returns ``(row_label, ok, detail)`` per row."""
    results: list[tuple[str, bool, str]] = []
    shared = [c for c in reference.columns if c in produced.columns]
    missing_cols = [c for c in reference.columns if c not in produced.columns]
    if missing_cols:
        results.append(("<columns>", False, f"produced table is missing columns {missing_cols}"))
    if len(produced) != len(reference):
        results.append(
            ("<rowcount>", False, f"produced {len(produced)} rows, reference has {len(reference)}")
        )
    for i in range(min(len(produced), len(reference))):
        p_row = produced.iloc[i]
        r_row = reference.iloc[i]
        label = " / ".join(str(r_row[c]) for c in ("solver", "setting") if c in reference.columns) or f"row {i}"
        diffs = []
        for column in shared:
            pv, rv = p_row[column], r_row[column]
            try:
                pf, rf = float(pv), float(rv)
                ok = abs(pf - rf) <= tolerance
                shown = f"{column}: got {pf} want {rf}"
            except (TypeError, ValueError):
                ok = str(pv).strip() == str(rv).strip()
                shown = f"{column}: got {pv!r} want {rv!r}"
            if not ok:
                diffs.append(shown)
        results.append((label, not diffs, "; ".join(diffs)))
    return results


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        tables = load_matched_dir(args.matched_dir)
    except Exception as exc:  # noqa: BLE001 - surface the reason, do not mask it
        print(f"ERROR loading matched-label tables: {exc}", file=sys.stderr)
        return 2

    print(f"Loaded {len(tables)} paper settings from {io.resolve(args.matched_dir)}")
    for table in tables:
        print(f"  {table.setting:<52} n={table.n}")
    print()
    print("Oracle labels are RECOMPUTED from the four observed outcomes in the")
    print("fixed order Baseline -> Single -> PER -> Broadcast -> None.")
    print()

    builders = dict(TABLES)
    if args.include_optional:
        builders.update(OPTIONAL_TABLES)

    output_dir = io.ensure_dir(args.output_dir) if args.output_dir else None
    failures = 0

    for filename, builder in builders.items():
        produced = builder(tables)
        if output_dir is not None:
            written = io.write_frame(output_dir / filename, produced)
            print(f"wrote {written}")
        if not args.reference_dir:
            continue
        reference_path = Path(io.resolve(args.reference_dir)) / filename
        print(f"\n=== {filename} ===")
        if not reference_path.is_file():
            print(f"  SKIP  reference not found: {reference_path}")
            continue
        reference = pd.read_csv(reference_path)
        results = _compare(produced, reference, tolerance=args.tolerance)
        for label, ok, detail in results:
            status = "PASS" if ok else "FAIL"
            print(f"  {status}  {label}" + (f"  <- {detail}" if detail else ""))
            failures += 0 if ok else 1

    if not args.reference_dir:
        print("\nNo --reference_dir given; tables regenerated but NOT verified.")
        return 0

    print()
    if failures:
        print(f"RESULT: FAIL ({failures} mismatching row(s))")
        return 1
    print("RESULT: PASS (every row matches the camera-ready tables exactly)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
