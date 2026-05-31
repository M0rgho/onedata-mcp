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
        Get harvester index details, including the configured schema template.

        Call this before ``term`` / ``wildcard`` searches. The ``schema`` field is a JSON string;
        read ``mappings.properties`` for top-level indexed field names and nested object shapes.
        Live runtime mapping may differ — use ``query_harvester_index`` with
        ``{"method": "get", "path": "_mapping"}`` when filters still return zero hits.
        """
        return await get_harvester_index_schema(harvester_id, index_id)

    @mcp.tool(name="query_harvester_index", annotations=ToolAnnotations(readOnlyHint=True))
    async def mcp_query_harvester_index(
        harvester_id: str = Field(description="Harvester id"),
        index_id: str = Field(description="Harvester index id"),
        query: HarvesterIndexQuery = Field(
            description=(
                "Harvester request object with method (get or post), path, and optional body. "
                "Pass query as a nested JSON object — never a JSON string. "
                "For POST _search, pass body as a JSON object (Elasticsearch DSL), not a string."
            ),
        ),
    ) -> dict[str, Any]:
        """
        Execute a harvester index request against the backend store (Elasticsearch-style).

        Pass ``harvester_id``, ``index_id``, and a single ``query`` **object** with ``method``,
        ``path``, and optional ``body``. Do **not** stringify ``query`` or ``body`` — both must be
        JSON objects in the tool call. Onezone forwards
        that triple to the plugin; this tool returns the parsed Elasticsearch JSON response —
        except for ``_mapping`` (see below).

        Prefer calling ``get_harvester_index_schema`` before calling this tool to verify the index schema.
        Use size and offset for sorted queries to minimize the number of hits returned.
        Do not asume metadata is sorted without explicit sort clause.

        **Path allowlist (Onezone ES backend):** only ``_search`` is accepted on ``POST``.
        Paths like ``_count`` return HTTP 400. Use ``query_harvester_index`` with ``method``
        ``get`` and ``path`` ``_mapping`` (no ``body``).

        Example ``query`` values (each is a full object — do not pass these as strings):

        - Live mapping (compact field→type map): ``{"method": "get", "path": "_mapping"}``.
        - Sample hit: ``{"method": "post", "path": "_search", "body": {"size": 1, "query":
          {"match_all": {}}}}``.
        - Hit count (not ``_count``): ``{"method": "post", "path": "_search", "body": {"size": 0,
          "track_total_hits": true, "query": {"match_all": {}}}}`` — read ``hits.total.value``.
        - Term filter: ``{"method": "post", "path": "_search", "body": {"size": 10, "query":
          {"term": {"enabled": true}}}}``.
        - OR query: put ``bool`` with ``should`` in ``body.query``; ``sort`` and ``_source`` are
          top-level keys in ``body``, not inside ``query``.
        - Trim payloads: add ``"_source": ["__onedata.fileName", "__onedata.fileId"]`` to ``body``.
        - Doc by ES id: ``{"method": "get", "path": "<document_id>"}`` (id from a prior hit).

        From ``_search`` hits, resolve files on Oneprovider via ``__onedata.path`` or file id
        through ``get_file_id`` / ``get_file_attributes``.


        What to do when a query returns zero hits:
        Do not conclude the data is missing after one failed query. Retry with adjusted field paths.

        1. Inspect the index schema with `get_harvester_index_schema` and verify your chosen fields.

        2. Inspect a sample document: `POST` `_search` with `{"size": 1, "query": {"match_all": {}}}`
            and compare `_source` keys to the fields in your `term` / `bool` filters.

        3. Narrow the failure: drop one filter at a time to see which clause
            eliminates hits, then fix that field path only.

        4. Remember: a field visible in `_source` is not always searchable — if `term` still
            returns zero after the steps above, the value may exist only in stored JSON; use
            `get_file_metadata` on the file path from `__onedata` when the task needs file truth.
        """
        return await query_harvester_index(harvester_id, index_id, query)
