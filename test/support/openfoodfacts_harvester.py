"""Discover openfoodfacts-images harvester fixtures and README oracles via live MCP."""

from __future__ import annotations

import re
from typing import Any

from fastmcp import FastMCP
from isolated_helpers import es_hits_total
from mcp_write_guard import guarded_call_tool
from plgrid_ground_truth import mcp_tool_json_result
from tool_serialization import tool_result_to_text

from onedata_mcp.api.harvesters import (
    harvester_es_search_query,
    harvester_index_query,
    unwrap_harvester_query_response,
)

OPENFOODFACTS_SPACE = "openfoodfacts-images"
OPENFOODFACTS_README_PATH = f"/{OPENFOODFACTS_SPACE}/README.md"
OPENFOODFACTS_GENERIC_INDEX_NAME = "generic-index"
OPENFOODFACTS_HARVESTER_NAME_FRAGMENT = "openfoodfacts"

# Stable strings from the space README (Open Food Facts images on S3).
README_DATA_KEYS_LISTING_URL = (
    "https://openfoodfacts-images.s3.eu-west-3.amazonaws.com/data/data_keys.txt"
)
README_S3_BUCKET_HOST = "openfoodfacts-images.s3.eu-west-3.amazonaws.com"
README_EXAMPLE_RAW_IMAGE_URL = (
    "https://openfoodfacts-images.s3.eu-west-3.amazonaws.com/data/401/235/911/4303/1.jpg"
)
README_THUMBNAIL_INFIX = ".400"
README_OCR_SUFFIX = ".json.gz"
README_EAN13_BARCODE = "4012359114303"
README_EAN13_IMAGE_SUBPATH = "401/235/911/4303/1.jpg"


class OpenFoodFactsHarvesterNotFoundError(RuntimeError):
    """Raised when the shared tenant has no openfoodfacts harvester / generic-index."""


async def discover_openfoodfacts_space_id(app: FastMCP) -> str:
    spaces = await mcp_tool_json_result(app, "list_available_spaces", {})
    if not isinstance(spaces, list):
        msg = "list_available_spaces did not return a list"
        raise AssertionError(msg)
    for row in spaces:
        if isinstance(row, dict) and row.get("name") == OPENFOODFACTS_SPACE:
            space_id = row.get("spaceId")
            if isinstance(space_id, str) and space_id:
                return space_id
    msg = f"Space {OPENFOODFACTS_SPACE!r} not found on provider"
    raise AssertionError(msg)


async def discover_openfoodfacts_harvester_bundle(app: FastMCP) -> tuple[str, str, str]:
    """Return ``(harvester_id, generic_index_id, space_id)`` from MCP."""

    space_id = await discover_openfoodfacts_space_id(app)
    rows = await mcp_tool_json_result(
        app,
        "list_user_harvesters",
        {"space_name": OPENFOODFACTS_SPACE},
    )
    if not isinstance(rows, list) or not rows:
        raise OpenFoodFactsHarvesterNotFoundError(
            f"No harvesters attached to {OPENFOODFACTS_SPACE!r}"
        )

    harvester: dict[str, Any] | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if isinstance(name, str) and OPENFOODFACTS_HARVESTER_NAME_FRAGMENT in name.lower():
            harvester = row
            break
    if harvester is None:
        harvester = rows[0] if isinstance(rows[0], dict) else None
    if not harvester:
        raise OpenFoodFactsHarvesterNotFoundError("No harvester row in list_user_harvesters")

    harvester_id = harvester.get("harvesterId")
    indices = harvester.get("indices")
    if not isinstance(harvester_id, str) or not isinstance(indices, list):
        raise OpenFoodFactsHarvesterNotFoundError("Harvester row missing harvesterId or indices")

    index_id = _pick_generic_index_id(indices)
    if index_id is None:
        raise OpenFoodFactsHarvesterNotFoundError(
            f"No index named {OPENFOODFACTS_GENERIC_INDEX_NAME!r} on harvester {harvester_id!r}"
        )
    return harvester_id, index_id, space_id


def _pick_generic_index_id(indices: list[Any]) -> str | None:
    for entry in indices:
        if not isinstance(entry, dict):
            continue
        if entry.get("name") == OPENFOODFACTS_GENERIC_INDEX_NAME:
            index_id = entry.get("indexId") or entry.get("index_id")
            if isinstance(index_id, str):
                return index_id
    return None


async def mcp_harvester_search(
    app: FastMCP,
    harvester_id: str,
    index_id: str,
    es_body: dict[str, Any],
) -> dict[str, Any]:
    raw = await mcp_tool_json_result(
        app,
        "query_harvester_index",
        {
            "harvester_id": harvester_id,
            "index_id": index_id,
            "query": harvester_index_query("post", "_search", harvester_es_search_query(es_body)),
        },
    )
    parsed = unwrap_harvester_query_response(raw)
    return parsed if isinstance(parsed, dict) else {}


async def count_indexed_filenames_wildcard(
    app: FastMCP,
    harvester_id: str,
    index_id: str,
    pattern: str,
) -> int:
    body = await mcp_harvester_search(
        app,
        harvester_id,
        index_id,
        {
            "size": 0,
            "track_total_hits": True,
            "query": {"wildcard": {"__onedata.fileName.keyword": pattern}},
        },
    )
    total = es_hits_total(body)
    if total is None:
        msg = f"Harvester wildcard count missing hits.total for pattern {pattern!r}"
        raise AssertionError(msg)
    return int(total)


async def readme_text(app: FastMCP) -> str:
    result = await guarded_call_tool(
        app,
        "download_file",
        {"file_id_or_path": OPENFOODFACTS_README_PATH},
    )
    text = tool_result_to_text(result)
    if not text.strip() or text.strip() == "null":
        msg = "download_file for README returned empty content"
        raise AssertionError(msg)
    return text


async def grep_readme(app: FastMCP, pattern: str) -> str:
    out = await mcp_tool_json_result(
        app,
        "grep_file_content",
        {"file_id_or_path": OPENFOODFACTS_README_PATH, "pattern": pattern},
    )
    if not isinstance(out, str):
        msg = "grep_file_content for README did not return str"
        raise AssertionError(msg)
    return out


def readme_declares_data_keys_listing_url(text: str) -> bool:
    return README_DATA_KEYS_LISTING_URL in text


def readme_declares_example_image_url(text: str) -> bool:
    return README_EXAMPLE_RAW_IMAGE_URL in text


def readme_declares_thumbnail_infix(text: str) -> bool:
    return README_THUMBNAIL_INFIX in text and ".400.jpg" in text


def readme_declares_ocr_sidecar_suffix(text: str) -> bool:
    return README_OCR_SUFFIX in text


def ean13_example_subpath_from_readme(text: str) -> str | None:
    """Return ``401/235/911/4303/1.jpg`` if README still documents the EAN13 example."""

    match = re.search(
        r"/(\d{3}/\d{3}/\d{3}/\d{4}/1\.jpg)",
        text,
    )
    return match.group(1) if match else None
