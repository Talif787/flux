from __future__ import annotations

import asyncio

import httpx

from flux.logging import get_logger

logger = get_logger(__name__)


class RegistrationClient:
    """Registers this worker with the control plane and keeps its lease alive.

    ``control_plane_url`` is where requests go; ``advertise_url`` is the base URL
    the gateway should use to reach this worker, sent as the registration payload.
    """

    def __init__(
        self,
        *,
        control_plane_url: str,
        api_key: str,
        worker_id: str,
        name: str,
        advertise_url: str,
        served_models: list[str],
        max_concurrency: int,
        timeout: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._worker_id = worker_id
        self._payload = {
            "name": name,
            "base_url": advertise_url,
            "served_models": served_models,
            "max_concurrency": max_concurrency,
        }
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=control_plane_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def register(self) -> None:
        response = await self._client.put(f"/v1/workers/{self._worker_id}", json=self._payload)
        response.raise_for_status()

    async def heartbeat(self) -> None:
        response = await self._client.post(f"/v1/workers/{self._worker_id}/heartbeat")
        response.raise_for_status()

    async def deregister(self) -> None:
        try:
            await self._client.delete(f"/v1/workers/{self._worker_id}")
        except httpx.HTTPError:
            logger.warning("worker_deregister_failed", worker=self._worker_id)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


async def register_with_retry(client: RegistrationClient, *, retries: int, delay: float) -> bool:
    """Register, retrying a few times; returns True on success, False if it gave up."""
    for attempt in range(retries + 1):
        try:
            await client.register()
            return True
        except Exception:
            if attempt < retries:
                await asyncio.sleep(delay)
    logger.error("worker_registration_failed")
    return False


async def heartbeat_loop(client: RegistrationClient, interval: float) -> None:
    """Send heartbeats forever; re-register if the lease has expired (404)."""
    while True:
        await asyncio.sleep(interval)
        try:
            await client.heartbeat()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                try:
                    await client.register()
                except Exception:
                    logger.warning("worker_reregister_failed")
            else:
                logger.warning("worker_heartbeat_failed")
        except Exception:
            logger.warning("worker_heartbeat_failed")
