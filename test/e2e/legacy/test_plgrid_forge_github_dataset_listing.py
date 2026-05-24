"""Read-only Forge E2E: shallow list under shared ``github_dataset`` space."""

from __future__ import annotations

from typing import Any

import pytest
from e2e_types import E2EScenario
from env_checks import forge_credentials_available, onedata_credentials_available
from legacy_forge import run_legacy_forge_scenario
from plgrid_ground_truth import ground_truth_file_basename, mcp_tool_json_result

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.legacy,
    pytest.mark.e2e,
    pytest.mark.onedata_integration,
    pytest.mark.skipif(
        not forge_credentials_available(),
        reason="PLGRID_FORGE_API_KEY and PLGRID_FORGE_MODEL required",
    ),
    pytest.mark.skipif(
        not onedata_credentials_available(),
        reason="Full Onedata credentials required",
    ),
]

_LIST_TOOLS = frozenset({"list_files"})
_KNOWN_EVENT = "github_event_11898.dat"
_EVENT_PATH = f"/github_dataset/github_dataset/{_KNOWN_EVENT}"


async def test_e2e_lists_known_github_event_basename(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    """Agent lists ``github_dataset`` tree; post-probe confirms a known event file exists."""
    scenario = E2EScenario(
        name="github-dataset-list-children",
        user_prompt=(
            "On this Oneprovider, in space github_dataset, list the immediate children "
            "of the github_dataset directory (one level under the space root). "
            "Reply with the basenames you see, comma-separated."
        ),
        required_tools=frozenset({"list_files"}),
        allowed_tools_for_minimal_context=_LIST_TOOLS,
        require_no_extra_tool_calls=True,
    )
    run = await run_legacy_forge_scenario(
        scenario=scenario,
        mcp_app=mcp_application,
        tool_context_mode="full",
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
    )
    assert run.metrics.required_tools_satisfied
    assert run.metrics.all_tool_calls_ok

    basename = await ground_truth_file_basename(mcp_application, _EVENT_PATH)
    assert basename == _KNOWN_EVENT

    listed = await mcp_tool_json_result(
        mcp_application,
        "list_files",
        {"parent_id_or_path": "/github_dataset/github_dataset", "limit": 100},
    )
    children = listed.get("children") if isinstance(listed, dict) else None
    names = {
        c.get("name")
        for c in (children or [])
        if isinstance(c, dict) and isinstance(c.get("name"), str)
    }
    assert _KNOWN_EVENT in names
