from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from flux.ids import new_id
from flux.worker.backend import InferenceBackend
from flux.worker.config import WorkerSettings, get_worker_settings
from flux.worker.domain import Chunk, InferenceJob
from flux.worker.schemas import ChatCompletionIn, ChatCompletionOut

router = APIRouter(tags=["worker"])

_JSON = "application/json"


def get_backend(request: Request) -> InferenceBackend:
    backend: InferenceBackend = request.app.state.backend
    return backend


Backend = Annotated[InferenceBackend, Depends(get_backend)]
SettingsDep = Annotated[WorkerSettings, Depends(get_worker_settings)]


def _ensure_served(model: str, settings: WorkerSettings) -> None:
    served = settings.served_model_set
    if served and model not in served:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"model not served by this worker: {model}",
        )


def _build_job(payload: ChatCompletionIn, settings: WorkerSettings) -> InferenceJob:
    sampling = payload.sampling()
    if sampling.max_tokens is not None and sampling.max_tokens > settings.max_tokens_cap:
        sampling = replace(sampling, max_tokens=settings.max_tokens_cap)
    return InferenceJob(model=payload.model, turns=payload.turns(), sampling=sampling)


def _chunk_payload(completion_id: str, created: int, model: str, chunk: Chunk) -> dict[str, object]:
    delta: dict[str, str] = {}
    if chunk.role is not None:
        delta["role"] = chunk.role.value
    if chunk.delta:
        delta["content"] = chunk.delta
    finish = chunk.finish_reason.value if chunk.finish_reason is not None else None
    return {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


async def _sse(backend: InferenceBackend, job: InferenceJob, model: str) -> AsyncIterator[str]:
    completion_id = f"chatcmpl-{new_id()}"
    created = int(time.time())
    async for chunk in backend.stream(job):
        yield f"data: {json.dumps(_chunk_payload(completion_id, created, model, chunk))}\n\n"
    yield "data: [DONE]\n\n"


@router.get("/livez")
async def livez() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(settings: SettingsDep) -> dict[str, object]:
    return {
        "status": "ready",
        "backend": settings.backend,
        "models": sorted(settings.served_model_set),
    }


@router.get("/v1/models")
async def list_models(settings: SettingsDep) -> dict[str, object]:
    data = [
        {"id": name, "object": "model", "owned_by": "flux"}
        for name in sorted(settings.served_model_set)
    ]
    return {"object": "list", "data": data}


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    payload: ChatCompletionIn, backend: Backend, settings: SettingsDep
) -> Response:
    _ensure_served(payload.model, settings)
    job = _build_job(payload, settings)
    if payload.stream:
        return StreamingResponse(_sse(backend, job, payload.model), media_type="text/event-stream")
    result = await backend.generate(job)
    out = ChatCompletionOut.build(id=f"chatcmpl-{new_id()}", model=payload.model, result=result)
    return Response(content=out.model_dump_json(), media_type=_JSON)
