from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import KeyFactory


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def _create_tenant(client: AsyncClient, admin_key: str, name: str) -> str:
    resp = await client.post("/v1/tenants", json={"name": name}, headers=_auth(admin_key))
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_tenant_lifecycle_as_admin(client: AsyncClient, admin_key: str) -> None:
    tenant_id = await _create_tenant(client, admin_key, "acme")

    listing = await client.get("/v1/tenants", headers=_auth(admin_key))
    assert listing.status_code == 200
    assert any(t["id"] == tenant_id for t in listing.json()["items"])

    suspended = await client.post(f"/v1/tenants/{tenant_id}/suspend", headers=_auth(admin_key))
    assert suspended.json()["status"] == "suspended"

    reactivated = await client.post(f"/v1/tenants/{tenant_id}/reactivate", headers=_auth(admin_key))
    assert reactivated.json()["status"] == "active"


async def test_non_admin_cannot_manage_tenants(client: AsyncClient, api_key: str) -> None:
    resp = await client.post("/v1/tenants", json={"name": "nope"}, headers=_auth(api_key))
    assert resp.status_code == 403


async def test_duplicate_tenant_name_conflicts(client: AsyncClient, admin_key: str) -> None:
    await _create_tenant(client, admin_key, "dup")
    resp = await client.post("/v1/tenants", json={"name": "dup"}, headers=_auth(admin_key))
    assert resp.status_code == 409


async def test_issue_key_returns_plaintext_once_and_it_works(
    client: AsyncClient, admin_key: str
) -> None:
    tenant_id = await _create_tenant(client, admin_key, "acme")
    issued = await client.post(
        f"/v1/tenants/{tenant_id}/api-keys",
        json={"name": "ci", "roles": ["model.read"]},
        headers=_auth(admin_key),
    )
    assert issued.status_code == 201
    body = issued.json()
    plaintext = body["api_key"]
    assert plaintext.startswith("flux_")
    assert body["prefix"] == plaintext[:12]

    # listing must not expose the secret, only the prefix
    listing = await client.get(f"/v1/tenants/{tenant_id}/api-keys", headers=_auth(admin_key))
    assert listing.status_code == 200
    item = listing.json()["items"][0]
    assert "api_key" not in item
    assert item["prefix"] == plaintext[:12]

    # the issued key authenticates and carries exactly its granted role
    assert (await client.get("/v1/models", headers=_auth(plaintext))).status_code == 200
    denied = await client.post(
        "/v1/models", json={"name": "m", "family": "llama"}, headers=_auth(plaintext)
    )
    assert denied.status_code == 403


async def test_revoked_key_stops_authenticating(client: AsyncClient, admin_key: str) -> None:
    tenant_id = await _create_tenant(client, admin_key, "acme")
    issued = await client.post(
        f"/v1/tenants/{tenant_id}/api-keys",
        json={"name": "ci", "roles": ["model.read"]},
        headers=_auth(admin_key),
    )
    body = issued.json()
    plaintext, key_id = body["api_key"], body["id"]
    assert (await client.get("/v1/models", headers=_auth(plaintext))).status_code == 200

    revoked = await client.post(
        f"/v1/tenants/{tenant_id}/api-keys/{key_id}/revoke", headers=_auth(admin_key)
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    assert (await client.get("/v1/models", headers=_auth(plaintext))).status_code == 401


async def test_tenant_admin_scope_and_privilege_escalation(
    client: AsyncClient, admin_key: str, key_factory: KeyFactory
) -> None:
    tenant_id = await _create_tenant(client, admin_key, "acme")
    ta_key, _ = await key_factory("tenant.admin", tenant_id=tenant_id)

    # tenant admin may issue a scoped key within its own tenant
    ok = await client.post(
        f"/v1/tenants/{tenant_id}/api-keys",
        json={"name": "svc", "roles": ["model.read"]},
        headers=_auth(ta_key),
    )
    assert ok.status_code == 201

    # but not for a different tenant
    other = await _create_tenant(client, admin_key, "other")
    cross = await client.post(
        f"/v1/tenants/{other}/api-keys",
        json={"name": "svc", "roles": ["model.read"]},
        headers=_auth(ta_key),
    )
    assert cross.status_code == 403

    # and cannot escalate by granting platform.admin
    escalate = await client.post(
        f"/v1/tenants/{tenant_id}/api-keys",
        json={"name": "evil", "roles": ["platform.admin"]},
        headers=_auth(ta_key),
    )
    assert escalate.status_code == 403
