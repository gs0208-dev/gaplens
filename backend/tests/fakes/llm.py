import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.ai.client import LLMResponse
from app.ai.schemas import Turn

NOT_GROUNDED = {"answer": "not found in the document", "cited_sources": [], "grounded": False}


@dataclass(frozen=True)
class RecordedCall:
    """What the app sent to the model: the system prompt, the turns and the limits."""

    system: str
    messages: list[Turn]
    output_model: type[BaseModel]
    max_tokens: int

    @property
    def user_text(self) -> str:
        return "\n".join(turn.content for turn in self.messages if turn.role == "user")


class FakeLLM:
    """Stands in for the model, which would need a network and a key. Replies are scripted, in
    order; with nothing scripted it answers "not grounded". Every call is recorded."""

    model = "fake-model"

    def __init__(self) -> None:
        self.calls: list[RecordedCall] = []
        self._script: list[LLMResponse | Exception] = []

    def reply(
        self,
        answer: str,
        cited_sources: list[int],
        *,
        grounded: bool = True,
        input_tokens: int = 120,
        output_tokens: int = 30,
    ) -> None:
        payload: dict[str, Any] = {
            "answer": answer,
            "cited_sources": cited_sources,
            "grounded": grounded,
        }
        self.reply_text(json.dumps(payload), input_tokens=input_tokens, output_tokens=output_tokens)

    def reply_text(
        self,
        text: str,
        *,
        stop_reason: str = "end_turn",
        input_tokens: int = 120,
        output_tokens: int = 30,
    ) -> None:
        self._script.append(
            LLMResponse(
                text=text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                stop_reason=stop_reason,
                latency_ms=42,
            )
        )

    def fail(self, error: Exception) -> None:
        self._script.append(error)

    async def complete(
        self,
        *,
        system: str,
        messages: list[Turn],
        output_model: type[BaseModel],
        max_tokens: int,
    ) -> LLMResponse:
        self.calls.append(RecordedCall(system, list(messages), output_model, max_tokens))
        if not self._script:
            self.reply(**NOT_GROUNDED)
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
