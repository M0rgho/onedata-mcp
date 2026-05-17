from fastmcp import FastMCP

from onedata_mcp.api.spaces import list_available_spaces


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
