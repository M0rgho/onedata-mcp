"""Onezone token introspection (``POST /tokens/examine``, etc.)."""

from __future__ import annotations

from typing import Any

from onedata_mcp.config import get_onezone_config
from onedata_mcp.utils import request


async def examine_access_token(token: str) -> dict[str, Any]:
    """Return caveats and metadata inferred from a serialized macaroon (no verification)."""

    response = await request(
        get_onezone_config(),
        "POST",
        "/tokens/examine",
        json_body={"token": token},
    )
    body = response["body"]
    if not isinstance(body, dict):
        msg = "tokens/examine: expected object body"
        raise TypeError(msg)
    return body


def token_has_data_readonly_caveat(examined: dict[str, Any]) -> bool:
    """True when the token carries a ``data.readonly`` caveat."""

    caveats = examined.get("caveats")
    if not isinstance(caveats, list):
        return False
    return any(isinstance(c, dict) and c.get("type") == "data.readonly" for c in caveats)
