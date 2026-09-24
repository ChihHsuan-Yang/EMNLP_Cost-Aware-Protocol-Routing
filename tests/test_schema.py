"""Schema validation of matched-outcome tables, and of the shipped configs.

A schema check is only worth having if it rejects things. Each validation test
here corrupts a copy of the fixture in the specific shape of the defect it
claims to catch.
"""

from __future__ import annotations

import pandas as pd
import pytest

from protocol_routing import io
from protocol_routing.matched import (
    REQUIRED_COLUMNS,
    MatchedTableError,
    coverage_table,
    load_matched_dir,
    load_matched_table,
    oracle_distribution_table,
    validate_matched_frame,
)
from protocol_routing.protocols import (
    ORACLE_ORDER,
    PROTOCOL_COLORS,
    PROTOCOL_DISPLAY,
    PROTOCOL_ORDER,
    Protocol,
    canonical_protocol,
)


def test_fixture_passes_validation(toy_frame):
    validate_matched_frame(toy_frame, source="fixture")


@pytest.mark.parametrize("column", list(REQUIRED_COLUMNS))
def test_dropping_any_required_column_is_rejected(toy_frame, column):
    with pytest.raises(MatchedTableError) as excinfo:
        validate_matched_frame(toy_frame.drop(columns=[column]), source="corrupt")
    assert column in str(excinfo.value)


def test_duplicate_problem_uid_is_rejected(toy_frame):
    """The matched design requires one row per problem; duplicates double-count."""
    doubled = pd.concat([toy_frame, toy_frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(MatchedTableError) as excinfo:
        validate_matched_frame(doubled, source="corrupt")
    assert "unique" in str(excinfo.value)


def test_non_binary_outcome_is_rejected(toy_frame):
    corrupt = toy_frame.copy()
    corrupt.loc[0, "per_correct"] = 2
    with pytest.raises(MatchedTableError):
        validate_matched_frame(corrupt, source="corrupt")


def test_mixed_settings_in_one_file_is_rejected(toy_frame):
    corrupt = toy_frame.copy()
    corrupt.loc[0, "setting"] = "some_other_setting"
    with pytest.raises(MatchedTableError) as excinfo:
        validate_matched_frame(corrupt, source="corrupt")
    assert "one setting" in str(excinfo.value)


def test_empty_table_is_rejected(toy_frame):
    with pytest.raises(MatchedTableError):
        validate_matched_frame(toy_frame.iloc[0:0], source="corrupt")


def test_load_matched_table_attaches_recomputed_oracle(fixture_dir):
    table = load_matched_table(fixture_dir / "toybench__text_only__toy_solver_a.csv")
    assert "oracle_label" in table.frame.columns
    assert table.n == 24
    assert set(table.frame["oracle_label"]).issubset({p.value for p in PROTOCOL_ORDER})


def test_load_matched_dir_non_strict_accepts_the_toy_settings(fixture_dir):
    """strict=True would reject these: they are not paper settings, by design."""
    tables = load_matched_dir(fixture_dir, strict=False)
    assert len(tables) == 2
    with pytest.raises(MatchedTableError):
        load_matched_dir(fixture_dir, strict=True)


def test_aggregates_have_the_camera_ready_column_names(fixture_dir):
    tables = load_matched_dir(fixture_dir, strict=False)
    coverage = coverage_table(tables)
    distribution = oracle_distribution_table(tables)
    assert list(coverage.columns) == [
        "solver", "setting", "n",
        "baseline_pct", "single_pct", "per_pct", "broadcast_pct", "oracle_pct",
    ]
    assert list(distribution.columns) == [
        "solver", "setting", "n",
        "baseline_pct", "single_pct", "per_pct", "broadcast_pct", "none_pct",
    ]


def test_oracle_distribution_shares_sum_to_one_hundred(fixture_dir):
    distribution = oracle_distribution_table(tables := load_matched_dir(fixture_dir, strict=False))
    assert len(tables) == 2
    share_columns = ["baseline_pct", "single_pct", "per_pct", "broadcast_pct", "none_pct"]
    for _, row in distribution.iterrows():
        assert abs(sum(row[c] for c in share_columns) - 100.0) < 0.05


def test_coverage_is_monotone_in_the_oracle(fixture_dir):
    """Oracle coverage cannot be below any single protocol's solve rate."""
    coverage = coverage_table(load_matched_dir(fixture_dir, strict=False))
    for _, row in coverage.iterrows():
        for column in ("baseline_pct", "single_pct", "per_pct", "broadcast_pct"):
            assert row["oracle_pct"] >= row[column] - 1e-9


# ---------------------------------------------------------------------------
# Protocol registry
# ---------------------------------------------------------------------------


def test_every_protocol_has_a_display_name_and_colour():
    for protocol in PROTOCOL_ORDER:
        assert PROTOCOL_DISPLAY[protocol.value]
        assert PROTOCOL_COLORS[protocol.value].startswith("#")


def test_protocol_colours_are_the_paper_palette():
    assert PROTOCOL_COLORS == {
        "baseline_llm": "#4C78A8",
        "single_agent": "#F58518",
        "planner_executor_reviewer": "#54A24B",
        "broadcast": "#B279A2",
        "none": "#9C9C9C",
    }


def test_colours_are_distinct():
    assert len(set(PROTOCOL_COLORS.values())) == len(PROTOCOL_COLORS)


@pytest.mark.parametrize(
    "spelling,expected",
    [
        ("per", Protocol.PER),
        ("planner_executor_reviewer", Protocol.PER),
        ("baseline", Protocol.BASELINE),
        ("baseline_llm", Protocol.BASELINE),
        ("unsolved", Protocol.NONE),
        ("none", Protocol.NONE),
        ("BROADCAST", Protocol.BROADCAST),
    ],
)
def test_protocol_aliases_resolve(spelling, expected):
    assert canonical_protocol(spelling) is expected


def test_unknown_protocol_name_raises_rather_than_passing_through():
    """A typo must not quietly become a sixth class."""
    with pytest.raises(ValueError):
        canonical_protocol("brodcast")


def test_none_is_not_in_the_oracle_execution_order():
    """`none` is a router ACTION, not a fifth execution."""
    assert Protocol.NONE not in ORACLE_ORDER
    assert Protocol.NONE in PROTOCOL_ORDER
    assert len(ORACLE_ORDER) == 4


# ---------------------------------------------------------------------------
# Shipped configs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["baseline", "single", "per", "broadcast"])
def test_protocol_config_is_loadable_and_documents_the_required_fields(repo_root, name):
    config = io.read_yaml(repo_root / "configs" / "protocols" / f"{name}.yaml")
    for field in (
        "protocol_id",
        "display_name",
        "roles",
        "turns",
        "stopping_rule",
        "retry_policy",
        "context_and_memory",
        "final_answer_selection",
        "evaluator_invocation",
        "token_accounting",
    ):
        assert field in config, f"{name}.yaml is missing required section {field!r}"
    assert canonical_protocol(config["protocol_id"])


def test_all_four_protocol_configs_exist_and_are_distinct(repo_root):
    """The four execution configs must name the four protocols, once each.

    Config files use the paper's short display spellings ("per"); the released
    per-problem tables use the longer research spellings
    ("planner_executor_reviewer").  Both are legitimate, so resolve through
    ``canonical_protocol`` rather than comparing raw strings -- otherwise this
    test enforces one arbitrary vocabulary over another and breaks whenever a
    config is written in the other one.
    """
    resolved = set()
    for name in ("baseline", "single", "per", "broadcast"):
        raw = io.read_yaml(
            repo_root / "configs" / "protocols" / f"{name}.yaml"
        )["protocol_id"]
        resolved.add(canonical_protocol(raw))
    assert resolved == set(ORACLE_ORDER)


def test_models_and_router_configs_load(repo_root):
    models = io.read_yaml(repo_root / "configs" / "models.yaml")
    assert "solvers" in models and "evaluator" in models
    for name in ("primary_split", "six_setting"):
        routers = io.read_yaml(repo_root / "configs" / "routers" / f"{name}.yaml")
        assert "split" in routers and "routers" in routers
