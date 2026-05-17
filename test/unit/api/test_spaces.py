import pytest
from pytest_httpx import HTTPXMock

from onedata_mcp.api import spaces


def _set_oneprovider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONEDATA_ONEPROVIDER_HOST", "https://provider.example")
    monkeypatch.setenv("ONEDATA_ONEPROVIDER_TOKEN", "token")
    monkeypatch.setenv("ONEDATA_ALLOW_INSECURE_TLS", "false")


@pytest.mark.asyncio
async def test_list_available_spaces_fetches_from_oneprovider_and_maps_fields(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_oneprovider_env(monkeypatch)
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/spaces",
        json=[
            {
                "spaceId": "sp1",
                "name": "Space One",
                "providers": [{"providerId": "p1", "providerName": "Cloud1"}],
                "dirId": "dir1",
                "trashDirId": "trash1",
                "archivesDirId": "arch1",
                "ignoredField": "ignored",
            },
            {
                "spaceId": "sp2",
                "name": "Space Two",
                "providers": [{"providerId": "p2", "providerName": "Cloud2"}],
                "dirId": "dir2",
            },
        ],
    )

    result = await spaces.list_available_spaces()

    assert len(result) == 2
    assert result[0] == {
        "spaceId": "sp1",
        "name": "Space One",
        "providers": [{"providerId": "p1", "providerName": "Cloud1"}],
        "dirId": "dir1",
        "trashDirId": "trash1",
        "archivesDirId": "arch1",
    }
    assert result[1]["spaceId"] == "sp2"
    assert "ignoredField" not in result[0]


@pytest.mark.asyncio
async def test_list_available_spaces_returns_empty_when_no_spaces(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_oneprovider_env(monkeypatch)
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/spaces",
        json=[],
    )

    result = await spaces.list_available_spaces()

    assert result == []
