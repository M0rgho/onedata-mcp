import asyncio
from typing import Any, Literal

from onedata_mcp.config import get_oneprovider_config
from onedata_mcp.utils import request

DatasetState = Literal["attached", "detached"]

_PROVIDER_SPACE_FIELDS = (
    "spaceId",
    "name",
    "providers",
)


def _map_provider_space(space: dict[str, Any]) -> dict[str, Any]:
    return {key: space.get(key) for key in _PROVIDER_SPACE_FIELDS}


async def list_available_spaces() -> list[dict[str, Any]]:
    """Spaces supported by this Oneprovider (``GET /spaces``, swagger-oneprovider.json)."""

    config = get_oneprovider_config()
    response = await request(config, "GET", "/spaces")
    body = response["body"]
    if not isinstance(body, list):
        return []
    return [_map_provider_space(space) for space in body if isinstance(space, dict)]


async def _resolve_space_id(space_id_or_name: str) -> str:
    key = space_id_or_name.strip().strip("/")
    if not key:
        msg = "space_id_or_name must be non-empty"
        raise ValueError(msg)

    for space in await list_available_spaces():
        name = space.get("name")
        space_id = space.get("spaceId")
        if key == name and isinstance(space_id, str):
            return space_id
        if key == space_id:
            return key

    return key


async def get_dataset(dataset_id: str) -> dict[str, Any]:
    """Dataset metadata (``GET /datasets/{did}``, swagger-oneprovider.json)."""

    config = get_oneprovider_config()
    response = await request(config, "GET", f"/datasets/{dataset_id}")
    return response["body"]


async def list_space_datasets(
    space_id_or_name: str,
    *,
    state: DatasetState = "attached",
    limit: int = 100,
    offset: int = 0,
    token: str | None = None,
) -> dict[str, Any]:
    """Top-level datasets in a space (``GET /spaces/{sid}/datasets``, swagger-oneprovider.json)."""

    if state not in ("attached", "detached"):
        msg = "state must be 'attached' or 'detached'"
        raise ValueError(msg)
    if limit < 1 or limit > 1000:
        msg = "Parameter 'limit' must be between 1 and 1000"
        raise ValueError(msg)

    space_id = await _resolve_space_id(space_id_or_name)
    params: dict[str, Any] = {
        "state": state,
        "limit": limit,
        "offset": offset,
    }
    if token is not None:
        params["token"] = token

    config = get_oneprovider_config()
    response = await request(
        config,
        "GET",
        f"/spaces/{space_id}/datasets",
        params=params,
    )
    listing = response["body"]
    if not isinstance(listing, dict):
        return {"datasets": []}

    listed = listing.get("datasets")
    if not isinstance(listed, list) or not listed:
        return {
            "datasets": [],
            "nextPageToken": listing.get("nextPageToken"),
        }

    dataset_ids = [
        entry["datasetId"]
        for entry in listed
        if isinstance(entry, dict) and isinstance(entry.get("datasetId"), str)
    ]
    details = await asyncio.gather(*(get_dataset(dataset_id) for dataset_id in dataset_ids))

    enriched: list[dict[str, Any]] = []
    detail_by_id = dict(zip(dataset_ids, details, strict=True))
    for entry in listed:
        if not isinstance(entry, dict):
            continue
        dataset_id = entry.get("datasetId")
        if not isinstance(dataset_id, str):
            enriched.append(dict(entry))
            continue
        enriched.append({**entry, **detail_by_id[dataset_id]})

    return {
        "datasets": enriched,
        "nextPageToken": listing.get("nextPageToken"),
    }
