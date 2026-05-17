from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from onedata_mcp.api.harvesters import (
    get_harvester_index_schema,
    list_user_harvesters,
    query_harvester_index,
)


def register_module(mcp: FastMCP) -> None:
    """Register onedata harvesters module tools with the MCP server."""

    @mcp.tool(name="list_user_harvesters", annotations=ToolAnnotations(readOnlyHint=True))
    async def mcp_list_user_harvesters(
        space_name: str | None = Field(
            default=None,
            description=(
                "Optional filter: return only harvesters attached to a space whose "
                "name contains this substring (case-insensitive, provider-supported spaces)"
            ),
        ),
    ) -> list[dict[str, Any]]:
        """
        List harvesters available to the current user.

        Each harvester embeds detailed index metadata and ``attached_spaces`` entries
        (``space_id``, ``space_name``). When ``space_name`` is set, only harvesters linked
        to a matching space are returned.
        """
        return await list_user_harvesters(space_name=space_name)

    @mcp.tool(name="get_harvester_index_schema", annotations=ToolAnnotations(readOnlyHint=True))
    async def mcp_get_harvester_index_schema(
        harvester_id: str = Field(description="Harvester id"),
        index_id: str = Field(description="Harvester index id"),
    ) -> dict[str, Any]:
        """
        Get harvester index details, including schema.
        """
        return await get_harvester_index_schema(harvester_id, index_id)

    @mcp.tool(name="query_harvester_index", annotations=ToolAnnotations(readOnlyHint=True))
    async def mcp_query_harvester_index(
        harvester_id: str = Field(description="Harvester id"),
        index_id: str = Field(description="Harvester index id"),
        query: dict[str, Any] | str = Field(
            description=(
                "Harvest query: **prefer a JSON object** "
                '`{"method":"post","path":"_search","body":"{...}"}`. '
                "If your client only allows a string, pass the **same object as one JSON string** "
                "(it will be parsed). `body` must remain a JSON **string** for Elasticsearch "
                "backends when present. Schema / field discovery — `path` `_search`, "
                "`match_all` inside the `body` string, e.g. "
                '{"method": "post", "path": "_search", '
                '"body": "{\\"query\\":{\\"match_all\\":{}},\\"size\\":5}"}. '
                "Index mapping JSON: "
                '{"method": "get", "path": "_mapping"}. '
                "Single document by id when supported: "
                '{"method": "get", "path": "<resource_id>"}. '
                "On `elasticsearch_harvesting_backend`, Onedata metadata is mostly under "
                "`__onedata` (e.g. `__onedata.fileName`, `__onedata.fileName.keyword` for "
                "exact terms); top-level `fileName` often matches nothing although the row "
                "exists. If `_search` returns `hits.total.value` 0, adjust field paths "
                "(or use `term` vs `match`) or inspect `_mapping` before concluding data "
                "is absent; use `get_harvester_index_schema` or `_mapping` when unsure. "
            )
        ),
    ) -> dict[str, Any]:
        """
        Execute a query against a specific harvester index.

        Elasticsearch: `body` is serialized JSON (a string). Use `_mapping` /
        `_search` as in `query`; zero-hit results often mean a wrong field path —
        indexed file facets usually live under `__onedata`.
        """
        return await query_harvester_index(harvester_id, index_id, query)
