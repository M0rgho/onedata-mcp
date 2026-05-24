from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from onedata_mcp.api.harvesters import (
    HarvesterIndexQuery,
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
        query: HarvesterIndexQuery = Field(
            description=(
                "Harvester request: method (get or post), path, and optional body. "
                "Pass body as a JSON object (Elasticsearch DSL for POST _search), not a string."
            ),
        ),
    ) -> dict[str, Any]:
        """
        Execute a harvester index request against the backing store (Elasticsearch-style).

        Pass ``harvester_id``, ``index_id``, and a single ``query`` object with ``method``,
        ``path``, and optional ``body``. Onezone forwards that triple to the plugin; this tool
        returns parsed Elasticsearch JSON (not the raw Onezone wrapper).

        Inspect field names via ``get_harvester_index_schema`` first; file metadata often appears
        under ``__onedata.*`` (e.g. ``fileName``, ``fileId``, ``path``).

        **Path allowlist (Onezone ES backend):** only ``_search`` is accepted on ``POST``.
        Paths like ``_count`` return HTTP 400. Use ``GET`` with ``_mapping`` for mapping JSON,
        or ``GET`` with a document id from a prior ``_search`` hit.

        Workflow: ``query`` with ``method`` ``get`` and ``path`` ``_mapping`` (no ``body``), then
        ``method`` ``post``, ``path`` ``_search``, and Elasticsearch DSL in ``body``.

        Example ``query`` values:

        - Mapping: ``{"method": "get", "path": "_mapping"}``.
        - Sample hit: ``{"method": "post", "path": "_search", "body": {"size": 1, "query": {"match_all": {}}}}``.
        - Hit count (not ``_count``): ``{"method": "post", "path": "_search", "body": {"size": 0,
          "track_total_hits": true, "query": {"match_all": {}}}}`` — read ``hits.total.value``.
        - Term on filename: ``post`` / ``_search`` with ``term`` on ``__onedata.fileName`` (set ``size``).
        - Harvested JSON field: e.g. ``{"query": {"term": {"enabled": true}}}`` in ``body``.
        - OR query: ``bool`` with ``should`` in ``body``.
        - Trim payloads: ``"_source": ["__onedata.fileName", "__onedata.fileId"]`` in ``body``.
        - Doc by ES id: ``{"method": "get", "path": "<document_id>"}`` (id from a prior hit).

        From ``_search`` hits, resolve files on Oneprovider via ``__onedata.path`` or file id
        through ``get_file_id`` / ``get_file_attributes``.
        """
        return await query_harvester_index(harvester_id, index_id, query)
