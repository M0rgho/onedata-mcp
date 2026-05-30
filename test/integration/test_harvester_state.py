"""Isolated E2E: section 3 harvester scenarios (Onezone)."""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from e2e_isolated_space import IsolatedE2ESpace
from env_checks import onedata_credentials_available
from isolated_helpers import (
    es_hits_total,
    require_harvester_index,
    seed_file,
    wait_for_harvester_hits,
)
from plgrid_ground_truth import mcp_tool_json_result

from onedata_mcp.api.harvesters import harvester_es_search_query, harvester_index_query

HARVESTER_SPACE_GROUP = "harvester"

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e_isolated,
    pytest.mark.onedata_integration,
    pytest.mark.e2e_isolated_space_group(HARVESTER_SPACE_GROUP),
    pytest.mark.skipif(
        not onedata_credentials_available(),
        reason="ONEDATA_ONEZONE_* and ONEDATA_ONEPROVIDER_* required (see docs/e2e-isolated-spaces.md)",
    ),
]


@pytest_asyncio.fixture
async def harvester_index(
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
) -> tuple[str, str]:
    harvester_id, index_id = await require_harvester_index(isolated_e2e_space)
    probe_path = f"{isolated_e2e_space.root_path}/e2e-harvest/probe.txt"
    await seed_file(probe_path, "harvest-probe\n", admin_token=onedata_admin_token)
    await wait_for_harvester_hits(harvester_id, index_id)
    return harvester_id, index_id


@pytest.mark.e2e_scenario("harvester-index-pair")
async def test_harvester_index_pair(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    harvester_index: tuple[str, str],
) -> None:
    """`harvester-index-pair`: list harvesters shows expected id/index for this space."""
    harvester_id, index_id = harvester_index
    rows = await mcp_tool_json_result(
        mcp_application_isolated,
        "list_user_harvesters",
        {"space_name": isolated_e2e_space.space_name},
    )
    assert isinstance(rows, list)
    ids = {
        row.get("harvesterId")
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("harvesterId"), str)
    }
    assert harvester_id in ids
    match = next(
        row for row in rows if isinstance(row, dict) and row.get("harvesterId") == harvester_id
    )
    indices = match.get("indices")
    assert isinstance(indices, list)
    index_ids = {
        idx.get("indexId")
        for idx in indices
        if isinstance(idx, dict) and isinstance(idx.get("indexId"), str)
    }
    assert index_id in index_ids


@pytest.mark.e2e_scenario("schema-match-all")
async def test_schema_match_all(
    mcp_application_isolated: Any,
    harvester_index: tuple[str, str],
) -> None:
    """`schema-match-all`: schema load then match_all returns at least one hit."""
    harvester_id, index_id = harvester_index
    schema = await mcp_tool_json_result(
        mcp_application_isolated,
        "get_harvester_index_schema",
        {"harvester_id": harvester_id, "index_id": index_id},
    )
    assert isinstance(schema, dict)

    body = await mcp_tool_json_result(
        mcp_application_isolated,
        "query_harvester_index",
        {
            "harvester_id": harvester_id,
            "index_id": index_id,
            "query": harvester_index_query(
                "post",
                "_search",
                harvester_es_search_query({"size": 1, "query": {"match_all": {}}}),
            ),
        },
    )
    total = es_hits_total(body)
    assert total is not None and total >= 1


@pytest.mark.e2e_scenario("query-json-twice")
async def test_query_json_twice(
    mcp_application_isolated: Any,
    harvester_index: tuple[str, str],
) -> None:
    """`query-json-twice`: repeated identical search calls yield the same payload."""
    harvester_id, index_id = harvester_index
    args = {
        "harvester_id": harvester_id,
        "index_id": index_id,
        "query": harvester_index_query(
            "post", "_search", harvester_es_search_query({"size": 1, "query": {"match_all": {}}})
        ),
    }
    first = await mcp_tool_json_result(mcp_application_isolated, "query_harvester_index", args)
    second = await mcp_tool_json_result(mcp_application_isolated, "query_harvester_index", args)
    assert first == second


@pytest.mark.e2e_scenario("field-retry-search")
async def test_field_retry_search(
    mcp_application_isolated: Any,
    harvester_index: tuple[str, str],
) -> None:
    """`field-retry-search`: bogus field yields 0 hits; match_all still works."""
    harvester_id, index_id = harvester_index
    wrong = await mcp_tool_json_result(
        mcp_application_isolated,
        "query_harvester_index",
        {
            "harvester_id": harvester_id,
            "index_id": index_id,
            "query": harvester_index_query(
                "post",
                "_search",
                harvester_es_search_query(
                    {
                        "size": 0,
                        "query": {"term": {"__onedata.nonexistent_field_xyz": "nope"}},
                    }
                ),
            ),
        },
    )
    wrong_total = es_hits_total(wrong)
    assert wrong_total == 0

    ok = await mcp_tool_json_result(
        mcp_application_isolated,
        "query_harvester_index",
        {
            "harvester_id": harvester_id,
            "index_id": index_id,
            "query": harvester_index_query(
                "post",
                "_search",
                harvester_es_search_query({"size": 1, "query": {"match_all": {}}}),
            ),
        },
    )
    ok_total = es_hits_total(ok)
    assert ok_total is not None and ok_total >= 1
