from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flux.errors import ConflictError
from flux.models.domain import ContextLength, Model, ModelVersion, Precision
from flux.models.persistence import SqlAlchemyModelRepository
from flux.pagination import PageParams


async def _repo(session: AsyncSession) -> SqlAlchemyModelRepository:
    return SqlAlchemyModelRepository(session)


async def test_add_and_get_model(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    model, _ = Model.register(tenant_id="t1", name="m1", family="llama")
    async with sessionmaker() as session:
        repo = await _repo(session)
        await repo.add_model(model)
    async with sessionmaker() as session:
        repo = await _repo(session)
        fetched = await repo.get_model("t1", model.id)
    assert fetched is not None
    assert fetched.name == "m1"


async def test_get_model_is_tenant_scoped(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    model, _ = Model.register(tenant_id="t1", name="m1", family="llama")
    async with sessionmaker() as session:
        await (await _repo(session)).add_model(model)
    async with sessionmaker() as session:
        assert await (await _repo(session)).get_model("other", model.id) is None


async def test_duplicate_name_raises_conflict(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    m1, _ = Model.register(tenant_id="t1", name="dup", family="llama")
    m2, _ = Model.register(tenant_id="t1", name="dup", family="llama")
    async with sessionmaker() as session:
        await (await _repo(session)).add_model(m1)
    with pytest.raises(ConflictError):
        async with sessionmaker() as session:
            await (await _repo(session)).add_model(m2)


async def test_list_models_paginates_and_filters(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        repo = await _repo(session)
        for i in range(3):
            model, _ = Model.register(tenant_id="t1", name=f"m{i}", family="llama")
            await repo.add_model(model)
        other, _ = Model.register(tenant_id="t1", name="mistral-a", family="mistral")
        await repo.add_model(other)
    async with sessionmaker() as session:
        page = await (await _repo(session)).list_models(
            "t1", family="llama", page=PageParams(limit=2, offset=0)
        )
    assert page.total == 3
    assert len(page.items) == 2


async def test_add_and_list_versions(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    model, _ = Model.register(tenant_id="t1", name="m1", family="llama")
    version, _ = ModelVersion.register(
        model_id=model.id,
        tenant_id="t1",
        version="v1",
        precision=Precision.BF16,
        context_length=ContextLength(4096),
    )
    async with sessionmaker() as session:
        repo = await _repo(session)
        await repo.add_model(model)
        await repo.add_version(version)
    async with sessionmaker() as session:
        page = await (await _repo(session)).list_versions("t1", model.id, page=PageParams())
    assert page.total == 1
    assert page.items[0].version == "v1"
