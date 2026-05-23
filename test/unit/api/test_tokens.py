"""Onezone token examine API."""

from __future__ import annotations

import json

import pytest
from pytest_httpx import HTTPXMock

from onedata_mcp.api.tokens import examine_access_token, token_has_data_readonly_caveat


def _set_onezone_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONEDATA_ONEZONE_HOST", "https://onezone.example")
    monkeypatch.setenv("ONEDATA_ONEZONE_TOKEN", "zone-token")
    monkeypatch.setenv("ONEDATA_ALLOW_INSECURE_TLS", "false")


@pytest.mark.asyncio
async def test_examine_access_token(monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock) -> None:
    _set_onezone_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url="https://onezone.example/api/v3/onezone/tokens/examine",
        json={
            "caveats": [
                {"type": "data.path", "whitelist": ["L3NwYWNl"]},
                {"type": "data.readonly"},
            ]
        },
    )

    examined = await examine_access_token("MDAx-provider-token")

    assert token_has_data_readonly_caveat(examined)
    request = httpx_mock.get_requests()[-1]
    assert json.loads(request.content) == {"token": "MDAx-provider-token"}


@pytest.mark.parametrize(
    ("caveats", "expected"),
    [
        ([{"type": "data.readonly"}], True),
        ([{"type": "data.path", "whitelist": []}], False),
        ([], False),
        (None, False),
    ],
)
def test_token_has_data_readonly_caveat(caveats: object, expected: bool) -> None:
    assert token_has_data_readonly_caveat({"caveats": caveats}) is expected
