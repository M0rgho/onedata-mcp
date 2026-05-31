from typing import Any, Literal, Optional

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from onedata_mcp.api.files import (
    create_file,
    delete_file,
    download_file,
    get_file_attributes,
    get_file_id,
    get_file_metadata,
    grep_file_content,
    list_files,
    list_files_recursive,
    set_file_metadata,
    set_file_xattrs,
)

# Body stored on the file — not the facet wrapper returned by get_file_metadata.
type JsonMetadataDocument = dict[str, Any] | list[Any]
type FileMetadataPayload = str | JsonMetadataDocument


def register_module(mcp: FastMCP, *, register_writers: bool = True) -> None:
    """Register onedata files module tools and prompts with the MCP server."""

    _register_read_tools(mcp)
    if register_writers:
        _register_write_tools(mcp)


def _register_read_tools(mcp: FastMCP) -> None:

    @mcp.tool(name="get_file_id", annotations=ToolAnnotations(readOnlyHint=True))
    async def mcp_get_file_id(
        path: str = Field(description="Path to the file in format /<space_name>/<path_to_file>"),
    ) -> str:
        """
        Get the file id for a given path.
        """
        return await get_file_id(path)

    @mcp.tool(name="get_file_attributes", annotations=ToolAnnotations(readOnlyHint=True))
    async def mcp_get_file_attributes(
        file_id_or_path: str = Field(
            description="File id or path to the file in format /<space_name>/<path_to_file>"
        ),
        attributes: Optional[list[str]] = Field(
            default=None,
            description="""
            (Optional) JSON array of attribute names to return for the file.
            Allowed values:
            - Identity/location: fileId, parentFileId, index, name, conflictingName, path, type
            - Permissions/access: activePermissionsType, posixPermissions, acl
            - Ownership/provider/shares: ownerUserId, originProviderId, directShareIds
            - Links: hardlinkCount, symlinkValue
            - Display ids: displayUid, displayGid
            - Timestamps/size: creationTime, atime, mtime, ctime, size
            - Replication: isFullyReplicatedLocally, localReplicationRate
            - Metadata: hasCustomMetadata, hasJsonMetadata, jsonMetadata, xattr.*
            """,
        ),
    ) -> dict[str, Any]:
        """
        Get attributes for a file id or a logical path.
        """
        return await get_file_attributes(file_id_or_path, attributes=attributes)

    @mcp.tool(name="list_files", annotations=ToolAnnotations(readOnlyHint=True))
    async def mcp_list_files(
        parent_id_or_path: str = Field(
            description="File id or path to the parent file in format /<space_name>/<path_to_file>"
        ),
        *,
        attributes: Optional[list[str]] = Field(
            default=None,
            description="""
            (Optional) Additional attribute names to return for each child.
            Use the same allowed values as in get_file_attributes.
            """,
        ),
        limit: int = Field(
            default=10,
            ge=1,
            le=100,
            description="Maximum number of items to return (files and subdirectories)",
        ),
        offset: int = Field(
            default=0,
            description="Offset into the shallow listing page",
        ),
        token: Optional[str] = Field(
            default=None,
            description="Token to continue listing from the next page of results",
        ),
    ) -> dict[str, Any]:
        """
        Shallow listing: a single level of files and subdirectories under the path or id.

        Not for locating one known filename in a large folder — use `get_file_metadata` on the
        logical path, the harvester index (check `get_harvester_index_schema` first; exact match
        is often on `__onedata.fileName.keyword`), or `list_files_recursive`.
        """
        return await list_files(
            parent_id_or_path, attributes=attributes, limit=limit, offset=offset, token=token
        )

    @mcp.tool(name="list_files_recursive", annotations=ToolAnnotations(readOnlyHint=True))
    async def mcp_list_files_recursive(
        parent_id_or_path: str = Field(
            description="File id or path to the parent file in format /<space_name>/<path_to_file>"
        ),
        *,
        attributes: Optional[list[str]] = Field(
            default=None,
            description="""
            (Optional) Additional attribute names to return for each listed file.
            Use the same allowed values as in get_file_attributes.
            """,
        ),
        limit: int = Field(
            default=10,
            ge=1,
            le=100,
            description="Maximum number of files to return",
        ),
        token: Optional[str] = Field(
            default=None,
            description="Token to continue listing from the next page of results",
        ),
        start_after: Optional[str] = Field(
            default=None,
            description=(
                "Start listing from first file path lexicographically greater than this value"
            ),
        ),
        prefix: Optional[str] = Field(
            default=None,
            description="Only files with paths starting with this value are listed",
        ),
    ) -> dict[str, Any]:
        """
        Recursively list non-directory files under a given file id or path.
        """
        return await list_files_recursive(
            parent_id_or_path,
            attributes=attributes,
            limit=limit,
            token=token,
            start_after=start_after,
            prefix=prefix,
        )

    @mcp.tool(name="download_file", annotations=ToolAnnotations(readOnlyHint=True))
    async def mcp_download_file(
        file_id_or_path: str = Field(
            description="File id or path to the file in format /<space_name>/<path_to_file>"
        ),
    ) -> bytes:
        """
        Download the content of a given file id or path.
        """
        return await download_file(file_id_or_path)

    @mcp.tool(name="grep_file_content", annotations=ToolAnnotations(readOnlyHint=True))
    async def mcp_grep_file_content(
        file_id_or_path: str = Field(
            description="File id or path to the file in format /<space_name>/<path_to_file>"
        ),
        pattern: str = Field(
            description="Pattern to search for in the file content",
        ),
    ) -> str:
        """
        Search for a pattern in the content of a given file id or path.
        """
        return await grep_file_content(file_id_or_path, pattern)

    @mcp.tool(name="get_file_metadata", annotations=ToolAnnotations(readOnlyHint=True))
    async def mcp_get_file_metadata(
        file_id_or_path: str = Field(
            description="File id or path to the file in format /<space_name>/<path_to_file>"
        ),
        metadata_types: list[str] = Field(
            description=(
                "Which facets to fetch. Allowed names (multiple allowed): `json`, `rdf`, `xattrs`."
            ),
            default=["json", "rdf", "xattrs"],
        ),
    ) -> dict[str, Any]:
        """
        Get metadata for a given file id or path by metadata types.

        For many metadata values from a single request, use
        get_file_attributes with metadata-related attributes.
        """
        return await get_file_metadata(file_id_or_path, metadata_types)


def _register_write_tools(mcp: FastMCP) -> None:
    @mcp.tool(name="create_file", annotations=ToolAnnotations(destructiveHint=True))
    async def mcp_create_file(
        path: str = Field(description="Path to the file in format /<space_name>/<path_to_file>"),
        content: str = Field(
            description="Content of the file as a string",
        ),
        create_parents: bool = Field(
            default=False,
            description="Create missing parent directories along the path (under the space root)",
        ),
    ) -> str:
        """
        Create a new file with the given content.

        Returns the file id of the created file.
        """
        return await create_file(path, content, create_parents=create_parents)

    @mcp.tool(name="delete_file", annotations=ToolAnnotations(destructiveHint=True))
    async def mcp_delete_file(
        file_id_or_path: str = Field(
            description="File id or path to the file in format /<space_name>/<path_to_file>"
        ),
    ) -> None:
        """
        Delete a given file or directory (recursively) by id or path.
        """
        return await delete_file(file_id_or_path)

    @mcp.tool(name="set_file_xattrs")
    async def mcp_set_file_xattrs(
        file_id_or_path: str = Field(
            description="File id or path to the file in format /<space_name>/<path_to_file>"
        ),
        xattrs: dict[str, str] | str = Field(
            description=(
                "Extended attributes: keys map to string values only "
                "(omitted keys are left unchanged). "
                "Use this rather than `set_file_metadata` for extended attributes. "
                "You may send a JSON object string instead, e.g. "
                '\'{"license": "CC-0"}\'. The payload must be a JSON object.'
            ),
        ),
    ) -> None:
        """
        Merge file extended attributes without replacing JSON or RDF metadata.
        """
        return await set_file_xattrs(file_id_or_path, xattrs)

    @mcp.tool(name="set_file_metadata", annotations=ToolAnnotations(destructiveHint=True))
    async def mcp_set_file_metadata(
        file_id_or_path: str = Field(
            description="File id or path to the file in format /<space_name>/<path_to_file>"
        ),
        metadata_type: Literal["json", "rdf"] = Field(
            description=(
                'Which facet to replace: `"json"` (JSON document) or `"rdf"` (RDF/XML string).'
            ),
        ),
        metadata: FileMetadataPayload = Field(
            description=(
                "New value for the chosen facet — whole-document replacement (not a patch). "
                'For `metadata_type` `"json"`: pass the JSON object or array itself, e.g. '
                '`{"version": 2, "title": "E2E"}`, or a UTF-8 JSON string of that value. '
                'Do not wrap it in `{"json": ...}`; that outer key is only in '
                "`get_file_metadata` responses."
                'For `metadata_type` `"rdf"`: pass one RDF/XML string.'
            ),
        ),
    ) -> None:
        """
        Replace JSON or RDF file metadata for one facet.

        The `metadata` argument is the stored document body, not the `get_file_metadata`
        response envelope. Omitted keys are removed — include every field you want kept.
        """
        return await set_file_metadata(file_id_or_path, metadata_type, metadata)
