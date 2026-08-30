from __future__ import annotations

import pytest

from flux.auth.domain import ApiKeyStatus, TenantStatus
from flux.errors import DomainError
from flux.tenancy.domain import ApiKey, Tenant


def test_create_tenant_trims_and_activates() -> None:
    tenant, event = Tenant.create("  Acme  ")
    assert tenant.name == "Acme"
    assert tenant.status is TenantStatus.ACTIVE
    assert event.tenant_id == tenant.id


@pytest.mark.parametrize("name", ["", "   "])
def test_create_tenant_rejects_empty(name: str) -> None:
    with pytest.raises(DomainError):
        Tenant.create(name)


def test_suspend_and_reactivate_transitions() -> None:
    tenant, _ = Tenant.create("acme")
    tenant.suspend()
    assert tenant.status is TenantStatus.SUSPENDED
    tenant.reactivate()
    assert tenant.status is TenantStatus.ACTIVE


def test_double_suspend_is_rejected() -> None:
    tenant, _ = Tenant.create("acme")
    tenant.suspend()
    with pytest.raises(DomainError):
        tenant.suspend()


def test_issue_api_key_sets_prefix_and_roles() -> None:
    key, event = ApiKey.issue(tenant_id="t1", name="ci", prefix="flux_abcdef", roles=["model.read"])
    assert key.prefix == "flux_abcdef"
    assert key.roles == frozenset({"model.read"})
    assert key.status is ApiKeyStatus.ACTIVE
    assert event.api_key_id == key.id


def test_issue_api_key_rejects_unknown_role() -> None:
    with pytest.raises(DomainError):
        ApiKey.issue(tenant_id="t1", name="ci", prefix="p", roles=["not-a-role"])


def test_revoke_is_idempotent_guarded() -> None:
    key, _ = ApiKey.issue(tenant_id="t1", name="ci", prefix="p", roles=["model.read"])
    key.revoke()
    assert key.status is ApiKeyStatus.REVOKED
    assert key.revoked_at is not None
    with pytest.raises(DomainError):
        key.revoke()
