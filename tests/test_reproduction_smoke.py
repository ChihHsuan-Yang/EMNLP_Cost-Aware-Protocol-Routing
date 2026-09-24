"""End-to-end smoke test on the tiny fixture only.

Constraints this test enforces on itself: no network, no model endpoint, no
GPU, no 58MB inputs, and it must finish in seconds. Everything runs against
tests/fixtures/, which is 48 synthetic rows.
"""

from __future__ import annotations

import subprocess
import sys

import pandas as pd
import pytest

from protocol_routing.bootstrap import bootstrap_metrics, paired_difference, percentile_bootstrap
from protocol_routing.confidence import (
    SELF_CONFIDENCE_GATE_THRESHOLD,
    confidence_report,
    parse_confidence,
    parse_confidence_series,
    self_confidence_gate,
    two_threshold_cascade,
)
from protocol_routing.matched import coverage_table, load_matched_dir, oracle_distribution_table
from protocol_routing.metrics import macro_f1, realized_outcomes, summarize_routing
from protocol_routing.protocols import CORRECTNESS_COLUMNS, Protocol
from protocol_routing.router import (
    MetadataOnlyRouter,
    SplitConfig,
    TextMetadataRouter,
    TierMajorityRouter,
    make_splits,
)

SCRIPTS = ["build_matched_tables", "train_router", "evaluate_router", "analyze_confidence",
           "analyze_protocol_interactions", "reproduce_paper_tables", "reproduce_paper_figures"]


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("script", SCRIPTS)
def test_every_script_has_working_help(repo_root, script):
    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / f"{script}.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


# ---------------------------------------------------------------------------
# Pipeline on the fixture
# ---------------------------------------------------------------------------


def test_tables_build_from_the_fixture(fixture_dir, tmp_path):
    tables = load_matched_dir(fixture_dir, strict=False)
    coverage = coverage_table(tables)
    distribution = oracle_distribution_table(tables)
    assert len(coverage) == 2 and len(distribution) == 2
    coverage.to_csv(tmp_path / "coverage.csv", index=False)
    assert (tmp_path / "coverage.csv").is_file()


def test_reproduce_paper_tables_cli_runs_on_the_fixture(repo_root, fixture_dir, tmp_path):
    """No --reference_dir: the fixture has no camera-ready counterpart."""
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "reproduce_paper_tables.py"),
            "--matched_dir", str(fixture_dir),
            "--output_dir", str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    # strict=True by default, and the toy settings are not paper settings, so
    # this must exit 2 with a clear message rather than silently produce nothing.
    assert result.returncode == 2
    assert "Missing matched-label tables" in result.stderr


def test_build_matched_tables_cli_runs_on_the_fixture(repo_root, fixture_dir, tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "build_matched_tables.py"),
            "--matched_dir", str(fixture_dir),
            "--output_dir", str(tmp_path),
            "--allow_non_paper_settings",
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    for name in ("matched_protocol_coverage.csv", "oracle_label_distribution.csv"):
        assert (tmp_path / name).is_file()


def test_figures_render_headless(repo_root, fixture_dir, tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "reproduce_paper_figures.py"),
            "--matched_dir", str(fixture_dir),
            "--output_dir", str(tmp_path),
            "--allow_non_paper_settings",
            "--dpi", "60",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "fig_oracle_label_distribution.png").stat().st_size > 1000


# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------


def test_splits_are_deterministic_and_order_independent(toy_frame):
    a = make_splits(toy_frame, config=SplitConfig.primary())
    b = make_splits(toy_frame.sample(frac=1.0, random_state=7), config=SplitConfig.primary())
    merged = pd.DataFrame({"uid": toy_frame["problem_uid"], "a": a.values}).merge(
        pd.DataFrame(
            {"uid": toy_frame.sample(frac=1.0, random_state=7)["problem_uid"], "b": b.values}
        ),
        on="uid",
    )
    assert (merged["a"] == merged["b"]).all(), "shuffling the input changed the split"


def test_split_configs_carry_the_paper_seeds():
    assert (SplitConfig.primary().seed, SplitConfig.primary().train_ratio) == (42, 0.8)
    assert (SplitConfig.six_setting().seed, SplitConfig.six_setting().train_ratio) == (20260712, 0.7)


def test_splits_are_disjoint_and_exhaustive(toy_frame):
    splits = make_splits(toy_frame, config=SplitConfig.primary())
    assert splits.notna().all()
    assert set(splits) <= {"train", "dev", "test"}
    assert len(splits) == len(toy_frame)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------


def test_tier_majority_fits_and_predicts(toy_frame):
    from protocol_routing.oracle import oracle_label_series

    labels = oracle_label_series(toy_frame)
    router = TierMajorityRouter().fit(toy_frame, labels.tolist())
    predictions = router.predict(toy_frame)
    assert len(predictions) == len(toy_frame)
    assert set(predictions) <= {p.value for p in Protocol}


def test_learned_routers_fit_on_the_fixture(toy_frame):
    from protocol_routing.oracle import oracle_label_series

    labels = oracle_label_series(toy_frame).tolist()
    for make in (TextMetadataRouter, MetadataOnlyRouter):
        router = make()
        router.fit(toy_frame, labels)
        predictions = router.predict(toy_frame)
        assert len(predictions) == len(toy_frame)
        assert 0.0 <= macro_f1(labels, predictions) <= 1.0


def test_realized_outcomes_replays_observed_results(toy_frame):
    from protocol_routing.oracle import oracle_label_series

    frame = toy_frame.copy()
    frame["oracle_label"] = oracle_label_series(frame)
    always_baseline = [Protocol.BASELINE.value] * len(frame)
    per_example = realized_outcomes(frame, always_baseline, success_columns=CORRECTNESS_COLUMNS)
    expected = frame["baseline_correct"].astype(float).tolist()
    assert per_example["success"].tolist() == expected


def test_routing_to_none_realises_no_success(toy_frame):
    from protocol_routing.oracle import oracle_label_series

    frame = toy_frame.copy()
    frame["oracle_label"] = oracle_label_series(frame)
    per_example = realized_outcomes(
        frame, [Protocol.NONE.value] * len(frame), success_columns=CORRECTNESS_COLUMNS
    )
    assert per_example["success"].sum() == 0.0


def test_oracle_policy_attains_the_oracle_coverage(toy_frame):
    """Following the oracle label must solve exactly the solvable problems."""
    from protocol_routing.oracle import oracle_label_series

    frame = toy_frame.copy()
    frame["oracle_label"] = oracle_label_series(frame)
    per_example = realized_outcomes(
        frame, frame["oracle_label"].tolist(), success_columns=CORRECTNESS_COLUMNS
    )
    solvable = (frame["oracle_label"] != Protocol.NONE.value).sum()
    assert per_example["success"].sum() == solvable
    summary = summarize_routing(per_example)
    assert summary["mode_accuracy"] == 1.0


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('{"PROBABILITY": 85}', 85.0),
        ("PROBABILITY: 42", 42.0),
        ("probability : 7", 7.0),
        ("  93  ", 93.0),
        ("I think about 60 percent", 60.0),
        ("", None),
        ("no number here", None),
        (None, None),
        ('{"PROBABILITY": 150}', 100.0),   # clipped
        ('{"PROBABILITY": -5}', 0.0),      # JSON gives -5; clipped up into range
    ],
)
def test_confidence_parsing_is_deterministic(raw, expected):
    assert parse_confidence(raw) == expected
    assert parse_confidence(raw) == parse_confidence(raw)


def test_gate_is_exactly_the_seventy_threshold():
    assert SELF_CONFIDENCE_GATE_THRESHOLD == 70.0
    assert self_confidence_gate(70.0) == Protocol.BASELINE.value
    assert self_confidence_gate(69.9) == Protocol.SINGLE.value
    assert self_confidence_gate(100.0) == Protocol.BASELINE.value
    assert self_confidence_gate(0.0) == Protocol.SINGLE.value


def test_gate_escalates_on_unparseable_confidence():
    """Escalating spends more, never less: the conservative direction."""
    assert self_confidence_gate(None) == Protocol.SINGLE.value
    assert self_confidence_gate(float("nan")) == Protocol.SINGLE.value


def test_gate_never_routes_to_per_or_broadcast():
    outputs = {self_confidence_gate(float(c)) for c in range(0, 101)}
    assert outputs == {Protocol.BASELINE.value, Protocol.SINGLE.value}


def test_two_threshold_cascade_is_a_separate_three_way_policy():
    assert two_threshold_cascade(90.0, "broadcast") == Protocol.BASELINE.value
    assert two_threshold_cascade(40.0, "broadcast") == Protocol.SINGLE.value
    assert two_threshold_cascade(5.0, "broadcast") == "broadcast"
    assert two_threshold_cascade(None, "broadcast") == "broadcast"


def test_confidence_report_on_the_fixture(toy_frame):
    confidence = parse_confidence_series(toy_frame["confidence_raw"].tolist())
    correct = toy_frame["baseline_correct"].astype(float).to_numpy()
    report = confidence_report(confidence.to_numpy(), correct)
    assert report["parse_rate"] == 1.0
    assert 0.0 <= report["failure_auroc"] <= 1.0
    assert 0.0 <= report["ece"] <= 1.0
    assert 0.0 <= report["brier"] <= 1.0


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def test_bootstrap_is_seeded_and_reproducible():
    values = pd.Series([0.0, 1.0] * 30)
    a = percentile_bootstrap(values, lambda s: float(pd.Series(s).mean()), n_resamples=200, seed=5)
    b = percentile_bootstrap(values, lambda s: float(pd.Series(s).mean()), n_resamples=200, seed=5)
    assert a == b


def test_bootstrap_different_seeds_differ():
    values = pd.Series([0.0, 1.0] * 30)
    a = percentile_bootstrap(values, lambda s: float(pd.Series(s).mean()), n_resamples=200, seed=1)
    b = percentile_bootstrap(values, lambda s: float(pd.Series(s).mean()), n_resamples=200, seed=2)
    assert a[0] == b[0]          # point estimate is not resampled
    assert (a[1], a[2]) != (b[1], b[2])


def test_bootstrap_interval_brackets_the_point_estimate():
    values = pd.Series([0.0] * 20 + [1.0] * 30)
    point, low, high = percentile_bootstrap(
        values, lambda s: float(pd.Series(s).mean()), n_resamples=500, seed=11
    )
    assert low <= point <= high


def test_paired_difference_requires_aligned_arms():
    with pytest.raises(ValueError):
        paired_difference([1.0, 0.0], [1.0])


def test_paired_difference_of_identical_arms_is_exactly_zero():
    """An A/A comparison must give a zero point estimate and a zero-width CI."""
    arm = [1.0, 0.0, 1.0, 1.0, 0.0] * 6
    point, low, high = paired_difference(arm, arm, n_resamples=200, seed=3)
    assert point == 0.0
    assert low == 0.0 and high == 0.0


def test_bootstrap_metrics_resamples_rows_jointly(toy_frame):
    from protocol_routing.oracle import oracle_label_series

    frame = toy_frame.copy()
    frame["oracle_label"] = oracle_label_series(frame)
    per_example = realized_outcomes(
        frame, frame["oracle_label"].tolist(), success_columns=CORRECTNESS_COLUMNS
    )
    intervals = bootstrap_metrics(per_example, summarize_routing, n_resamples=100, seed=13)
    assert "solve_rate" in intervals
    point, low, high = intervals["solve_rate"]
    assert low <= point <= high


def test_make_splits_derives_the_label_when_absent(toy_frame):
    """The fixture has no oracle_label column; stratification must still work."""
    assert "oracle_label" not in toy_frame.columns
    splits = make_splits(toy_frame, config=SplitConfig.primary())
    assert set(splits) <= {"train", "dev", "test"}


def test_make_splits_reports_a_frame_it_cannot_label():
    """No label and no outcome columns must raise, not fall back to unstratified."""
    frame = pd.DataFrame({"problem_uid": ["a", "b", "c"], "difficulty": [1.0, 2.0, 3.0]})
    with pytest.raises(KeyError):
        make_splits(frame, config=SplitConfig.primary())


def test_duplicate_ids_break_a_reproducible_split(toy_frame):
    doubled = pd.concat([toy_frame, toy_frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError):
        make_splits(doubled, config=SplitConfig.primary())
