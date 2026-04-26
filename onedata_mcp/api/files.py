from asyncio.log import logger
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote

import httpx

from onedata_mcp.config import get_oneprovider_config
from onedata_mcp.utils import OnedataApiError, OnedataInvalidSpaceError, request

DEFAULT_FILE_ATTRIBUTE_KEYS = (
    "fileId",
    "path",
    "parentFileId",
    "name",
    "type",
    "size",
    "posixPermissions",
    # "ownerUserId",
    "originProviderId",
    "atime",
    "mtime",
    "ctime",
    "hardlinkCount",
)

DEPRECATED_ATTRIBUTE_NAME_MAPPING = {
    "file_id": "fileId",
    "mode": "posixPermissions",
    "parent_id": "parentFileId",
    "storage_group_id": "displayGid",
    "storage_user_id": "displayUid",
    "is_fully_replicated": "isFullyReplicatedLocally",
    "provider_id": "originProviderId",
    "shares": "directShareIds",
    "owner_id": "ownerUserId",
    "hardlinks_count": "hardlinkCount",
}


def _reject_deprecated_attributes(attributes: Iterable[str] | None) -> None:
    if attributes is None:
        return

    deprecated = [attr for attr in attributes if attr in DEPRECATED_ATTRIBUTE_NAME_MAPPING]
    if not deprecated:
        return

    replacements = ", ".join(
        f"{old}->{DEPRECATED_ATTRIBUTE_NAME_MAPPING[old]}" for old in sorted(set(deprecated))
    )
    raise ValueError(
        "Deprecated attribute names are not supported. "
        f"Use the new names instead: {replacements}"
    )


async def _raise_invalid_space_error_if_needed(error: OnedataApiError) -> None:
    if error.error_id != "spaceNotSupportedBy":
        return

    # Local import to avoid circular dependency between API modules.
    from onedata_mcp.api.spaces import list_user_spaces

    try:
        spaces = await list_user_spaces()
        space_names = sorted(
            {space["name"] for space in spaces if isinstance(space.get("name"), str)}
        )
    except Exception:
        space_names = []

    hint = f" Available spaces: {', '.join(space_names)}." if space_names else ""
    raise OnedataInvalidSpaceError(f"Space does not exist.{hint}", response=error.response) from error


async def get_file_id(path: str) -> str:
    config = get_oneprovider_config()
    normalized_path = path if path.startswith("/") else f"/{path}"
    encoded_path = quote(normalized_path, safe="")
    try:
        response = await request(config, "POST", f"/lookup-file-id/{encoded_path}")
    except OnedataApiError as e:
        if e.errno == "enoent":
            raise FileNotFoundError(f'Path "{path}" not found') from e
        raise
    return response["body"]["fileId"]


async def get_file_attributes(
    file_id_or_path: str,
    *,
    attributes: Iterable[str] | None = DEFAULT_FILE_ATTRIBUTE_KEYS,
) -> dict[str, Any]:
    config = get_oneprovider_config()
    requested_attributes = tuple[str, ...](attributes or DEFAULT_FILE_ATTRIBUTE_KEYS)

    file_id = await _normalize_path_to_file_id(file_id_or_path)
    response = await request(
        config,
        "GET",
        f"/data/{file_id}",
        json_body=({"attributes": list(requested_attributes)} if requested_attributes else None),
    )
    logger.debug(f"Fetched file attributes for file {file_id_or_path}: {response['body']}")
    return response["body"]


async def _normalize_path_to_file_id(file_id_or_path: str) -> str:
    if not file_id_or_path.startswith("/"):
        return file_id_or_path

    return await get_file_id(file_id_or_path)


async def list_children(
    parent_id_or_path: str,
    *,
    attributes: Iterable[str] | None = DEFAULT_FILE_ATTRIBUTE_KEYS,
    limit: int,
    offset: int,
    token: str | None = None,
) -> dict[str, Any]:
    config = get_oneprovider_config()
    parent_id = await _normalize_path_to_file_id(parent_id_or_path)
    _reject_deprecated_attributes(attributes)
    request_body: dict[str, Any] = {"limit": limit, "offset": offset}
    if token is not None:
        request_body["token"] = token
    if attributes is not None:
        request_body["attributes"] = list(attributes)

    try:
        response = await request(
            config,
            "GET",
            f"/data/{parent_id}/children",
            json_body=request_body,
        )
    except OnedataApiError as e:
        await _raise_invalid_space_error_if_needed(e)
        raise
    return response["body"]


async def list_files_recursively(
    parent_id_or_path: str,
    *,
    attributes: Iterable[str] | None = DEFAULT_FILE_ATTRIBUTE_KEYS,
    limit: int,
    token: str | None = None,
    start_after: str | None = None,
    prefix: str | None = None,
) -> dict[str, Any]:
    config = get_oneprovider_config()
    parent_id = await _normalize_path_to_file_id(parent_id_or_path)
    _reject_deprecated_attributes(attributes)
    request_body: dict[str, Any] = {"limit": limit}
    if token is not None:
        request_body["token"] = token
    if start_after is not None:
        request_body["start_after"] = start_after
    if prefix is not None:
        request_body["prefix"] = prefix
    if attributes is not None:
        request_body["attributes"] = list(attributes)

    try:
        response = await request(
            config,
            "GET",
            f"/data/{parent_id}/files",
            json_body=request_body,
        )
    except OnedataApiError as e:
        await _raise_invalid_space_error_if_needed(e)
        raise
    return response["body"]


async def download_file(file_id_or_path: str) -> bytes:
    config = get_oneprovider_config()
    file_id = await _normalize_path_to_file_id(file_id_or_path)

    file_attributes = await get_file_attributes(file_id_or_path)
    if file_attributes["type"] == "DIR":
        raise ValueError("Cannot download content of a directory")

    if file_attributes["size"] > 5 * 1024 * 1024:
        size_in_mb = file_attributes["size"] / 1024 / 1024
        raise ValueError(
            f"File size is too large to download (max 5MB), actual: {size_in_mb:.2f}MB"
        )

    headers = dict(config.auth_headers)
    headers["Accept"] = "*/*"
    headers.pop("Content-Type", None)

    async with httpx.AsyncClient(
        base_url=config.base_url, headers=headers, verify=config.verify_ssl
    ) as client:
        response = await client.get(f"/data/{file_id}/content")

    if response.is_error:
        raise RuntimeError(
            f"Onedata API request failed: GET /data/{file_id}/content "
            f"(status={response.status_code}) - {response.text}"
        )

    return response.content


async def grep_file_content(
    file_id_or_path: str,
    pattern: str,
) -> str:

    content = await download_file(file_id_or_path)
    content_str = content.decode("utf-8", errors="replace")
    return "\n".join(line for line in content_str.splitlines() if pattern in line)


async def create_file(path: str, content: str) -> str:
    config = get_oneprovider_config()
    parent_path, file_name = path.rsplit("/", 1)

    parent_id = await _normalize_path_to_file_id(parent_path)

    try:
        response = await request(
            config,
            "POST",
            f"/data/{parent_id}/children",
            params={"name": file_name, "type": "REG"},
            body=content.encode("utf-8"),
            additional_headers={"Content-Type": "application/octet-stream"},
        )
        return response["body"]["fileId"]
    except OnedataApiError as e:
        if e.errno == "eexist":
            raise FileExistsError(f"File {path} already exists") from e

        logger.error(f"Error creating file {path}: {e}")
        raise e


async def delete_file(file_id_or_path: str) -> None:
    config = get_oneprovider_config()
    file_id = await _normalize_path_to_file_id(file_id_or_path)
    await request(config, "DELETE", f"/data/{file_id}")


async def get_file_metadata(file_id_or_path: str, metadata_types: list[str]) -> dict[str, Any]:
    config = get_oneprovider_config()
    file_id = await _normalize_path_to_file_id(file_id_or_path)
    allowed_types = {"json", "rdf", "xattrs"}

    invalid_types = sorted(set(metadata_types) - allowed_types)
    if invalid_types:
        supported = ", ".join(sorted(allowed_types))
        invalid = ", ".join(invalid_types)
        raise ValueError(f"Unsupported metadata type(s): {invalid}. Supported types: {supported}")

    result: dict[str, Any] = {}
    for metadata_type in metadata_types:
        try:
            additional_headers = (
                {"Accept": "application/rdf+xml"} if metadata_type == "rdf" else None
            )
            response = await request(
                config,
                "GET",
                f"/data/{file_id}/metadata/{metadata_type}",
                additional_headers=additional_headers,
            )
            result[metadata_type] = response["body"]
        except OnedataApiError as e:
            if e.errno == "enodata":
                result[metadata_type] = None
                continue
            raise

    return result


async def set_file_metadata(
    file_id_or_path: str, metadata_type: str, metadata: str | bytes
) -> None:
    config = get_oneprovider_config()
    file_id = await _normalize_path_to_file_id(file_id_or_path)
    additional_headers = (
        {"Content-Type": "application/rdf+xml"}
        if metadata_type == "rdf"
        else {"Content-Type": "application/json"}
    )
    return await request(
        config,
        "PUT",
        f"/data/{file_id}/metadata/{metadata_type}",
        body=metadata if isinstance(metadata, bytes) else metadata.encode("utf-8"),
        additional_headers=additional_headers,
    )
