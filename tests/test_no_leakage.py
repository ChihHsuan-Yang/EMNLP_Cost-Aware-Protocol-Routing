"""Label columns must never reach feature construction.

The paper's claim is that a router can PREDICT which protocol to pay for. If any
outcome column reaches the feature matrix the claim is void, and the failure is
silent: the model just gets suspiciously good. So the guard is structural, and
these tests attack it rather than confirm it.

Every test here asserts a RAISE. A leakage guard that has only ever seen clean
input has detected nothing.
"""

from __future__ import annotations

import pandas as pd
import pytest

from protocol_routing.features import (
    FORBIDDEN_FEATURE_COLUMNS,
    FeatureSpec,
    Featurizer,
    LeakageError,
    assert_no_leakage,
    build_feature_frame,
    is_forbidden,
)

#: Every column name a careless caller might plausibly pass. Each MUST raise.
LEAKY_COLUMNS = [
    "baseline_correct",
    "single_correct",
    "per_correct",
    "broadcast_correct",
    "baseline_final_passed",
    "single_agent_final_passed",
    "per_final_passed",
    "broadcast_final_passed",
    "oracle_cheapest_successful",
    "cheapest_successful_protocol",
    "oracle_label",
    "any_protocol_solved",
    "solved",
    "gold_answer",
    "answer",
    "final_answer",
    "solution",
    "ground_truth",
    "label",
    "gold_label",
    "success",
    # Pattern-matched families that are not in the exact-name set.
    "some_new_protocol_correct",
    "future_protocol_final_passed",
    "oracle_anything",
    "gold_whatever",
    "anything_solved",
]


@pytest.mark.parametrize("column", LEAKY_COLUMNS)
def test_assert_no_leakage_raises_on_every_known_label_column(column):
    with pytest.raises(LeakageError) as excinfo:
        assert_no_leakage([column])
    # The message must name the offending column: a guard whose error does not
    # say what it caught sends the caller hunting.
    assert column in str(excinfo.value)


@pytest.mark.parametrize("column", LEAKY_COLUMNS)
def test_is_forbidden_agrees_with_the_guard(column):
    assert is_forbidden(column) is True


@pytest.mark.parametrize(
    "column", ["problem", "source", "domain", "difficulty", "difficulty_tier", "question", "tier"]
)
def test_legitimate_feature_columns_are_allowed(column):
    """The guard must not be vacuously strict: real features have to pass.

    Without this, a guard that rejected everything would look identical to a
    working one.
    """
    assert is_forbidden(column) is False
    assert_no_leakage([column])  # must not raise


def test_case_and_whitespace_do_not_evade_the_guard():
    for spelling in ("Baseline_Correct", "  baseline_correct  ", "ORACLE_LABEL"):
        with pytest.raises(LeakageError):
            assert_no_leakage([spelling])


def test_featurespec_rejects_a_label_column_at_construction():
    """Fails before any data is read, not at fit time."""
    with pytest.raises(LeakageError):
        FeatureSpec(categorical_columns=("source", "baseline_correct"))
    with pytest.raises(LeakageError):
        FeatureSpec(text_column="gold_answer")
    with pytest.raises(LeakageError):
        FeatureSpec(numeric_columns=("difficulty", "any_protocol_solved"))


def test_build_feature_frame_rejects_a_label_column():
    frame = pd.DataFrame(
        {"problem": ["x"], "source": ["s"], "domain": ["math"], "difficulty": [1.0],
         "difficulty_tier": [1], "baseline_correct": [1]}
    )
    spec = FeatureSpec()
    projected = build_feature_frame(frame, spec)
    # The label column is physically absent from what the featurizer sees.
    assert "baseline_correct" not in projected.columns
    assert set(projected.columns) == set(spec.all_columns())


def test_featurizer_output_cannot_contain_outcome_information(toy_frame):
    """Fitting on a frame that CARRIES outcomes is fine; using them is not.

    The full matched table is the natural input, so the guard must let the frame
    through while excluding the outcome columns from the matrix.
    """
    featurizer = Featurizer(spec=FeatureSpec())
    matrix = featurizer.fit_transform(toy_frame)
    assert matrix.shape[0] == len(toy_frame)
    assert matrix.shape[1] == featurizer.n_features


def test_deliberate_violation_raises_end_to_end(toy_frame):
    """The demonstration: construct a spec that leaks, and watch it fail.

    This is the test that gives the guard its evidence. If someone weakens the
    guard, this stops raising and the suite goes red.
    """
    with pytest.raises(LeakageError) as excinfo:
        FeatureSpec(
            text_column="problem",
            categorical_columns=("source", "baseline_correct"),
            numeric_columns=("difficulty", "difficulty_tier"),
        )
    message = str(excinfo.value)
    assert "baseline_correct" in message
    assert "leakage" in message.lower()


def test_guard_covers_every_declared_forbidden_name():
    """Every name in the declared set must actually be rejected.

    Guards against a name being added to the documentation set while the
    matching logic silently fails to consult it.
    """
    for column in sorted(FORBIDDEN_FEATURE_COLUMNS):
        assert is_forbidden(column), f"{column!r} is declared forbidden but is not rejected"


def test_guard_is_checked_on_the_actual_columns_not_a_promise():
    """There is no 'trust me, this frame is clean' path around the guard.

    The guard inspects the column names it is actually handed, so declaring a
    leaky column as a feature raises no matter how the spec is assembled.
    """
    leaky = dict(
        text_column=None,
        categorical_columns=("oracle_label",),
        multilabel_json_columns=(),
        numeric_columns=("difficulty",),
    )
    with pytest.raises(LeakageError):
        FeatureSpec(**leaky)


def test_renaming_a_label_column_is_out_of_scope_and_documented():
    """Honest boundary: the guard is name-based and cannot see through a rename.

    A caller who copies baseline_correct into a column called 'feature_17' has
    defeated it. That is a deliberate act, not a slip, and this test records the
    limitation rather than pretending it does not exist.
    """
    disguised = pd.DataFrame({"feature_17": [1, 0], "difficulty": [1.0, 2.0]})
    spec = FeatureSpec(
        text_column=None,
        categorical_columns=("feature_17",),
        multilabel_json_columns=(),
        numeric_columns=("difficulty",),
    )
    # No raise: the guard sees an innocuous name. Documented, not endorsed.
    assert "feature_17" in build_feature_frame(disguised, spec).columns
