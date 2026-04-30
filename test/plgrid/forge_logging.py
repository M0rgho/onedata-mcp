"""File tracing for PLGrid Forge (OpenAI-compatible) chat rounds."""

from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path
from typing import Any

# First trace under each resolved logs base picks the run folder name for that base (UTC).
_RUN_SUBDIRS_BY_BASE: dict[str, str] = {}


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
