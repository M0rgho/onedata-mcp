from typing import Any

from onedata_mcp.config import get_oneprovider_config
from onedata_mcp.utils import request

_PROVIDER_SPACE_FIELDS = (
    "spaceId",
    "name",
    "providers",
    "dirId",
    "trashDirId",
    "archivesDirId",
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
