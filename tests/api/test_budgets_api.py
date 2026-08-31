from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient

from flux.config import Settings, get_settings
from tests.conftest import KeyFactory


def _auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


async def _register_model(client: AsyncClient, api_key: str, name: str) -> None:
    resp = await client.post(
        "/v1/models", json={"name": name, "family": "stub"}, headers=_auth(api_key)
    )
    assert resp.status_code == 201


async def _invoke(client: AsyncClient, api_key: str, model: str) -> int:
    resp = await client.post(
        "/v1/chat/completions",
        json={"model": model, "messages": [{"role": "user", "content": "hello there friend"}]},
        headers=_auth(api_key),
    )
    return resp.status_code


# --- budget CRUD + RBAC ---


async def test_set_list_get_delete_budget(client: AsyncClient, key_factory: KeyFactory) -> None:
    admin, _ = await key_factory("platform.admin")
    viewer, viewer_tenant = await key_factory("tenant.admin")

    put = await client.put(
        f"/v1/budgets/{viewer_tenant}",
        json={"monthly_limit": "25.00"},
        headers=_auth(admin),
    )
    assert put.status_code == 200
    assert put.json()["monthly_limit"] == "25.00"

    listing = await client.get("/v1/budgets", headers=_auth(admin))
    assert listing.status_code == 200
    assert any(b["tenant_id"] == viewer_tenant for b in listing.json()["items"])

    # tenant-admin can view its own budget status
    got = await client.get(f"/v1/budgets/{viewer_tenant}", headers=_auth(viewer))
    assert got.status_code == 200
    body = got.json()
    assert body["monthly_limit"] == "25.00"
    assert body["exceeded"] is False
    assert body["currency"] == "USD"

    deleted = await client.delete(f"/v1/budgets/{viewer_tenant}", headers=_auth(admin))
    assert deleted.status_code == 204
    missing = await client.get(f"/v1/budgets/{viewer_tenant}", headers=_auth(admin))
    assert missing.status_code == 404


async def test_managing_budgets_requires_platform_admin(
    client: AsyncClient, key_factory: KeyFactory
) -> None:
    viewer, viewer_tenant = await key_factory("tenant.admin")
    resp = await client.put(
        f"/v1/budgets/{viewer_tenant}",
        json={"monthly_limit": "5.00"},
        headers=_auth(viewer),
    )
    assert resp.status_code == 403


async def test_viewing_budget_requires_viewer_role(
    client: AsyncClient, key_factory: KeyFactory
) -> None:
    raw, tenant_id = await key_factory("inference.invoke")
    resp = await client.get(f"/v1/budgets/{tenant_id}", headers=_auth(raw))
    assert resp.status_code == 403


async def test_cannot_view_another_tenants_budget(
    client: AsyncClient, key_factory: KeyFactory
) -> None:
    viewer, _ = await key_factory("tenant.admin")
    resp = await client.get("/v1/budgets/some-other-tenant", headers=_auth(viewer))
    assert resp.status_code == 403


async def test_status_reflects_usage(client: AsyncClient, key_factory: KeyFactory) -> None:
    admin, tenant_id = await key_factory("platform.admin,model.write,inference.invoke,tenant.admin")
    await _register_model(client, admin, "gpt-stub")
    await client.put(
        f"/v1/budgets/{tenant_id}",
        json={"monthly_limit": "100.00"},
        headers=_auth(admin),
    )
    assert await _invoke(client, admin, "gpt-stub") == 200

    status = await client.get(f"/v1/budgets/{tenant_id}", headers=_auth(admin))
    assert status.status_code == 200
    body = status.json()
    assert float(body["spent"]) > 0
    assert body["exceeded"] is False
    assert float(body["remaining"]) < 100.0


# --- enforcement (serving path returns 402 when over budget) ---


async def test_enforcement_blocks_when_over_budget(
    app: FastAPI, client: AsyncClient, settings: Settings, key_factory: KeyFactory
) -> None:
    # Flip enforcement on for this app instance only.
    app.dependency_overrides[get_settings] = lambda: settings.model_copy(
        update={"budget_enforcement_enabled": True}
    )
    admin, tenant_id = await key_factory("platform.admin")

    await _register_model(client, admin, "gpt-stub")
    # High price so a single request's cost clears a tiny budget.
    await client.put(
        "/v1/pricing/gpt-stub",
        json={"prompt_per_1k": "1.0", "completion_per_1k": "1.0"},
        headers=_auth(admin),
    )
    await client.put(
        f"/v1/budgets/{tenant_id}",
        json={"monthly_limit": "0.001"},
        headers=_auth(admin),
    )

    # First call: no prior spend, allowed.
    assert await _invoke(client, admin, "gpt-stub") == 200
    # Second call: prior spend now exceeds the tiny budget, blocked with 402.
    assert await _invoke(client, admin, "gpt-stub") == 402


async def test_enforcement_off_by_default_allows_over_budget(
    client: AsyncClient, key_factory: KeyFactory
) -> None:
    admin, tenant_id = await key_factory("platform.admin")
    await _register_model(client, admin, "gpt-stub")
    await client.put(
        "/v1/pricing/gpt-stub",
        json={"prompt_per_1k": "1.0", "completion_per_1k": "1.0"},
        headers=_auth(admin),
    )
    await client.put(
        f"/v1/budgets/{tenant_id}",
        json={"monthly_limit": "0.000001"},
        headers=_auth(admin),
    )
    # Enforcement is disabled by default, so repeated calls all succeed.
    assert await _invoke(client, admin, "gpt-stub") == 200
    assert await _invoke(client, admin, "gpt-stub") == 200
