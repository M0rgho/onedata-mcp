from __future__ import annotations

import json
from typing import Any

from env_checks import KRK_SPACES
from fastmcp import FastMCP
from tool_serialization import tool_result_to_text


async def mcp_tool_json_result(app: FastMCP, name: str, arguments: dict[str, Any]) -> Any:
    result = await app.call_tool(name, arguments)
    raw = tool_result_to_text(result)
    return json.loads(raw)


async def ground_truth_user_space_names(app: FastMCP) -> list[str]:
    data = await mcp_tool_json_result(app, "list_available_spaces", {})
    if not isinstance(data, list):
        return []
    names: list[str] = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
    return names


async def ground_truth_krk_space_subset(app: FastMCP) -> frozenset[str]:
    all_names = frozenset(await ground_truth_user_space_names(app))
    return frozenset(all_names & KRK_SPACES)


async def ground_truth_first_harvester_index(app: FastMCP) -> tuple[str, str] | None:
    harvesters = await mcp_tool_json_result(app, "list_user_harvesters", {})
    if not isinstance(harvesters, list) or not harvesters:
        return None
    first_any = harvesters[0]
    if not isinstance(first_any, dict):
        return None
    hid = first_any.get("harvesterId") or first_any.get("harvester_id") or first_any.get("id")
    indices = first_any.get("indices")
    if (
        not isinstance(hid, str)
        or not isinstance(indices, list)
        or not indices
        or not isinstance(indices[0], dict)
    ):
        return None
    idx_any = indices[0]
    idx = idx_any.get("indexId") or idx_any.get("index_id") or idx_any.get("id")
    if not isinstance(idx, str):
        return None
    return hid, idx


async def ground_truth_file_basename(app: FastMCP, file_id_or_path: str) -> str | None:
    """Resolve the file `name` attribute via live MCP (None if missing or error)."""

    attrs = await mcp_tool_json_result(
        app,
        "get_file_attributes",
        {"file_id_or_path": file_id_or_path},
    )
    if not isinstance(attrs, dict):
        return None
    name = attrs.get("name")
    return name if isinstance(name, str) and name else None


async def ground_truth_file_size_bytes(app: FastMCP, logical_path: str) -> int | None:
    attrs = await mcp_tool_json_result(
        app,
        "get_file_attributes",
        {"file_id_or_path": logical_path},
    )
    if not isinstance(attrs, dict):
        return None
    size = attrs.get("size")
    return int(size) if isinstance(size, int) else None


def recall_for_names_in_text(names: frozenset[str], answer: str | None) -> float:
    if not names:
        return 1.0
    if not answer:
        return 0.0
    lowered = answer.lower()
    found = sum(1 for n in names if n.lower() in lowered)
    return found / len(names)
