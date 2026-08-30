from __future__ import annotations

from httpx import AsyncClient


def _auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


async def test_health_endpoints(client: AsyncClient) -> None:
    assert (await client.get("/livez")).status_code == 200
    ready = await client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


async def test_register_model_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/v1/models", json={"name": "m", "family": "llama"})
    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_register_and_fetch_model(client: AsyncClient, api_key: str) -> None:
    created = await client.post(
        "/v1/models",
        json={"name": "llama-3-8b", "family": "llama"},
        headers=_auth(api_key),
    )
    assert created.status_code == 201
    model_id = created.json()["id"]

    fetched = await client.get(f"/v1/models/{model_id}", headers=_auth(api_key))
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "llama-3-8b"

    listing = await client.get("/v1/models", headers=_auth(api_key))
    assert listing.status_code == 200
    assert listing.json()["meta"]["total"] == 1


async def test_duplicate_model_returns_conflict(
    client: AsyncClient, api_key: str
) -> None:
    body = {"name": "dup", "family": "llama"}
    assert (
        await client.post("/v1/models", json=body, headers=_auth(api_key))
    ).status_code == 201
    conflict = await client.post("/v1/models", json=body, headers=_auth(api_key))
    assert conflict.status_code == 409


async def test_register_version_and_validation(
    client: AsyncClient, api_key: str
) -> None:
    created = await client.post(
        "/v1/models",
        json={"name": "m", "family": "llama"},
        headers=_auth(api_key),
    )
    model_id = created.json()["id"]

    version = await client.post(
        f"/v1/models/{model_id}/versions",
        json={"version": "v1", "precision": "fp16", "context_length": 8192},
        headers=_auth(api_key),
    )
    assert version.status_code == 201
    assert version.json()["status"] == "registered"

    invalid = await client.post(
        f"/v1/models/{model_id}/versions",
        json={"version": "v2", "precision": "not-a-precision", "context_length": 1},
        headers=_auth(api_key),
    )
    assert invalid.status_code == 422


async def test_get_missing_model_returns_not_found(
    client: AsyncClient, api_key: str
) -> None:
    resp = await client.get("/v1/models/does-not-exist", headers=_auth(api_key))
    assert resp.status_code == 404
