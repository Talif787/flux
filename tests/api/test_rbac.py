from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import KeyFactory


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def test_reader_can_list_but_not_create(client: AsyncClient, key_factory: KeyFactory) -> None:
    reader, _ = await key_factory("model.read")
    assert (await client.get("/v1/models", headers=_auth(reader))).status_code == 200
    denied = await client.post(
        "/v1/models", json={"name": "m", "family": "llama"}, headers=_auth(reader)
    )
    assert denied.status_code == 403


async def test_key_without_model_roles_is_forbidden(
    client: AsyncClient, key_factory: KeyFactory
) -> None:
    norole, _ = await key_factory("tenant.admin")
    assert (await client.get("/v1/models", headers=_auth(norole))).status_code == 403


async def test_platform_admin_is_superuser_on_models(client: AsyncClient, admin_key: str) -> None:
    created = await client.post(
        "/v1/models", json={"name": "m", "family": "llama"}, headers=_auth(admin_key)
    )
    assert created.status_code == 201


async def test_writer_can_create(client: AsyncClient, key_factory: KeyFactory) -> None:
    writer, _ = await key_factory("model.write")
    created = await client.post(
        "/v1/models", json={"name": "m", "family": "llama"}, headers=_auth(writer)
    )
    assert created.status_code == 201
