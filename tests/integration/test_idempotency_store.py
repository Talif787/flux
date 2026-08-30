from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flux.errors import ConflictError, IdempotencyMismatchError
from flux.serving.persistence import SqlAlchemyIdempotencyStore


async def test_idempotency_lifecycle(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant, key, fp = "t1", "k1", "fp-abc"

    async with sessionmaker() as session:
        assert (await SqlAlchemyIdempotencyStore(session).begin(tenant, key, fp)).is_new

    # A concurrent request with the same key finds an in-progress record.
    async with sessionmaker() as session:
        with pytest.raises(ConflictError):
            await SqlAlchemyIdempotencyStore(session).begin(tenant, key, fp)

    async with sessionmaker() as session:
        await SqlAlchemyIdempotencyStore(session).complete(tenant, key, 200, '{"ok":true}')

    # A repeat now replays the stored response.
    async with sessionmaker() as session:
        outcome = await SqlAlchemyIdempotencyStore(session).begin(tenant, key, fp)
    assert not outcome.is_new
    assert outcome.replay_code == 200
    assert outcome.replay_body == '{"ok":true}'

    # Reusing the key with a different payload is rejected.
    async with sessionmaker() as session:
        with pytest.raises(IdempotencyMismatchError):
            await SqlAlchemyIdempotencyStore(session).begin(tenant, key, "other-fp")


async def test_discard_allows_retry(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant, key, fp = "t2", "k2", "fp-1"

    async with sessionmaker() as session:
        assert (await SqlAlchemyIdempotencyStore(session).begin(tenant, key, fp)).is_new

    async with sessionmaker() as session:
        await SqlAlchemyIdempotencyStore(session).discard(tenant, key)

    # After a discard the key is free to claim again.
    async with sessionmaker() as session:
        assert (await SqlAlchemyIdempotencyStore(session).begin(tenant, key, fp)).is_new
