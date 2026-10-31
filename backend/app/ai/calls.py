import logging
import uuid
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient, LLMResponse
from app.ai.errors import LLMError, LLMInvalidOutput, LLMTimeout
from app.ai.models import LlmCall
from app.ai.schemas import Turn
from app.core.request_id import request_id_var

logger = logging.getLogger(__name__)

# One call, plus one repair retry when the reply does not match the schema (AGENTS.md).
MAX_ATTEMPTS = 2


@dataclass(frozen=True)
class StructuredResult[T: BaseModel]:
    parsed: T
    input_tokens: int | None
    output_tokens: int | None


def _record(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    purpose: str,
    model: str,
    prompt_version: str,
    status: str,
    error_code: str | None = None,
    response: LLMResponse | None = None,
    latency_ms: int | None = None,
) -> None:
    """Add the llm_calls row. It holds sizes and outcomes only, never a prompt or an answer."""
    request_id = request_id_var.get()
    session.add(
        LlmCall(
            owner_id=owner_id,
            purpose=purpose,
            model=model,
            prompt_version=prompt_version,
            input_tokens=response.input_tokens if response else None,
            output_tokens=response.output_tokens if response else None,
            latency_ms=response.latency_ms if response else latency_ms,
            status=status,
            error_code=error_code,
            # "-" is the logging placeholder for "no request", not a real id.
            request_id=None if request_id == "-" else request_id,
        )
    )


def _validation_summary(error: ValidationError) -> str:
    # Field paths and messages only. error.errors() also carries the rejected input, which is
    # text the model produced and must not be copied around.
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc']) or 'reply'}: {item['msg']}"
        for item in error.errors(include_input=False)
    )


async def call_structured[T: BaseModel](
    session: AsyncSession,
    client: LLMClient,
    *,
    owner_id: uuid.UUID,
    purpose: str,
    prompt_version: str,
    system: str,
    messages: list[Turn],
    output_model: type[T],
    max_tokens: int,
) -> StructuredResult[T]:
    """Ask the model for an object of `output_model`, check it, and record every attempt.

    On success the llm_calls row is only added to the session; the caller commits it together
    with its own work. On failure the rows are committed here, before the error is raised,
    because raising rolls the caller's transaction back and the cost of a failed call must not
    vanish. The caller must have no other pending changes when it calls this.
    """
    turns = list(messages)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await client.complete(
                system=system, messages=turns, output_model=output_model, max_tokens=max_tokens
            )
        except LLMError as error:
            _record(
                session,
                owner_id=owner_id,
                purpose=purpose,
                model=client.model,
                prompt_version=prompt_version,
                status="timeout" if isinstance(error, LLMTimeout) else "error",
                error_code=error.code,
            )
            await session.commit()
            raise

        problem: str | None = None
        parsed: T | None = None
        if response.stop_reason in ("refusal", "max_tokens"):
            # A repeat would not help: the model declined, or the reply is cut off.
            problem = f"stopped: {response.stop_reason}"
        else:
            try:
                parsed = output_model.model_validate_json(response.text)
            except ValidationError as error:
                problem = _validation_summary(error)

        if parsed is not None:
            _record(
                session,
                owner_id=owner_id,
                purpose=purpose,
                model=client.model,
                prompt_version=prompt_version,
                status="ok",
                response=response,
            )
            return StructuredResult(parsed, response.input_tokens, response.output_tokens)

        _record(
            session,
            owner_id=owner_id,
            purpose=purpose,
            model=client.model,
            prompt_version=prompt_version,
            status="invalid_output",
            error_code=LLMInvalidOutput.code,
            response=response,
        )
        logger.warning("llm output invalid purpose=%s attempt=%d", purpose, attempt)
        if response.stop_reason in ("refusal", "max_tokens") or attempt == MAX_ATTEMPTS:
            await session.commit()
            raise LLMInvalidOutput

        turns = [
            *messages,
            Turn(role="assistant", content=response.text or "(empty)"),
            Turn(
                role="user",
                content=(
                    f"Your reply did not match the required format ({problem}). "
                    "Reply again with only the JSON object, with exactly the required keys."
                ),
            ),
        ]
    raise LLMInvalidOutput  # unreachable: the loop always returns or raises
