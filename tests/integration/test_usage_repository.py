from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flux.metering.persistence import (
    SqlAlchemyUsageRecorder,
    SqlAlchemyUsageRepository,
)


async def _record(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    tenant_id: str,
    model_name: str,
    prompt: int,
    completion: int,
) -> None:
    async with sessionmaker() as session:
        await SqlAlchemyUsageRecorder(session).record(
            tenant_id=tenant_id,
            model_id=f"m-{model_name}",
            model_name=model_name,
            prompt_tokens=prompt,
            completion_tokens=completion,
        )


async def test_aggregate_groups_by_model(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await _record(sessionmaker, tenant_id="t-1", model_name="gpt-stub", prompt=10, completion=5)
    await _record(sessionmaker, tenant_id="t-1", model_name="gpt-stub", prompt=20, completion=8)
    await _record(sessionmaker, tenant_id="t-1", model_name="llama", prompt=4, completion=2)

    async with sessionmaker() as session:
        aggregates = await SqlAlchemyUsageRepository(session).aggregate(
            tenant_id="t-1", model_name=None, start=None, end=None
        )

    by_model = {a.model_name: a for a in aggregates}
    assert by_model["gpt-stub"].prompt_tokens == 30
    assert by_model["gpt-stub"].completion_tokens == 13
    assert by_model["gpt-stub"].request_count == 2
    assert by_model["llama"].request_count == 1


async def test_aggregate_scopes_by_tenant(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await _record(sessionmaker, tenant_id="t-1", model_name="gpt-stub", prompt=10, completion=5)
    await _record(sessionmaker, tenant_id="t-2", model_name="gpt-stub", prompt=99, completion=99)

    async with sessionmaker() as session:
        aggregates = await SqlAlchemyUsageRepository(session).aggregate(
            tenant_id="t-1", model_name=None, start=None, end=None
        )

    assert len(aggregates) == 1
    assert aggregates[0].prompt_tokens == 10


async def test_aggregate_filters_by_model(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await _record(sessionmaker, tenant_id="t-1", model_name="gpt-stub", prompt=10, completion=5)
    await _record(sessionmaker, tenant_id="t-1", model_name="llama", prompt=7, completion=3)

    async with sessionmaker() as session:
        aggregates = await SqlAlchemyUsageRepository(session).aggregate(
            tenant_id="t-1", model_name="llama", start=None, end=None
        )

    assert len(aggregates) == 1
    assert aggregates[0].model_name == "llama"
    assert aggregates[0].prompt_tokens == 7


async def test_aggregate_empty_returns_no_lines(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        aggregates = await SqlAlchemyUsageRepository(session).aggregate(
            tenant_id="t-nobody", model_name=None, start=None, end=None
        )
    assert aggregates == []
