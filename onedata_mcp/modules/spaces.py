from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from onedata_mcp.api.spaces import list_marketplace_spaces, list_user_spaces


def register_module(mcp: FastMCP) -> None:
    """Register onedata spaces module tools and prompts with the MCP server."""

    @mcp.tool(name="list_user_spaces", description="List spaces available to the user")
    async def mcp_list_user_spaces() -> list[dict]:
        """
        Get all onedata spaces

        A space is a top-level shared data workspace that groups files,
        users, and storage providers in Onedata.
        """
        return await list_user_spaces()

    @mcp.tool(name="list_marketplace_spaces", description="List marketplace spaces with details")
    async def mcp_list_marketplace_spaces(
        tags: list[str] | None = Field(
            default=None,
            description="Optional tags filter; returns spaces that match at least one provided tag",
        ),
        limit: int = Field(default=20, ge=1, le=50),
        token: str | None = Field(
            default=None,
            description="Pagination token from previous response",
        ),
        offset: int = Field(
            default=0,
            description="Offset relative to token start point; can be negative",
        ),
    ) -> dict[str, Any]:
        """
        List spaces advertised in the Marketplace and return detailed entries.

        Supports tags filtering and pagination with limit/token/offset.
        """
        return await list_marketplace_spaces(
            tags=tags,
            limit=limit,
            token=token,
            offset=offset,
        )
