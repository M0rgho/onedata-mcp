import asyncio
import json
from typing import Any, Literal

from onedata_mcp.api.spaces import list_available_spaces
from onedata_mcp.config import get_onezone_config
from onedata_mcp.utils import request


def build_onezone_harvester_query(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build Onezone ``HarvesterQuery`` JSON (``body`` serialized as a string)."""
    payload: dict[str, Any] = {"method": method.lower(), "path": path}
    if body is not None:
        payload["body"] = json.dumps(body, separators=(",", ":"))
    return payload


def harvester_es_search_query(es_body: dict[str, Any]) -> dict[str, Any]:
    """Elasticsearch ``_search`` request body for ``query_harvester_index`` (``POST``)."""
    return es_body


async def get_user_harvester(harvester_id: str) -> dict[str, Any]:
    config = get_onezone_config()
    response = await request(config, "GET", f"/user/harvesters/{harvester_id}")
    return response["body"]


async def list_harvester_indices(harvester_id: str) -> list[str]:
    config = get_onezone_config()
    response = await request(config, "GET", f"/harvesters/{harvester_id}/indices")
    return response["body"]["indices"]


async def list_harvester_spaces(harvester_id: str) -> list[str]:
    """Space ids linked to the harvester (metadata sources). See ``GET /harvesters/{id}/spaces``."""
    config = get_onezone_config()
    response = await request(config, "GET", f"/harvesters/{harvester_id}/spaces")
    return response["body"]["spaces"]


async def get_harvester_index(harvester_id: str, index_id: str) -> dict[str, Any]:
    config = get_onezone_config()
    response = await request(config, "GET", f"/harvesters/{harvester_id}/indices/{index_id}")
    return response["body"]


def _without_schema(index_details: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in index_details.items() if key != "schema"}


async def _space_id_to_name_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for space in await list_available_spaces():
        space_id = space.get("spaceId")
        name = space.get("name")
        if isinstance(space_id, str) and isinstance(name, str):
            mapping[space_id] = name
    return mapping


def _space_ids_for_name_substring(space_name: str, id_to_name: dict[str, str]) -> frozenset[str]:
    needle = space_name.strip().casefold()
    if not needle:
        return frozenset()
    return frozenset(space_id for space_id, name in id_to_name.items() if needle in name.casefold())


def _attached_spaces_payload(
    space_ids: list[str], id_to_name: dict[str, str]
) -> list[dict[str, str | None]]:
    return [
        {
            "space_id": space_id,
            "space_name": id_to_name.get(space_id),
        }
        for space_id in space_ids
        if isinstance(space_id, str)
    ]


def _attached_space_ids(harvester: dict[str, Any]) -> list[str]:
    attached = harvester.get("attached_spaces")
    if not isinstance(attached, list):
        return []
    ids: list[str] = []
    for item in attached:
        if isinstance(item, str):
            ids.append(item)
        elif isinstance(item, dict):
            space_id = item.get("space_id")
            if isinstance(space_id, str):
                ids.append(space_id)
    return ids


def _harvester_attached_to_any_space(harvester: dict[str, Any], space_ids: frozenset[str]) -> bool:
    return any(space_id in space_ids for space_id in _attached_space_ids(harvester))


async def list_user_harvesters(*, space_name: str | None = None) -> list[dict[str, Any]]:
    id_to_name = await _space_id_to_name_map()

    matching_space_ids: frozenset[str] | None = None
    if space_name is not None and space_name.strip():
        matching_space_ids = _space_ids_for_name_substring(space_name, id_to_name)
        if not matching_space_ids:
            return []

    config = get_onezone_config()
    response = await request(config, "GET", "/user/harvesters")
    harvester_ids = response["body"]["harvesters"]

    async def _fetch_harvester_with_indices(harvester_id: str) -> dict[str, Any]:
        harvester, index_ids, attached_spaces = await asyncio.gather(
            get_user_harvester(harvester_id),
            list_harvester_indices(harvester_id),
            list_harvester_spaces(harvester_id),
        )
        index_details = await asyncio.gather(
            *(get_harvester_index(harvester_id, index_id) for index_id in index_ids)
        )
        harvester["indices"] = [_without_schema(index) for index in index_details]
        harvester["attached_spaces"] = _attached_spaces_payload(attached_spaces, id_to_name)
        return harvester

    result = await asyncio.gather(*(_fetch_harvester_with_indices(hid) for hid in harvester_ids))

    if matching_space_ids is None:
        return list(result)

    return [
        harvester
        for harvester in result
        if _harvester_attached_to_any_space(harvester, matching_space_ids)
    ]


async def get_harvester_index_schema(harvester_id: str, index_id: str) -> dict[str, Any]:
    return await get_harvester_index(harvester_id, index_id)


def unwrap_harvester_query_response(payload: Any) -> Any:
    """Parse Onezone ``HarvesterQueryResponse`` (ES JSON in ``body`` string) to a dict."""
    if not isinstance(payload, dict):
        return payload
    if "hits" in payload:
        return payload
    inner = payload.get("body")
    if isinstance(inner, str):
        try:
            parsed: Any = json.loads(inner)
        except json.JSONDecodeError:
            return payload
        return parsed if isinstance(parsed, dict) else payload
    if isinstance(inner, dict):
        return inner
    return payload


async def query_harvester_index(
    harvester_id: str,
    index_id: str,
    method: Literal["get", "post"] | str,
    path: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = get_onezone_config()
    onezone_query = build_onezone_harvester_query(method, path, body)
    response = await request(
        config,
        "POST",
        f"/harvesters/{harvester_id}/indices/{index_id}/query",
        json_body=onezone_query,
    )
    raw = response["body"]
    unwrapped = unwrap_harvester_query_response(raw)
    return unwrapped if isinstance(unwrapped, dict) else raw
