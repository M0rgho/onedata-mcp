"""Forge: is the github_dataset event catalog populated?"""

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_required_tools_and_optional_policy
from e2e_types import E2EScenario
from github_dataset_harvester import (
    GITHUB_DATASET_SPACE,
    mcp_harvester_search,
    schema_declares_field,
)
from github_forge_e2e import (
    GITHUB_FORGE_MAX_TOKENS,
    GITHUB_FORGE_MAX_TOOL_ROUNDS,
    GITHUB_FORGE_PYTESTMARK,
    GITHUB_FORGE_USER_SYSTEM,
    assert_successful_harvester_queries,
)
from isolated_helpers import es_hits_total
from legacy_forge import run_shared_forge_scenario
from plgrid_ground_truth import mcp_tool_json_result

pytestmark = GITHUB_FORGE_PYTESTMARK


@pytest.mark.e2e_scenario("github-schema-match-all")
async def test_forge_github_schema_match_all(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    github_harvester_bundle: tuple[str, str, str],
) -> None:
    harvester_id, index_id, _space_id = github_harvester_bundle

    async def verify(app: Any) -> None:
        schema = await mcp_tool_json_result(
            app,
            "get_harvester_index_schema",
            {"harvester_id": harvester_id, "index_id": index_id},
        )
        assert isinstance(schema, dict)
        assert schema_declares_field(schema, "type")
        assert not schema_declares_field(schema, "eventType")
        body = await mcp_harvester_search(
            app, harvester_id, index_id, {"size": 1, "query": {"match_all": {}}}
        )
        total = es_hits_total(body)
        assert total is not None and total >= 1

    scenario = E2EScenario(
        name="forge-github-schema-match-all",
        system_prompt=GITHUB_FORGE_USER_SYSTEM,
        user_prompt=(
            f"In {GITHUB_DATASET_SPACE}, do we already have a searchable catalog of GitHub "
            "events from the harvester, or is that index still empty? "
            "I only need to know whether there is real data in there and what kinds of "
            "fields the catalog tracks."
        ),
        required_tools=frozenset({"query_harvester_index"}),
        max_tokens=GITHUB_FORGE_MAX_TOKENS,
        max_tool_rounds=GITHUB_FORGE_MAX_TOOL_ROUNDS,
    )
    run = await run_shared_forge_scenario(
        scenario=scenario,
        mcp_app=mcp_application,
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
        verify_state=verify,
    )
    assert_required_tools_and_optional_policy(run)
    assert_successful_harvester_queries(run)
