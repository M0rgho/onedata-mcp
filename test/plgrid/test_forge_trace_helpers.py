"""Small unit tests for trace helpers (no Forge / MCP network)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from e2e_types import RunMetrics, ToolCallMetric
from forge_logging import (
    chat_messages_stats,
    extract_usage_counts,
    mcp_tools_context_stats,
)


def test_mcp_tools_context_stats_measures_payload() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "alpha",
                "description": "d",
                "parameters": {"type": "object", "properties": {"x": {"type": "string"}}},
            },
        }
    ]
    stats = mcp_tools_context_stats(tools)
    assert stats["tool_count"] == 1
    assert "alpha" in stats["tool_names"]
    assert stats["tools_definitions_json_utf8_bytes"] > 20


def test_chat_messages_stats_and_usage_extract() -> None:
    msgs = [{"role": "user", "content": "hello"}]
    cs = chat_messages_stats(msgs)
    assert cs["messages_json_utf8_bytes"] >= 25
    blob = {"usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}
    usage = extract_usage_counts(blob)
    assert usage["total_tokens"] == 12


def test_trace_path_defaults_to_logs_dir(monkeypatch, tmp_path: Path) -> None:
    from forge_logging import trace_output_path

    monkeypatch.delenv("PLGRID_E2E_TRACE_FILE", raising=False)
    monkeypatch.delenv("PLGRID_E2E_TRACE_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    p = trace_output_path("scenario")
    assert p is not None
    assert p.parent.parent == tmp_path / "logs"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}", p.parent.name)
    assert p.name.startswith("forge_trace_")


def test_trace_path_dir_mode(monkeypatch, tmp_path: Path) -> None:
    from forge_logging import trace_output_path

    monkeypatch.delenv("PLGRID_E2E_TRACE_FILE", raising=False)
    monkeypatch.setenv("PLGRID_E2E_TRACE_DIR", str(tmp_path))
    p = trace_output_path("scenario?weird/")
    assert p is not None
    assert p.parent.parent.resolve() == tmp_path.resolve()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}", p.parent.name)
    assert p.name.startswith("forge_trace_")


def test_patch_forge_trace_test_result_rewrite(tmp_path: Path) -> None:
    from forge_logging import patch_forge_trace_test_result

    p = tmp_path / "t.json"
    p.write_text('{"schema_version": "plgrid-forge-e2e-trace/1"}', encoding="utf-8")
    patch_forge_trace_test_result(p, passed=True)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("test_result") == "success"
    patch_forge_trace_test_result(p, passed=False)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("test_result") == "failure"


def test_run_metrics_tool_calls_echo_counts() -> None:
    m = RunMetrics(
        tools_in_context_count=1,
        tool_call_count=0,
        tool_calls=[
            ToolCallMetric("a", 0.0, True),
            ToolCallMetric("b", 0.0, False),
            ToolCallMetric("c", 0.0, True),
        ],
    )
    m.recompute_tool_sets(frozenset())
    assert m.tool_calls_echo_counts() == {
        "tool_calls_total": 3,
        "tool_calls_successful": 2,
    }


def test_explicit_file_flag(monkeypatch) -> None:
    from forge_logging import trace_uses_explicit_file

    monkeypatch.delenv("PLGRID_E2E_TRACE_FILE", raising=False)
    assert trace_uses_explicit_file() is False
    monkeypatch.setenv("PLGRID_E2E_TRACE_FILE", "/tmp/x.json")
    assert trace_uses_explicit_file() is True
