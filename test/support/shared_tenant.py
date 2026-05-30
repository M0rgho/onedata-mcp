"""Shared PLGrid tenant spaces (not isolated; tests must be read-only)."""

from __future__ import annotations

from e2e_types import E2EScenario

from onedata_mcp.token_policy import WRITE_TOOL_NAMES

# Spaces with long-lived reference data; never mutate from automated tests.
SHARED_TENANT_SPACE_NAMES = frozenset(
    {
        "github_dataset",
        "krk-p",
        "europeana",
        "openfoodfacts-images",
    }
)

# Subset checked for "reference tenant" recall / list-spaces oracles.
SHARED_REFERENCE_SPACE_NAMES = frozenset({"github_dataset", "krk-p"})

# MCP tools that change Onedata state — forbidden on shared-tenant runs.
SHARED_MUTATING_MCP_TOOLS = WRITE_TOOL_NAMES


def shared_readonly_scenario(**kwargs: object) -> E2EScenario:
    """Build an ``E2EScenario`` with mutating tools forbidden (shared tenant policy)."""

    extra = kwargs.pop("forbidden_tools", frozenset())
    if not isinstance(extra, frozenset):
        msg = "forbidden_tools must be a frozenset"
        raise TypeError(msg)
    return E2EScenario(
        **kwargs,  # type: ignore[arg-type]
        forbidden_tools=SHARED_MUTATING_MCP_TOOLS | extra,
    )
