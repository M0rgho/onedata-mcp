import pytest
from pytest_httpx import HTTPXMock

from onedata_mcp.api import harvesters


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONEDATA_ONEZONE_HOST", "https://onezone.example")
    monkeypatch.setenv("ONEDATA_ONEZONE_TOKEN", "token")
    monkeypatch.setenv("ONEDATA_ALLOW_INSECURE_TLS", "false")


@pytest.mark.asyncio
async def test_list_user_harvesters_embeds_indices_without_schema(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/user/harvesters",
        json={"harvesters": ["h1"]},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/user/harvesters/h1",
        json={
            "harvesterId": "h1",
            "name": "My Harvester",
            "plugin": "elasticsearch_plugin",
            "endpoint": "https://example.elastic.com",
        },
    )
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/harvesters/h1/indices",
        json={"indices": ["idx1"]},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/harvesters/h1/indices/idx1",
        json={
            "indexId": "idx1",
            "name": "Index 1",
            "guiPluginName": "study",
            "schema": '{"mappings":{"properties":{"foo":{"type":"keyword"}}}}',
        },
    )

    result = await harvesters.list_user_harvesters()

    assert len(result) == 1
    assert result[0]["harvesterId"] == "h1"
    assert result[0]["indices"] == [
        {
            "indexId": "idx1",
            "name": "Index 1",
            "guiPluginName": "study",
        }
    ]


@pytest.mark.asyncio
async def test_get_harvester_index_schema_returns_full_details(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/harvesters/h1/indices/idx1",
        json={
            "indexId": "idx1",
            "name": "Index 1",
            "guiPluginName": "study",
            "schema": '{"mappings":{}}',
        },
    )

    result = await harvesters.get_harvester_index_schema("h1", "idx1")

    assert result["indexId"] == "idx1"
    assert result["schema"] == '{"mappings":{}}'


@pytest.mark.asyncio
async def test_query_harvester_index_posts_query_body(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url="https://onezone.example/api/v3/onezone/harvesters/h1/indices/idx1/query",
        json={"hits": {"total": 1, "hits": [{"_id": "resource_id"}]}},
    )

    payload = {"method": "get", "path": "resource_id"}
    result = await harvesters.query_harvester_index("h1", "idx1", payload)

    assert result["hits"]["total"] == 1
    req = httpx_mock.get_requests()[0]
    assert req.method == "POST"
    assert req.url.path == "/api/v3/onezone/harvesters/h1/indices/idx1/query"
    assert req.content == b'{"method":"get","path":"resource_id"}'


@pytest.mark.asyncio
async def test_query_harvester_index_accepts_json_string_query(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url="https://onezone.example/api/v3/onezone/harvesters/h1/indices/idx1/query",
        json={"hits": {"total": 1}},
    )

    payload_str = '{"method": "get", "path": "_mapping"}'
    result = await harvesters.query_harvester_index("h1", "idx1", payload_str)

    assert result["hits"]["total"] == 1
    req = httpx_mock.get_requests()[0]
    assert req.content == b'{"method":"get","path":"_mapping"}'


def test_coerce_harvesters_index_query_dict_passthrough() -> None:
    d = {"method": "post", "path": "_search", "body": "{}"}
    assert harvesters.coerce_harvesters_index_query(d) is d


def test_coerce_harvesters_index_query_rejects_non_object_json() -> None:
    with pytest.raises(TypeError, match="deserialize to an object"):
        harvesters.coerce_harvesters_index_query("[1]")
