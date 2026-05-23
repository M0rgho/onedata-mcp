"""Isolated E2E: section 5 robustness scenarios (confined read token)."""

from __future__ import annotations

from typing import Any

import pytest
from e2e_isolated_space import IsolatedE2ESpace
from env_checks import onedata_credentials_available
from isolated_helpers import seed_file
from plgrid_ground_truth import mcp_tool_json_result

ROBUSTNESS_SPACE_GROUP = "robustness"

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e_isolated,
    pytest.mark.onedata_integration,
    pytest.mark.e2e_isolated_space_group(ROBUSTNESS_SPACE_GROUP),
    pytest.mark.skipif(
        not onedata_credentials_available(),
        reason="ONEDATA_ONEZONE_* and ONEDATA_ONEPROVIDER_* required (see docs/e2e-isolated-spaces.md)",
    ),
]


@pytest.mark.e2e_scenario("wrong-path-recover")
async def test_wrong_path_recover(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
) -> None:
    """`wrong-path-recover`: missing path then successful read on correct path."""
    parent = f"{isolated_e2e_space.root_path}/e2e-recover"
    correct = f"{parent}/exists.txt"
    wrong = f"{parent}/no-such-file.txt"

    await seed_file(correct, "ok\n", admin_token=onedata_admin_token)

    with pytest.raises(Exception):
        await mcp_tool_json_result(
            mcp_application_isolated,
            "get_file_attributes",
            {"file_id_or_path": wrong},
        )

    listing = await mcp_tool_json_result(
        mcp_application_isolated,
        "list_files",
        {"parent_id_or_path": parent, "limit": 20},
    )
    assert isinstance(listing, dict)

    attrs = await mcp_tool_json_result(
        mcp_application_isolated,
        "get_file_attributes",
        {"file_id_or_path": correct, "attributes": ["path", "name"]},
    )
    assert isinstance(attrs, dict)
    assert attrs.get("name") == "exists.txt"
