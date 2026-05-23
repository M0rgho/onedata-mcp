from typing import Any, Literal

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
        method: Literal["get", "post"] = Field(description="HTTP method (get or post)"),
        path: str = Field(
            description=(
                "Backend-relative path forwarded to the harvester plugin. "
                "For Elasticsearch: _mapping, _search, _count, or a document _id from a prior hit."
            ),
        ),
        body: dict[str, Any] | None = Field(
            default=None,
            description=(
                "JSON object for POST requests (Elasticsearch query DSL in body). "
                "Not used when method is get."
            ),
        ),
    ) -> dict[str, Any]:
        """
        Execute a harvester index request against the backing store (Elasticsearch-style).

        Onezone forwards ``method``, ``path``, and optional ``body`` to the plugin. Inspect
        field names via ``get_harvester_index_schema`` first; file metadata often appears
        under ``__onedata.*`` (e.g. ``fileName``, ``fileId``, ``path``).

        Workflow: ``GET`` with ``path`` ``_mapping`` and no ``body``, then ``POST`` with
        ``path`` ``_search`` and a query DSL dict in ``body``.

        Omit ``body`` for GET; for POST the ES payload is passed as structured fields (dict),
        not a serialized JSON string.

        Examples (``method`` / ``path`` / ``body``):

        - Mapping: ``get``, ``_mapping``, no body.
        - Sample hit: ``post``, ``_search``, ``{"size": 1, "query": {"match_all": {}}}``.
        - Term on filename: ``post``, ``_search``, ``term`` on ``__onedata.fileName``
          (set ``size``).
        - Harvested JSON field: ``post``, ``_search``, e.g.
          ``{"query": {"term": {"enabled": true}}}``.
        - OR query: ``post``, ``_search``, ``bool`` with ``should`` (``term``, ``range``, …).
        - Trim payloads: include ``"_source": ["__onedata.fileName", "__onedata.fileId"]``
          in the ``_search`` body.
        - Count hits: ``post``, ``_count``, ``{"query": {"match_all": {}}}``.
        - Doc by ES id: ``get``, literal document id path, no body
          (id from a prior ``_search`` hit).

        From ``_search`` hits, resolve files on Oneprovider via ``__onedata.path`` or file id
        through ``get_file_id`` / ``get_file_attributes``.
        """
        return await query_harvester_index(harvester_id, index_id, method, path, body)
