"""Fixtures for ``test/e2e/openfoodfacts_images/`` Forge scenarios."""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from openfoodfacts_harvester import (
    OpenFoodFactsHarvesterNotFoundError,
    count_indexed_filenames_wildcard,
    discover_openfoodfacts_harvester_bundle,
)


@pytest_asyncio.fixture
async def openfoodfacts_harvester_bundle(mcp_application: Any) -> tuple[str, str, str]:
    try:
        return await discover_openfoodfacts_harvester_bundle(mcp_application)
    except OpenFoodFactsHarvesterNotFoundError as exc:
        pytest.skip(str(exc))


@pytest_asyncio.fixture
async def openfoodfacts_indexed_400jpg_count(
    mcp_application: Any,
    openfoodfacts_harvester_bundle: tuple[str, str, str],
) -> int:
    harvester_id, index_id, _space_id = openfoodfacts_harvester_bundle
    return await count_indexed_filenames_wildcard(
        mcp_application,
        harvester_id,
        index_id,
        "*.400.jpg",
    )
