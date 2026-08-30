from __future__ import annotations

import pytest

from flux.errors import NoWorkerAvailableError
from flux.serving.domain import (
    ChatMessage,
    ChatRole,
    InferenceRequest,
    SamplingParams,
    WorkerEndpoint,
)
from flux.serving.routing import RegistryRouter, RoundRobinSelector


class FakeDirectory:
    def __init__(self, endpoints: list[WorkerEndpoint]) -> None:
        self._endpoints = endpoints

    async def candidates(self, model_name: str) -> list[WorkerEndpoint]:
        return list(self._endpoints)


def _request() -> InferenceRequest:
    return InferenceRequest(
        tenant_id="t-1",
        model_id="m-1",
        model_name="gpt-stub",
        messages=(ChatMessage(role=ChatRole.USER, content="hi"),),
        sampling=SamplingParams(),
    )


async def test_registry_router_round_robins_across_workers() -> None:
    endpoints = [
        WorkerEndpoint(worker_id="w-1", base_url="http://a"),
        WorkerEndpoint(worker_id="w-2", base_url="http://b"),
    ]
    router = RegistryRouter(FakeDirectory(endpoints), RoundRobinSelector())

    first = await router.route(_request())
    second = await router.route(_request())
    third = await router.route(_request())

    assert (first.worker_id, first.endpoint) == ("w-1", "http://a")
    assert (second.worker_id, second.endpoint) == ("w-2", "http://b")
    assert third.worker_id == "w-1"


async def test_registry_router_raises_when_no_candidates() -> None:
    router = RegistryRouter(FakeDirectory([]), RoundRobinSelector())
    with pytest.raises(NoWorkerAvailableError):
        await router.route(_request())


def test_round_robin_selector_handles_empty_list() -> None:
    assert RoundRobinSelector().pick([]) is None
