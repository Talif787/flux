from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import KeyFactory


def _auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


async def test_register_worker_requires_worker_role(
    client: AsyncClient, key_factory: KeyFactory
) -> None:
    raw, _ = await key_factory("model.read")
    resp = await client.put(
        "/v1/workers/w-1",
        json={"name": "node-1", "base_url": "http://w1:8090"},
        headers=_auth(raw),
    )
    assert resp.status_code == 403


async def test_register_worker_rejects_anonymous(client: AsyncClient) -> None:
    resp = await client.put(
        "/v1/workers/w-1",
        json={"name": "node-1", "base_url": "http://w1:8090"},
    )
    assert resp.status_code == 401


async def test_register_and_list_worker(client: AsyncClient, key_factory: KeyFactory) -> None:
    raw, _ = await key_factory("worker.register")

    reg = await client.put(
        "/v1/workers/w-1",
        json={
            "name": "node-1",
            "base_url": "http://w1:8090",
            "served_models": ["gpt-stub", "llama-3-8b"],
            "max_concurrency": 4,
        },
        headers=_auth(raw),
    )
    assert reg.status_code == 200
    body = reg.json()
    assert body["id"] == "w-1"
    assert body["status"] == "active"
    assert body["served_models"] == ["gpt-stub", "llama-3-8b"]

    listing = await client.get("/v1/workers", headers=_auth(raw))
    assert listing.status_code == 200
    lbody = listing.json()
    assert lbody["meta"]["total"] == 1
    assert lbody["items"][0]["id"] == "w-1"


async def test_heartbeat_updates_worker(client: AsyncClient, key_factory: KeyFactory) -> None:
    raw, _ = await key_factory("worker.register")
    await client.put(
        "/v1/workers/w-1",
        json={"name": "node-1", "base_url": "http://w1:8090"},
        headers=_auth(raw),
    )
    hb = await client.post("/v1/workers/w-1/heartbeat", headers=_auth(raw))
    assert hb.status_code == 200
    assert hb.json()["id"] == "w-1"


async def test_heartbeat_unknown_worker_returns_404(
    client: AsyncClient, key_factory: KeyFactory
) -> None:
    raw, _ = await key_factory("worker.register")
    hb = await client.post("/v1/workers/ghost/heartbeat", headers=_auth(raw))
    assert hb.status_code == 404


async def test_deregister_is_idempotent(client: AsyncClient, key_factory: KeyFactory) -> None:
    raw, _ = await key_factory("worker.register")
    await client.put(
        "/v1/workers/w-1",
        json={"name": "node-1", "base_url": "http://w1:8090"},
        headers=_auth(raw),
    )
    first = await client.delete("/v1/workers/w-1", headers=_auth(raw))
    second = await client.delete("/v1/workers/w-1", headers=_auth(raw))
    assert first.status_code == 204
    assert second.status_code == 204
