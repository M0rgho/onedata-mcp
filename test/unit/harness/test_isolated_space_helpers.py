"""Unit tests for E2E space helpers (test/support/e2e_isolated_space.py)."""

from __future__ import annotations

import base64

from e2e_isolated_space import (
    _b64_path,
    _canonical_space_path,
    _cache_key,
    _get_onepanel_config,
    _support_size_bytes,
    e2e_admin_oneprovider_token,
    make_space_name,
)


def test_canonical_and_b64_path_round_trip() -> None:
    space_id = "fb519d81146bcc635b890ff03a5da0fdch34fe"
    canonical = _canonical_space_path(space_id)
    assert canonical == f"/{space_id}"
    decoded = base64.standard_b64decode(_b64_path(canonical)).decode("utf-8")
    assert decoded == canonical


def test_cache_key_includes_host_and_mode(monkeypatch) -> None:
    monkeypatch.setenv("ONEDATA_ONEPROVIDER_HOST", "https://provider.example")
    rw = _cache_key("sid", readonly=False)
    ro = _cache_key("sid", readonly=True)
    assert rw != ro
    assert rw.endswith(":rw")
    assert ro.endswith(":ro")


def test_make_space_name_prefix(monkeypatch) -> None:
    monkeypatch.setenv("ONEDATA_E2E_SPACE_PREFIX", "mcp-e2e")
    name = make_space_name(suffix="demo")
    assert name.startswith("mcp-e2e-demo")


def test_make_space_name_stable_per_scope(monkeypatch) -> None:
    monkeypatch.setenv("ONEDATA_E2E_SPACE_PREFIX", "mcp-e2e")
    assert make_space_name(suffix="read-state") == "mcp-e2e-read-state"
    assert make_space_name(suffix="read-state") == "mcp-e2e-read-state"


def test_e2e_admin_token_prefers_dedicated_env(monkeypatch) -> None:
    monkeypatch.setenv("ONEDATA_E2E_ADMIN_TOKEN", "admin-only")
    monkeypatch.setenv("ONEDATA_ONEPROVIDER_TOKEN", "provider-env")
    assert e2e_admin_oneprovider_token() == "admin-only"


def test_onepanel_base_url(monkeypatch) -> None:
    monkeypatch.setenv("ONEDATA_ONEPROVIDER_HOST", "https://provider.example")
    monkeypatch.setenv("ONEDATA_E2E_ONEPANEL_TOKEN", "panel-secret")
    monkeypatch.delenv("ONEDATA_E2E_ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("ONEDATA_ONEPROVIDER_TOKEN", "fallback")
    config = _get_onepanel_config()
    assert config.base_url == "https://provider.example/api/v3/onepanel"
    assert config.auth_headers["X-Auth-Token"] == "panel-secret"


def test_onepanel_falls_back_to_e2e_admin(monkeypatch) -> None:
    monkeypatch.setenv("ONEDATA_ONEPROVIDER_HOST", "https://provider.example")
    monkeypatch.delenv("ONEDATA_E2E_ONEPANEL_TOKEN", raising=False)
    monkeypatch.setenv("ONEDATA_E2E_ADMIN_TOKEN", "admin-secret")
    monkeypatch.delenv("ONEDATA_ONEPROVIDER_TOKEN", raising=False)
    config = _get_onepanel_config()
    assert config.auth_headers["X-Auth-Token"] == "admin-secret"


def test_support_size_default(monkeypatch) -> None:
    monkeypatch.delenv("ONEDATA_E2E_SUPPORT_SIZE_BYTES", raising=False)
    assert _support_size_bytes() == 100 * 1024**2
