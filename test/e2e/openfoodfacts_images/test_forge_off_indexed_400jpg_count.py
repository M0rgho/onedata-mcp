"""Forge: count of 400px resized JPEGs in the harvester catalog."""

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
    count_indexed_filenames_wildcard,
    readme_declares_thumbnail_infix,
    readme_text,
)

pytestmark = OPENFOODFACTS_FORGE_PYTESTMARK


@pytest.mark.e2e_scenario("off-indexed-400jpg-count")
async def test_forge_off_indexed_400jpg_count(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    openfoodfacts_harvester_bundle: tuple[str, str, str],
    openfoodfacts_indexed_400jpg_count: int,
) -> None:
    harvester_id, index_id, _space_id = openfoodfacts_harvester_bundle
    expected_count = openfoodfacts_indexed_400jpg_count

    async def verify(app: Any) -> None:
        text = await readme_text(app)
        assert readme_declares_thumbnail_infix(text)
        count = await count_indexed_filenames_wildcard(
            app,
            harvester_id,
            index_id,
            "*.400.jpg",
        )
        assert count == expected_count
        assert count >= 100_000

    scenario = E2EScenario(
        name="forge-off-indexed-400jpg-count",
        system_prompt=OPENFOODFACTS_FORGE_USER_SYSTEM,
        user_prompt=(
            f"In {OPENFOODFACTS_SPACE_LABEL}, use the dataset documentation at the space "
            "root to learn how 400-pixel-wide JPEG variants are named, then query the "
            "harvester generic search index for that workspace. How many such resized "
            "image files are catalogued in the index? Reply with the count only."
        ),
        required_tools=frozenset({"query_harvester_index"}),
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
        answer_fragments=(str(expected_count),),
        answer_hint="Final answer should state the indexed 400px JPEG count as a plain number.",
    )
