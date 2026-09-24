"""Console-script entry points declared in ``pyproject.toml``.

These mirror the thin CLIs in ``scripts/`` so that an installed package exposes
them on PATH. The ``scripts/`` versions stay the documented interface for a
source checkout.
"""

from __future__ import annotations

import sys


def reproduce_tables_main(argv: list[str] | None = None) -> int:
    """``protocol-routing-tables``: rebuild and verify the aggregate tables."""
    import argparse

    from protocol_routing import io
    from protocol_routing.matched import (
        coverage_table,
        load_matched_dir,
        oracle_distribution_table,
    )

    parser = argparse.ArgumentParser(
        prog="protocol-routing-tables",
        description=(
            "Rebuild matched_protocol_coverage.csv and oracle_label_distribution.csv "
            "from per-problem matched outcomes, recomputing the fixed-order oracle."
        ),
    )
    parser.add_argument("--matched_dir", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--allow_non_paper_settings", action="store_true")
    args = parser.parse_args(argv)

    try:
        tables = load_matched_dir(args.matched_dir, strict=not args.allow_non_paper_settings)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    out = io.ensure_dir(args.output_dir)
    for name, frame in (
        ("matched_protocol_coverage.csv", coverage_table(tables)),
        ("oracle_label_distribution.csv", oracle_distribution_table(tables)),
    ):
        print(f"wrote {io.write_frame(out / name, frame)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(reproduce_tables_main())
