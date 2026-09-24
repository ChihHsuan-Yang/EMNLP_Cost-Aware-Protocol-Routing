"""Load, validate and aggregate the matched per-problem outcome tables.

A *matched* table has one row per problem and one binary outcome column per
protocol, so all four protocols are observed on the same problem set.  This is
what makes the fixed-order oracle and the paired protocol comparisons
well-defined.

Two aggregations are produced here, and they are the two camera-ready
ancillary tables:

``coverage_table``
    per-protocol solve rates plus fixed-order-oracle coverage.
``oracle_distribution_table``
    fixed-order-oracle label percentages (the five label shares).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pandas as pd

from protocol_routing import io
from protocol_routing.oracle import oracle_label_series
from protocol_routing.protocols import CORRECTNESS_COLUMNS, ORACLE_ORDER, Protocol

#: Columns every matched-label table must carry.
REQUIRED_COLUMNS: tuple[str, ...] = (
    "setting",
    "benchmark_id",
    "slice_id",
    "run_id",
    "model",
    "model_endpoint",
    "domain",
    "problem_uid",
    "baseline_correct",
    "single_correct",
    "per_correct",
    "broadcast_correct",
)

#: Paper-facing display names.  Settings not listed here are NOT paper settings
#: and are dropped by :func:`load_matched_dir` unless ``strict=False``.
#: The map is (solver display name, setting display name) keyed by the
#: ``setting`` value written in the tables themselves.
PAPER_SETTINGS: Mapping[str, tuple[str, str]] = {
    "omnimath2__competition_math_4181__gpt_oss_120b": ("gpt-oss-120b", "OmniMath"),
    "jeebench__text_only__gpt_oss_120b": ("gpt-oss-120b", "JEEBench"),
    "scibench__text_only__gpt_oss_120b": ("gpt-oss-120b", "SciBench"),
    "labbench__llm_strict__gpt_oss_120b": ("gpt-oss-120b", "LAB-Bench strict"),
    "labbench__text_no_tool__gpt_oss_120b_text_no_tool": ("gpt-oss-120b", "LAB-Bench text-no-tool"),
    "omnimath2__competition_math_4181__gemma_4_31b": ("Gemma-4-31B-it", "OmniMath"),
    "jeebench__text_only__gemma_4_31b": ("Gemma-4-31B-it", "JEEBench"),
    "scibench__text_only__gemma_4_31b": ("Gemma-4-31B-it", "SciBench"),
    "labbench__llm_strict__gemma_4_31b": ("Gemma-4-31B-it", "LAB-Bench strict"),
    "labbench__text_no_tool__gemma_4_31b_text_no_tool": ("Gemma-4-31B-it", "LAB-Bench text-no-tool"),
}

#: Row order of the camera-ready coverage table: solver-major, then setting.
COVERAGE_ROW_ORDER: tuple[str, ...] = (
    "omnimath2__competition_math_4181__gpt_oss_120b",
    "jeebench__text_only__gpt_oss_120b",
    "scibench__text_only__gpt_oss_120b",
    "labbench__llm_strict__gpt_oss_120b",
    "labbench__text_no_tool__gpt_oss_120b_text_no_tool",
    "omnimath2__competition_math_4181__gemma_4_31b",
    "jeebench__text_only__gemma_4_31b",
    "scibench__text_only__gemma_4_31b",
    "labbench__llm_strict__gemma_4_31b",
    "labbench__text_no_tool__gemma_4_31b_text_no_tool",
)

#: Row order of the camera-ready oracle-distribution table: setting-major,
#: Gemma before gpt-oss within each setting.
ORACLE_ROW_ORDER: tuple[str, ...] = (
    "omnimath2__competition_math_4181__gemma_4_31b",
    "omnimath2__competition_math_4181__gpt_oss_120b",
    "jeebench__text_only__gemma_4_31b",
    "jeebench__text_only__gpt_oss_120b",
    "scibench__text_only__gemma_4_31b",
    "scibench__text_only__gpt_oss_120b",
    "labbench__llm_strict__gemma_4_31b",
    "labbench__llm_strict__gpt_oss_120b",
    "labbench__text_no_tool__gemma_4_31b_text_no_tool",
    "labbench__text_no_tool__gpt_oss_120b_text_no_tool",
)


class MatchedTableError(ValueError):
    """Raised when a matched-label table fails schema validation."""


@dataclass(frozen=True)
class MatchedTable:
    """One validated matched-label table plus its recomputed oracle labels."""

    setting: str
    frame: pd.DataFrame

    @property
    def n(self) -> int:
        return len(self.frame)

    @property
    def solver(self) -> str:
        return PAPER_SETTINGS[self.setting][0] if self.setting in PAPER_SETTINGS else str(
            self.frame["model_endpoint"].iloc[0]
        )

    @property
    def setting_label(self) -> str:
        return PAPER_SETTINGS[self.setting][1] if self.setting in PAPER_SETTINGS else self.setting


def validate_matched_frame(frame: pd.DataFrame, *, source: str = "<frame>") -> None:
    """Schema-check one matched-label table.  Raises :class:`MatchedTableError`."""
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise MatchedTableError(f"{source}: missing required columns {missing}")
    if frame.empty:
        raise MatchedTableError(f"{source}: table is empty")
    if frame["setting"].nunique() != 1:
        raise MatchedTableError(
            f"{source}: expected exactly one setting per file, found "
            f"{sorted(frame['setting'].unique())}"
        )
    if frame["problem_uid"].duplicated().any():
        dupes = frame.loc[frame["problem_uid"].duplicated(), "problem_uid"].unique()[:5]
        raise MatchedTableError(
            f"{source}: problem_uid must be unique (matched design); e.g. {list(dupes)}"
        )
    for protocol in ORACLE_ORDER:
        column = CORRECTNESS_COLUMNS[protocol.value]
        values = set(pd.unique(frame[column]))
        bad = {v for v in values if str(v).strip().lower() not in {"0", "1", "true", "false"}}
        if bad:
            raise MatchedTableError(
                f"{source}: column {column!r} has non-binary values {sorted(map(str, bad))[:5]}"
            )


def load_matched_table(path: str | Path) -> MatchedTable:
    """Read and validate a single matched-label CSV, attaching ``oracle_label``."""
    resolved = io.require_file(path, what="matched-label CSV")
    frame = pd.read_csv(resolved)
    validate_matched_frame(frame, source=resolved.name)
    frame = frame.copy()
    frame["oracle_label"] = oracle_label_series(frame)
    return MatchedTable(setting=str(frame["setting"].iloc[0]), frame=frame)


def load_matched_dir(
    directory: str | Path,
    *,
    settings: Sequence[str] | None = None,
    strict: bool = True,
) -> list[MatchedTable]:
    """Load every ``*.csv`` in ``directory`` that is a paper setting.

    Parameters
    ----------
    settings
        Explicit allowlist of ``setting`` values.  Defaults to
        :data:`PAPER_SETTINGS`.
    strict
        If ``True`` (default), files whose ``setting`` is not in the allowlist
        are skipped, and it is an error if any allowlisted setting is missing.
        Non-paper settings present in the released extract (e.g. the MaScQA
        runs and the Gemma-3-27B tier-sampled OmniMath run) are excluded from
        every paper table by this mechanism.
    """
    allow = set(PAPER_SETTINGS if settings is None else settings)

    # The released Hugging Face dataset ships ONE combined table
    # (``data/matched_labels.csv``) with a ``setting_id`` column, while the
    # internal extracts ship one CSV per setting in a directory.  Accept both:
    # a reader who follows the documented download should not have to reshape
    # the data before the documented reproduction command will run.
    candidate = Path(directory)
    if candidate.is_file():
        return load_matched_combined(candidate, settings=settings, strict=strict)

    root = io.require_dir(directory, what="matched-label directory")
    tables: dict[str, MatchedTable] = {}
    for path in sorted(root.glob("*.csv")):
        table = load_matched_table(path)
        if strict and table.setting not in allow:
            continue
        if table.setting in tables:
            raise MatchedTableError(f"Duplicate setting {table.setting!r} in {root}")
        tables[table.setting] = table
    if strict:
        missing = sorted(allow - set(tables))
        if missing:
            raise MatchedTableError(f"Missing matched-label tables for settings: {missing}")
    return [tables[s] for s in sorted(tables)]


def load_matched_combined(
    path: str | Path,
    *,
    settings: Sequence[str] | None = None,
    strict: bool = True,
) -> list[MatchedTable]:
    """Load the released single-file matched-label table.

    The Hugging Face release publishes every setting in one CSV keyed by
    ``setting_id``.  This splits it back into per-setting tables so that the
    rest of the pipeline sees exactly the same objects as the directory form.
    """
    allow = set(PAPER_SETTINGS if settings is None else settings)
    resolved = io.require_file(path, what="matched-label CSV")
    frame = pd.read_csv(resolved)

    key = "setting_id" if "setting_id" in frame.columns else "setting"
    if key not in frame.columns:
        raise MatchedTableError(
            f"{resolved.name} has neither a 'setting_id' nor a 'setting' column, "
            "so it cannot be split into per-setting tables."
        )

    tables: dict[str, MatchedTable] = {}
    for setting, group in frame.groupby(key, sort=True):
        setting = str(setting)
        if strict and setting not in allow:
            continue
        part = group.copy()
        if "setting" not in part.columns:
            part["setting"] = setting
        # The release normalises the problem key to ``problem_id``; the internal
        # extracts call it ``problem_uid``. Accept either, without mutating the
        # released column, so both forms validate identically.
        if "problem_uid" not in part.columns and "problem_id" in part.columns:
            part["problem_uid"] = part["problem_id"]
        # Likewise for the oracle column name.
        if ("oracle_cheapest_successful" not in part.columns
                and "oracle_label" in part.columns):
            part["oracle_cheapest_successful"] = part["oracle_label"]
            part = part.drop(columns=["oracle_label"])
        validate_matched_frame(part, source=f"{resolved.name}[{setting}]")
        part["oracle_label"] = oracle_label_series(part)
        tables[setting] = MatchedTable(setting=setting, frame=part.reset_index(drop=True))

    if strict:
        missing = sorted(allow - set(tables))
        if missing:
            raise MatchedTableError(
                f"Missing matched-label rows for settings: {missing} in {resolved.name}"
            )
    return [tables[s] for s in sorted(tables)]


def _bool_series(frame: pd.DataFrame, column: str) -> pd.Series:
    """Coerce an outcome column to strict booleans.

    One definition, used by every aggregation here. The same coercion was
    previously written inline three times; a divergence between copies would
    have silently changed a rate rather than raised.
    """
    return frame[column].map(lambda v: str(v).strip().lower() in {"1", "true"})


def _ordered(tables: Iterable[MatchedTable], order: Sequence[str]) -> list[MatchedTable]:
    by_setting = {t.setting: t for t in tables}
    known = [by_setting[s] for s in order if s in by_setting]
    extra = sorted((t for s, t in by_setting.items() if s not in order), key=lambda t: t.setting)
    return known + extra


def coverage_table(tables: Iterable[MatchedTable], *, decimals: int = 2) -> pd.DataFrame:
    """Four-protocol solve rates plus fixed-order-oracle coverage, in percent.

    Reproduces ``anc/matched_protocol_coverage.csv``.
    """
    rows = []
    for table in _ordered(tables, COVERAGE_ROW_ORDER):
        frame = table.frame
        row = {"solver": table.solver, "setting": table.setting_label, "n": int(len(frame))}
        for protocol in ORACLE_ORDER:
            column = CORRECTNESS_COLUMNS[protocol.value]
            key = {"planner_executor_reviewer": "per"}.get(protocol.value, protocol.value)
            key = key.replace("_llm", "").replace("_agent", "")
            row[f"{key}_pct"] = round(100.0 * float(_bool_series(frame, column).mean()), decimals)
        solved = frame["oracle_label"] != Protocol.NONE.value
        row["oracle_pct"] = round(100.0 * float(solved.mean()), decimals)
        rows.append(row)
    return pd.DataFrame(rows)


def oracle_distribution_table(tables: Iterable[MatchedTable], *, decimals: int = 2) -> pd.DataFrame:
    """Fixed-order-oracle label percentages.

    Reproduces ``anc/oracle_label_distribution.csv``.
    """
    rows = []
    for table in _ordered(tables, ORACLE_ROW_ORDER):
        frame = table.frame
        labels = frame["oracle_label"]
        row = {"solver": table.solver, "setting": table.setting_label, "n": int(len(frame))}
        for protocol in ORACLE_ORDER:
            key = {"planner_executor_reviewer": "per"}.get(protocol.value, protocol.value)
            key = key.replace("_llm", "").replace("_agent", "")
            row[f"{key}_pct"] = round(100.0 * float((labels == protocol.value).mean()), decimals)
        row["none_pct"] = round(100.0 * float((labels == Protocol.NONE.value).mean()), decimals)
        rows.append(row)
    return pd.DataFrame(rows)


def per_broadcast_interaction_table(tables: Iterable[MatchedTable], *, decimals: int = 1) -> pd.DataFrame:
    """PER and Broadcast outcomes conditional on Baseline AND Single failing.

    Reproduces the point estimates and counts of
    ``anc/per_broadcast_interaction.csv``.  The bootstrap CI column of that
    file is produced separately by :mod:`protocol_routing.bootstrap`.
    """
    rows = []
    for table in _ordered(tables, ORACLE_ROW_ORDER):
        frame = table.frame
        subset = frame[
            (~_bool_series(frame, "baseline_correct")) & (~_bool_series(frame, "single_correct"))
        ]
        n = len(subset)
        if n == 0:
            continue
        per = _bool_series(subset, "per_correct")
        bro = _bool_series(subset, "broadcast_correct")
        rows.append(
            {
                "solver": table.solver,
                "setting": table.setting_label,
                "n": int(n),
                "per_solve_pct": round(100.0 * float(per.mean()), decimals),
                "broadcast_solve_pct": round(100.0 * float(bro.mean()), decimals),
                "broadcast_minus_per_points": round(100.0 * float(bro.mean() - per.mean()), decimals),
                "per_only_count": int((per & ~bro).sum()),
                "per_only_pct": round(100.0 * float((per & ~bro).mean()), decimals),
                "broadcast_only_count": int((bro & ~per).sum()),
                "broadcast_only_pct": round(100.0 * float((bro & ~per).mean()), decimals),
                "both_count": int((per & bro).sum()),
                "both_pct": round(100.0 * float((per & bro).mean()), decimals),
                "neither_count": int((~per & ~bro).sum()),
                "neither_pct": round(100.0 * float((~per & ~bro).mean()), decimals),
            }
        )
    return pd.DataFrame(rows)
