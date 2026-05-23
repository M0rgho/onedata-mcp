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


def test_flush_forge_trace_summary_csv_one_file_per_test_directory(tmp_path: Path) -> None:
    import csv

    from forge_logging import (
        flush_forge_trace_summary_csvs,
        register_forge_trace_for_summary,
    )

    run_dir = tmp_path / "logs_run"
    run_dir.mkdir()
    t1 = run_dir / "forge_trace_one_1.json"
    t2 = run_dir / "forge_trace_two_2.json"
    minimal: dict = {
        "schema_version": "plgrid-forge-e2e-trace/1",
        "scenario": {
            "name": "scenario-a",
            "tool_context_mode": "full",
            "temperature": 0.0,
            "max_tokens_cap": 100,
            "max_tool_rounds_cap": 3,
        },
        "effective_model_id": "m1",
        "forge_base_url_host_only": "https://example.invalid",
        "mcp_tools_context_stats": {
            "tool_count": 2,
            "tool_names": ["a", "b"],
            "tools_definitions_json_utf8_bytes": 10,
            "tools_definitions_json_char_len": 10,
            "tools_definitions_approx_tokens_heuristic": 3,
        },
        "completion_rounds": [
            {"response": {"usage": {"used_plgrid_credits": 0.5}}},
        ],
        "final_finish_reason": "stop",
        "metrics_echo": {
            "tools_in_context_count": 2,
            "tool_calls_by_model": 1,
            "tool_calls_total": 1,
            "tool_calls_successful": 1,
            "estimated_prompt_peak_utf8_bytes": 999,
            "forge_usage_totals": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        },
        "test_result": "success",
        "pytest_nodeid": "test/e2e/foo.py::test_one",
    }
    t1.write_text(json.dumps(minimal, indent=2), encoding="utf-8")
    minimal_b = json.loads(json.dumps(minimal))
    minimal_b["scenario"]["name"] = "scenario-b"
    minimal_b["test_result"] = "failure"
    minimal_b["pytest_nodeid"] = "test/unit/api/bar.py::test_two"
    t2.write_text(json.dumps(minimal_b, indent=2), encoding="utf-8")

    register_forge_trace_for_summary(t1, "test/e2e/foo.py::test_one")
    register_forge_trace_for_summary(t2, "test/unit/api/bar.py::test_two")
    flush_forge_trace_summary_csvs()

    csv_e2e = run_dir / "forge_traces_summary__test__e2e.csv"
    csv_unit = run_dir / "forge_traces_summary__test__unit__api.csv"
    assert csv_e2e.is_file()
    assert csv_unit.is_file()

    with csv_e2e.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["scenario_name"] == "scenario-a"
    assert rows[0]["test_passed"] == "True"
    assert rows[0]["pytest_test_directory"] == "test/e2e"
    assert rows[0]["trace_json_path"] == str(t1.resolve())
    assert rows[0]["used_plgrid_credits_sum"] == "0.5"

    with csv_unit.open(encoding="utf-8") as fh:
        rows_u = list(csv.DictReader(fh))
    assert len(rows_u) == 1
    assert rows_u[0]["scenario_name"] == "scenario-b"
    assert rows_u[0]["test_passed"] == "False"
    assert rows_u[0]["pytest_test_directory"] == "test/unit/api"


def test_write_forge_trace_summary_csvs_for_run_dir_scans_glob(tmp_path: Path) -> None:
    from forge_logging import write_forge_trace_summary_csvs_for_run_dir

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "forge_trace_a.json").write_text(
        json.dumps(
            {
                "schema_version": "plgrid-forge-e2e-trace/1",
                "scenario": {"name": "n"},
                "mcp_tools_context_stats": {},
                "completion_rounds": [],
                "metrics_echo": {"forge_usage_totals": {}},
            }
        ),
        encoding="utf-8",
    )
    write_forge_trace_summary_csvs_for_run_dir(run_dir)
    csv_unknown = run_dir / "forge_traces_summary___unknown.csv"
    assert csv_unknown.is_file()


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
