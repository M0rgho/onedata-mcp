"""Unit tests for shared Forge assertion helpers."""

from __future__ import annotations

import pytest
from assertions_lib import (
    _text_contains_fragment,
    assert_final_answer_contains_all,
    assert_forge_scenario_outcome,
    assert_required_tools_and_optional_policy,
)
from e2e_types import E2EScenario, ForgeRunResult, RunMetrics, ToolCallMetric


def test_text_contains_fragment_ignores_comma_thousands() -> None:
    assert _text_contains_fragment("The total is 12,548 events.", "12548")


def test_assert_required_tools_any_of_group() -> None:
    scenario = E2EScenario(
        name="t",
        user_prompt="p",
        required_tools=frozenset({"query_harvester_index"}),
    )
    metrics = RunMetrics(
        tools_in_context_count=3,
        tool_call_count=2,
        tool_calls=[
            ToolCallMetric("query_harvester_index", 1.0, True),
            ToolCallMetric("get_file_id", 1.0, True),
        ],
    )
    metrics.recompute_tool_sets(scenario.required_tools)
    run = ForgeRunResult(
        scenario=scenario,
        dispatch_mode="mcp",
        metrics=metrics,
        final_assistant_text="ok",
        finish_reason="stop",
        raw_tool_names_in_order=["query_harvester_index", "get_file_id"],
    )
    assert_required_tools_and_optional_policy(
        run, any_of=(frozenset({"get_file_attributes", "list_files", "get_file_id"}),)
    )


def test_assert_required_tools_any_of_group_fails_when_missing() -> None:
    scenario = E2EScenario(
        name="t",
        user_prompt="p",
        required_tools=frozenset({"query_harvester_index"}),
    )
    metrics = RunMetrics(
        tools_in_context_count=1,
        tool_call_count=1,
        tool_calls=[ToolCallMetric("query_harvester_index", 1.0, True)],
    )
    metrics.recompute_tool_sets(scenario.required_tools)
    run = ForgeRunResult(
        scenario=scenario,
        dispatch_mode="mcp",
        metrics=metrics,
        final_assistant_text="ok",
        finish_reason="stop",
        raw_tool_names_in_order=["query_harvester_index"],
    )
    with pytest.raises(AssertionError, match="get_file_attributes"):
        assert_required_tools_and_optional_policy(
            run, any_of=(frozenset({"get_file_attributes", "list_files"}),)
        )


def test_assert_required_tools_relaxed_when_answer_fragments_match() -> None:
    scenario = E2EScenario(
        name="t",
        user_prompt="p",
        required_tools=frozenset({"grep_file_content"}),
    )
    metrics = RunMetrics(
        tools_in_context_count=2,
        tool_call_count=1,
        tool_calls=[ToolCallMetric("download_file", 1.0, True)],
    )
    metrics.recompute_tool_sets(scenario.required_tools)
    run = ForgeRunResult(
        scenario=scenario,
        dispatch_mode="mcp",
        metrics=metrics,
        final_assistant_text=(
            "https://openfoodfacts-images.s3.eu-west-3.amazonaws.com/data/401/235/911/4303/1.jpg"
        ),
        finish_reason="stop",
        raw_tool_names_in_order=["download_file"],
    )
    assert_forge_scenario_outcome(
        run,
        answer_fragments=(
            "openfoodfacts-images.s3.eu-west-3.amazonaws.com",
            "401/235/911/4303/1.jpg",
        ),
    )


def test_assert_final_answer_contains_all_accepts_comma_formatted_count() -> None:
    scenario = E2EScenario(
        name="t",
        user_prompt="p",
        required_tools=frozenset(),
    )
    run = ForgeRunResult(
        scenario=scenario,
        dispatch_mode="mcp",
        metrics=RunMetrics(0, 0),
        final_assistant_text="User dim12512a has 12,548 PushEvent records.",
        finish_reason="stop",
        raw_tool_names_in_order=[],
    )
    assert_final_answer_contains_all(run, ("12548", "dim12512a"))
