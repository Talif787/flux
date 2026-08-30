from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import KeyFactory


def _auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


async def _register_model(client: AsyncClient, api_key: str, name: str) -> None:
    resp = await client.post(
        "/v1/models",
        json={"name": name, "family": "stub"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201


async def _invoke(client: AsyncClient, api_key: str, model: str, content: str) -> None:
    resp = await client.post(
        "/v1/chat/completions",
        json={"model": model, "messages": [{"role": "user", "content": content}]},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200


# --- pricing CRUD (platform-admin manages, tenant-admin views) ---


async def test_pricing_requires_platform_admin_to_set(
    client: AsyncClient, key_factory: KeyFactory
) -> None:
    raw, _ = await key_factory("tenant.admin")
    resp = await client.put(
        "/v1/pricing/gpt-stub",
        json={"prompt_per_1k": "0.001", "completion_per_1k": "0.002"},
        headers=_auth(raw),
    )
    assert resp.status_code == 403


async def test_set_get_list_delete_price(client: AsyncClient, key_factory: KeyFactory) -> None:
    admin, _ = await key_factory("platform.admin")

    put = await client.put(
        "/v1/pricing/gpt-stub",
        json={"prompt_per_1k": "0.001", "completion_per_1k": "0.002"},
        headers=_auth(admin),
    )
    assert put.status_code == 200
    body = put.json()
    assert body["model_name"] == "gpt-stub"
    assert body["prompt_per_1k"] == "0.001"

    got = await client.get("/v1/pricing/gpt-stub", headers=_auth(admin))
    assert got.status_code == 200
    assert got.json()["completion_per_1k"] == "0.002"

    listing = await client.get("/v1/pricing", headers=_auth(admin))
    assert listing.status_code == 200
    assert any(p["model_name"] == "gpt-stub" for p in listing.json()["items"])

    deleted = await client.delete("/v1/pricing/gpt-stub", headers=_auth(admin))
    assert deleted.status_code == 204
    missing = await client.get("/v1/pricing/gpt-stub", headers=_auth(admin))
    assert missing.status_code == 404


# --- usage report (metering hook end to end) ---


async def test_usage_report_reflects_invocations(
    client: AsyncClient, key_factory: KeyFactory
) -> None:
    # One key with the roles to register a model, invoke, and view usage.
    raw, tenant_id = await key_factory("model.write,inference.invoke,tenant.admin")
    await _register_model(client, raw, "gpt-stub")
    await _invoke(client, raw, "gpt-stub", "hello there friend")
    await _invoke(client, raw, "gpt-stub", "another request here")

    resp = await client.get("/v1/usage", headers=_auth(raw))
    assert resp.status_code == 200
    report = resp.json()
    assert report["tenant"] == tenant_id
    assert report["currency"] == "USD"

    lines = {line["model_name"]: line for line in report["lines"]}
    assert "gpt-stub" in lines
    gpt = lines["gpt-stub"]
    assert gpt["request_count"] == 2
    assert gpt["prompt_tokens"] > 0
    assert gpt["completion_tokens"] > 0
    # default pricing applied, so cost is a positive decimal string
    assert float(gpt["cost"]) > 0
    assert report["totals"]["request_count"] == 2


async def test_usage_report_uses_configured_price(
    client: AsyncClient, key_factory: KeyFactory
) -> None:
    admin, tenant_id = await key_factory("platform.admin,model.write,inference.invoke")
    # Set a high price so the cost is easy to assert as nonzero and model-specific.
    await client.put(
        "/v1/pricing/gpt-stub",
        json={"prompt_per_1k": "1.0", "completion_per_1k": "1.0"},
        headers=_auth(admin),
    )
    await _register_model(client, admin, "gpt-stub")
    await _invoke(client, admin, "gpt-stub", "price this request please")

    resp = await client.get(f"/v1/usage?tenant={tenant_id}", headers=_auth(admin))
    assert resp.status_code == 200
    line = resp.json()["lines"][0]
    total_tokens = line["prompt_tokens"] + line["completion_tokens"]
    # cost = total_tokens/1000 * 1.0
    assert abs(float(line["cost"]) - total_tokens / 1000) < 1e-9


async def test_usage_report_denies_cross_tenant_for_non_admin(
    client: AsyncClient, key_factory: KeyFactory
) -> None:
    raw, _ = await key_factory("tenant.admin")
    resp = await client.get("/v1/usage?tenant=some-other-tenant", headers=_auth(raw))
    assert resp.status_code == 403


async def test_usage_report_requires_a_viewer_role(
    client: AsyncClient, key_factory: KeyFactory
) -> None:
    raw, _ = await key_factory("inference.invoke")  # not tenant.admin/platform.admin
    resp = await client.get("/v1/usage", headers=_auth(raw))
    assert resp.status_code == 403
