"""The single authoritative implementation of the fixed-order oracle.

The oracle label of a problem is the FIRST protocol, in the fixed order

    Baseline -> Single -> PER -> Broadcast -> None

whose observed execution was correct.  ``None`` means all four observed
executions failed.

Two properties this module exists to guarantee:

1. The order is fixed and is not a per-problem cost argmin.  A later protocol
   succeeding never overrides an earlier protocol that also succeeded.
2. There is exactly one implementation.  Every table, figure, router label and
   test in this package routes through :func:`cheapest_successful_protocol` or
   :func:`oracle_label_series`.  Duplicating the if/elif ladder elsewhere is
   how the order silently drifts.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from protocol_routing.protocols import (
    CORRECTNESS_COLUMNS,
    ORACLE_ORDER,
    Protocol,
)


def _as_bool(value: object) -> bool:
    """Coerce an outcome cell to a strict boolean.

    Accepts 1/0, True/False, "1"/"0", "true"/"false", "True"/"False".
    Anything else (including NaN, empty string, "unknown") raises, because a
    silently-falsy missing outcome would move probability mass into ``none``
    and make the oracle look pessimistic rather than broken.
    """
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)) and value in (0, 1):
        return bool(value)
    if isinstance(value, (float, np.floating)):
        if value == 0.0:
            return False
        if value == 1.0:
            return True
        raise ValueError(f"Non-binary outcome value: {value!r}")
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes"}:
        return True
    if text in {"0", "false", "f", "no"}:
        return False
    raise ValueError(
        f"Cannot interpret {value!r} as a protocol outcome. "
        "Outcomes must be strictly binary; missing values are not allowed "
        "because a missing outcome is not a failure."
    )


def cheapest_successful_protocol(outcomes: Mapping[str, object]) -> Protocol:
    """Return the fixed-order oracle label for one problem.

    Parameters
    ----------
    outcomes
        Mapping from protocol identifier (any spelling accepted by
        :func:`~protocol_routing.protocols.canonical_protocol`, or the matched
        table column names ``baseline_correct`` etc.) to a binary outcome.

    Returns
    -------
    Protocol
        The first successful protocol in ``ORACLE_ORDER``, or ``Protocol.NONE``
        if all four failed.
    """
    resolved: dict[str, object] = {}
    for key, value in outcomes.items():
        text = str(key).strip().lower()
        # Accept the matched-table column spellings directly.
        matched = [p for p, col in CORRECTNESS_COLUMNS.items() if col == text]
        if matched:
            resolved[matched[0]] = value
            continue
        from protocol_routing.protocols import canonical_protocol

        resolved[canonical_protocol(text).value] = value

    # Validate completeness BEFORE scanning. Short-circuiting on an early
    # success would let a truncated row through unnoticed, and a row missing
    # its expensive-protocol outcomes is not a row we can label.
    missing = [p.value for p in ORACLE_ORDER if p.value not in resolved]
    if missing:
        raise KeyError(
            f"Missing outcome(s) for protocol(s) {missing}; "
            f"the oracle needs all of {[p.value for p in ORACLE_ORDER]}."
        )
    # Coerce ALL four before scanning, not just up to the first success. The
    # vectorised path validates every cell, and a scalar path that stopped early
    # would accept rows the batch path rejects -- the two must agree or a
    # per-row check and a whole-table check disagree on the same data.
    values = [_as_bool(resolved[p.value]) for p in ORACLE_ORDER]
    for protocol, ok in zip(ORACLE_ORDER, values):
        if ok:
            return protocol
    return Protocol.NONE


def oracle_label_series(
    frame: pd.DataFrame,
    *,
    columns: Mapping[str, str] | None = None,
) -> pd.Series:
    """Vectorised fixed-order oracle over a whole outcome table.

    Parameters
    ----------
    frame
        One row per problem, with one binary column per protocol.
    columns
        Optional override mapping protocol identifier -> column name.  Defaults
        to :data:`~protocol_routing.protocols.CORRECTNESS_COLUMNS`.

    Returns
    -------
    pandas.Series
        Oracle label per row, dtype ``object``, values drawn from
        ``{"baseline_llm", "single_agent", "planner_executor_reviewer",
        "broadcast", "none"}``.
    """
    column_map = dict(CORRECTNESS_COLUMNS if columns is None else columns)
    missing = [
        column_map[p.value] for p in ORACLE_ORDER if column_map.get(p.value) not in frame.columns
    ]
    if missing:
        raise KeyError(f"Outcome table is missing required columns: {missing}")

    labels = pd.Series(Protocol.NONE.value, index=frame.index, dtype=object)
    assigned = pd.Series(False, index=frame.index)
    for protocol in ORACLE_ORDER:
        raw = frame[column_map[protocol.value]]
        success = raw.map(_as_bool).astype(bool)
        # `~assigned` is what makes the order binding: once a cheaper protocol
        # has claimed a row, a later success cannot overwrite it.
        newly = (~assigned) & success
        labels[newly] = protocol.value
        assigned = assigned | newly
    return labels


def any_protocol_solved(frame: pd.DataFrame, *, columns: Mapping[str, str] | None = None) -> pd.Series:
    """Boolean series: did at least one of the four protocols succeed?"""
    return oracle_label_series(frame, columns=columns) != Protocol.NONE.value


def oracle_distribution(labels: Iterable[str]) -> dict[str, float]:
    """Percentage of rows per oracle label, over all five label values."""
    series = pd.Series(list(labels), dtype=object)
    n = len(series)
    from protocol_routing.protocols import PROTOCOL_ORDER

    if n == 0:
        return {p.value: 0.0 for p in PROTOCOL_ORDER}
    return {p.value: 100.0 * float((series == p.value).mean()) for p in PROTOCOL_ORDER}


def escalation_direction(predicted: str, oracle: str) -> str:
    """``"over"``, ``"under"`` or ``"match"`` for one routing decision."""
    from protocol_routing.protocols import ESCALATION_RANK, canonical_protocol

    p = ESCALATION_RANK[canonical_protocol(predicted).value]
    o = ESCALATION_RANK[canonical_protocol(oracle).value]
    if p > o:
        return "over"
    if p < o:
        return "under"
    return "match"


def _unused(_: Sequence[object]) -> None:  # pragma: no cover
    """Placeholder kept out of the public surface."""
