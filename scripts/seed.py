from __future__ import annotations

import asyncio
import secrets

from flux.auth.dependencies import hash_api_key
from flux.auth.persistence import ApiKeyRow, TenantRow
from flux.config import get_settings
from flux.db import create_engine, create_sessionmaker
from flux.ids import new_id


async def seed() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    raw_key = "flux_" + secrets.token_urlsafe(32)
    tenant = TenantRow(id=new_id(), name="default", status="active")
    async with sessionmaker() as session:
        session.add(tenant)
        session.add(
            ApiKeyRow(
                id=new_id(),
                tenant_id=tenant.id,
                key_hash=hash_api_key(raw_key, settings.api_key_pepper),
                roles="model.read,model.write",
                status="active",
            )
        )
        await session.commit()
    await engine.dispose()
    print(f"Seeded tenant 'default' ({tenant.id})")
    print(f"API key (shown once, store securely): {raw_key}")


if __name__ == "__main__":
    asyncio.run(seed())
