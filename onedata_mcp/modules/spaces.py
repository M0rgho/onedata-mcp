from typing import Any, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from onedata_mcp.api.spaces import list_available_spaces, list_space_datasets


def register_module(mcp: FastMCP) -> None:
    """Register onedata spaces module tools and prompts with the MCP server."""

    @mcp.tool(
        name="list_available_spaces",
        description="List Onedata spaces supported by the connected Oneprovider",
    )
    async def mcp_list_available_spaces() -> list[dict]:
        """
        List available spaces this Oneprovider can serve.

        Returns only spaces supported by the configured Oneprovider (not the full
        zone-wide catalog). A space is a top-level shared data workspace for files.
        """
        return await list_available_spaces()

    @mcp.tool(name="list_space_datasets", annotations=ToolAnnotations(readOnlyHint=True))
    async def mcp_list_space_datasets(
        space_id_or_name: str = Field(
            description="Space id or space name (as returned by list_available_spaces)",
        ),
        state: Literal["attached", "detached"] = Field(
            default="attached",
            description=(
                "Dataset tree: 'attached' follows current file layout; "
                "'detached' is the hierarchy frozen at detachment time"
            ),
        ),
        limit: int = Field(
            default=100,
            ge=1,
            le=1000,
            description="Maximum number of top-level datasets to return",
        ),
        offset: int = Field(default=0, description="Entry offset for pagination"),
        token: str | None = Field(
            default=None,
            description="Pagination token from a previous response's nextPageToken",
        ),
    ) -> dict[str, Any]:
        """
        List top-level datasets in a space with full dataset metadata per entry.

        Datasets are file or directory subtrees marked as datasets. Only root-level
        entries (no parent dataset) are returned.
        """
        return await list_space_datasets(
            space_id_or_name,
            state=state,
            limit=limit,
            offset=offset,
            token=token,
        )
