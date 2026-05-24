"""Shared Forge E2E configuration for ``openfoodfacts-images`` README scenarios."""

from __future__ import annotations

import pytest
from env_checks import forge_credentials_available, onedata_credentials_available
from openfoodfacts_harvester import OPENFOODFACTS_SPACE

OPENFOODFACTS_FORGE_USER_SYSTEM = (
    "You help people work with their Onedata storage: spaces, files, and harvester search "
    "indexes. Answer from live lookups; do not invent URLs, counts, or field names. "
    "In final replies use plain digits for numbers, never thousands separators. "
    "When the user points you at dataset documentation in a workspace, read that file from "
    "Onedata (for example via list_files at the space root, grep, or download) before "
    "answering. Include every fact the user asked for (URLs, counts, path segments)."
)

README_LOOKUP_TOOLS = frozenset(
    {
        "list_files",
        "grep_file_content",
        "download_file",
        "get_file_attributes",
        "list_available_spaces",
    }
)

HARVESTER_TOOLS = (
    frozenset(
        {
            "list_user_harvesters",
            "get_harvester_index_schema",
            "query_harvester_index",
            "list_available_spaces",
        }
    )
    | README_LOOKUP_TOOLS
)

OPENFOODFACTS_FORGE_MAX_TOKENS = 8192
OPENFOODFACTS_FORGE_MAX_TOOL_ROUNDS = 20

OPENFOODFACTS_FORGE_PYTESTMARK = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.shared_tenant,
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

# Natural-language space label for prompts (not a filesystem path).
OPENFOODFACTS_SPACE_LABEL = f"the {OPENFOODFACTS_SPACE} workspace"
