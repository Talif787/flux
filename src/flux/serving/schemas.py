from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from flux.serving.domain import (
    ChatMessage,
    ChatRole,
    CompletionResult,
    SamplingParams,
)


class ChatMessageSchema(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = Field(min_length=1)
    messages: list[ChatMessageSchema] = Field(min_length=1)
    temperature: float = Field(default=1.0, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, gt=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1)
    stream: bool = False
    stop: str | list[str] | None = None
    n: int = Field(default=1, ge=1, le=1)

    def to_messages(self) -> tuple[ChatMessage, ...]:
        return tuple(ChatMessage(role=ChatRole(m.role), content=m.content) for m in self.messages)

    def to_sampling(self) -> SamplingParams:
        if self.stop is None:
            stop: tuple[str, ...] = ()
        elif isinstance(self.stop, list):
            stop = tuple(self.stop)
        else:
            stop = (self.stop,)
        return SamplingParams(
            temperature=self.temperature,
            top_p=self.top_p,
            max_tokens=self.max_tokens,
            stop=stop,
        )


class ResponseMessage(BaseModel):
    role: str
    content: str


class Choice(BaseModel):
    index: int
    message: ResponseMessage
    finish_reason: str


class UsageSchema(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: UsageSchema
    system_fingerprint: str | None = None

    @classmethod
    def from_result(
        cls, *, id: str, created: int, model: str, result: CompletionResult
    ) -> ChatCompletionResponse:
        return cls(
            id=id,
            created=created,
            model=model,
            choices=[
                Choice(
                    index=0,
                    message=ResponseMessage(role="assistant", content=result.content),
                    finish_reason=result.finish_reason.value,
                )
            ],
            usage=UsageSchema(
                prompt_tokens=result.usage.prompt_tokens,
                completion_tokens=result.usage.completion_tokens,
                total_tokens=result.usage.total_tokens,
            ),
            system_fingerprint="fp_flux_stub",
        )
