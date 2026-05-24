"""Forge: example HTTPS URL for a raw product image (EAN13 path rules from README)."""

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
    README_EAN13_BARCODE,
    README_EAN13_IMAGE_SUBPATH,
    README_EXAMPLE_RAW_IMAGE_URL,
    README_S3_BUCKET_HOST,
    readme_declares_example_image_url,
    readme_text,
)

pytestmark = OPENFOODFACTS_FORGE_PYTESTMARK


@pytest.mark.e2e_scenario("off-readme-example-image-url")
async def test_forge_off_readme_example_raw_image_https_url(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    async def verify(app: Any) -> None:
        text = await readme_text(app)
        assert readme_declares_example_image_url(text)
        assert README_EXAMPLE_RAW_IMAGE_URL in text

    scenario = E2EScenario(
        name="forge-off-readme-example-image-url",
        system_prompt=OPENFOODFACTS_FORGE_USER_SYSTEM,
        user_prompt=(
            f"In {OPENFOODFACTS_SPACE_LABEL}, for barcode {README_EAN13_BARCODE}, "
            "what HTTPS URL fetches image 1 per the space README?"
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
        answer_fragments=(README_S3_BUCKET_HOST, README_EAN13_IMAGE_SUBPATH),
        answer_hint="Answer should include the S3 host and the split barcode path to 1.jpg.",
    )
