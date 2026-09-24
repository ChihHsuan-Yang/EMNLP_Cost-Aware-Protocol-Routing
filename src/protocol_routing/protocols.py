"""Protocol registry: identifiers, fixed oracle order, display names, colours.

Four collaboration protocols are compared in the paper.  Every one of them was
executed on *every* problem, so the per-problem outcome tables are matched: for
each problem we observe four independent (protocol, correct?, cost) triples.

    Baseline  (``baseline_llm``)              direct one-shot answer
    Single    (``single_agent``)              iterative self-correction, one agent
    PER       (``planner_executor_reviewer``) planner / executor / reviewer pipeline
    Broadcast (``broadcast``)                 multi-agent deliberation

``none`` is NOT a fifth execution.  It is the retrospective oracle/router
*action* taken when all four observed executions failed.
"""

from __future__ import annotations

from enum import Enum
from typing import Mapping


class Protocol(str, Enum):
    """Canonical protocol identifiers as written in released outcome tables."""

    BASELINE = "baseline_llm"
    SINGLE = "single_agent"
    PER = "planner_executor_reviewer"
    BROADCAST = "broadcast"
    NONE = "none"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


#: The fixed cheapest-success oracle order.  DO NOT REORDER.
#:
#: The oracle label for a problem is the FIRST protocol in this tuple whose
#: observed execution was correct.  If none of the four was correct the label
#: is ``Protocol.NONE``.  The order encodes the monotone cost ladder reported
#: in the paper (Baseline cheapest, Broadcast most expensive); it is a fixed
#: convention, not a per-problem cost argmin.
ORACLE_ORDER: tuple[Protocol, ...] = (
    Protocol.BASELINE,
    Protocol.SINGLE,
    Protocol.PER,
    Protocol.BROADCAST,
)

#: Display/plot order (the four executions plus the ``none`` action).
PROTOCOL_ORDER: tuple[Protocol, ...] = ORACLE_ORDER + (Protocol.NONE,)

#: Escalation rank, used for over- vs under-escalation accounting.
#: ``none`` is ranked -1 because it is an abstention, not an escalation.
ESCALATION_RANK: Mapping[str, int] = {
    Protocol.BASELINE.value: 0,
    Protocol.SINGLE.value: 1,
    Protocol.PER.value: 2,
    Protocol.BROADCAST.value: 3,
    Protocol.NONE.value: -1,
}

PROTOCOL_DISPLAY: Mapping[str, str] = {
    Protocol.BASELINE.value: "Baseline",
    Protocol.SINGLE.value: "Single",
    Protocol.PER.value: "PER",
    Protocol.BROADCAST.value: "Broadcast",
    Protocol.NONE.value: "None",
}

#: Paper protocol palette.  Held fixed across every protocol chart.
PROTOCOL_COLORS: Mapping[str, str] = {
    Protocol.BASELINE.value: "#4C78A8",
    Protocol.SINGLE.value: "#F58518",
    Protocol.PER.value: "#54A24B",
    Protocol.BROADCAST.value: "#B279A2",
    Protocol.NONE.value: "#9C9C9C",
}

#: Per-protocol boolean-outcome column names used in the matched-label tables.
CORRECTNESS_COLUMNS: Mapping[str, str] = {
    Protocol.BASELINE.value: "baseline_correct",
    Protocol.SINGLE.value: "single_correct",
    Protocol.PER.value: "per_correct",
    Protocol.BROADCAST.value: "broadcast_correct",
}

#: Aliases seen in older artifacts / short-paper benchmark CSVs.  The
#: short-paper ``routing_benchmark.csv`` writes PER as ``per``; the matched
#: per-problem tables write it as ``planner_executor_reviewer``.  Both mean the
#: same protocol.  ``unsolved`` is the matched-table spelling of ``none``.
PROTOCOL_ALIASES: Mapping[str, str] = {
    "baseline": Protocol.BASELINE.value,
    "baseline_llm": Protocol.BASELINE.value,
    "single": Protocol.SINGLE.value,
    "single_agent": Protocol.SINGLE.value,
    "per": Protocol.PER.value,
    "planner_executor_reviewer": Protocol.PER.value,
    "broadcast": Protocol.BROADCAST.value,
    "none": Protocol.NONE.value,
    "unsolved": Protocol.NONE.value,
}


def canonical_protocol(name: str) -> Protocol:
    """Map any known spelling of a protocol to its :class:`Protocol` member.

    Raises
    ------
    ValueError
        If ``name`` is not a recognised protocol spelling.  Unknown protocol
        names are an error rather than a silent pass-through: a typo in a label
        column must not quietly become a new class.
    """
    key = str(name).strip().lower()
    if key not in PROTOCOL_ALIASES:
        raise ValueError(
            f"Unknown protocol name {name!r}. "
            f"Known spellings: {sorted(PROTOCOL_ALIASES)}"
        )
    return Protocol(PROTOCOL_ALIASES[key])


def display_name(name: str) -> str:
    """Human-readable protocol name for tables and figures."""
    return PROTOCOL_DISPLAY[canonical_protocol(name).value]


def color(name: str) -> str:
    """Paper colour for a protocol."""
    return PROTOCOL_COLORS[canonical_protocol(name).value]
