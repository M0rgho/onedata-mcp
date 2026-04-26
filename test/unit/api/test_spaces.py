import pytest
from pytest_httpx import HTTPXMock

from onedata_mcp.api import spaces


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONEDATA_ONEZONE_HOST", "https://onezone.example")
    monkeypatch.setenv("ONEDATA_ONEZONE_TOKEN", "token")
    monkeypatch.setenv("ONEDATA_ALLOW_INSECURE_TLS", "false")


@pytest.mark.asyncio
async def test_get_space_details_returns_response_body(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/spaces/sp1",
        json={
            "spaceId": "sp1",
            "name": "Space One",
            "description": "desc",
            "providers": {"p1": {}},
            "organizationName": "Org",
            "creationTime": 1700000000,
            "tags": ["a", "b"],
        },
    )

    result = await spaces.get_space_details("sp1")

    assert result["spaceId"] == "sp1"
    assert result["name"] == "Space One"


@pytest.mark.asyncio
async def test_list_user_spaces_fetches_ids_and_details_and_maps_fields(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/spaces",
        json={"spaces": ["sp1", "sp2"]},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/spaces/sp1",
        json={
            "spaceId": "sp1",
            "name": "Space One",
            "description": "desc1",
            "providers": {"p1": {}},
            "organizationName": "Org1",
            "creationTime": 1700000001,
            "tags": ["tag1"],
            "ignoredField": "ignored",
        },
    )
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/spaces/sp2",
        json={
            "spaceId": "sp2",
            "name": "Space Two",
            "description": "desc2",
            "providers": {"p2": {}},
            "organizationName": "Org2",
            "creationTime": 1700000002,
            "tags": [],
        },
    )

    result = await spaces.list_user_spaces()

    assert len(result) == 2
    assert result[0] == {
        "tags": ["tag1"],
        "description": "desc1",
        "spaceId": "sp1",
        "providers": {"p1": {}},
        "organizationName": "Org1",
        "name": "Space One",
        "creationTime": 1700000001,
    }
    assert result[1]["spaceId"] == "sp2"
    assert "ignoredField" not in result[0]


@pytest.mark.asyncio
async def test_list_user_spaces_returns_empty_when_no_spaces(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/spaces",
        json={"spaces": []},
    )

    result = await spaces.list_user_spaces()

    assert result == []


@pytest.mark.asyncio
async def test_get_marketplace_space_details_returns_response_body(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/spaces/marketplace/sp1",
        json={
            "name": "Meteo dataset",
            "index": "Meteo dataset@2c0160248ba9a66f45da751ca459535a",
            "description": "Meteorological data for major Polish cities.",
            "organizationName": "ACK Cyfronet AGH",
            "tags": ["archival", "big-data", "open-data", "environment"],
            "providerNames": ["krakow", "paris"],
            "totalSupportSize": 30500000000,
            "creationTime": 1576152793,
        },
    )

    result = await spaces.get_marketplace_space_details("sp1")

    assert result["name"] == "Meteo dataset"
    assert result["organizationName"] == "ACK Cyfronet AGH"
    assert result["providerNames"] == ["krakow", "paris"]


@pytest.mark.asyncio
async def test_list_marketplace_spaces_returns_paginated_detailed_list(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url="https://onezone.example/api/v3/onezone/spaces/marketplace/list",
        json={
            "spaces": [
                {"spaceId": "sp1", "index": "aqua@sp1"},
                {"spaceId": "sp2", "index": "terra@sp2"},
            ],
            "isLast": False,
            "nextPageToken": "next-token",
        },
    )
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/spaces/marketplace/sp1",
        json={
            "name": "Aqua dataset",
            "description": "Water data",
            "organizationName": "Org 1",
            "tags": ["open-data"],
            "providerNames": ["krakow"],
            "totalSupportSize": 100,
            "creationTime": 1576152793,
        },
    )
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/spaces/marketplace/sp2",
        json={
            "name": "Terra dataset",
            "index": "terra@sp2",
            "description": "Soil data",
            "organizationName": "Org 2",
            "tags": ["environment"],
            "providerNames": ["paris"],
            "totalSupportSize": 200,
            "creationTime": 1576152794,
        },
    )

    result = await spaces.list_marketplace_spaces(tags=["open-data"], limit=2, offset=0)

    assert result["isLast"] is False
    assert result["nextPageToken"] == "next-token"
    assert len(result["spaces"]) == 2
    assert result["spaces"][0]["spaceId"] == "sp1"
    assert result["spaces"][0]["index"] == "aqua@sp1"
    assert result["spaces"][1]["spaceId"] == "sp2"
    assert result["spaces"][1]["index"] == "terra@sp2"

    requests = httpx_mock.get_requests()
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/api/v3/onezone/spaces/marketplace/list"
    assert requests[0].content == b'{"limit":2,"offset":0,"tags":["open-data"]}'


@pytest.mark.asyncio
async def test_list_marketplace_spaces_rejects_limit_out_of_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)

    with pytest.raises(ValueError, match="between 1 and 50"):
        await spaces.list_marketplace_spaces(limit=0)

    with pytest.raises(ValueError, match="between 1 and 50"):
        await spaces.list_marketplace_spaces(limit=51)
