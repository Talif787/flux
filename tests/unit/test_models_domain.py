from __future__ import annotations

import pytest

from flux.errors import DomainError
from flux.models.domain import (
    ContextLength,
    Model,
    ModelRegistered,
    ModelVersion,
    ModelVersionRegistered,
    Precision,
    VersionStatus,
)


def test_register_model_produces_entity_and_event() -> None:
    model, event = Model.register(tenant_id="t1", name="  llama-3-8b ", family="llama")
    assert model.name == "llama-3-8b"
    assert model.tenant_id == "t1"
    assert isinstance(event, ModelRegistered)
    assert event.model_id == model.id
    assert event.name == "llama-3-8b"


@pytest.mark.parametrize("name", ["", "   "])
def test_register_model_rejects_empty_name(name: str) -> None:
    with pytest.raises(DomainError):
        Model.register(tenant_id="t1", name=name, family="llama")


def test_register_model_rejects_empty_family() -> None:
    with pytest.raises(DomainError):
        Model.register(tenant_id="t1", name="m", family="  ")


def test_register_version_defaults_to_registered_status() -> None:
    version, event = ModelVersion.register(
        model_id="m1",
        tenant_id="t1",
        version="v1",
        precision=Precision.FP16,
        context_length=ContextLength(8192),
    )
    assert version.status is VersionStatus.REGISTERED
    assert version.precision is Precision.FP16
    assert isinstance(event, ModelVersionRegistered)
    assert event.version == "v1"
