import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal, Protocol

import anthropic
from anthropic.types import MessageParam, OutputConfigParam
from pydantic import BaseModel

from app.ai.errors import LLMTimeout, LLMUnavailable
from app.ai.schemas import Turn
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Grounded question answering needs little reasoning. Low effort keeps cost and latency down, and
# it is the only lever there is: the model rejects temperature, top_p and top_k (ADR-038).
EFFORT: Literal["low"] = "low"


@dataclass(frozen=True)
class LLMResponse:
    """One reply from the model, before anything has been checked."""

    text: str
    input_tokens: int | None
    output_tokens: int | None
    # Why the model stopped: "end_turn", "max_tokens", "refusal" and so on.
    stop_reason: str | None
    latency_ms: int


class LLMClient(Protocol):
    """The one way the app talks to a language model. Tests replace it with a fake."""

    @property
    def model(self) -> str: ...

    async def complete(
        self,
        *,
        system: str,
        messages: list[Turn],
        output_model: type[BaseModel],
        max_tokens: int,
    ) -> LLMResponse: ...


def _to_sdk_messages(messages: list[Turn]) -> list[MessageParam]:
    return [
        {"role": "assistant", "content": turn.content}
        if turn.role == "assistant"
        else {"role": "user", "content": turn.content}
        for turn in messages
    ]


class AnthropicClient:
    """Claude through the official SDK, asked for a reply that matches a JSON schema."""

    def __init__(self) -> None:
        self._client: anthropic.AsyncAnthropic | None = None

    @property
    def model(self) -> str:
        return get_settings().anthropic_model

    def _sdk_client(self) -> anthropic.AsyncAnthropic:
        settings = get_settings()
        key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else ""
        if not key:
            # An empty value in .env counts as missing. The key itself is never logged.
            logger.error("anthropic api key is not configured")
            raise LLMUnavailable
        if self._client is None:
            # The SDK retries 429, 5xx, connection errors and timeouts twice with backoff
            # (docs/ai-engineering.md), and each try has the explicit timeout below.
            self._client = anthropic.AsyncAnthropic(
                api_key=key, timeout=settings.llm_timeout_seconds, max_retries=2
            )
        return self._client

    async def complete(
        self,
        *,
        system: str,
        messages: list[Turn],
        output_model: type[BaseModel],
        max_tokens: int,
    ) -> LLMResponse:
        client = self._sdk_client()
        output_config: OutputConfigParam = {
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": anthropic.transform_schema(output_model)},
        }
        started = time.perf_counter()
        try:
            response = await client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=_to_sdk_messages(messages),
                output_config=output_config,
            )
        except anthropic.APITimeoutError as error:
            raise LLMTimeout from error
        except anthropic.APIStatusError as error:
            # Only the status is logged: the body of an error can echo the request.
            logger.warning("llm call failed status=%s", error.status_code)
            raise LLMUnavailable from error
        except anthropic.APIConnectionError as error:
            logger.warning("llm call failed error_type=%s", type(error).__name__)
            raise LLMUnavailable from error
        latency_ms = int((time.perf_counter() - started) * 1000)

        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMResponse(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
            latency_ms=latency_ms,
        )


@lru_cache
def get_llm_client() -> LLMClient:
    """FastAPI dependency. One client per process; tests override it with a fake."""
    return AnthropicClient()


def schema_of(model: type[BaseModel]) -> dict[str, Any]:
    """The JSON schema the API is asked to enforce, for tests and documentation."""
    return anthropic.transform_schema(model)
