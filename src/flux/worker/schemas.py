from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from flux.worker.domain import ChatRole, ChatTurn, Completion, Sampling


class ChatMessageIn(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatCompletionIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = Field(min_length=1)
    messages: list[ChatMessageIn] = Field(min_length=1)
    temperature: float = Field(default=1.0, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, gt=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1)
    stream: bool = False
    stop: str | list[str] | None = None

    def turns(self) -> tuple[ChatTurn, ...]:
        return tuple(ChatTurn(role=ChatRole(m.role), content=m.content) for m in self.messages)

    def sampling(self) -> Sampling:
        if self.stop is None:
            stop: tuple[str, ...] = ()
        elif isinstance(self.stop, list):
            stop = tuple(self.stop)
        else:
            stop = (self.stop,)
        return Sampling(
            temperature=self.temperature,
            top_p=self.top_p,
            max_tokens=self.max_tokens,
            stop=stop,
        )


class MessageOut(BaseModel):
    role: str
    content: str


class ChoiceOut(BaseModel):
    index: int
    message: MessageOut
    finish_reason: str


class UsageOut(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionOut(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChoiceOut]
    usage: UsageOut

    @classmethod
    def build(cls, *, id: str, model: str, result: Completion) -> ChatCompletionOut:
        return cls(
            id=id,
            created=int(time.time()),
            model=model,
            choices=[
                ChoiceOut(
                    index=0,
                    message=MessageOut(role="assistant", content=result.content),
                    finish_reason=result.finish_reason.value,
                )
            ],
            usage=UsageOut(
                prompt_tokens=result.usage.prompt_tokens,
                completion_tokens=result.usage.completion_tokens,
                total_tokens=result.usage.total_tokens,
            ),
        )
