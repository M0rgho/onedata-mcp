import pytest
from pytest_httpx import HTTPXMock

from onedata_mcp.api import spaces
from onedata_mcp.utils import OnedataApiError


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


@pytest.mark.asyncio
async def test_list_space_datasets_by_space_id(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_oneprovider_env(monkeypatch)
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/spaces",
        json=[{"spaceId": "sp1", "name": "Space One"}],
        is_reusable=True,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/spaces/sp1/datasets",
        match_params={"state": "attached", "limit": "10", "offset": "0"},
        json={
            "datasets": [
                {"datasetId": "d1", "name": "File1.txt"},
                {"datasetId": "d2", "name": "Dir2"},
            ],
            "nextPageToken": "page-2",
        },
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/datasets/d1",
        json={
            "state": "attached",
            "datasetId": "d1",
            "rootFilePath": "/Space One/File1.txt",
            "rootFileType": "REG",
            "protectionFlags": ["data_protection"],
        },
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/datasets/d2",
        json={
            "state": "attached",
            "datasetId": "d2",
            "rootFilePath": "/Space One/Dir2",
            "rootFileType": "DIR",
        },
    )

    result = await spaces.list_space_datasets("sp1", limit=10)

    assert result["datasets"][0]["name"] == "File1.txt"
    assert result["datasets"][0]["rootFilePath"] == "/Space One/File1.txt"
    assert result["datasets"][1]["rootFileType"] == "DIR"
    assert result["nextPageToken"] == "page-2"
    datasets_request = next(
        r for r in httpx_mock.get_requests() if r.url.path.endswith("/spaces/sp1/datasets")
    )
    assert datasets_request.url.params["state"] == "attached"
    assert datasets_request.url.params["limit"] == "10"
    assert datasets_request.url.params["offset"] == "0"


@pytest.mark.asyncio
async def test_list_space_datasets_resolves_space_name(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_oneprovider_env(monkeypatch)
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/spaces",
        json=[{"spaceId": "sp1", "name": "my-space"}],
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/spaces/sp1/datasets",
        match_params={"state": "detached", "limit": "100", "offset": "0"},
        json={"datasets": [], "nextPageToken": None},
    )

    result = await spaces.list_space_datasets("my-space", state="detached")

    assert result["datasets"] == []


@pytest.mark.asyncio
async def test_list_space_datasets_passes_pagination_token(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_oneprovider_env(monkeypatch)
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/spaces",
        json=[{"spaceId": "sp1", "name": "Space One"}],
        is_reusable=True,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/spaces/sp1/datasets",
        match_params={
            "state": "attached",
            "limit": "100",
            "offset": "5",
            "token": "abc",
        },
        json={"datasets": [], "nextPageToken": None},
    )

    await spaces.list_space_datasets("sp1", offset=5, token="abc")

    datasets_request = httpx_mock.get_requests()[-1]
    assert datasets_request.url.params["offset"] == "5"
    assert datasets_request.url.params["token"] == "abc"


@pytest.mark.asyncio
async def test_list_space_datasets_raises_when_catalog_unauthorized_under_data_path_caveat(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    """Confined ``data.path`` tokens cannot use ``GET /spaces/{{sid}}/datasets`` (no fallback)."""
    _set_oneprovider_env(monkeypatch)
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/spaces",
        json=[{"spaceId": "sp1", "name": "my-space"}],
        is_reusable=True,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/spaces/sp1/datasets",
        match_params={"state": "attached", "limit": "100", "offset": "0"},
        status_code=401,
        json={
            "error": {
                "id": "unauthorized",
                "details": {
                    "authError": {
                        "id": "tokenCaveatUnverified",
                        "details": {
                            "caveat": {"type": "data.path", "whitelist": ["L21jcC1zcGFjZQ=="]}
                        },
                    }
                },
            }
        },
    )

    with pytest.raises(OnedataApiError, match="status=401"):
        await spaces.list_space_datasets("my-space", state="attached")

    urls = [str(request.url) for request in httpx_mock.get_requests()]
    assert any("/spaces/sp1/datasets" in url for url in urls)
    assert not any("lookup-file-id" in url for url in urls)
    assert not any("/data/" in url for url in urls)


@pytest.mark.asyncio
async def test_list_space_datasets_rejects_limit_out_of_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_oneprovider_env(monkeypatch)

    with pytest.raises(ValueError, match="between 1 and 1000"):
        await spaces.list_space_datasets("sp1", limit=0)

    with pytest.raises(ValueError, match="between 1 and 1000"):
        await spaces.list_space_datasets("sp1", limit=1001)
