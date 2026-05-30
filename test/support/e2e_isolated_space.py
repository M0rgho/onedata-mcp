"""Isolated E2E spaces: create, reset, and Oneprovider tokens scoped to one space."""

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from onedata_mcp.config import OnedataConfig, get_oneprovider_config, get_onezone_config
from onedata_mcp.utils import OnedataApiError, request

_CACHE_DIR = Path(__file__).resolve().parent / ".e2e-token-cache"
_CACHE_FILE = _CACHE_DIR / "tokens.json"
_DEFAULT_PREFIX = "mcp-e2e"
_E2E_NAMED_TOKEN_PREFIXES = ("mcp-e2e-base-", "mcp-e2e-support-")
_TOKEN_TTL_SECONDS = 24 * 3600
_CACHE_EXPIRY_GRACE_SECONDS = 60
_DEFAULT_SUPPORT_SIZE_BYTES = 100 * 1024**2  # 100 MiB quota for isolated E2E spaces


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


def e2e_admin_oneprovider_token() -> str:
    """Cluster admin Oneprovider token for reset, support, and ``POST /datasets``.

    Prefer ``ONEDATA_E2E_ADMIN_TOKEN`` so ``ONEDATA_ONEPROVIDER_TOKEN`` can stay unset or
    be overwritten by the confined MCP token during isolated tests.
    """

    token = (
        os.getenv("ONEDATA_E2E_ADMIN_TOKEN", "").strip()
        or os.getenv("ONEDATA_ONEPROVIDER_TOKEN", "").strip()
    )
    if not token:
        msg = "ONEDATA_E2E_ADMIN_TOKEN or ONEDATA_ONEPROVIDER_TOKEN required for isolated E2E admin ops"
        raise ValueError(msg)
    return token


@asynccontextmanager
async def use_admin_oneprovider_token(admin_token: str | None = None) -> AsyncIterator[None]:
    """Temporarily set ``ONEDATA_ONEPROVIDER_TOKEN`` to the cluster admin token."""

    token = admin_token or e2e_admin_oneprovider_token()

    previous = os.environ.get("ONEDATA_ONEPROVIDER_TOKEN")
    os.environ["ONEDATA_ONEPROVIDER_TOKEN"] = token
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("ONEDATA_ONEPROVIDER_TOKEN", None)
        else:
            os.environ["ONEDATA_ONEPROVIDER_TOKEN"] = previous


def _canonical_space_path(space_id: str) -> str:
    """Canonical data.path whitelist entry (slash + space id, no trailing slash)."""
    return f"/{space_id.strip().strip('/')}"


def _b64_path(path: str) -> str:
    return base64.standard_b64encode(path.encode("utf-8")).decode("ascii")


_SESSION_CREATED_SPACE_IDS: set[str] = set()
_E2E_HARVESTER_PAIR: tuple[str, str] | None = None
_HARVESTER_SCOPES = frozenset({"read-state", "harvester"})

# Stable Onedata space display names for isolated E2E scopes (not mcp-e2e-{scope}).
_STABLE_ISOLATED_SPACE_NAMES: dict[str, str] = {
    "read-state": "my-storage",
    "write-state": "my-workspace",
}


@dataclass(frozen=True)
class IsolatedE2ESpace:
    space_id: str
    space_name: str
    provider_token: str
    provider_token_write: str | None = None
    reused: bool = False

    @property
    def root_path(self) -> str:
        """Logical REST path prefix for files (``/<space_name>``; see ``lookup-file-id``)."""
        return f"/{self.space_name}"

    def confined_token_for_mcp(self, *, write: bool = False) -> str:
        """Confined Oneprovider token for MCP (read-only by default)."""

        if write:
            if not self.provider_token_write:
                msg = "Write confined token was not provisioned (use e2e_isolated_confined_write)"
                raise ValueError(msg)
            return self.provider_token_write
        return self.provider_token


def _load_cache() -> dict[str, Any]:
    if not _CACHE_FILE.is_file():
        return {}
    try:
        data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save_cache(data: dict[str, Any]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _cache_key(space_id: str, *, readonly: bool) -> str:
    host = os.getenv("ONEDATA_ONEPROVIDER_HOST", "").rstrip("/")
    mode = "ro" if readonly else "rw"
    return f"{host}:{space_id}:{mode}"


def _parse_cache_key(key: str) -> tuple[str, str, str] | None:
    """Return ``(host, space_id, mode)`` for keys ``{host}:{space_id}:rw|ro``."""

    parts = key.rsplit(":", 2)
    if len(parts) != 3:
        return None
    host, space_id, mode = parts
    if mode not in {"rw", "ro"} or not host or not space_id:
        return None
    return host, space_id, mode


def prune_token_cache(
    *,
    space_ids: frozenset[str] | set[str] | None = None,
    drop_expired: bool = True,
    now: int | None = None,
) -> int:
    """Drop stale rows from ``tokens.json`` (expired macaroons and/or deleted spaces).

    Returns the number of keys removed.
    """

    if _truthy("ONEDATA_E2E_TOKEN_CACHE_DISABLE_GC"):
        return 0

    now_ts = int(time.time()) if now is None else now
    remove_ids = frozenset(space_ids) if space_ids else frozenset()
    cache = _load_cache()
    if not cache:
        return 0

    to_drop: list[str] = []
    for key, entry in cache.items():
        parsed = _parse_cache_key(key)
        if parsed is None or not isinstance(entry, dict):
            to_drop.append(key)
            continue
        _, space_id, _ = parsed
        if space_id in remove_ids:
            to_drop.append(key)
            continue
        if drop_expired:
            expires = entry.get("validUntil")
            if not isinstance(expires, int) or expires <= now_ts + _CACHE_EXPIRY_GRACE_SECONDS:
                to_drop.append(key)

    if not to_drop:
        return 0

    for key in to_drop:
        cache.pop(key, None)
    if cache:
        _save_cache(cache)
    elif _CACHE_FILE.is_file():
        _CACHE_FILE.unlink()
    return len(to_drop)


def _is_e2e_named_token_name(
    name: str, prefixes: tuple[str, ...] = _E2E_NAMED_TOKEN_PREFIXES
) -> bool:
    return any(name.startswith(prefix) for prefix in prefixes)


async def _list_user_named_token_ids() -> list[str]:
    response = await _onezone("GET", "/user/tokens/named")
    body = response.get("body")
    if not isinstance(body, dict):
        return []
    tokens = body.get("tokens")
    if not isinstance(tokens, list):
        return []
    return [token_id for token_id in tokens if isinstance(token_id, str)]


async def _get_named_token_record(token_id: str) -> dict[str, Any] | None:
    try:
        response = await _onezone("GET", f"/tokens/named/{token_id}")
    except OnedataApiError:
        return None
    body = response.get("body")
    return body if isinstance(body, dict) else None


async def delete_named_token_on_onedata(token_id: str) -> None:
    await _onezone("DELETE", f"/tokens/named/{token_id}")


async def revoke_all_temporary_tokens_on_onedata() -> None:
    """Invalidate every temporary/confined macaroon for the current Onezone user."""

    await _onezone("DELETE", "/user/tokens/temporary")


async def cleanup_e2e_onedata_tokens(
    *,
    delete_named: bool = True,
    revoke_temporary: bool = True,
    named_prefixes: tuple[str, ...] = _E2E_NAMED_TOKEN_PREFIXES,
    clear_local_cache: bool = True,
) -> dict[str, int]:
    """Remove E2E artifacts from Onedata (not only ``tokens.json``).

    - Deletes named tokens whose names start with ``mcp-e2e-base-`` or ``mcp-e2e-support-``.
    - Optionally revokes **all** temporary tokens for the Onezone user (invalidates confined
      macaroons created via ``POST /tokens/confine``).
    - Optionally deletes the local token cache file.
    """

    stats = {"named_deleted": 0, "temporary_revoked": 0, "local_cache_cleared": 0}

    if delete_named:
        for token_id in await _list_user_named_token_ids():
            record = await _get_named_token_record(token_id)
            if not record:
                continue
            name = record.get("name")
            if not isinstance(name, str) or not _is_e2e_named_token_name(name, named_prefixes):
                continue
            await delete_named_token_on_onedata(token_id)
            stats["named_deleted"] += 1

    if revoke_temporary:
        await revoke_all_temporary_tokens_on_onedata()
        stats["temporary_revoked"] = 1

    if clear_local_cache:
        cache = _load_cache()
        stats["local_cache_cleared"] = len(cache)
        if _CACHE_FILE.is_file():
            _CACHE_FILE.unlink()

    return stats


async def _onezone(method: str, path: str, *, json_body: dict[str, Any] | None = None) -> Any:
    config = get_onezone_config()
    return await request(config, method, path, json_body=json_body)


def _get_onepanel_config() -> OnedataConfig:
    """Oneprovider host + panel/cluster admin token (not the confined MCP token)."""
    base = get_oneprovider_config()
    panel_token = (
        os.getenv("ONEDATA_E2E_ONEPANEL_TOKEN", "").strip() or e2e_admin_oneprovider_token()
    )
    return OnedataConfig(
        base_url=f"{base.base_url.rsplit('/api/', 1)[0]}/api/v3/onepanel",
        auth_headers={
            **{k: v for k, v in base.auth_headers.items() if k.lower() != "x-auth-token"},
            "X-Auth-Token": panel_token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        verify_ssl=base.verify_ssl,
    )


async def _onepanel(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    return await request(_get_onepanel_config(), method, path, json_body=json_body, params=params)


async def _oneprovider_admin(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    config = get_oneprovider_config()
    return await request(config, method, path, json_body=json_body, params=params)


async def _oneprovider_with_token(
    token: str,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    base = get_oneprovider_config()
    headers = dict(base.auth_headers)
    headers["X-Auth-Token"] = token
    config = OnedataConfig(base_url=base.base_url, auth_headers=headers, verify_ssl=base.verify_ssl)
    return await request(config, method, path, json_body=json_body, params=params)


async def _list_user_space_ids() -> set[str]:
    response = await _onezone("GET", "/user/spaces")
    body = response.get("body")
    if not isinstance(body, dict):
        return set()
    spaces = body.get("spaces")
    if not isinstance(spaces, list):
        return set()
    return {sid for sid in spaces if isinstance(sid, str)}


def _space_id_from_location(location: str) -> str | None:
    return resource_id_from_location(location)


def resource_id_from_location(location: str) -> str | None:
    """Last path segment of a Onezone ``Location`` header (space, harvester, index, …)."""
    resource_id = location.strip().rstrip("/").rsplit("/", 1)[-1]
    return resource_id if resource_id else None


def _space_id_from_body(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    for key in ("spaceId", "space_id", "id"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


async def _find_user_space_id_by_name(name: str) -> str | None:
    for space_id in await _list_user_space_ids():
        response = await _onezone("GET", f"/user/spaces/{space_id}")
        body = response.get("body")
        if isinstance(body, dict) and body.get("name") == name:
            return space_id
    return None


async def find_space_id_by_name(name: str) -> str | None:
    """Resolve a space id by name (Oneprovider listing, then Onezone)."""

    response = await _oneprovider_admin("GET", "/spaces")
    body = response.get("body")
    provider_ids: list[str] = []
    if isinstance(body, list):
        for row in body:
            if isinstance(row, dict) and row.get("name") == name:
                space_id = row.get("spaceId")
                if isinstance(space_id, str):
                    provider_ids.append(space_id)
    if len(provider_ids) == 1:
        return provider_ids[0]
    if len(provider_ids) > 1:
        return sorted(provider_ids)[-1]
    return await _find_user_space_id_by_name(name)


async def get_or_create_user_space(name: str) -> tuple[str, bool]:
    """Return ``(space_id, created)``; reuse an existing user space with the same name."""

    existing = await find_space_id_by_name(name)
    if existing:
        return existing, False
    space_id = await create_user_space(name)
    _SESSION_CREATED_SPACE_IDS.add(space_id)
    return space_id, True


def session_created_space_ids() -> frozenset[str]:
    """Space ids created in this pytest process (not reused from a prior run)."""

    return frozenset(_SESSION_CREATED_SPACE_IDS)


async def create_user_space(name: str) -> str:
    """Create space; return space id (Location header, body, or list diff)."""
    before = await _list_user_space_ids()
    response = await _onezone("POST", "/user/spaces", json_body={"name": name})
    headers = response.get("headers")
    header_map = headers if isinstance(headers, dict) else {}
    location = header_map.get("Location") or header_map.get("location")
    if isinstance(location, str) and location.strip():
        space_id = _space_id_from_location(location)
        if space_id:
            return space_id

    body = response.get("body")
    space_id = _space_id_from_body(body)
    if space_id:
        return space_id

    after = await _list_user_space_ids()
    created = after - before
    if len(created) == 1:
        return next(iter(created))

    by_name = await _find_user_space_id_by_name(name)
    if by_name:
        return by_name

    msg = "create_user_space: could not resolve space id (no Location header or listing match)"
    raise OnedataApiError(msg, response if isinstance(response, dict) else None)


async def wait_until_space_on_provider(space_id: str, *, timeout_s: float = 120.0) -> None:
    """Poll until the space appears in GET /spaces on the configured Oneprovider."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        response = await _oneprovider_admin("GET", "/spaces")
        body = response.get("body")
        if isinstance(body, list):
            for item in body:
                if isinstance(item, dict) and item.get("spaceId") == space_id:
                    return
        await _async_sleep(2.0)
    msg = f"Space {space_id} not visible on Oneprovider after {timeout_s}s"
    raise TimeoutError(msg)


async def _async_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


def _support_size_bytes() -> int:
    raw = os.getenv("ONEDATA_E2E_SUPPORT_SIZE_BYTES", str(_DEFAULT_SUPPORT_SIZE_BYTES)).strip()
    return int(raw)


def _support_storage_id() -> str:
    storage_id = os.getenv("ONEDATA_E2E_STORAGE_ID", "").strip()
    if not storage_id:
        msg = (
            "ONEDATA_E2E_STORAGE_ID is required to register provider support "
            "(storage backend id on the target Oneprovider)"
        )
        raise ValueError(msg)
    return storage_id


async def resolve_target_provider_id() -> str:
    """Provider id for the configured Oneprovider (env or GET /configuration)."""
    configured = os.getenv("ONEDATA_E2E_PROVIDER_ID", "").strip()
    if configured:
        return configured
    response = await _oneprovider_admin("GET", "/configuration")
    body = response.get("body")
    if isinstance(body, dict) and isinstance(body.get("providerId"), str):
        return body["providerId"]
    msg = "Could not resolve provider id; set ONEDATA_E2E_PROVIDER_ID"
    raise ValueError(msg)


async def create_space_support_token(space_id: str) -> str:
    """Named invite token with ``supportSpace`` for the given space (Onezone)."""
    token_name = f"mcp-e2e-support-{space_id[:12]}-{uuid.uuid4().hex[:6]}"
    response = await _onezone(
        "POST",
        "/user/tokens/named",
        json_body={
            "name": token_name,
            "type": {
                "inviteToken": {
                    "inviteType": "supportSpace",
                    "spaceId": space_id,
                }
            },
        },
    )
    body = response.get("body")
    if isinstance(body, dict) and isinstance(body.get("token"), str):
        return body["token"]
    msg = "create_space_support_token: missing token in named token response"
    raise OnedataApiError(msg, response if isinstance(response, dict) else None)


async def add_provider_support(space_id: str, support_token: str) -> None:
    """Register space support on the cluster via OnePanel API (not Oneprovider REST)."""
    payload: dict[str, Any] = {
        "token": support_token,
        "size": str(_support_size_bytes()),
        "storageId": _support_storage_id(),
    }
    await _onepanel("POST", "/provider/spaces", json_body=payload)


async def space_has_provider_support(space_id: str, provider_id: str) -> bool:
    response = await _onezone("GET", f"/spaces/{space_id}")
    body = response.get("body")
    if not isinstance(body, dict):
        return False
    providers = body.get("providers")
    return isinstance(providers, dict) and provider_id in providers


async def ensure_space_supported_on_provider(space_id: str) -> str:
    """Verify Onezone lists the target provider on the space; return provider id."""
    provider_id = await resolve_target_provider_id()
    if await space_has_provider_support(space_id, provider_id):
        return provider_id
    msg = (
        f"Space {space_id} is not supported by provider {provider_id}. "
        "Check ONEDATA_E2E_STORAGE_ID, panel token (ONEDATA_E2E_ONEPANEL_TOKEN or "
        "ONEDATA_ONEPROVIDER_TOKEN), and that POST /api/v3/onepanel/provider/spaces succeeds."
    )
    raise RuntimeError(msg)


async def _create_named_base_token(name: str) -> str:
    response = await _onezone("POST", "/user/tokens/named", json_body={"name": name})
    body = response.get("body")
    if isinstance(body, dict) and isinstance(body.get("token"), str):
        return body["token"]
    msg = "create_named_token: missing token in body"
    raise OnedataApiError(msg, response if isinstance(response, dict) else None)


async def confine_provider_token(
    base_token: str,
    space_id: str,
    *,
    space_name: str | None = None,
    readonly: bool = False,
    valid_until: int | None = None,
) -> str:
    valid_until = valid_until or int(time.time()) + _TOKEN_TTL_SECONDS
    path_whitelist = [_canonical_space_path(space_id)]
    if space_name:
        name_path = f"/{space_name.strip().strip('/')}"
        if name_path not in path_whitelist:
            path_whitelist.append(name_path)
    caveats: list[dict[str, Any]] = [
        {"type": "time", "validUntil": valid_until},
        {"type": "interface", "interface": "rest"},
        {
            "type": "data.path",
            "whitelist": [_b64_path(path) for path in path_whitelist],
        },
    ]
    if readonly:
        caveats.append({"type": "data.readonly"})
    response = await _onezone(
        "POST",
        "/tokens/confine",
        json_body={"token": base_token, "caveats": caveats},
    )
    body = response.get("body")
    if isinstance(body, dict) and isinstance(body.get("token"), str):
        return body["token"]
    msg = "confine: missing token in body"
    raise OnedataApiError(msg, response if isinstance(response, dict) else None)


async def get_or_create_scoped_token(
    space_id: str,
    *,
    space_name: str | None = None,
    readonly: bool = False,
) -> str:
    prune_token_cache(drop_expired=True)
    if not _truthy("ONEDATA_E2E_TOKEN_CACHE_REFRESH"):
        cached = _load_cache().get(_cache_key(space_id, readonly=readonly))
        if isinstance(cached, dict) and isinstance(cached.get("token"), str):
            expires = cached.get("validUntil")
            if isinstance(expires, int) and expires > int(time.time()) + 60:
                return cached["token"]

    base_name = f"mcp-e2e-base-{space_id[:12]}-{uuid.uuid4().hex[:6]}"
    base = await _create_named_base_token(base_name)
    confined = await confine_provider_token(
        base,
        space_id,
        space_name=space_name,
        readonly=readonly,
    )
    entry = {
        "token": confined,
        "validUntil": int(time.time()) + _TOKEN_TTL_SECONDS,
        "spaceId": space_id,
        "readonly": readonly,
    }
    cache = _load_cache()
    cache[_cache_key(space_id, readonly=readonly)] = entry
    _save_cache(cache)
    return confined


async def _remove_space_datasets(space: IsolatedE2ESpace, token: str) -> None:
    """Drop attached/detached datasets so listing tests start from an empty catalog."""
    from onedata_mcp.api import spaces as spaces_api

    previous = os.environ.get("ONEDATA_ONEPROVIDER_TOKEN")
    os.environ["ONEDATA_ONEPROVIDER_TOKEN"] = token
    try:
        for state in ("attached", "detached"):
            listing = await spaces_api.list_space_datasets(
                space.space_id,
                state=state,  # type: ignore[arg-type]
                limit=1000,
            )
            datasets = listing.get("datasets")
            if not isinstance(datasets, list):
                continue
            for row in datasets:
                if not isinstance(row, dict):
                    continue
                dataset_id = row.get("datasetId")
                if not isinstance(dataset_id, str):
                    continue
                with suppress(OnedataApiError):
                    await _oneprovider_with_token(token, "DELETE", f"/datasets/{dataset_id}")
    finally:
        if previous is None:
            os.environ.pop("ONEDATA_ONEPROVIDER_TOKEN", None)
        else:
            os.environ["ONEDATA_ONEPROVIDER_TOKEN"] = previous


def _api_status_code(exc: OnedataApiError) -> int | None:
    response = exc.response
    if isinstance(response, dict):
        code = response.get("status_code")
        if isinstance(code, int):
            return code
    return None


async def _list_space_files_for_reset(
    token: str,
    dir_id: str,
    *,
    retries: int = 5,
    retry_delay_s: float = 1.0,
) -> list[dict[str, Any]]:
    """``GET /data/{dirId}/files`` (swagger ``list_files_recursively``)."""

    last_exc: OnedataApiError | None = None
    for attempt in range(retries):
        try:
            listing = await _oneprovider_with_token(
                token,
                "GET",
                f"/data/{dir_id}/files",
                json_body={"limit": 1000, "attributes": ["fileId", "path"]},
            )
            break
        except OnedataApiError as exc:
            last_exc = exc
            if _api_status_code(exc) == 404 and attempt + 1 < retries:
                await _async_sleep(retry_delay_s)
                continue
            if _api_status_code(exc) == 404:
                return []
            raise
    else:
        if last_exc is not None:
            raise last_exc
        return []

    collected: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        body = listing.get("body")
        if not isinstance(body, dict):
            break
        files = body.get("files")
        if isinstance(files, list):
            collected.extend(row for row in files if isinstance(row, dict))
        if body.get("isLast") is True:
            break
        page_token = body.get("nextPageToken")
        if not isinstance(page_token, str) or not page_token:
            break
        listing = await _oneprovider_with_token(
            token,
            "GET",
            f"/data/{dir_id}/files",
            json_body={
                "limit": 1000,
                "token": page_token,
                "attributes": ["fileId", "path"],
            },
        )
    return collected


async def reset_space_contents(space: IsolatedE2ESpace, *, admin_token: str | None = None) -> None:
    """Remove datasets and delete every child under the space root (admin token)."""
    from onedata_mcp.api import files as files_api

    token = admin_token or e2e_admin_oneprovider_token()

    await _remove_space_datasets(space, token)

    spaces = await _oneprovider_with_token(token, "GET", "/spaces")
    body = spaces.get("body")
    space_row: dict[str, Any] | None = None
    if isinstance(body, list):
        for row in body:
            if isinstance(row, dict) and row.get("spaceId") == space.space_id:
                space_row = row
                break
    if space_row is None:
        return
    dir_id = space_row.get("dirId")
    if not isinstance(dir_id, str):
        return

    files = await _list_space_files_for_reset(token, dir_id)
    entries = [f for f in files if f.get("path") not in (None, ".", "")]
    entries.sort(key=lambda e: len(str(e.get("path", ""))), reverse=True)

    previous = os.environ.get("ONEDATA_ONEPROVIDER_TOKEN")
    os.environ["ONEDATA_ONEPROVIDER_TOKEN"] = token
    try:
        for entry in entries:
            file_id = entry.get("fileId")
            if isinstance(file_id, str):
                try:
                    await files_api.delete_file(file_id)
                    continue
                except (OnedataApiError, FileNotFoundError):
                    pass
            rel = str(entry.get("path", "")).lstrip("/")
            logical = f"{space.root_path}/{rel}" if rel else space.root_path
            await files_api.delete_file(logical)
    finally:
        if previous is None:
            os.environ.pop("ONEDATA_ONEPROVIDER_TOKEN", None)
        else:
            os.environ["ONEDATA_ONEPROVIDER_TOKEN"] = previous


async def delete_user_space(space_id: str) -> None:
    await _onezone("DELETE", f"/user/spaces/{space_id}")
    prune_token_cache(space_ids={space_id}, drop_expired=False)


def make_space_name(*, suffix: str = "") -> str:
    if suffix in _STABLE_ISOLATED_SPACE_NAMES:
        return _STABLE_ISOLATED_SPACE_NAMES[suffix]
    prefix = os.getenv("ONEDATA_E2E_SPACE_PREFIX", _DEFAULT_PREFIX).strip() or _DEFAULT_PREFIX
    part = suffix or uuid.uuid4().hex[:10]
    name = f"{prefix}-{part}"
    return name.replace("_", "-")[:63]


def _e2e_harvester_name() -> str:
    prefix = os.getenv("ONEDATA_E2E_SPACE_PREFIX", _DEFAULT_PREFIX).strip() or _DEFAULT_PREFIX
    return f"{prefix}-harvester".replace("_", "-")[:63]


def _e2e_harvester_index_name() -> str:
    prefix = os.getenv("ONEDATA_E2E_SPACE_PREFIX", _DEFAULT_PREFIX).strip() or _DEFAULT_PREFIX
    return f"{prefix}-index".replace("_", "-")[:63]


def isolated_scope_needs_harvester(scope: str) -> bool:
    return scope in _HARVESTER_SCOPES


async def _list_user_harvester_ids() -> list[str]:
    response = await _onezone("GET", "/user/harvesters")
    body = response.get("body")
    if not isinstance(body, dict):
        return []
    harvesters = body.get("harvesters")
    if not isinstance(harvesters, list):
        return []
    return [hid for hid in harvesters if isinstance(hid, str)]


async def _find_user_harvester_id_by_name(name: str) -> str | None:
    for harvester_id in await _list_user_harvester_ids():
        response = await _onezone("GET", f"/user/harvesters/{harvester_id}")
        body = response.get("body")
        if isinstance(body, dict) and body.get("name") == name:
            return harvester_id
    return None


async def _create_user_harvester(name: str) -> str:
    body: dict[str, Any] = {"name": name}
    endpoint = os.getenv("ONEDATA_E2E_HARVESTING_BACKEND_ENDPOINT", "").strip()
    backend_type = os.getenv(
        "ONEDATA_E2E_HARVESTING_BACKEND_TYPE",
        "elasticsearch_harvesting_backend",
    ).strip()
    if endpoint:
        body["harvestingBackendEndpoint"] = endpoint
        body["harvestingBackendType"] = backend_type
    response = await _onezone("POST", "/user/harvesters", json_body=body)
    headers = response.get("headers")
    header_map = headers if isinstance(headers, dict) else {}
    location = header_map.get("Location") or header_map.get("location")
    if isinstance(location, str):
        harvester_id = resource_id_from_location(location)
        if harvester_id:
            return harvester_id
    msg = (
        "create_user_harvester: could not resolve harvester id from Location header. "
        "Set ONEDATA_E2E_HARVESTING_BACKEND_ENDPOINT if the zone has no default backend."
    )
    raise OnedataApiError(msg, response if isinstance(response, dict) else None)


async def _list_harvester_index_ids(harvester_id: str) -> list[str]:
    response = await _onezone("GET", f"/harvesters/{harvester_id}/indices")
    body = response.get("body")
    if not isinstance(body, dict):
        return []
    indices = body.get("indices")
    if not isinstance(indices, list):
        return []
    return [index_id for index_id in indices if isinstance(index_id, str)]


async def _create_harvester_index(harvester_id: str, name: str) -> str:
    response = await _onezone(
        "POST",
        f"/harvesters/{harvester_id}/indices",
        json_body={
            "name": name,
            "includeMetadata": ["xattrs", "json"],
            "includeFileDetails": ["fileName", "spaceId"],
        },
    )
    headers = response.get("headers")
    header_map = headers if isinstance(headers, dict) else {}
    location = header_map.get("Location") or header_map.get("location")
    if isinstance(location, str):
        index_id = resource_id_from_location(location)
        if index_id:
            return index_id
    msg = (
        "create_harvester_index: could not resolve index id (requires oz_harvesters_update or "
        "set ONEDATA_E2E_HARVESTER_INDEX_ID to an existing index on ONEDATA_E2E_HARVESTER_ID)"
    )
    raise OnedataApiError(msg, response if isinstance(response, dict) else None)


async def _ensure_harvester_index(harvester_id: str) -> str:
    env_index = os.getenv("ONEDATA_E2E_HARVESTER_INDEX_ID", "").strip()
    if env_index:
        return env_index
    indices = await _list_harvester_index_ids(harvester_id)
    if indices:
        return indices[0]
    return await _create_harvester_index(harvester_id, _e2e_harvester_index_name())


async def _first_user_harvester_with_index() -> tuple[str, str] | None:
    for harvester_id in await _list_user_harvester_ids():
        indices = await _list_harvester_index_ids(harvester_id)
        if indices:
            return harvester_id, indices[0]
    return None


async def get_or_create_e2e_harvester() -> tuple[str, str]:
    """Return stable ``(harvester_id, index_id)`` for isolated E2E (cached per process)."""
    global _E2E_HARVESTER_PAIR  # noqa: PLW0603
    if _E2E_HARVESTER_PAIR is not None:
        return _E2E_HARVESTER_PAIR

    env_harvester = os.getenv("ONEDATA_E2E_HARVESTER_ID", "").strip()
    if env_harvester:
        harvester_id = env_harvester
    else:
        harvester_name = _e2e_harvester_name()
        harvester_id = await _find_user_harvester_id_by_name(harvester_name)
        if not harvester_id:
            has_backend = bool(os.getenv("ONEDATA_E2E_HARVESTING_BACKEND_ENDPOINT", "").strip())
            if has_backend:
                harvester_id = await _create_user_harvester(harvester_name)
            else:
                reused = await _first_user_harvester_with_index()
                if reused is None:
                    msg = (
                        "No E2E harvester available: set ONEDATA_E2E_HARVESTER_ID, or "
                        "ONEDATA_E2E_HARVESTING_BACKEND_ENDPOINT to create "
                        f"{harvester_name!r}, or create a user harvester with at least one index"
                    )
                    raise RuntimeError(msg)
                harvester_id, index_id = reused
                _E2E_HARVESTER_PAIR = (harvester_id, index_id)
                return _E2E_HARVESTER_PAIR

    index_id = await _ensure_harvester_index(harvester_id)
    _E2E_HARVESTER_PAIR = (harvester_id, index_id)
    return _E2E_HARVESTER_PAIR


async def _harvester_attached_space_ids(harvester_id: str) -> set[str]:
    response = await _onezone("GET", f"/harvesters/{harvester_id}/spaces")
    body = response.get("body")
    if not isinstance(body, dict):
        return set()
    spaces = body.get("spaces")
    if not isinstance(spaces, list):
        return set()
    return {space_id for space_id in spaces if isinstance(space_id, str)}


async def _create_space_join_harvester_token(harvester_id: str) -> str:
    """Invite token for ``POST /spaces/{id}/harvesters/join`` (space-side join)."""
    response = await _onezone("POST", f"/harvesters/{harvester_id}/spaces/token")
    body = response.get("body")
    if isinstance(body, dict) and isinstance(body.get("token"), str):
        return body["token"]

    token_name = f"mcp-e2e-sjoin-{harvester_id[:12]}-{uuid.uuid4().hex[:8]}"
    response = await _onezone(
        "POST",
        "/user/tokens/named",
        json_body={
            "name": token_name,
            "type": {
                "inviteToken": {
                    "inviteType": "spaceJoinHarvester",
                    "harvesterId": harvester_id,
                }
            },
        },
    )
    body = response.get("body")
    if isinstance(body, dict) and isinstance(body.get("token"), str):
        return body["token"]
    msg = (
        "create_space_join_harvester_token: missing token "
        "(needs harvester_invite_space on the E2E harvester)"
    )
    raise OnedataApiError(msg, response if isinstance(response, dict) else None)


async def _space_harvester_ids(space_id: str) -> set[str]:
    response = await _onezone("GET", f"/spaces/{space_id}/harvesters")
    body = response.get("body")
    if not isinstance(body, dict):
        return set()
    harvesters = body.get("harvesters")
    if not isinstance(harvesters, list):
        return set()
    return {hid for hid in harvesters if isinstance(hid, str)}


async def _attach_space_to_harvester(space_id: str, harvester_id: str) -> None:
    """Join space to harvester as the space owner (``spaceJoinHarvester`` flow)."""
    if harvester_id in await _space_harvester_ids(space_id):
        return
    token = await _create_space_join_harvester_token(harvester_id)
    await _onezone(
        "POST",
        f"/spaces/{space_id}/harvesters/join",
        json_body={"token": token},
    )
    if harvester_id not in await _space_harvester_ids(space_id):
        msg = (
            f"Space {space_id} is not linked to harvester {harvester_id} after "
            "POST /spaces/{id}/harvesters/join"
        )
        raise RuntimeError(msg)


async def ensure_isolated_space_harvester(space: IsolatedE2ESpace) -> tuple[str, str]:
    """Attach the shared E2E harvester (and index) to ``space`` when missing."""
    if _truthy("ONEDATA_E2E_SKIP_HARVESTER"):
        msg = "ONEDATA_E2E_SKIP_HARVESTER is set but this test scope requires a harvester"
        raise RuntimeError(msg)

    harvester_id, index_id = await get_or_create_e2e_harvester()
    await _attach_space_to_harvester(space.space_id, harvester_id)
    return harvester_id, index_id


async def provision_isolated_space(
    *,
    name: str | None = None,
    scope: str = "function",
    confined_write: bool = False,
) -> IsolatedE2ESpace:
    """Get or create a space by stable name, ensure provider support, return scoped tokens.

    By default only a **read-only** confined token is minted (``data.readonly``) for MCP.
    Pass ``confined_write=True`` (or pytest marker ``e2e_isolated_confined_write``) to also
    mint a read-write confined token for mutation scenarios.
    """
    space_name = name or make_space_name(suffix=scope)
    space_id, created = await get_or_create_user_space(space_name)

    if not _truthy("ONEDATA_E2E_SKIP_PROVIDER_SUPPORT"):
        provider_id = await resolve_target_provider_id()
        if created or not await space_has_provider_support(space_id, provider_id):
            support = await create_space_support_token(space_id)
            await add_provider_support(space_id, support)
        await ensure_space_supported_on_provider(space_id)

    await wait_until_space_on_provider(space_id)

    read_token = await get_or_create_scoped_token(space_id, space_name=space_name, readonly=True)
    write_token: str | None = None
    if confined_write:
        write_token = await get_or_create_scoped_token(
            space_id, space_name=space_name, readonly=False
        )
    return IsolatedE2ESpace(
        space_id=space_id,
        space_name=space_name,
        provider_token=read_token,
        provider_token_write=write_token,
        reused=not created,
    )
