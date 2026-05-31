from __future__ import annotations

import copy
import json
import time
from contextlib import nullcontext
from typing import Any

from assertions_lib import summarize_failed_tool_calls
from e2e_types import E2EScenario, ForgeRunResult, RunMetrics, ToolCallMetric
from fastmcp import FastMCP
from forge_logging import (
    chat_messages_stats,
    mcp_tools_context_stats,
    register_forge_trace_for_summary,
    serialize_openai_completion,
    trace_output_path,
    trace_uses_explicit_file,
    usage_from_chat_completion,
    write_forge_trace,
)
from forge_pytest_integration import LAST_FORGE_RUN
from mcp_openai_bridge import build_forge_system_message, build_openai_tools_full
from mcp_write_guard import (
    current_allowed_write_tools,
    guarded_dispatch_mcp,
    mcp_write_guard,
    merge_write_policy_with_scenario,
)
from openai import AsyncOpenAI


async def _dispatch_mcp(
    app: FastMCP, tool_name: str, arguments: dict[str, Any]
) -> tuple[str, bool, str | None]:
    return await guarded_dispatch_mcp(app, tool_name, arguments)


def _serialize_tool_calls_for_history(tool_calls: list[Any]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for tc in tool_calls:
        serialized.append(
            {
                "id": tc.id,
                "type": getattr(tc, "type", "function") or "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments or "{}",
                },
            }
        )
    return serialized


def _acc_usage_totals(
    accumulator: dict[str, int],
    incremental: dict[str, int],
) -> None:
    for key, value in incremental.items():
        accumulator[key] = accumulator.get(key, 0) + value


async def run_forge_scenario(
    *,
    scenario: E2EScenario,
    mcp_app: FastMCP,
    forge_api_key: str,
    forge_base_url: str,
    model: str,
    pytest_request: Any = None,
    isolated_space_id: str | None = None,
    isolated_space_name: str | None = None,
) -> ForgeRunResult:
    openai_tools, context_names = await build_openai_tools_full(mcp_app)
    openai_names = frozenset(t["function"]["name"] for t in openai_tools)
    if openai_names != context_names:
        missing = context_names - openai_names
        if missing:
            raise RuntimeError(f"Missing tools in OpenAI export: {sorted(missing)}")

    metrics = RunMetrics(tools_in_context_count=len(openai_tools), tool_call_count=0)
    tools_ctx = mcp_tools_context_stats(openai_tools)
    metrics.mcp_tools_context_stats = tools_ctx
    tools_def_bytes = tools_ctx["tools_definitions_json_utf8_bytes"]
    raw_names: list[str] = []

    system, mcp_server_instructions = build_forge_system_message(mcp_app, scenario.system_prompt)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": scenario.user_prompt},
    ]

    client = AsyncOpenAI(api_key=forge_api_key, base_url=forge_base_url)
    model_name = scenario.model or model

    trace_path_obj = trace_output_path(scenario.name)
    rounds_log: list[dict[str, Any]] = []
    usage_totals: dict[str, int] = {}

    loop_t0 = time.perf_counter()
    final_text: str | None = None
    finish_reason: str | None = None
    peak_chat_bytes = 0
    peak_combined_est = 0

    forge_write_policy = merge_write_policy_with_scenario(
        current_allowed_write_tools(),
        scenario.allowed_write_tools,
    )
    guard_ctx = (
        mcp_write_guard(forge_write_policy) if forge_write_policy is not None else nullcontext()
    )

    with guard_ctx:
        for round_ix in range(scenario.max_tool_rounds):
            messages_snapshot_pre = copy.deepcopy(messages)
            msg_stats_before = chat_messages_stats(messages_snapshot_pre)
            combined_est = msg_stats_before["messages_json_utf8_bytes"] + tools_def_bytes
            peak_chat_bytes = max(peak_chat_bytes, msg_stats_before["messages_json_utf8_bytes"])
            peak_combined_est = max(peak_combined_est, combined_est)

            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=openai_tools,
                tool_choice="auto",
                temperature=scenario.temperature,
                max_tokens=scenario.max_tokens,
            )

            usage_piece = usage_from_chat_completion(response)
            if usage_piece:
                _acc_usage_totals(usage_totals, usage_piece)

            response_dict = serialize_openai_completion(response)
            rounds_log.append(
                {
                    "round_index": round_ix,
                    "request": {
                        "model": model_name,
                        "temperature": scenario.temperature,
                        "max_tokens": scenario.max_tokens,
                        "tool_choice": "auto",
                        "messages_snapshot_pre_request": messages_snapshot_pre,
                        "chat_context_before_request_stats": msg_stats_before,
                        "estimated_combined_prompt_footprint_utf8_bytes": combined_est,
                    },
                    "response": response_dict,
                    "usage_derived_incremental": usage_piece,
                }
            )

            metrics.forge_token_usage_rounds.append({"round_index": round_ix, **usage_piece})

            choice = response.choices[0]
            finish_reason = choice.finish_reason
            msg = choice.message

            tool_calls = list(msg.tool_calls or [])

            assistant_entry: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content or None,
            }
            if tool_calls:
                assistant_entry["tool_calls"] = _serialize_tool_calls_for_history(tool_calls)
            messages.append(assistant_entry)

            if not tool_calls:
                final_text = msg.content
                break

            for tc in tool_calls:
                name = tc.function.name
                raw_names.append(name)
                try:
                    arguments = json.loads(tc.function.arguments or "{}")
                    if not isinstance(arguments, dict):
                        arguments = {}
                except json.JSONDecodeError:
                    arguments = {}

                tc_t0 = time.perf_counter()
                content, ok, err = await _dispatch_mcp(mcp_app, name, arguments)
                duration_ms = (time.perf_counter() - tc_t0) * 1000.0

                metrics.tool_calls.append(
                    ToolCallMetric(
                        tool_name=name,
                        duration_ms=duration_ms,
                        ok=ok,
                        error=err,
                        arguments=arguments,
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": content,
                    }
                )
        else:
            final_text = None

    metrics.chat_context_peak_stats = {
        "messages_only_peak_utf8_bytes": peak_chat_bytes,
        "tools_definitions_repeat_each_round_utf8_bytes": tools_def_bytes,
        **tools_ctx,
    }
    metrics.forge_token_usage_totals = usage_totals
    metrics.estimated_prompt_footprint_utf8_peak_bytes = peak_combined_est

    metrics.forge_loop_wall_time_ms = (time.perf_counter() - loop_t0) * 1000.0
    metrics.recompute_tool_sets(
        scenario.required_tools,
        optional=scenario.optional_tools,
        forbidden=scenario.forbidden_tools,
    )

    peak_footprint = metrics.estimated_prompt_footprint_utf8_peak_bytes
    mcp_tool_wall_ms_sum = sum(tc.duration_ms for tc in metrics.tool_calls)
    envelope: dict[str, Any] = {
        "schema_version": "plgrid-forge-e2e-trace/1",
        "scenario": {
            "name": scenario.name,
            "dispatch_mode": "mcp",
            "temperature": scenario.temperature,
            "max_tokens_cap": scenario.max_tokens,
            "max_tool_rounds_cap": scenario.max_tool_rounds,
            "required_tools_sorted": sorted(scenario.required_tools),
            "optional_tools_sorted": sorted(scenario.optional_tools),
            "forbidden_tools_sorted": sorted(scenario.forbidden_tools),
            "tools_in_context_sorted": sorted(context_names),
            "user_prompt": scenario.user_prompt,
            "scenario_system_prompt": scenario.system_prompt,
            "mcp_server_instructions": mcp_server_instructions,
            "system_prompt_effective": system,
        },
        "isolated_space_id": isolated_space_id,
        "isolated_space_name": isolated_space_name,
        "forge_base_url_host_only": forge_base_url,
        "effective_model_id": model_name,
        "mcp_tools_definitions_once": openai_tools,
        "mcp_tools_context_stats": tools_ctx,
        "completion_rounds": rounds_log,
        "final_finish_reason": finish_reason,
        "final_assistant_text": final_text,
        "metrics_echo": {
            "tools_in_context_count": metrics.tools_in_context_count,
            "tool_calls_by_model": metrics.tool_call_count,
            **metrics.tool_calls_echo_counts(),
            "estimated_prompt_peak_utf8_bytes": peak_footprint,
            "forge_usage_totals": metrics.forge_token_usage_totals,
            "forge_loop_wall_time_ms": metrics.forge_loop_wall_time_ms,
            "mcp_tool_calls_wall_time_ms_sum": mcp_tool_wall_ms_sum,
            "forbidden_tools_called_sorted": sorted(metrics.forbidden_tools_called),
            "failed_tool_calls": summarize_failed_tool_calls(tool_calls=metrics.tool_calls),
        },
        "tool_calls_detail": [
            {
                "tool_name": c.tool_name,
                "ok": c.ok,
                "duration_ms": c.duration_ms,
                "arguments": c.arguments,
                "error": c.error,
            }
            for c in metrics.tool_calls
        ],
        "test_result": None,
        "pytest_nodeid": pytest_request.node.nodeid if pytest_request is not None else None,
    }
    append = trace_uses_explicit_file()
    write_forge_trace(trace_path_obj, envelope, append=append)
    if not append:
        register_forge_trace_for_summary(
            trace_path_obj,
            pytest_request.node.nodeid if pytest_request is not None else None,
        )

    result_obj = ForgeRunResult(
        scenario=scenario,
        dispatch_mode="mcp",
        metrics=metrics,
        final_assistant_text=final_text,
        finish_reason=finish_reason,
        raw_tool_names_in_order=raw_names,
        trace_path_written=trace_path_obj,
    )
    if pytest_request is not None:
        pytest_request.node.stash[LAST_FORGE_RUN] = result_obj
    return result_obj
