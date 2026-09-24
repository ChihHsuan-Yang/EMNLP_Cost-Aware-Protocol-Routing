#!/usr/bin/env python3
"""Render the protocol-composition figures from the matched outcome tables.

OFFLINE. Matplotlib only; no model calls, no network.

Renders two figures that follow directly from the released per-problem
outcomes:

``fig_oracle_label_distribution``
    Stacked oracle-label shares per setting.
``fig_protocol_coverage``
    Per-protocol solve rates with the fixed-order-oracle ceiling.

Scope note: this reproduces the protocol-composition panels, not every figure
in the paper. Figures that depend on artifacts outside the matched tables
(reliability diagrams, cost-frontier panels, loss histories) need those inputs
and are not regenerated here.

The protocol palette is fixed in ``protocol_routing.protocols`` so every chart
in the release uses the same colour for the same protocol.
"""

from __future__ import annotations

import argparse

import matplotlib

import _bootstrap_path  # noqa: F401

matplotlib.use("Agg")  # headless: never require a display
import matplotlib.pyplot as plt  # noqa: E402

from protocol_routing import io  # noqa: E402
from protocol_routing.matched import (  # noqa: E402
    coverage_table,
    load_matched_dir,
    oracle_distribution_table,
)
from protocol_routing.protocols import (  # noqa: E402
    ORACLE_ORDER,
    PROTOCOL_COLORS,
    PROTOCOL_DISPLAY,
    PROTOCOL_ORDER,
    Protocol,
)

_PCT_KEY = {
    Protocol.BASELINE.value: "baseline_pct",
    Protocol.SINGLE.value: "single_pct",
    Protocol.PER.value: "per_pct",
    Protocol.BROADCAST.value: "broadcast_pct",
    Protocol.NONE.value: "none_pct",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--matched_dir", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--format", default="png", choices=["png", "pdf", "svg"])
    parser.add_argument("--allow_non_paper_settings", action="store_true")
    return parser.parse_args(argv)


_SHORT_SETTING = {
    "LAB-Bench strict": "LAB strict",
    "LAB-Bench text-no-tool": "LAB no-tool",
}
_SHORT_SOLVER = {"Gemma-4-31B-it": "Gemma-4-31B"}


def _labels(frame) -> list[str]:
    """Two-line tick labels, shortened so 10 of them fit without overlapping."""
    return [
        f"{_SHORT_SOLVER.get(r['solver'], r['solver'])}\n{_SHORT_SETTING.get(r['setting'], r['setting'])}"
        for _, r in frame.iterrows()
    ]


def plot_oracle_distribution(frame, path, *, dpi: int) -> None:
    fig, ax = plt.subplots(figsize=(11, 5.0), dpi=dpi)
    labels = _labels(frame)
    bottom = [0.0] * len(frame)
    for protocol in PROTOCOL_ORDER:
        values = frame[_PCT_KEY[protocol.value]].tolist()
        ax.bar(
            labels,
            values,
            bottom=bottom,
            color=PROTOCOL_COLORS[protocol.value],
            label=PROTOCOL_DISPLAY[protocol.value],
            edgecolor="white",
            linewidth=0.6,
        )
        bottom = [b + v for b, v in zip(bottom, values)]
    ax.set_ylabel("Share of problems (%)")
    ax.set_ylim(0, 100)
    ax.set_title("Fixed-order oracle label distribution")
    ax.tick_params(axis="x", labelsize=7)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", rotation_mode="anchor")
    ax.legend(ncol=5, fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.22))
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def plot_coverage(frame, path, *, dpi: int) -> None:
    fig, ax = plt.subplots(figsize=(11, 5.0), dpi=dpi)
    labels = _labels(frame)
    n = len(frame)
    width = 0.19
    for i, protocol in enumerate(ORACLE_ORDER):
        offsets = [x + (i - 1.5) * width for x in range(n)]
        ax.bar(
            offsets,
            frame[_PCT_KEY[protocol.value]].tolist(),
            width=width,
            color=PROTOCOL_COLORS[protocol.value],
            label=PROTOCOL_DISPLAY[protocol.value],
        )
    ax.plot(
        range(n),
        frame["oracle_pct"].tolist(),
        marker="D",
        linestyle="none",
        color=PROTOCOL_COLORS[Protocol.NONE.value],
        markeredgecolor="#333333",
        label="Oracle coverage",
    )
    ax.set_xticks(range(n))
    ax.set_xticklabels(labels, fontsize=7, rotation=30, ha="right", rotation_mode="anchor")
    ax.set_ylabel("Solve rate (%)")
    ax.set_ylim(0, 100)
    ax.set_title("Per-protocol solve rates and fixed-order-oracle coverage")
    ax.legend(ncol=5, fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.22))
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tables = load_matched_dir(args.matched_dir, strict=not args.allow_non_paper_settings)
    out = io.ensure_dir(args.output_dir)

    distribution = oracle_distribution_table(tables)
    coverage = coverage_table(tables)

    a = out / f"fig_oracle_label_distribution.{args.format}"
    b = out / f"fig_protocol_coverage.{args.format}"
    plot_oracle_distribution(distribution, a, dpi=args.dpi)
    print(f"wrote {a}")
    plot_coverage(coverage, b, dpi=args.dpi)
    print(f"wrote {b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
