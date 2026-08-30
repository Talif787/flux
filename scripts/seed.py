from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from flux.auth.domain import Role
from flux.auth.hashing import generate_api_key, hash_api_key, key_prefix
from flux.auth.persistence import ApiKeyRow, TenantRow
from flux.config import get_settings
from flux.db import create_engine, create_sessionmaker
from flux.ids import new_id


async def seed() -> None:
    """Create a bootstrap tenant and a platform-admin API key.

    The platform-admin key is a superuser: use it to create tenants and issue
    scoped keys via the API. The plaintext is printed once and never stored.
    """
    settings = get_settings()
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    raw_key = generate_api_key()
    now = datetime.now(UTC)
    tenant = TenantRow(id=new_id(), name="default", status="active", created_at=now)
    async with sessionmaker() as session:
        session.add(tenant)
        session.add(
            ApiKeyRow(
                id=new_id(),
                tenant_id=tenant.id,
                key_hash=hash_api_key(raw_key, settings.api_key_pepper),
                name="bootstrap-admin",
                prefix=key_prefix(raw_key),
                roles=Role.PLATFORM_ADMIN.value,
                status="active",
                created_at=now,
            )
        )
        await session.commit()
    await engine.dispose()
    print(f"Seeded tenant 'default' ({tenant.id})")
    print(f"Platform-admin API key (shown once, store securely): {raw_key}")


if __name__ == "__main__":
    asyncio.run(seed())
