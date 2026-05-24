"""MCP integration probes for openfoodfacts-images README oracles (no Forge)."""

from __future__ import annotations

from typing import Any

import pytest
from env_checks import onedata_credentials_available
from openfoodfacts_harvester import (
    OPENFOODFACTS_GENERIC_INDEX_NAME,
    README_DATA_KEYS_LISTING_URL,
    README_THUMBNAIL_INFIX,
    count_indexed_filenames_wildcard,
    discover_openfoodfacts_harvester_bundle,
    ean13_example_subpath_from_readme,
    grep_readme,
    readme_declares_data_keys_listing_url,
    readme_declares_example_image_url,
    readme_declares_ocr_sidecar_suffix,
    readme_declares_thumbnail_infix,
    readme_text,
)
from plgrid_ground_truth import mcp_tool_json_result

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.onedata_integration,
    pytest.mark.shared_tenant,
    pytest.mark.skipif(
        not onedata_credentials_available(),
        reason="ONEDATA_ONEZONE_* and ONEDATA_ONEPROVIDER_* required",
    ),
]


@pytest.mark.e2e_scenario("off-readme-data-keys-url")
async def test_openfoodfacts_readme_data_keys_listing_url(mcp_application: Any) -> None:
    text = await readme_text(mcp_application)
    assert readme_declares_data_keys_listing_url(text)
    grep_out = await grep_readme(mcp_application, "data_keys.txt")
    assert README_DATA_KEYS_LISTING_URL in grep_out


@pytest.mark.e2e_scenario("off-readme-example-image-url")
async def test_openfoodfacts_readme_example_https_image_url(mcp_application: Any) -> None:
    text = await readme_text(mcp_application)
    assert readme_declares_example_image_url(text)
    assert ean13_example_subpath_from_readme(text) == "401/235/911/4303/1.jpg"


@pytest.mark.e2e_scenario("off-readme-naming-conventions")
async def test_openfoodfacts_readme_thumbnail_and_ocr_naming(mcp_application: Any) -> None:
    text = await readme_text(mcp_application)
    assert readme_declares_thumbnail_infix(text)
    assert readme_declares_ocr_sidecar_suffix(text)
    assert README_THUMBNAIL_INFIX in text


@pytest.mark.e2e_scenario("off-indexed-400jpg-count")
async def test_openfoodfacts_indexed_400jpg_count(mcp_application: Any) -> None:
    harvester_id, index_id, space_id = await discover_openfoodfacts_harvester_bundle(
        mcp_application
    )
    rows = await mcp_tool_json_result(
        mcp_application,
        "list_user_harvesters",
        {"space_name": "openfoodfacts-images"},
    )
    harvester = next(
        r for r in rows if isinstance(r, dict) and r.get("harvesterId") == harvester_id
    )
    index_names = {i.get("name") for i in (harvester.get("indices") or []) if isinstance(i, dict)}
    assert index_names == {OPENFOODFACTS_GENERIC_INDEX_NAME}

    count = await count_indexed_filenames_wildcard(
        mcp_application,
        harvester_id,
        index_id,
        "*.400.jpg",
    )
    assert count >= 100_000, f"expected large 400px JPEG catalog, got {count}"
    assert space_id
