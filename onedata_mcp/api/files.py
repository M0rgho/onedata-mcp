from ast import If
import json
from asyncio.log import logger
from collections.abc import Iterable, Mapping, Sequence
from typing import Any
from urllib.parse import quote

import httpx

from onedata_mcp.api.spaces import list_available_spaces
from onedata_mcp.config import get_oneprovider_config
from onedata_mcp.utils import OnedataApiError, OnedataInvalidSpaceError, request

ONEPROVIDER_FILE_LISTING_ALLOWED_NAMES = frozenset(
    {
        "activePermissionsType",
        "acl",
        "aggregateQosStatus",
        "archiveRecallRootFileId",
        "atime",
        "conflictingName",
        "creationTime",
        "ctime",
        "directShareIds",
        "displayGid",
        "displayUid",
        "effDatasetInheritancePath",
        "effDatasetProtectionFlags",
        "effProtectionFlags",
        "effQosInheritancePath",
        "fileId",
        "hardlinkCount",
        "hasCustomMetadata",
        "hasJsonMetadata",
        "index",
        "isFullyReplicatedLocally",
        "jsonMetadata",
        "localReplicationRate",
        "mtime",
        "name",
        "originProviderId",
        "ownerUserId",
        "parentFileId",
        "path",
        "posixPermissions",
        "size",
        "symlinkValue",
        "type",
    }
)

_MINIMAL_FALLBACK_ATTRIBUTES = ("name", "type", "path", "size")

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

DEFAULT_FILE_ATTRIBUTE_KEYS = (
    "path",
    "name",
    "type",
    "size",
    "posixPermissions",
    "atime",
    "mtime",
)


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
        f"Deprecated attribute names are not supported. Use the new names instead: {replacements}"
    )


def _is_allowed_bulk_list_attribute(name: str) -> bool:
    return name.startswith("xattr.") or name in ONEPROVIDER_FILE_LISTING_ALLOWED_NAMES


def _sanitize_listing_attributes(attributes: Iterable[str] | None) -> list[str]:
    """
    Oneprovider rejects unknown ``attributes`` on ``/children`` and ``/files`` with 400.

    Canonicalize legacy synonyms, drop values outside the server's supported set,
    then fall back to a minimal safe tuple if nothing remains.
    """

    seq = tuple(attributes or DEFAULT_FILE_ATTRIBUTE_KEYS)
    seen: dict[str, None] = {}
    result: list[str] = []
    for raw in seq:
        key = DEPRECATED_ATTRIBUTE_NAME_MAPPING.get(raw, raw)
        if not _is_allowed_bulk_list_attribute(key):
            logger.debug(f"Ignoring unsupported file listing attribute: {raw!r} -> {key!r}")
            continue
        if key not in seen:
            seen[key] = None
            result.append(key)
    if not result:
        for k in DEFAULT_FILE_ATTRIBUTE_KEYS:
            nk = DEPRECATED_ATTRIBUTE_NAME_MAPPING.get(k, k)
            if _is_allowed_bulk_list_attribute(nk):
                result.append(nk)
    if not result:
        result.extend(list(dict.fromkeys(_MINIMAL_FALLBACK_ATTRIBUTES)))
    return result


def _strip_deprecated_fields_in_list(
    response_body: dict[str, Any], list_key: str
) -> dict[str, Any]:
    items = response_body.get(list_key)
    if not isinstance(items, list):
        return response_body

    deprecated_keys = set(DEPRECATED_ATTRIBUTE_NAME_MAPPING.keys())
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in deprecated_keys:
            item.pop(key, None)

    return response_body


async def _list_provider_space_names() -> list[str]:
    try:
        spaces = await list_available_spaces()
        return sorted(
            {name for name in (space.get("name") for space in spaces) if isinstance(name, str)}
        )
    except Exception:
        return []


async def _raise_invalid_space_error_if_needed(error: OnedataApiError, path: str) -> None:
    if error.error_id != "spaceNotSupportedBy":
        return
    error_details = error.body.get("error", {}).get("details", {})
    requested_space_name = (
        error_details.get("spaceId") if isinstance(error_details.get("spaceId"), str) else None
    )
    if not requested_space_name and path.startswith("/"):
        requested_space_name = path.split("/")[1]

    space_names = await _list_provider_space_names()

    requested_part = (
        f'Space "{requested_space_name}" does not exist.'
        if requested_space_name
        else "Space does not exist."
    )
    quoted_names = ", ".join(f'"{name}"' for name in space_names)
    hint = f" Available spaces: {quoted_names}." if quoted_names else ""
    raise OnedataInvalidSpaceError(f"{requested_part}{hint}", response=error.response) from error


async def get_file_id(path: str) -> str:
    config = get_oneprovider_config()
    normalized_path = path if path.startswith("/") else f"/{path}"
    encoded_path = quote(normalized_path, safe="")
    try:
        response = await request(config, "POST", f"/lookup-file-id/{encoded_path}")
    except OnedataApiError as e:
        logger.debug(f"Error getting file id for path {path}: {e}")
        await _raise_invalid_space_error_if_needed(e, path)
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


def _looks_like_file_id(value: str) -> bool:
    return value.startswith("00000000") and len(value) == 180 and value.isalnum()


async def _normalize_path_to_file_id(file_id_or_path: str) -> str:
    """Resolve a logical path or opaque id through lookup-file-id; return opaque file ids unchanged."""
    if _looks_like_file_id(file_id_or_path):
        return file_id_or_path

    return await get_file_id(file_id_or_path)


async def list_files(
    parent_id_or_path: str,
    *,
    attributes: Iterable[str] | None = DEFAULT_FILE_ATTRIBUTE_KEYS,
    limit: int,
    offset: int,
    token: str | None = None,
) -> dict[str, Any]:
    config = get_oneprovider_config()
    parent_id = await _normalize_path_to_file_id(parent_id_or_path)
    requested_attributes = _sanitize_listing_attributes(attributes)
    request_body: dict[str, Any] = {"limit": limit, "offset": offset}
    if token is not None:
        request_body["token"] = token
    if requested_attributes:
        request_body["attributes"] = requested_attributes

    try:
        response = await request(
            config,
            "GET",
            f"/data/{parent_id}/children",
            json_body=request_body,
        )
    except OnedataApiError as e:
        await _raise_invalid_space_error_if_needed(e, parent_id_or_path)
        raise
    return _strip_deprecated_fields_in_list(response["body"], "children")


async def list_files_recursive(
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
    requested_attributes = _sanitize_listing_attributes(attributes)
    request_body: dict[str, Any] = {"limit": limit}
    if token is not None:
        request_body["token"] = token
    if start_after is not None:
        request_body["start_after"] = start_after
    if prefix is not None:
        request_body["prefix"] = prefix
    if requested_attributes:
        request_body["attributes"] = requested_attributes

    try:
        response = await request(
            config,
            "GET",
            f"/data/{parent_id}/files",
            json_body=request_body,
        )
    except OnedataApiError as e:
        await _raise_invalid_space_error_if_needed(e, parent_id_or_path)
        raise
    return _strip_deprecated_fields_in_list(response["body"], "files")


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


async def create_file(path: str, content: str, *, create_parents: bool = False) -> str:
    config = get_oneprovider_config()
    normalized = path.strip("/")

    if create_parents:
        if "/" not in normalized:
            raise ValueError(
                "path must be /<space_name>/<path_to_file> when create_parents is true"
            )
        space_name, relative_path = normalized.split("/", 1)
        if not relative_path:
            raise ValueError("path must include a file path under the space")
        root_id = await get_file_id(f"/{space_name}")
        encoded_path = quote(relative_path, safe="/")
        try:
            response = await request(
                config,
                "PUT",
                f"/data/{root_id}/path/{encoded_path}",
                params={"create_parents": True},
                body=content.encode("utf-8"),
                additional_headers={"Content-Type": "application/octet-stream"},
            )
        except OnedataApiError as e:
            if e.errno == "eexist":
                raise FileExistsError(f"File {path} already exists") from e
            logger.error(f"Error creating file {path}: {e}")
            raise e
        return response["body"]["fileId"]

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


MetadataSetPayload = str | bytes | Mapping[str, Any] | Sequence[Any]


def _xattrs_put_body(metadata: MetadataSetPayload) -> bytes:
    """Build JSON body for ``PUT .../metadata/xattrs`` (string-valued object only)."""

    raw: object
    if isinstance(metadata, bytes):
        raw = json.loads(metadata.decode("utf-8"))
    elif isinstance(metadata, str):
        raw = json.loads(metadata)
    elif isinstance(metadata, Mapping):
        raw = dict(metadata)
    else:
        msg = "xattrs metadata must be a JSON object (str, bytes, or dict), not a list"
        raise TypeError(msg)
    if not isinstance(raw, dict):
        msg = "xattrs body must be a JSON object mapping attribute names to string values"
        raise ValueError(msg)
    out: dict[str, str] = {}
    for key, val in raw.items():
        if not isinstance(key, str):
            msg = f"xattrs keys must be strings, not {type(key).__name__}"
            raise TypeError(msg)
        if not isinstance(val, str):
            msg = (
                f"xattrs values must be strings (Oneprovider schema); key {key!r} is "
                f"{type(val).__name__}. Encode structured data as a JSON string value if needed."
            )
            raise TypeError(msg)
        out[key] = val
    return json.dumps(out).encode("utf-8")


def _metadata_put_body(metadata_type: str, metadata: MetadataSetPayload) -> bytes:
    if metadata_type == "xattrs":
        return _xattrs_put_body(metadata)
    if isinstance(metadata, bytes):
        return metadata
    if isinstance(metadata, str):
        return metadata.encode("utf-8")
    if metadata_type == "rdf":
        msg = "RDF metadata body must be str or bytes"
        raise TypeError(msg)
    return json.dumps(metadata).encode("utf-8")


async def set_file_xattrs(file_id_or_path: str, xattrs: MetadataSetPayload) -> None:
    """Merge extended attributes (string values only).

    Same as calling :func:`set_file_metadata` with ``metadata_type='xattrs'``.
    Omitted keys are unchanged.
    """
    await set_file_metadata(file_id_or_path, "xattrs", xattrs)


async def set_file_metadata(
    file_id_or_path: str, metadata_type: str, metadata: MetadataSetPayload
) -> None:
    config = get_oneprovider_config()
    file_id = await _normalize_path_to_file_id(file_id_or_path)
    allowed_types = {"json", "rdf", "xattrs"}
    if metadata_type not in allowed_types:
        supported = ", ".join(sorted(allowed_types))
        msg = f"Unsupported metadata type: {metadata_type!r}. Supported types: {supported}"
        raise ValueError(msg)
    additional_headers = (
        {"Content-Type": "application/rdf+xml"}
        if metadata_type == "rdf"
        else {"Content-Type": "application/json"}
    )
    return await request(
        config,
        "PUT",
        f"/data/{file_id}/metadata/{metadata_type}",
        body=_metadata_put_body(metadata_type, metadata),
        additional_headers=additional_headers,
    )
