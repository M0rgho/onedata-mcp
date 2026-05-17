import json
import re
from urllib.parse import quote

import pytest
from pytest_httpx import HTTPXMock

from onedata_mcp.api import files
from onedata_mcp.utils import OnedataInvalidSpaceError


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONEDATA_ONEPROVIDER_HOST", "https://provider.example")
    monkeypatch.setenv("ONEDATA_ONEPROVIDER_TOKEN", "token")
    monkeypatch.setenv("ONEDATA_ALLOW_INSECURE_TLS", "false")


def _lookup_url(path: str) -> str:
    return f"https://provider.example/api/v3/oneprovider/lookup-file-id/{quote(path, safe='')}"


def _mock_available_spaces(httpx_mock: HTTPXMock, names: list[str]) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/spaces",
        json=[{"name": name, "spaceId": f"s{i}"} for i, name in enumerate(names)],
        is_reusable=True,
        is_optional=True,
    )


@pytest.fixture
def available_spaces(request: pytest.FixtureRequest) -> list[str]:
    return getattr(request, "param", ["space"])


@pytest.fixture(autouse=True)
def _mock_spaces_for_tests(httpx_mock: HTTPXMock, available_spaces: list[str]) -> None:
    _mock_available_spaces(httpx_mock, available_spaces)


@pytest.mark.asyncio
async def test_get_file_id_encodes_path_and_returns_id(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/my dir"),
        json={"fileId": "fid-123"},
    )

    result = await files.get_file_id("/space/my dir")

    assert result == "fid-123"


@pytest.mark.asyncio
async def test_get_file_id_maps_enoent_to_file_not_found(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/missing"),
        status_code=400,
        json={"error": {"details": {"errno": "enoent"}}},
    )

    with pytest.raises(FileNotFoundError):
        await files.get_file_id("/space/missing")


@pytest.mark.asyncio
async def test_get_file_attributes_sends_selected_attributes(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/path"),
        json={"fileId": "file-id"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/data/file-id",
        json={"name": "x"},
    )

    result = await files.get_file_attributes("/space/path", attributes=["name", "size"])

    assert result == {"name": "x"}
    provider_requests = [r for r in httpx_mock.get_requests() if r.url.host == "provider.example"]
    assert provider_requests[1].method == "GET"
    assert provider_requests[1].url.path == "/api/v3/oneprovider/data/file-id"
    assert provider_requests[1].content == b'{"attributes":["name","size"]}'


@pytest.mark.asyncio
async def test_list_files_applies_default_attributes_when_none(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/path"),
        json={"fileId": "parent-id"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/data/parent-id/children",
        json={"children": [], "isLast": True, "nextPageToken": None},
    )

    await files.list_files("/space/path", attributes=None, limit=10, offset=0)

    request = next(
        r for r in httpx_mock.get_requests() if r.url.path.endswith("/data/parent-id/children")
    )
    assert b'"attributes":' in request.content


@pytest.mark.asyncio
async def test_list_files_recursive_applies_default_attributes_when_none(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/path"),
        json={"fileId": "parent-id"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/data/parent-id/files",
        json={"files": [], "isLast": True, "nextPageToken": None},
    )

    await files.list_files_recursive("/space/path", attributes=None, limit=10)

    request = next(
        r for r in httpx_mock.get_requests() if r.url.path.endswith("/data/parent-id/files")
    )
    assert b'"attributes":' in request.content


@pytest.mark.asyncio
async def test_list_files_canonicalizes_deprecated_attribute_aliases(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/path"),
        json={"fileId": "parent-id"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/data/parent-id/children",
        json={"children": [], "isLast": True, "nextPageToken": None},
    )

    await files.list_files("/space/path", attributes=["file_id"], limit=10, offset=0)

    request = next(
        r for r in httpx_mock.get_requests() if r.url.path.endswith("/data/parent-id/children")
    )
    payload = json.loads(request.content.decode("utf-8"))
    assert payload["attributes"] == ["fileId"]


@pytest.mark.asyncio
async def test_list_files_drops_unknown_attributes(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/path"),
        json={"fileId": "parent-id"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/data/parent-id/children",
        json={"children": [], "isLast": True, "nextPageToken": None},
    )

    await files.list_files(
        "/space/path",
        attributes=["notAnApiField", "name", "xattr.custom"],
        limit=10,
        offset=0,
    )

    request = next(
        r for r in httpx_mock.get_requests() if r.url.path.endswith("/data/parent-id/children")
    )
    payload = json.loads(request.content.decode("utf-8"))
    assert payload["attributes"] == ["name", "xattr.custom"]


@pytest.mark.asyncio
async def test_list_files_recursive_canonicalizes_deprecated_attribute_aliases(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/path"),
        json={"fileId": "parent-id"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/data/parent-id/files",
        json={"files": [], "isLast": True, "nextPageToken": None},
    )

    await files.list_files_recursive("/space/path", attributes=["mode"], limit=10)

    request = next(
        r for r in httpx_mock.get_requests() if r.url.path.endswith("/data/parent-id/files")
    )
    payload = json.loads(request.content.decode("utf-8"))
    assert payload["attributes"] == ["posixPermissions"]


@pytest.mark.asyncio
async def test_list_files_filters_deprecated_response_fields(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/path"),
        json={"fileId": "parent-id"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/data/parent-id/children",
        json={
            "children": [
                {"name": "a.txt", "file_id": "old-id", "fileId": "new-id"},
                {"name": "b.txt", "mode": "0777", "posixPermissions": "0777"},
            ],
            "isLast": True,
            "nextPageToken": None,
        },
    )

    result = await files.list_files("/space/path", limit=10, offset=0)

    assert result["children"][0]["fileId"] == "new-id"
    assert "file_id" not in result["children"][0]
    assert "mode" not in result["children"][1]
    assert result["children"][1]["posixPermissions"] == "0777"


@pytest.mark.asyncio
async def test_list_files_recursive_filters_deprecated_response_fields(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/path"),
        json={"fileId": "parent-id"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/data/parent-id/files",
        json={
            "files": [
                {"name": "a.txt", "file_id": "old-id", "fileId": "new-id"},
                {"name": "b.txt", "owner_id": "123", "ownerUserId": "123"},
            ],
            "isLast": True,
            "nextPageToken": None,
        },
    )

    result = await files.list_files_recursive("/space/path", limit=10)

    assert result["files"][0]["fileId"] == "new-id"
    assert "file_id" not in result["files"][0]
    assert "owner_id" not in result["files"][1]
    assert result["files"][1]["ownerUserId"] == "123"


@pytest.mark.asyncio
@pytest.mark.parametrize("available_spaces", [["Alpha", "Beta"]], indirect=True)
async def test_list_files_recursive_formats_invalid_space_error_with_hints(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/dsadas"),
        json={"fileId": "dsadas"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/data/dsadas/files",
        status_code=400,
        json={
            "error": {
                "id": "spaceNotSupportedBy",
                "details": {"spaceId": "dsadas", "providerId": "provider-1"},
            }
        },
    )

    with pytest.raises(OnedataInvalidSpaceError, match='Space "dsadas" does not exist') as exc:
        await files.list_files_recursive("dsadas", limit=10)

    assert 'Available spaces: "Alpha", "Beta".' in str(exc.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("available_spaces", [["Alpha"]], indirect=True)
async def test_list_files_formats_invalid_space_error_with_hints(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/dsadas"),
        json={"fileId": "dsadas"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/data/dsadas/children",
        status_code=400,
        json={
            "error": {
                "id": "spaceNotSupportedBy",
                "details": {"spaceId": "dsadas", "providerId": "provider-1"},
            }
        },
    )

    with pytest.raises(OnedataInvalidSpaceError, match='Space "dsadas" does not exist') as exc:
        await files.list_files("dsadas", limit=10, offset=0)

    assert 'Available spaces: "Alpha".' in str(exc.value)


@pytest.mark.asyncio
async def test_download_file_rejects_directory(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/dir"),
        json={"fileId": "fid-dir"},
        is_reusable=True,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/data/fid-dir",
        json={"type": "DIR", "size": 10},
    )

    with pytest.raises(ValueError, match="directory"):
        await files.download_file("/space/dir")


@pytest.mark.asyncio
async def test_download_file_rejects_large_files(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/big"),
        json={"fileId": "fid-big"},
        is_reusable=True,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/data/fid-big",
        json={"type": "REG", "size": 6 * 1024 * 1024},
    )

    with pytest.raises(ValueError, match="too large"):
        await files.download_file("/space/big")


@pytest.mark.asyncio
async def test_download_file_uses_httpx_async_client(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/file.txt"),
        json={"fileId": "fid-1"},
        is_reusable=True,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/data/fid-1",
        json={"type": "REG", "size": 3},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/data/fid-1/content",
        text="abc",
        headers={"Content-Type": "text/plain"},
    )

    result = await files.download_file("/space/file.txt")

    assert result == b"abc"
    content_req = httpx_mock.get_requests()[-1]
    assert content_req.url.path == "/api/v3/oneprovider/data/fid-1/content"
    assert content_req.headers["Accept"] == "*/*"
    assert "Content-Type" not in content_req.headers


@pytest.mark.asyncio
async def test_get_file_metadata_fetches_each_type_with_rdf_accept_header(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/a"),
        json={"fileId": "fid-meta"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/data/fid-meta/metadata/json",
        json={"k": "v"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/data/fid-meta/metadata/rdf",
        text="<rdf/>",
        headers={"Content-Type": "application/rdf+xml"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/data/fid-meta/metadata/xattrs",
        json={"x": "1"},
    )

    result = await files.get_file_metadata("/space/a", ["json", "rdf", "xattrs"])

    assert result["json"] == {"k": "v"}
    assert result["rdf"] == "<rdf/>"
    assert result["xattrs"] == {"x": "1"}
    rdf_req = next(
        r for r in httpx_mock.get_requests() if r.url.path.endswith("/data/fid-meta/metadata/rdf")
    )
    assert rdf_req.url.path == "/api/v3/oneprovider/data/fid-meta/metadata/rdf"
    assert rdf_req.headers["Accept"] == "application/rdf+xml"


@pytest.mark.asyncio
async def test_get_file_metadata_maps_enodata_to_none(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/a"),
        json={"fileId": "fid-meta"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://provider.example/api/v3/oneprovider/data/fid-meta/metadata/rdf",
        status_code=400,
        json={"error": {"details": {"errno": "enodata"}}},
    )

    result = await files.get_file_metadata("/space/a", ["rdf"])

    assert result == {"rdf": None}


@pytest.mark.asyncio
async def test_get_file_metadata_rejects_invalid_type(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/a"),
        json={"fileId": "fid-meta"},
    )
    with pytest.raises(ValueError, match="Unsupported metadata type"):
        await files.get_file_metadata("/space/a", ["json", "bad"])


@pytest.mark.asyncio
async def test_set_file_metadata_sets_content_type(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/a"),
        json={"fileId": "fid-set"},
    )
    httpx_mock.add_response(
        method="PUT",
        url="https://provider.example/api/v3/oneprovider/data/fid-set/metadata/rdf",
        json={},
    )
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/a"),
        json={"fileId": "fid-set"},
    )
    httpx_mock.add_response(
        method="PUT",
        url="https://provider.example/api/v3/oneprovider/data/fid-set/metadata/json",
        json={},
    )
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/a"),
        json={"fileId": "fid-set"},
    )
    httpx_mock.add_response(
        method="PUT",
        url="https://provider.example/api/v3/oneprovider/data/fid-set/metadata/json",
        json={},
    )
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/a"),
        json={"fileId": "fid-set"},
    )
    httpx_mock.add_response(
        method="PUT",
        url="https://provider.example/api/v3/oneprovider/data/fid-set/metadata/xattrs",
        json={},
    )

    await files.set_file_metadata("/space/a", "rdf", "<rdf/>")
    await files.set_file_metadata("/space/a", "json", '{"a":1}')
    await files.set_file_metadata("/space/a", "json", {"b": 2})
    await files.set_file_metadata("/space/a", "xattrs", {"license": "CC-0"})

    put_requests = [
        r
        for r in httpx_mock.get_requests()
        if r.method == "PUT" and r.url.host == "provider.example"
    ]
    assert put_requests[0].headers["Content-Type"] == "application/rdf+xml"
    assert put_requests[1].headers["Content-Type"] == "application/json"
    assert put_requests[2].headers["Content-Type"] == "application/json"
    assert put_requests[3].headers["Content-Type"] == "application/json"
    assert put_requests[0].content == b"<rdf/>"
    assert put_requests[1].content == b'{"a":1}'
    assert put_requests[2].content == b'{"b": 2}'
    assert put_requests[3].content == b'{"license": "CC-0"}'


@pytest.mark.asyncio
async def test_set_file_xattrs_writes_xattrs_body(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/a"),
        json={"fileId": "fid-set"},
    )
    httpx_mock.add_response(
        method="PUT",
        url="https://provider.example/api/v3/oneprovider/data/fid-set/metadata/xattrs",
        json={},
    )

    await files.set_file_xattrs("/space/a", {"license": "CC-0"})

    put = next(
        r
        for r in httpx_mock.get_requests()
        if r.method == "PUT"
        and r.url.host == "provider.example"
        and str(r.url).endswith("/metadata/xattrs")
    )
    assert put.headers["Content-Type"] == "application/json"
    assert put.content == b'{"license": "CC-0"}'


@pytest.mark.asyncio
async def test_set_file_metadata_rejects_unknown_type(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/a"),
        json={"fileId": "fid-set"},
    )
    with pytest.raises(ValueError, match="Unsupported metadata type"):
        await files.set_file_metadata("/space/a", "custom", "{}")


@pytest.mark.asyncio
async def test_set_file_metadata_xattrs_rejects_non_string_values(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/a"),
        json={"fileId": "fid-set"},
    )
    with pytest.raises(TypeError, match="xattrs values must be strings"):
        await files.set_file_metadata("/space/a", "xattrs", {"n": 1})


@pytest.mark.asyncio
async def test_set_file_metadata_xattrs_rejects_top_level_array(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/a"),
        json={"fileId": "fid-set"},
    )
    with pytest.raises(ValueError, match="JSON object"):
        await files.set_file_metadata("/space/a", "xattrs", "[1,2]")


@pytest.mark.asyncio
async def test_set_file_metadata_rdf_rejects_dict_body(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/a"),
        json={"fileId": "fid-set"},
    )
    with pytest.raises(TypeError, match="RDF metadata body"):
        await files.set_file_metadata("/space/a", "rdf", {"a": 1})


@pytest.mark.asyncio
async def test_create_file_posts_child_when_create_parents_false(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space/parent"),
        json={"fileId": "parent-id"},
    )
    httpx_mock.add_response(
        method="POST",
        url=re.compile(r"https://provider\.example/api/v3/oneprovider/data/parent-id/children\?.*"),
        json={"fileId": "new-fid"},
    )

    fid = await files.create_file("/space/parent/note.txt", "hello")

    assert fid == "new-fid"
    post = next(
        r
        for r in httpx_mock.get_requests()
        if r.method == "POST" and r.url.host == "provider.example" and "/children" in r.url.path
    )
    assert post.url.params["name"] == "note.txt"


@pytest.mark.asyncio
async def test_create_file_put_path_when_create_parents_true(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    _set_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=_lookup_url("/space"),
        json={"fileId": "root-id"},
    )
    httpx_mock.add_response(
        method="PUT",
        url=re.compile(
            r"https://provider\.example/api/v3/oneprovider/data/root-id/path/results/d\.csv\?.*"
        ),
        json={"fileId": "nested-fid"},
    )

    fid = await files.create_file("/space/results/d.csv", "x", create_parents=True)

    assert fid == "nested-fid"
    put = next(
        r
        for r in httpx_mock.get_requests()
        if r.method == "PUT" and r.url.host == "provider.example" and "/path/" in r.url.path
    )
    assert put.url.params["create_parents"] == "true"
    assert put.content == b"x"
