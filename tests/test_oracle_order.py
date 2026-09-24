"""The fixed-order oracle: Baseline -> Single -> PER -> Broadcast -> None.

These tests exist because the order is a convention, not a derivation. Nothing
in the data enforces it; only this code does. If the order ever silently
changes, every oracle number in the paper changes with it, so the order is
pinned here exhaustively rather than by example.
"""

from __future__ import annotations

import itertools

import pandas as pd
import pytest

from protocol_routing.oracle import (
    any_protocol_solved,
    cheapest_successful_protocol,
    escalation_direction,
    oracle_label_series,
)
from protocol_routing.protocols import ORACLE_ORDER, Protocol

COLUMNS = ["baseline_correct", "single_correct", "per_correct", "broadcast_correct"]
EXPECTED_ORDER = [
    Protocol.BASELINE,
    Protocol.SINGLE,
    Protocol.PER,
    Protocol.BROADCAST,
]


def test_oracle_order_constant_is_exactly_the_paper_order():
    assert list(ORACLE_ORDER) == EXPECTED_ORDER
    assert [p.value for p in ORACLE_ORDER] == [
        "baseline_llm",
        "single_agent",
        "planner_executor_reviewer",
        "broadcast",
    ]


@pytest.mark.parametrize("outcomes", list(itertools.product([0, 1], repeat=4)))
def test_all_sixteen_outcome_patterns(outcomes):
    """Exhaustive over every possible outcome vector.

    The expected label is computed independently here (a plain left-to-right
    scan) rather than by calling the implementation, so this is a real check
    and not a tautology.
    """
    row = dict(zip(COLUMNS, outcomes))
    expected = Protocol.NONE
    for protocol, value in zip(ORACLE_ORDER, outcomes):
        if value == 1:
            expected = protocol
            break
    assert cheapest_successful_protocol(row) is expected


def test_none_when_all_four_fail():
    assert cheapest_successful_protocol(dict(zip(COLUMNS, [0, 0, 0, 0]))) is Protocol.NONE


def test_all_four_succeeding_gives_the_cheapest_not_the_best():
    assert cheapest_successful_protocol(dict(zip(COLUMNS, [1, 1, 1, 1]))) is Protocol.BASELINE


@pytest.mark.parametrize(
    "earlier_index,later_index",
    [(i, j) for i in range(4) for j in range(4) if i < j],
)
def test_a_later_success_never_overrides_an_earlier_one(earlier_index, later_index):
    """The load-bearing property: order beats any notion of 'better'."""
    outcomes = [0, 0, 0, 0]
    outcomes[earlier_index] = 1
    outcomes[later_index] = 1
    row = dict(zip(COLUMNS, outcomes))
    assert cheapest_successful_protocol(row) is ORACLE_ORDER[earlier_index]
    assert cheapest_successful_protocol(row) is not ORACLE_ORDER[later_index]


def test_order_is_not_a_cost_argmin():
    """A cheap-but-later protocol must NOT win. Only position matters.

    Broadcast succeeding alone yields Broadcast even though PER is 'cheaper' in
    the ladder: PER failed, so it is not a candidate at all.
    """
    assert cheapest_successful_protocol(dict(zip(COLUMNS, [0, 0, 0, 1]))) is Protocol.BROADCAST
    assert cheapest_successful_protocol(dict(zip(COLUMNS, [0, 0, 1, 1]))) is Protocol.PER


def test_vectorised_matches_scalar_on_the_fixture(toy_frame):
    vector = oracle_label_series(toy_frame).tolist()
    scalar = [
        cheapest_successful_protocol({c: row[c] for c in COLUMNS}).value
        for _, row in toy_frame.iterrows()
    ]
    assert vector == scalar


def test_fixture_exercises_every_label(toy_frame):
    """A fixture that never produces 'none' could not detect a broken none case."""
    labels = set(oracle_label_series(toy_frame))
    assert Protocol.NONE.value in labels
    assert Protocol.BASELINE.value in labels
    assert len(labels) >= 4


def test_fixture_contains_non_monotone_rows(toy_frame):
    """An earlier success with a later failure must exist, or the order is untested."""
    non_monotone = (
        (toy_frame["baseline_correct"] == 1) & (toy_frame["broadcast_correct"] == 0)
    ).sum()
    assert non_monotone > 0


def test_missing_protocol_column_raises():
    with pytest.raises(KeyError):
        cheapest_successful_protocol({"baseline_correct": 1, "single_correct": 0})


def test_unparseable_outcome_raises_rather_than_counting_as_failure():
    """A missing outcome is not a failure; silently coercing it would bias 'none' up."""
    row = dict(zip(COLUMNS, [0, 0, 0, 0]))
    row["per_correct"] = "unknown"
    with pytest.raises(ValueError):
        cheapest_successful_protocol(row)


def test_nan_outcome_raises():
    frame = pd.DataFrame(
        {
            "baseline_correct": [0],
            "single_correct": [float("nan")],
            "per_correct": [0],
            "broadcast_correct": [0],
        }
    )
    with pytest.raises(ValueError):
        oracle_label_series(frame)


def test_accepts_string_and_bool_spellings():
    assert cheapest_successful_protocol(
        {
            "baseline_correct": "False",
            "single_correct": "true",
            "per_correct": False,
            "broadcast_correct": True,
        }
    ) is Protocol.SINGLE


def test_any_protocol_solved_agrees_with_the_label(toy_frame):
    solved = any_protocol_solved(toy_frame)
    labels = oracle_label_series(toy_frame)
    assert list(solved) == [label != Protocol.NONE.value for label in labels]


def test_escalation_direction_ranks_none_as_abstention():
    assert escalation_direction("broadcast", "baseline_llm") == "over"
    assert escalation_direction("baseline_llm", "broadcast") == "under"
    assert escalation_direction("per", "planner_executor_reviewer") == "match"
    # `none` is rank -1: routing to none when the oracle solved it is under-escalation.
    assert escalation_direction("none", "single_agent") == "under"


def test_scalar_and_vector_paths_agree_on_strictness():
    """A row the batch path rejects must not be accepted by the per-row path.

    Regression guard: an early-returning scalar implementation would label this
    row 'baseline_llm' and never look at the corrupt Broadcast cell, while
    oracle_label_series would raise on it.
    """
    row = {
        "baseline_correct": 1,
        "single_correct": 0,
        "per_correct": 0,
        "broadcast_correct": "corrupt",
    }
    with pytest.raises(ValueError):
        cheapest_successful_protocol(row)
    with pytest.raises(ValueError):
        oracle_label_series(pd.DataFrame([row]))
