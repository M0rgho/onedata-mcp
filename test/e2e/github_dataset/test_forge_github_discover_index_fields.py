"""Forge: which GitHub event fields does the github-index harvester catalog expose?"""

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_forge_scenario_outcome, assert_required_tools_and_optional_policy
from e2e_types import E2EScenario
from github_dataset_harvester import (
    GITHUB_DATASET_SPACE,
    GITHUB_INDEX_NAME,
    harvester_index_schema_properties,
)
from github_forge_e2e import (
    GITHUB_FORGE_MAX_TOKENS,
    GITHUB_FORGE_MAX_TOOL_ROUNDS,
    GITHUB_FORGE_PYTESTMARK,
    GITHUB_FORGE_USER_SYSTEM,
)
from legacy_forge import run_shared_forge_scenario
from plgrid_ground_truth import mcp_tool_json_result

pytestmark = GITHUB_FORGE_PYTESTMARK

# Top-level properties from the shared github-index configured schema (2026-05).
INDEXED_TOP_LEVEL_FIELDS: tuple[str, ...] = (
    "id",
    "type",
    "created_at",
    "public",
    "actor",
    "repo",
    "org",
    "payload",
    "__onedata",
)


@pytest.mark.e2e_scenario("discover-index-fields")
async def test_discover_index_fields(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    github_harvester_bundle: tuple[str, str, str],
) -> None:
    harvester_id, index_id, _space_id = github_harvester_bundle

    async def verify(app: Any) -> None:
        index_detail = await mcp_tool_json_result(
            app,
            "get_harvester_index_schema",
            {"harvester_id": harvester_id, "index_id": index_id},
        )
        assert isinstance(index_detail, dict)
        assert index_detail.get("name") == GITHUB_INDEX_NAME
        assert index_detail.get("indexId") == index_id
        assert isinstance(index_detail.get("schema"), str)
        properties = harvester_index_schema_properties(index_detail)
        assert properties, "schema JSON missing mappings.properties"
        for field in INDEXED_TOP_LEVEL_FIELDS:
            assert field in properties, field
        assert "eventType" not in properties

    scenario = E2EScenario(
        name="discover-index-fields",
        system_prompt=GITHUB_FORGE_USER_SYSTEM,
        user_prompt=(
            f"For the GitHub event harvester attached to {GITHUB_DATASET_SPACE}, "
            "what fields are available in the dedicated github index?"
            "List the top-level field names the index is tracking."
        ),
        required_tools=frozenset({"get_harvester_index_schema"}),
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
    assert_forge_scenario_outcome(
        run,
        answer_fragments=INDEXED_TOP_LEVEL_FIELDS,
        answer_hint=(
            "Answer should mention each top-level indexed field: "
            + ", ".join(INDEXED_TOP_LEVEL_FIELDS)
            + "."
        ),
    )
