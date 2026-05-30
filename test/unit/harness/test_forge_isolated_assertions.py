"""Unit tests for Forge isolated-space trace assertions."""

from __future__ import annotations

import pytest
from assertions_lib import (
    assert_forbidden_tools,
    assert_isolated_forge_trace,
    assert_tool_arguments_stay_in_isolated_space,
    summarize_failed_tool_calls,
)
from e2e_isolated_space import IsolatedE2ESpace
from e2e_types import E2EScenario, ForgeRunResult, RunMetrics, ToolCallMetric


def _space() -> IsolatedE2ESpace:
    return IsolatedE2ESpace(
        space_id="859a3016ba09be09f14f7d904c4cc7e6ch805d",
        space_name="mcp-e2e-read-state",
        provider_token="tok",
    )


def _run(
    *,
    tools: list[ToolCallMetric],
    forbidden: frozenset[str] = frozenset(),
    required_tools: frozenset[str] | None = None,
    final_text: str = "ok",
) -> ForgeRunResult:
    required = (
        required_tools if required_tools is not None else frozenset({"list_available_spaces"})
    )
    scenario = E2EScenario(
        name="t",
        user_prompt="p",
        required_tools=required,
        forbidden_tools=forbidden,
    )
    metrics = RunMetrics(tools_in_context_count=1, tool_call_count=len(tools), tool_calls=tools)
    metrics.recompute_tool_sets(scenario.required_tools, forbidden=scenario.forbidden_tools)
    return ForgeRunResult(
        scenario=scenario,
        dispatch_mode="mcp",
        metrics=metrics,
        final_assistant_text=final_text,
        finish_reason="stop",
        raw_tool_names_in_order=[t.tool_name for t in tools],
    )


def test_assert_isolated_forge_trace_allows_failed_retry() -> None:
    run = _run(
        required_tools=frozenset({"get_file_id", "get_file_attributes"}),
        tools=[
            ToolCallMetric("get_file_id", 1.0, True),
            ToolCallMetric(
                "get_file_attributes",
                1.0,
                False,
                error="attributes must be a list",
            ),
            ToolCallMetric("get_file_attributes", 1.0, True),
        ],
        final_text="file id and path retrieved",
    )
    assert_isolated_forge_trace(run)
    failed = summarize_failed_tool_calls(run)
    assert len(failed) == 1
    assert failed[0]["tool_name"] == "get_file_attributes"


def test_assert_isolated_forge_trace_requires_nonempty_final_answer() -> None:
    run = _run(tools=[ToolCallMetric("list_available_spaces", 1.0, True)], final_text="  ")
    with pytest.raises(AssertionError, match="non-empty final assistant"):
        assert_isolated_forge_trace(run)


def test_assert_isolated_forge_trace_requires_successful_required_tool() -> None:
    run = _run(
        required_tools=frozenset({"get_file_attributes"}),
        tools=[
            ToolCallMetric("get_file_attributes", 1.0, False, error="validation error"),
        ],
        final_text="here is the answer anyway",
    )
    with pytest.raises(AssertionError, match="never succeeded"):
        assert_isolated_forge_trace(run)


def test_assert_forbidden_tools_rejects_blocked_tool() -> None:
    run = _run(
        tools=[
            ToolCallMetric(
                tool_name="delete_file",
                duration_ms=1.0,
                ok=True,
                arguments={"path": "/mcp-e2e-read-state/x"},
            )
        ],
        forbidden=frozenset({"delete_file"}),
    )
    with pytest.raises(AssertionError, match="Forbidden tools"):
        assert_forbidden_tools(run)


def test_assert_tool_paths_reject_shared_tenant_name() -> None:
    run = _run(
        tools=[
            ToolCallMetric(
                tool_name="list_files",
                duration_ms=1.0,
                ok=True,
                arguments={"parent_id_or_path": "/krk-p"},
            )
        ],
    )
    with pytest.raises(AssertionError, match="shared tenant"):
        assert_tool_arguments_stay_in_isolated_space(run, _space())


def test_assert_tool_paths_allow_isolated_prefix() -> None:
    space = _space()
    run = _run(
        tools=[
            ToolCallMetric(
                tool_name="get_file_id",
                duration_ms=1.0,
                ok=True,
                arguments={"path": f"{space.root_path}/e2e-roundtrip/hello.txt"},
            )
        ],
    )
    assert_tool_arguments_stay_in_isolated_space(run, space)
