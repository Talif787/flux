from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse

from flux.auth.dependencies import require_roles
from flux.auth.domain import Principal, Role
from flux.config import Settings, get_settings
from flux.ids import new_id
from flux.serving.application import InferenceService, Prepared
from flux.serving.deps import get_idempotency_store, get_inference_service
from flux.serving.domain import (
    ChatMessage,
    CompletionChunk,
    IdempotencyStore,
    SamplingParams,
)
from flux.serving.idempotency import fingerprint
from flux.serving.schemas import ChatCompletionRequest, ChatCompletionResponse

router = APIRouter(prefix="/v1", tags=["serving"])

InferenceCaller = Annotated[Principal, Depends(require_roles(Role.INFERENCE))]
Svc = Annotated[InferenceService, Depends(get_inference_service)]
IdemStore = Annotated[IdempotencyStore, Depends(get_idempotency_store)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

_JSON = "application/json"


def _chunk_payload(
    completion_id: str, created: int, model: str, chunk: CompletionChunk
) -> dict[str, object]:
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


async def _sse(service: InferenceService, prepared: Prepared, model: str) -> AsyncIterator[str]:
    completion_id = f"chatcmpl-{new_id()}"
    created = int(time.time())
    async for chunk in service.stream(prepared):
        yield f"data: {json.dumps(_chunk_payload(completion_id, created, model, chunk))}\n\n"
    yield "data: [DONE]\n\n"


async def _produce(
    service: InferenceService,
    tenant_id: str,
    model: str,
    messages: tuple[ChatMessage, ...],
    sampling: SamplingParams,
) -> ChatCompletionResponse:
    prepared = await service.prepare(
        tenant_id=tenant_id, model=model, messages=messages, sampling=sampling
    )
    result = await service.complete(prepared)
    return ChatCompletionResponse.from_result(
        id=f"chatcmpl-{new_id()}",
        created=int(time.time()),
        model=model,
        result=result,
    )


@router.post("/chat/completions", response_model=None)
async def chat_completions(
    payload: ChatCompletionRequest,
    request: Request,
    principal: InferenceCaller,
    service: Svc,
    idem: IdemStore,
    settings: SettingsDep,
) -> Response:
    messages = payload.to_messages()
    sampling = payload.to_sampling()  # may raise DomainError -> 422
    tenant_id = principal.tenant_id

    if payload.stream:
        prepared = await service.prepare(
            tenant_id=tenant_id,
            model=payload.model,
            messages=messages,
            sampling=sampling,
        )
        return StreamingResponse(
            _sse(service, prepared, payload.model),
            media_type="text/event-stream",
        )

    idem_key = request.headers.get("Idempotency-Key")
    if settings.idempotency_enabled and idem_key:
        raw = await request.body()
        fp = fingerprint(tenant_id, "POST", request.url.path, raw)
        outcome = await idem.begin(tenant_id, idem_key, fp)
        if not outcome.is_new:
            return Response(
                content=outcome.replay_body or "",
                status_code=outcome.replay_code or 200,
                media_type=_JSON,
                headers={"Idempotent-Replay": "true"},
            )
        try:
            response = await _produce(service, tenant_id, payload.model, messages, sampling)
            text = response.model_dump_json()
            await idem.complete(tenant_id, idem_key, 200, text)
            return Response(content=text, media_type=_JSON)
        except BaseException:
            await idem.discard(tenant_id, idem_key)
            raise

    response = await _produce(service, tenant_id, payload.model, messages, sampling)
    return Response(content=response.model_dump_json(), media_type=_JSON)
