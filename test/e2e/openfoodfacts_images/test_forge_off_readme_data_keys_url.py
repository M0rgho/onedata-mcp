"""Forge: HTTPS URL to download the full S3 object key listing (from workspace README)."""

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_forge_scenario_outcome
from e2e_types import E2EScenario
from legacy_forge import run_shared_forge_scenario
from openfoodfacts_forge_e2e import (
    HARVESTER_TOOLS,
    OPENFOODFACTS_FORGE_MAX_TOKENS,
    OPENFOODFACTS_FORGE_MAX_TOOL_ROUNDS,
    OPENFOODFACTS_FORGE_PYTESTMARK,
    OPENFOODFACTS_FORGE_USER_SYSTEM,
    OPENFOODFACTS_SPACE_LABEL,
)
from openfoodfacts_harvester import (
    README_DATA_KEYS_LISTING_URL,
    README_S3_BUCKET_HOST,
    grep_readme,
    readme_declares_data_keys_listing_url,
    readme_text,
)

pytestmark = OPENFOODFACTS_FORGE_PYTESTMARK


@pytest.mark.e2e_scenario("off-readme-data-keys-url")
async def test_forge_off_readme_data_keys_listing_url(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    async def verify(app: Any) -> None:
        text = await readme_text(app)
        assert readme_declares_data_keys_listing_url(text)
        grep_out = await grep_readme(app, "data_keys.txt")
        assert README_DATA_KEYS_LISTING_URL in grep_out

    scenario = E2EScenario(
        name="forge-off-readme-data-keys-url",
        system_prompt=OPENFOODFACTS_FORGE_USER_SYSTEM,
        user_prompt=(
            f"In {OPENFOODFACTS_SPACE_LABEL}, what HTTPS URL downloads the full S3 key listing "
            "from the space README?"
        ),
        required_tools=frozenset({"grep_file_content"}),
        allowed_tools_for_minimal_context=HARVESTER_TOOLS,
        max_tokens=OPENFOODFACTS_FORGE_MAX_TOKENS,
        max_tool_rounds=OPENFOODFACTS_FORGE_MAX_TOOL_ROUNDS,
    )
    run = await run_shared_forge_scenario(
        scenario=scenario,
        mcp_app=mcp_application,
        tool_context_mode="full",
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
        verify_state=verify,
    )
    assert_forge_scenario_outcome(
        run,
        answer_fragments=(README_S3_BUCKET_HOST, "data_keys.txt"),
        answer_hint="Answer should include the S3 host and data_keys.txt filename.",
    )
