"""File tracing for PLGrid Forge (OpenAI-compatible) chat rounds."""

from __future__ import annotations

import csv
import datetime
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

# First trace under each resolved logs base picks the run folder name for that base (UTC).
_RUN_SUBDIRS_BY_BASE: dict[str, str] = {}

# (trace path, pytest node id) pairs for post-run CSV summaries (single-file traces only).
_SESSION_SUMMARY_TRACES: list[tuple[Path, str | None]] = []


def _run_subdirectory_for_base(base: Path) -> str:
    key = str(base.resolve())
    cached = _RUN_SUBDIRS_BY_BASE.get(key)
    if cached is not None:
        return cached
    sub = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d_%H-%M-%S")
    _RUN_SUBDIRS_BY_BASE[key] = sub
    return sub


def trace_output_path(scenario_slug: str) -> Path:
    """
    Resolve trace output path.

    PLGRID_E2E_TRACE_FILE: append one pretty-printed JSON object per scenario run.

    Otherwise: write one file per scenario run under PLGRID_E2E_TRACE_DIR (default ``logs``,
    relative to cwd). Traces share one subdirectory per pytest process and trace base directory,
    named UTC ``YYYY-MM-DD_HH-MM-SS`` fixed on the **first** trace in that bucket:
    ``<dir>/<YYYY-MM-DD_HH-MM-SS>/forge_trace_<slug>_<utc>_<pid>.json``.
    """

    explicit = os.getenv("PLGRID_E2E_TRACE_FILE", "").strip()
    if explicit:
        file_path = Path(explicit).expanduser()
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        return file_path.resolve()

    trace_dir = (os.getenv("PLGRID_E2E_TRACE_DIR") or "logs").strip()
    if not trace_dir:
        trace_dir = "logs"
    base_path = Path(trace_dir).expanduser()
    if not base_path.is_absolute():
        base_path = Path.cwd() / base_path
    base = base_path.resolve()
    run_dir = _run_subdirectory_for_base(base)
    safe_slug = re.sub(r"[^\w\-]+", "_", scenario_slug)[:80] or "scenario"
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    pid = os.getpid()
    return base / run_dir / f"forge_trace_{safe_slug}_{ts}_{pid}.json"


def trace_uses_explicit_file() -> bool:
    return bool(os.getenv("PLGRID_E2E_TRACE_FILE", "").strip())


def mcp_tools_context_stats(openai_tools: list[dict[str, Any]]) -> dict[str, Any]:
    """MCP tools as included on every Forge completion (excluding chat messages)."""

    raw = json.dumps(openai_tools, ensure_ascii=False, default=str)
    utf8_bytes = len(raw.encode("utf-8"))
    return {
        "tool_count": len(openai_tools),
        "tool_names": sorted(entry.get("function", {}).get("name", "?") for entry in openai_tools),
        "tools_definitions_json_utf8_bytes": utf8_bytes,
        "tools_definitions_json_char_len": len(raw),
        "tools_definitions_approx_tokens_heuristic": max(1, len(raw) // 4),
    }


def serialize_openai_completion(response: Any) -> dict[str, Any]:
    try:
        if hasattr(response, "model_dump"):
            return response.model_dump(mode="json")
        return json.loads(response.model_dump_json())
    except Exception:
        return {"repr": repr(response)}


def extract_usage_counts(response_obj: dict[str, Any]) -> dict[str, int]:
    usage = response_obj.get("usage")
    if not isinstance(usage, dict):
        return {}
    out: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
            out[key] = value
    return out


def usage_from_chat_completion(response: Any) -> dict[str, int]:
    """Lightweight token stats without serializing the whole completion object."""

    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    out: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = getattr(usage, key, None)
        if isinstance(value, int):
            out[key] = value
    return out


def chat_messages_stats(messages: list[dict[str, Any]]) -> dict[str, Any]:
    raw = json.dumps(messages, ensure_ascii=False, default=str)
    utf8 = len(raw.encode("utf-8"))
    return {
        "messages_json_utf8_bytes": utf8,
        "messages_json_char_len": len(raw),
        "messages_approx_tokens_heuristic": max(1, len(raw) // 4),
        "conversation_turn_roles": [m.get("role") for m in messages],
    }


def write_forge_trace(path: Path, envelope: dict[str, Any], *, append: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(envelope, ensure_ascii=False, indent=2, default=str)
    block = payload + "\n"
    if append:
        existed = path.exists() and path.stat().st_size > 0
        with path.open("a", encoding="utf-8") as fh:
            if existed:
                fh.write("\n")
            fh.write(block)
    else:
        path.write_text(block, encoding="utf-8")


def register_forge_trace_for_summary(path: Path, pytest_nodeid: str | None) -> None:
    """Record a trace path for ``flush_forge_trace_summary_csvs`` (pytest session end)."""

    _SESSION_SUMMARY_TRACES.append((path.resolve(), pytest_nodeid))


def _test_directory_from_nodeid(pytest_nodeid: str | None) -> str:
    if not pytest_nodeid:
        return "_unknown"
    file_part = pytest_nodeid.split("::", 1)[0]
    parent = Path(file_part).parent.as_posix()
    return parent if parent != "." else "_unknown"


def _summary_csv_basename_for_test_dir(test_directory: str) -> str:
    safe = re.sub(r"[^\w\-]+", "_", test_directory.replace("/", "__"))
    return f"forge_traces_summary__{safe or 'unknown'}.csv"


def _used_plgrid_credits_sum(completion_rounds: Any) -> float | None:
    if not isinstance(completion_rounds, list):
        return None
    total = 0.0
    any_found = False
    for rnd in completion_rounds:
        if not isinstance(rnd, dict):
            continue
        usage = rnd.get("response", {})
        usage = usage.get("usage") if isinstance(usage, dict) else None
        if not isinstance(usage, dict):
            continue
        v = usage.get("used_plgrid_credits")
        if isinstance(v, (int, float)):
            total += float(v)
            any_found = True
    return total if any_found else None


def _flatten_trace_summary_row(
    trace_path: Path,
    data: dict[str, Any],
    pytest_nodeid: str | None,
) -> dict[str, Any]:
    scenario = data.get("scenario")
    scenario = scenario if isinstance(scenario, dict) else {}
    metrics_echo = data.get("metrics_echo")
    metrics_echo = metrics_echo if isinstance(metrics_echo, dict) else {}
    forge_usage = metrics_echo.get("forge_usage_totals")
    forge_usage = forge_usage if isinstance(forge_usage, dict) else {}
    ctx = data.get("mcp_tools_context_stats")
    ctx = ctx if isinstance(ctx, dict) else {}
    rounds = data.get("completion_rounds")
    rounds_count = len(rounds) if isinstance(rounds, list) else 0

    test_result = data.get("test_result")
    if test_result == "success":
        test_passed = True
    elif test_result == "failure":
        test_passed = False
    else:
        test_passed = ""

    nodeid = data.get("pytest_nodeid") or pytest_nodeid
    tdir = _test_directory_from_nodeid(str(nodeid) if nodeid else None)
    file_part = str(nodeid).split("::", 1)[0] if nodeid else ""

    tool_names = ctx.get("tool_names")
    ctx_tool_names_json = (
        json.dumps(tool_names, ensure_ascii=False, sort_keys=True)
        if isinstance(tool_names, list)
        else ""
    )

    credits = _used_plgrid_credits_sum(rounds)

    row: dict[str, Any] = {
        "trace_json_path": str(trace_path.resolve()),
        "pytest_nodeid": nodeid or "",
        "pytest_test_file": file_part,
        "pytest_test_directory": tdir,
        "schema_version": data.get("schema_version", ""),
        "scenario_name": scenario.get("name", ""),
        "test_result": test_result if test_result is not None else "",
        "test_passed": test_passed,
        "final_finish_reason": data.get("final_finish_reason", ""),
        "effective_model_id": data.get("effective_model_id", ""),
        "forge_base_url_host_only": data.get("forge_base_url_host_only", ""),
        "scenario_temperature": scenario.get("temperature", ""),
        "scenario_max_tokens_cap": scenario.get("max_tokens_cap", ""),
        "scenario_max_tool_rounds_cap": scenario.get("max_tool_rounds_cap", ""),
        "completion_rounds_count": rounds_count,
        "metrics_echo_tools_in_context_count": metrics_echo.get("tools_in_context_count", ""),
        "metrics_echo_tool_calls_by_model": metrics_echo.get("tool_calls_by_model", ""),
        "metrics_echo_tool_calls_total": metrics_echo.get("tool_calls_total", ""),
        "metrics_echo_tool_calls_successful": metrics_echo.get("tool_calls_successful", ""),
        "metrics_echo_estimated_prompt_peak_utf8_bytes": metrics_echo.get(
            "estimated_prompt_peak_utf8_bytes", ""
        ),
        "metrics_echo_forge_usage_prompt_tokens": forge_usage.get("prompt_tokens", ""),
        "metrics_echo_forge_usage_completion_tokens": forge_usage.get("completion_tokens", ""),
        "metrics_echo_forge_usage_total_tokens": forge_usage.get("total_tokens", ""),
        "metrics_echo_forge_loop_wall_time_ms": metrics_echo.get("forge_loop_wall_time_ms", ""),
        "metrics_echo_mcp_tool_calls_wall_time_ms_sum": metrics_echo.get(
            "mcp_tool_calls_wall_time_ms_sum", ""
        ),
        "mcp_ctx_tool_count": ctx.get("tool_count", ""),
        "mcp_ctx_tools_definitions_json_utf8_bytes": ctx.get(
            "tools_definitions_json_utf8_bytes", ""
        ),
        "mcp_ctx_tools_definitions_json_char_len": ctx.get("tools_definitions_json_char_len", ""),
        "mcp_ctx_tools_definitions_approx_tokens_heuristic": ctx.get(
            "tools_definitions_approx_tokens_heuristic", ""
        ),
        "mcp_ctx_tool_names_json": ctx_tool_names_json,
        "used_plgrid_credits_sum": "" if credits is None else credits,
    }
    return row


def _write_grouped_trace_summary_csvs(
    grouped: dict[tuple[str, Path], list[tuple[Path, str | None]]],
) -> None:
    for (test_directory, parent_dir), entries in grouped.items():
        rows: list[dict[str, Any]] = []
        for path, nodeid in entries:
            try:
                raw = path.read_text(encoding="utf-8").strip()
                blob = json.loads(raw)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(blob, dict):
                continue
            rows.append(_flatten_trace_summary_row(path, blob, nodeid))

        if not rows:
            continue
        fieldnames = sorted({k for r in rows for k in r})
        out = parent_dir / _summary_csv_basename_for_test_dir(test_directory)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)


def write_forge_trace_summary_csvs_for_run_dir(run_dir: Path) -> None:
    """Summarize ``forge_trace_*.json`` under ``run_dir`` into CSV files (offline backfill)."""

    grouped: dict[tuple[str, Path], list[tuple[Path, str | None]]] = defaultdict(list)
    for path in sorted(run_dir.glob("forge_trace_*.json")):
        nodeid: str | None = None
        try:
            blob = json.loads(path.read_text(encoding="utf-8").strip())
            if isinstance(blob, dict):
                raw_n = blob.get("pytest_nodeid")
                nodeid = str(raw_n) if raw_n else None
        except (OSError, json.JSONDecodeError):
            pass
        td = _test_directory_from_nodeid(nodeid)
        grouped[(td, path.parent)].append((path.resolve(), nodeid))
    _write_grouped_trace_summary_csvs(grouped)


def flush_forge_trace_summary_csvs() -> None:
    """Write one CSV per test directory under each trace run folder; clear the registry."""

    global _SESSION_SUMMARY_TRACES
    if not _SESSION_SUMMARY_TRACES:
        return
    grouped: dict[tuple[str, Path], list[tuple[Path, str | None]]] = defaultdict(list)
    for path, nodeid in _SESSION_SUMMARY_TRACES:
        td = _test_directory_from_nodeid(nodeid)
        grouped[(td, path.parent)].append((path, nodeid))

    _write_grouped_trace_summary_csvs(grouped)
    _SESSION_SUMMARY_TRACES.clear()


def patch_forge_trace_test_result(path: Path, *, passed: bool) -> None:
    """Rewrite trace JSON with test_result ("success" | "failure") for single-document files only.

    Multi-block append traces (explicit PLGRID_E2E_TRACE_FILE) are skipped.
    """

    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if not raw:
        return
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    if not isinstance(data, dict):
        return
    data.pop("pytest_passed", None)
    data["test_result"] = "success" if passed else "failure"
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
