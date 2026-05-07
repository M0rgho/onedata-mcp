from typing import Any, Optional

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
    list_children,
    list_files_recursively,
    set_file_metadata,
)


def register_module(mcp: FastMCP) -> None:
    """Register onedata files module tools and prompts with the MCP server."""

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
            (Optional) List of attribute names to request from Oneprovider. 
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

    @mcp.tool(name="list_children", annotations=ToolAnnotations(readOnlyHint=True))
    async def mcp_list_children(
        parent_id_or_path: str = Field(
            description="File id or path to the parent file in format /<space_name>/<path_to_file>"
        ),
        *,
        attributes: Optional[list[str]] = Field(
            default=None,
            description="""
            (Optional) List of attribute names to request from Oneprovider. 
            Use the same allowed values as in get_file_attributes.
            """,
        ),
        limit: int = Field(
            default=10,
            ge=1,
            le=100,
            description="Maximum number of children",
        ),
        offset: int = Field(
            default=0,
            description="Starting offset of the children",
        ),
        token: Optional[str] = Field(
            default=None,
            description="Token to continue listing from the next page of results",
        ),
    ) -> dict[str, Any]:
        """
        List children (files and directories) of a given file id or path.

        """
        return await list_children(
            parent_id_or_path, attributes=attributes, limit=limit, offset=offset, token=token
        )

    @mcp.tool(name="list_files_recursively", annotations=ToolAnnotations(readOnlyHint=True))
    async def mcp_list_files_recursively(
        parent_id_or_path: str = Field(
            description="File id or path to the parent file in format /<space_name>/<path_to_file>"
        ),
        *,
        attributes: Optional[list[str]] = Field(
            default=None,
            description="""
            (Optional) List of attribute names to request from Oneprovider. 
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
        return await list_files_recursively(
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

    @mcp.tool(name="create_file", annotations=ToolAnnotations(destructiveHint=True))
    async def mcp_create_file(
        path: str = Field(description="Path to the file in format /<space_name>/<path_to_file>"),
        content: str = Field(
            description="Content of the file as a string",
        ),
        create_parents: bool = Field(
            default=False,
            description="Create missing directories under the space root via Oneprovider path API",
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

    @mcp.tool(name="get_file_metadata", annotations=ToolAnnotations(readOnlyHint=True))
    async def mcp_get_file_metadata(
        file_id_or_path: str = Field(
            description="File id or path to the file in format /<space_name>/<path_to_file>"
        ),
        metadata_types: list[str] = Field(
            description="List of metadata types to get",
            default=["json", "rdf", "xattrs"],
        ),
    ) -> dict[str, Any]:
        """
        Get metadata for a given file id or path by metadata types.

        For many metadata values from a single request, use
        get_file_attributes with metadata-related attributes.
        """
        return await get_file_metadata(file_id_or_path, metadata_types)

    @mcp.tool(name="set_file_metadata", annotations=ToolAnnotations(destructiveHint=True))
    async def mcp_set_file_metadata(
        file_id_or_path: str = Field(
            description="File id or path to the file in format /<space_name>/<path_to_file>"
        ),
        metadata_type: str = Field(
            description="Metadata type to set",
        ),
        metadata: str = Field(
            description="Metadata content to set",
        ),
    ) -> None:
        """
        Set metadata for a given file id or path by metadata type.
        """
        return await set_file_metadata(file_id_or_path, metadata_type, metadata)
