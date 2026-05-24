import pytest
from pytest_httpx import HTTPXMock

from onedata_mcp.api import harvesters


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONEDATA_ONEZONE_HOST", "https://onezone.example")
    monkeypatch.setenv("ONEDATA_ONEZONE_TOKEN", "token")
    monkeypatch.setenv("ONEDATA_ALLOW_INSECURE_TLS", "false")


def _set_env_with_oneprovider(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.setenv("ONEDATA_ONEPROVIDER_HOST", "https://provider.example")
    monkeypatch.setenv("ONEDATA_ONEPROVIDER_TOKEN", "token")


def _mock_provider_spaces(httpx_mock: HTTPXMock, spaces: list[dict[str, str]]) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/spaces",
        json=spaces,
        is_reusable=True,
    )


@pytest.mark.asyncio
async def test_list_user_harvesters_embeds_indices_without_schema(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env_with_oneprovider(monkeypatch)
    _mock_provider_spaces(
        httpx_mock,
        [
            {"spaceId": "spaceA", "name": "space-a"},
            {"spaceId": "spaceB", "name": "space-b"},
        ],
    )
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
        url="https://onezone.example/api/v3/onezone/harvesters/h1/spaces",
        json={"spaces": ["spaceA", "spaceB"]},
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
    assert result[0]["attached_spaces"] == [
        {"space_id": "spaceA", "space_name": "space-a"},
        {"space_id": "spaceB", "space_name": "space-b"},
    ]


@pytest.mark.asyncio
async def test_list_user_harvesters_filters_by_space_name_substring(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env_with_oneprovider(monkeypatch)
    _mock_provider_spaces(
        httpx_mock,
        [
            {"spaceId": "sid-krk", "name": "krk-iu"},
            {"spaceId": "sid-other", "name": "open-data"},
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/user/harvesters",
        json={"harvesters": ["h1", "h2"]},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/user/harvesters/h1",
        json={"harvesterId": "h1", "name": "Harvester KRK"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/user/harvesters/h2",
        json={"harvesterId": "h2", "name": "Harvester Other"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/harvesters/h1/indices",
        json={"indices": []},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/harvesters/h2/indices",
        json={"indices": []},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/harvesters/h1/spaces",
        json={"spaces": ["sid-krk"]},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://onezone.example/api/v3/onezone/harvesters/h2/spaces",
        json={"spaces": ["sid-other"]},
    )

    result = await harvesters.list_user_harvesters(space_name="krk")

    assert len(result) == 1
    assert result[0]["harvesterId"] == "h1"
    assert result[0]["attached_spaces"] == [
        {"space_id": "sid-krk", "space_name": "krk-iu"},
    ]


@pytest.mark.asyncio
async def test_list_user_harvesters_space_name_filter_no_matching_spaces_returns_empty(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env_with_oneprovider(monkeypatch)
    _mock_provider_spaces(
        httpx_mock,
        [{"spaceId": "sid-other", "name": "open-data"}],
    )

    result = await harvesters.list_user_harvesters(space_name="krk")

    assert result == []
    zone_requests = [r for r in httpx_mock.get_requests() if "onezone" in str(r.url)]
    assert zone_requests == []


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

    result = await harvesters.query_harvester_index(
        "h1", "idx1", harvesters.harvester_index_query("get", "resource_id")
    )

    assert result["hits"]["total"] == 1
    req = httpx_mock.get_requests()[0]
    assert req.method == "POST"
    assert req.url.path == "/api/v3/onezone/harvesters/h1/indices/idx1/query"
    assert req.content == b'{"method":"get","path":"resource_id"}'


@pytest.mark.asyncio
async def test_query_harvester_index_post_search_serializes_body(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url="https://onezone.example/api/v3/onezone/harvesters/h1/indices/idx1/query",
        json={"hits": {"total": 1}},
    )

    es_body = harvesters.harvester_es_search_query({"size": 1, "query": {"match_all": {}}})
    result = await harvesters.query_harvester_index(
        "h1", "idx1", harvesters.harvester_index_query("post", "_search", es_body)
    )

    assert result["hits"]["total"] == 1
    req = httpx_mock.get_requests()[0]
    assert (
        req.content
        == b'{"method":"post","path":"_search","body":"{\\"size\\":1,\\"query\\":{\\"match_all\\":{}}}"}'
    )


def test_build_onezone_harvester_query_serializes_body() -> None:
    assert harvesters.build_onezone_harvester_query(
        "post",
        "_search",
        {"size": 1, "query": {"match_all": {}}},
    ) == {
        "method": "post",
        "path": "_search",
        "body": '{"size":1,"query":{"match_all":{}}}',
    }


def test_unwrap_harvester_query_response_parses_body_string() -> None:
    wrapped = {
        "code": 200,
        "headers": {},
        "body": '{"hits":{"total":{"value":2},"hits":[]}}',
    }
    parsed = harvesters.unwrap_harvester_query_response(wrapped)
    assert isinstance(parsed, dict)
    assert parsed["hits"]["total"]["value"] == 2


def test_harvester_es_search_query_returns_body() -> None:
    es_body = {"size": 1, "query": {"match_all": {}}}
    assert harvesters.harvester_es_search_query(es_body) is es_body


def test_harvester_index_query_builds_nested_object() -> None:
    es_body = {"size": 1, "query": {"match_all": {}}}
    assert harvesters.harvester_index_query("post", "_search", es_body) == {
        "method": "post",
        "path": "_search",
        "body": es_body,
    }
    assert harvesters.harvester_index_query("get", "_mapping") == {
        "method": "get",
        "path": "_mapping",
    }
