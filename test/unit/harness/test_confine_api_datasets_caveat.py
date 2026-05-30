"""Confined MCP tokens use data.path only (dataset catalog is not available under that caveat)."""

from __future__ import annotations

from typing import Any

import pytest
from e2e_isolated_space import confine_provider_token


@pytest.mark.asyncio
async def test_confine_readonly_uses_data_path_only(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_onezone(
        method: str, path: str, *, json_body: dict[str, Any] | None = None
    ) -> Any:
        _ = method
        captured["json_body"] = json_body
        return {"body": {"token": "confined"}}

    monkeypatch.setattr("e2e_isolated_space._onezone", fake_onezone)

    await confine_provider_token("base", "test-space", space_name="mcp-e2e-demo", readonly=True)
    caveats = captured["json_body"]["caveats"]
    types = [c["type"] for c in caveats]
    assert "data.path" in types
    assert "data.readonly" in types
    assert "data.objectid" not in types
    assert "api" not in types
