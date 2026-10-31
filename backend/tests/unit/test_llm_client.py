from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from pydantic import SecretStr

from app.ai.client import AnthropicClient
from app.ai.errors import LLMTimeout, LLMUnavailable
from app.ai.schemas import ChatAnswerOut, Turn
from app.core.config import get_settings

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


class StubMessages:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.sent: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.sent = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def client_with(
    outcome: Any, monkeypatch: pytest.MonkeyPatch
) -> tuple[AnthropicClient, StubMessages]:
    # A made-up key: the stub never sends it anywhere, but the client checks that one is set.
    monkeypatch.setattr(get_settings(), "anthropic_api_key", SecretStr("not-a-real-key"))
    client = AnthropicClient()
    messages = StubMessages(outcome)
    client._client = SimpleNamespace(messages=messages)  # type: ignore[assignment]
    return client, messages


def reply() -> Any:
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", text="ignored"),
            SimpleNamespace(type="text", text='{"answer": "a"'),
            SimpleNamespace(type="text", text=', "cited_sources": [], "grounded": false}'),
        ],
        usage=SimpleNamespace(input_tokens=11, output_tokens=7),
        stop_reason="end_turn",
    )


async def ask(client: AnthropicClient) -> Any:
    return await client.complete(
        system="system text",
        messages=[Turn("user", "hello"), Turn("assistant", "hi"), Turn("user", "again")],
        output_model=ChatAnswerOut,
        max_tokens=500,
    )


async def test_the_request_has_no_sampling_parameters_and_asks_for_a_json_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, messages = client_with(reply(), monkeypatch)

    await ask(client)

    sent = messages.sent
    assert sent["model"] == get_settings().anthropic_model
    assert sent["max_tokens"] == 500
    assert sent["system"] == "system text"
    assert [m["role"] for m in sent["messages"]] == ["user", "assistant", "user"]
    assert not {"temperature", "top_p", "top_k", "tool_choice", "thinking"} & set(sent)
    assert sent["output_config"]["effort"] == "low"
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert sent["output_config"]["format"]["schema"]["additionalProperties"] is False


async def test_the_reply_text_tokens_and_stop_reason_are_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = client_with(reply(), monkeypatch)

    response = await ask(client)

    assert response.text == '{"answer": "a", "cited_sources": [], "grounded": false}'
    assert (response.input_tokens, response.output_tokens) == (11, 7)
    assert response.stop_reason == "end_turn"
    assert response.latency_ms >= 0


async def test_a_timeout_becomes_llm_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = client_with(anthropic.APITimeoutError(request=REQUEST), monkeypatch)

    with pytest.raises(LLMTimeout):
        await ask(client)


@pytest.mark.parametrize("status", [400, 401, 429, 500, 529])
async def test_http_errors_become_llm_unavailable_without_logging_the_body(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, status: int
) -> None:
    response = httpx2.Response(status, request=REQUEST)
    error = anthropic.APIStatusError("secret request echo", response=response, body=None)
    client, _ = client_with(error, monkeypatch)

    with pytest.raises(LLMUnavailable):
        await ask(client)
    assert "secret request echo" not in caplog.text


async def test_a_connection_failure_becomes_llm_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = client_with(anthropic.APIConnectionError(request=REQUEST), monkeypatch)

    with pytest.raises(LLMUnavailable):
        await ask(client)


@pytest.mark.parametrize("key", [None, ""])
async def test_a_missing_or_empty_key_is_llm_unavailable_and_nothing_is_sent(
    monkeypatch: pytest.MonkeyPatch, key: str | None
) -> None:
    monkeypatch.setattr(
        get_settings(), "anthropic_api_key", None if key is None else SecretStr(key)
    )

    with pytest.raises(LLMUnavailable):
        await ask(AnthropicClient())
