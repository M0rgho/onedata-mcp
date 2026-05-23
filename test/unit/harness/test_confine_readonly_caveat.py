"""Unit tests for confined-token caveat selection."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from e2e_isolated_space import confine_provider_token


@pytest.mark.asyncio
async def test_confine_readonly_adds_data_readonly_caveat(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_onezone(
        method: str, path: str, *, json_body: dict[str, Any] | None = None
    ) -> Any:
        _ = method
        captured["path"] = path
        captured["json_body"] = json_body
        return {"body": {"token": "confined-serialized"}}

    monkeypatch.setattr("e2e_isolated_space._onezone", fake_onezone)

    token = await confine_provider_token(
        "base-token",
        "space-id-abc",
        space_name="mcp-e2e-demo",
        readonly=True,
    )
    assert token == "confined-serialized"
    caveats = captured["json_body"]["caveats"]
    types = [c["type"] for c in caveats]
    assert "data.readonly" in types
    assert "data.path" in types


@pytest.mark.asyncio
async def test_confine_write_omits_data_readonly_caveat(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_onezone(
        method: str, path: str, *, json_body: dict[str, Any] | None = None
    ) -> Any:
        _ = method
        captured["json_body"] = json_body
        return {"body": {"token": "confined-rw"}}

    monkeypatch.setattr("e2e_isolated_space._onezone", fake_onezone)

    await confine_provider_token("base", "sid", readonly=False)
    types = [c["type"] for c in captured["json_body"]["caveats"]]
    assert "data.readonly" not in types
