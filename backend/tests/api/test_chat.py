import logging
import re
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.errors import LLMUnavailable
from app.ai.prompts import CHAT_PROMPT_VERSION, load_prompt
from app.ai.schemas import ChatAnswerOut
from app.core.config import get_settings
from app.modules.chat.grounding import NOT_FOUND_ANSWER
from tests.api.helpers import (
    DOCUMENTS_URL,
    Account,
    auth_headers,
    embedded_text_of_chunk,
    upload,
    without_request_id,
)
from tests.fakes.llm import FakeLLM, RecordedCall
from tests.sop_fixtures import DATASETS, SOP_TEXT

CHAT_URL = DOCUMENTS_URL + "/{document_id}/chat"
THREADS_URL = "/api/v1/threads"
MARKER = "ZEBRA-CLAUSE-7731-confidential-refund-rule"
PROBLEM_FIELDS = {"type", "title", "status", "code", "detail", "request_id"}


async def make_document(
    client: AsyncClient,
    headers: dict[str, str],
    data: bytes = SOP_TEXT.encode(),
    name: str = "sop.md",
) -> str:
    response = await upload(client, headers, data, name)
    return str(response.json()["document"]["id"])


@pytest.fixture
async def document_id(api_client: AsyncClient, headers: dict[str, str]) -> str:
    return await make_document(api_client, headers)


@pytest.fixture
async def question(migrated_engine: AsyncEngine, document_id: str) -> str:
    """A question that makes chunk 3 (sections 3.1-3.5) the first source in the prompt."""
    return await embedded_text_of_chunk(migrated_engine, uuid.UUID(document_id), 3)


async def chat(
    client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    question: str,
    thread_id: str | None = None,
) -> Any:
    body: dict[str, Any] = {"question": question}
    if thread_id is not None:
        body["thread_id"] = thread_id
    return await client.post(CHAT_URL.format(document_id=document_id), headers=headers, json=body)


def source_labels(call: RecordedCall) -> dict[int, str | None]:
    """Which section label each numbered source had in the prompt the model was sent."""
    found = re.findall(r'<source n="(\d+)"(?: section="([^"]*)")?', call.user_text)
    return {int(number): label or None for number, label in found}


async def table_rows(engine: AsyncEngine, sql: str) -> list[Any]:
    async with engine.connect() as connection:
        return list((await connection.execute(text(sql))).all())


async def test_a_grounded_answer_comes_back_with_verified_citations(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    question: str,
    fake_llm: FakeLLM,
    migrated_engine: AsyncEngine,
) -> None:
    fake_llm.reply("L1 agents may approve refunds up to INR 5,000 per request.", [1])

    response = await chat(api_client, headers, document_id, question)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"thread_id", "message"}
    message = body["message"]
    assert message["role"] == "assistant"
    assert message["content"] == "L1 agents may approve refunds up to INR 5,000 per request."
    assert message["grounded"] is True
    (citation,) = message["citations"]
    stored = await table_rows(
        migrated_engine,
        "SELECT id, content FROM document_chunks WHERE section_label = '3.1-3.5'",
    )
    assert citation["chunk_id"] == str(stored[0].id)
    assert citation["section_label"] == "3.1-3.5"
    assert citation["quote"].startswith("3.1 L1 agents may approve refunds up to INR 5,000")
    assert citation["quote"] in stored[0].content


async def test_the_prompt_the_model_receives_is_the_fixed_one_with_the_sources_as_data(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    question: str,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply("Answer.", [1])

    await chat(api_client, headers, document_id, question)

    (call,) = fake_llm.calls
    assert call.system == load_prompt(CHAT_PROMPT_VERSION)
    assert call.output_model is ChatAnswerOut
    assert call.max_tokens == get_settings().chat_max_tokens
    assert source_labels(call)[1] == "3.1-3.5"
    assert len(source_labels(call)) == get_settings().retrieval_top_k
    assert call.user_text.index("<sources>") < call.user_text.index("<question>")


async def test_the_question_never_enters_the_system_prompt(
    api_client: AsyncClient, headers: dict[str, str], document_id: str, fake_llm: FakeLLM
) -> None:
    await chat(api_client, headers, document_id, f"What does {MARKER} say?")

    (call,) = fake_llm.calls
    assert MARKER not in call.system
    assert MARKER in call.user_text


async def test_citations_to_sources_that_do_not_exist_are_dropped(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    question: str,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply("Answer.", [1, 99, 0, -3, 1])

    message = (await chat(api_client, headers, document_id, question)).json()["message"]

    assert message["grounded"] is True
    assert [c["section_label"] for c in message["citations"]] == ["3.1-3.5"]


async def test_two_contradicting_sources_are_both_cited(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    question: str,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply("Section 3.x says 5,000 and section 5.x says 2,500.", [1, 2])

    message = (await chat(api_client, headers, document_id, question)).json()["message"]

    assert len(message["citations"]) == 2
    assert message["citations"][0]["section_label"] == "3.1-3.5"


async def test_an_answer_that_claims_to_be_grounded_without_a_valid_citation_is_not_shown(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    question: str,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply("The limit is INR 9,999.", [42])

    message = (await chat(api_client, headers, document_id, question)).json()["message"]

    assert message["content"] == NOT_FOUND_ANSWER
    assert (message["grounded"], message["citations"]) == (False, [])


async def test_when_the_model_says_not_found_the_fixed_text_is_what_the_user_sees(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    question: str,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply("I could not find this, but probably about INR 9,999.", [1], grounded=False)

    message = (await chat(api_client, headers, document_id, question)).json()["message"]

    assert message["content"] == NOT_FOUND_ANSWER
    assert (message["grounded"], message["citations"]) == (False, [])


async def test_with_no_sources_left_the_model_is_not_called_at_all(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    fake_llm: FakeLLM,
    migrated_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "retrieval_min_score", 0.999)

    response = await chat(api_client, headers, document_id, "Something unrelated entirely")

    assert response.status_code == 200
    assert response.json()["message"]["content"] == NOT_FOUND_ANSWER
    assert fake_llm.calls == []
    assert await table_rows(migrated_engine, "SELECT id FROM llm_calls") == []
    assert len(await table_rows(migrated_engine, "SELECT id FROM chat_messages")) == 2


async def test_the_question_and_answer_are_stored_in_order_and_can_be_read_back(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    question: str,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply("Answer.", [1])
    reply = (await chat(api_client, headers, document_id, f"  {question}  ")).json()

    response = await api_client.get(f"{THREADS_URL}/{reply['thread_id']}/messages", headers=headers)

    assert response.status_code == 200
    page = response.json()
    assert page["next_cursor"] is None
    assert [m["role"] for m in page["items"]] == ["user", "assistant"]
    assert page["items"][0]["content"] == question
    assert page["items"][0]["grounded"] is None
    assert page["items"][1] == reply["message"]


async def test_a_new_thread_is_titled_with_the_start_of_the_first_question(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    migrated_engine: AsyncEngine,
) -> None:
    await chat(api_client, headers, document_id, "x" * 200)

    (row,) = await table_rows(migrated_engine, "SELECT title, document_id FROM chat_threads")
    assert row.title == "x" * 80
    assert str(row.document_id) == document_id


async def test_a_follow_up_in_the_same_thread_sees_only_the_last_four_messages(
    api_client: AsyncClient, headers: dict[str, str], document_id: str, fake_llm: FakeLLM
) -> None:
    first = (await chat(api_client, headers, document_id, "question number one")).json()
    thread_id = first["thread_id"]
    assert "<history>" not in fake_llm.calls[0].user_text
    await chat(api_client, headers, document_id, "question number two", thread_id)
    await chat(api_client, headers, document_id, "question number three", thread_id)
    await chat(api_client, headers, document_id, "question number four", thread_id)

    second_call, fourth_call = fake_llm.calls[1], fake_llm.calls[3]

    assert second_call.user_text.count("<turn ") == 2
    assert "question number one" in second_call.user_text
    assert fourth_call.user_text.count("<turn ") == 4
    # Six messages exist by now; the last four are question two to the answer to question three.
    assert "question number one" not in fourth_call.user_text
    assert "question number two" in fourth_call.user_text
    assert "question number three" in fourth_call.user_text


async def test_messages_come_back_in_pages(
    api_client: AsyncClient, headers: dict[str, str], document_id: str
) -> None:
    thread_id = (await chat(api_client, headers, document_id, "one")).json()["thread_id"]
    await chat(api_client, headers, document_id, "two", thread_id)
    await chat(api_client, headers, document_id, "three", thread_id)
    url = f"{THREADS_URL}/{thread_id}/messages"

    seen: list[str] = []
    cursor: str | None = None
    sizes: list[int] = []
    while True:
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        page = (await api_client.get(url, headers=headers, params=params)).json()
        sizes.append(len(page["items"]))
        seen += [m["content"] for m in page["items"] if m["role"] == "user"]
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert sizes == [2, 2, 2]
    assert seen == ["one", "two", "three"]


async def test_a_bad_cursor_or_limit_is_a_validation_error(
    api_client: AsyncClient, headers: dict[str, str], document_id: str
) -> None:
    thread_id = (await chat(api_client, headers, document_id, "one")).json()["thread_id"]
    url = f"{THREADS_URL}/{thread_id}/messages"

    bad_cursor = await api_client.get(url, headers=headers, params={"cursor": "nonsense"})
    bad_limit = await api_client.get(url, headers=headers, params={"limit": 101})

    assert (bad_cursor.status_code, bad_cursor.json()["code"]) == (422, "invalid_cursor")
    assert bad_limit.status_code == 422


async def test_the_model_call_is_recorded_without_any_content(
    api_client: AsyncClient,
    headers: dict[str, str],
    migrated_engine: AsyncEngine,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply(f"The answer mentions {MARKER}.", [1], input_tokens=777, output_tokens=55)
    document_id = await make_document(
        api_client, headers, f"1.1 The rule is {MARKER}.".encode(), "secret.txt"
    )

    response = await chat(api_client, headers, document_id, f"What about {MARKER}?")

    (row,) = await table_rows(migrated_engine, "SELECT * FROM llm_calls")
    assert (row.purpose, row.model, row.prompt_version) == (
        "chat",
        "fake-model",
        CHAT_PROMPT_VERSION,
    )
    assert (row.input_tokens, row.output_tokens, row.status) == (777, 55, "ok")
    assert row.latency_ms == 42 and row.error_code is None
    assert row.request_id == response.headers["x-request-id"]
    owner = (await table_rows(migrated_engine, "SELECT id FROM users"))[0].id
    assert row.owner_id == owner
    dump = (await table_rows(migrated_engine, "SELECT row_to_json(c)::text AS j FROM llm_calls c"))[
        0
    ].j
    assert MARKER not in dump


async def test_an_invalid_reply_gets_one_repair_retry_and_both_attempts_are_recorded(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    question: str,
    fake_llm: FakeLLM,
    migrated_engine: AsyncEngine,
) -> None:
    fake_llm.reply_text("this is not json", input_tokens=100, output_tokens=5)
    fake_llm.reply("Fixed answer.", [1])

    response = await chat(api_client, headers, document_id, question)

    assert response.status_code == 200
    assert response.json()["message"]["content"] == "Fixed answer."
    first, retry = fake_llm.calls
    assert len(retry.messages) == len(first.messages) + 2
    assert retry.messages[-2].role == "assistant"
    assert "did not match the required format" in retry.messages[-1].content
    rows = await table_rows(
        migrated_engine, "SELECT status, input_tokens FROM llm_calls ORDER BY created_at"
    )
    assert [(r.status, r.input_tokens) for r in rows] == [("invalid_output", 100), ("ok", 120)]


async def test_two_invalid_replies_fail_with_503_and_store_no_conversation(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    question: str,
    fake_llm: FakeLLM,
    migrated_engine: AsyncEngine,
) -> None:
    fake_llm.reply_text("not json")
    fake_llm.reply_text('{"answer": "x"}')

    response = await chat(api_client, headers, document_id, question)

    assert response.status_code == 503
    assert set(response.json()) == PROBLEM_FIELDS
    assert response.json()["code"] == "llm_invalid_output"
    assert len(fake_llm.calls) == 2
    assert await table_rows(migrated_engine, "SELECT id FROM chat_threads") == []
    assert await table_rows(migrated_engine, "SELECT id FROM chat_messages") == []
    rows = await table_rows(migrated_engine, "SELECT status, error_code FROM llm_calls")
    assert [(r.status, r.error_code) for r in rows] == [
        ("invalid_output", "llm_invalid_output")
    ] * 2


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
async def test_a_refusal_or_a_cut_off_reply_is_not_retried(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    question: str,
    fake_llm: FakeLLM,
    migrated_engine: AsyncEngine,
    stop_reason: str,
) -> None:
    fake_llm.reply_text('{"answer": "cut', stop_reason=stop_reason)

    response = await chat(api_client, headers, document_id, question)

    assert (response.status_code, response.json()["code"]) == (503, "llm_invalid_output")
    assert len(fake_llm.calls) == 1
    assert len(await table_rows(migrated_engine, "SELECT id FROM llm_calls")) == 1


async def test_a_timeout_is_a_503_and_is_recorded(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    question: str,
    fake_llm: FakeLLM,
    migrated_engine: AsyncEngine,
) -> None:
    from app.ai.errors import LLMTimeout

    fake_llm.fail(LLMTimeout())

    response = await chat(api_client, headers, document_id, question)

    assert (response.status_code, response.json()["code"]) == (503, "llm_timeout")
    (row,) = await table_rows(
        migrated_engine, "SELECT status, error_code, input_tokens FROM llm_calls"
    )
    assert (row.status, row.error_code, row.input_tokens) == ("timeout", "llm_timeout", None)
    assert await table_rows(migrated_engine, "SELECT id FROM chat_threads") == []


async def test_an_unavailable_model_is_a_503_and_is_recorded(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    question: str,
    fake_llm: FakeLLM,
    migrated_engine: AsyncEngine,
) -> None:
    fake_llm.fail(LLMUnavailable())

    response = await chat(api_client, headers, document_id, question)

    assert (response.status_code, response.json()["code"]) == (503, "llm_unavailable")
    (row,) = await table_rows(migrated_engine, "SELECT status, error_code FROM llm_calls")
    assert (row.status, row.error_code) == ("error", "llm_unavailable")


async def test_a_failure_in_a_follow_up_leaves_the_existing_thread_unchanged(
    api_client: AsyncClient, headers: dict[str, str], document_id: str, fake_llm: FakeLLM
) -> None:
    thread_id = (await chat(api_client, headers, document_id, "first")).json()["thread_id"]
    fake_llm.fail(LLMUnavailable())

    failed = await chat(api_client, headers, document_id, "second", thread_id)
    messages = await api_client.get(f"{THREADS_URL}/{thread_id}/messages", headers=headers)

    assert failed.status_code == 503
    assert [m["content"] for m in messages.json()["items"] if m["role"] == "user"] == ["first"]


async def test_another_users_document_looks_missing_and_the_model_is_not_called(
    api_client: AsyncClient,
    headers: dict[str, str],
    other_account: Account,
    document_id: str,
    fake_llm: FakeLLM,
    migrated_engine: AsyncEngine,
) -> None:
    other_headers = await auth_headers(api_client, other_account)

    foreign = await chat(api_client, other_headers, document_id, "anything")
    missing = await chat(api_client, other_headers, str(uuid.uuid4()), "anything")

    assert foreign.status_code == 404
    assert without_request_id(foreign) == without_request_id(missing)
    assert fake_llm.calls == []
    assert await table_rows(migrated_engine, "SELECT id FROM llm_calls") == []


async def test_a_deleted_document_and_a_document_not_ready_cannot_be_asked(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    fake_llm: FakeLLM,
    migrated_engine: AsyncEngine,
) -> None:
    async with migrated_engine.begin() as connection:
        await connection.execute(text("UPDATE documents SET status = 'processing'"))
    not_ready = await chat(api_client, headers, document_id, "anything")
    async with migrated_engine.begin() as connection:
        await connection.execute(text("UPDATE documents SET status = 'ready'"))
    await api_client.delete(f"{DOCUMENTS_URL}/{document_id}", headers=headers)
    deleted = await chat(api_client, headers, document_id, "anything")

    assert (not_ready.status_code, not_ready.json()["code"]) == (409, "document_not_ready")
    assert (deleted.status_code, deleted.json()["code"]) == (404, "document_not_found")
    assert fake_llm.calls == []


async def test_threads_of_other_users_and_other_documents_look_missing(
    api_client: AsyncClient,
    headers: dict[str, str],
    other_account: Account,
    document_id: str,
    fake_llm: FakeLLM,
) -> None:
    thread_id = (await chat(api_client, headers, document_id, "mine")).json()["thread_id"]
    second_document = await make_document(api_client, headers, b"1.1 A second document here.")
    other_headers = await auth_headers(api_client, other_account)
    other_document = await make_document(api_client, other_headers, b"1.1 Their own document.")
    calls_before = len(fake_llm.calls)

    attempts = [
        await chat(api_client, other_headers, other_document, "x", thread_id),
        await chat(api_client, headers, second_document, "x", thread_id),
        await chat(api_client, headers, document_id, "x", str(uuid.uuid4())),
    ]
    read_foreign = await api_client.get(
        f"{THREADS_URL}/{thread_id}/messages", headers=other_headers
    )
    read_missing = await api_client.get(
        f"{THREADS_URL}/{uuid.uuid4()}/messages", headers=other_headers
    )

    assert [a.status_code for a in attempts] == [404, 404, 404]
    assert {a.json()["code"] for a in attempts} == {"thread_not_found"}
    assert without_request_id(read_foreign) == without_request_id(read_missing)
    assert read_foreign.status_code == 404
    assert len(fake_llm.calls) == calls_before


async def test_chat_needs_a_valid_token(api_client: AsyncClient, document_id: str) -> None:
    chat_response = await api_client.post(
        CHAT_URL.format(document_id=document_id), json={"question": "x"}
    )
    read = await api_client.get(f"{THREADS_URL}/{uuid.uuid4()}/messages")

    assert (chat_response.status_code, read.status_code) == (401, 401)


@pytest.mark.parametrize(
    "body",
    [
        {"question": ""},
        {"question": "   "},
        {"question": "x" * 1001},
        {},
        {"question": "ok", "extra": 1},
        {"question": "ok", "thread_id": "not-a-uuid"},
    ],
)
async def test_bad_requests_are_validation_errors_and_cost_nothing(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    fake_llm: FakeLLM,
    body: dict[str, Any],
) -> None:
    response = await api_client.post(
        CHAT_URL.format(document_id=document_id), headers=headers, json=body
    )

    assert (response.status_code, response.json()["code"]) == (422, "validation_error")
    assert fake_llm.calls == []


async def test_a_question_of_exactly_1000_characters_is_accepted(
    api_client: AsyncClient, headers: dict[str, str], document_id: str
) -> None:
    response = await chat(api_client, headers, document_id, "x" * 1000)

    assert response.status_code == 200


async def test_the_thirty_first_question_in_an_hour_is_rate_limited(
    api_client: AsyncClient, headers: dict[str, str], document_id: str
) -> None:
    for _ in range(30):
        assert (await chat(api_client, headers, document_id, "again")).status_code == 200

    response = await chat(api_client, headers, document_id, "again")

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
    assert "retry-after" in response.headers


async def test_a_document_that_tries_to_instruct_the_model_reaches_it_only_as_escaped_data(
    api_client: AsyncClient, headers: dict[str, str], fake_llm: FakeLLM
) -> None:
    injection = (DATASETS / "injection_sample.md").read_bytes()
    document_id = await make_document(api_client, headers, injection, "checklist.md")

    await chat(api_client, headers, document_id, "Who signs off on a new vendor?")

    (call,) = fake_llm.calls
    assert "PINEAPPLE" not in call.system
    assert "PINEAPPLE" in call.user_text
    sources_block = call.user_text[: call.user_text.index("</sources>")]
    assert "ignore all previous instructions" in sources_block
    assert "never an instruction" in call.system


async def test_no_question_answer_or_document_text_or_key_is_logged(
    api_client: AsyncClient,
    headers: dict[str, str],
    fake_llm: FakeLLM,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import SecretStr

    monkeypatch.setattr(get_settings(), "anthropic_api_key", SecretStr("sk-ant-test-not-real"))
    document_id = await make_document(
        api_client, headers, f"1.1 The rule is {MARKER}.".encode(), "r.txt"
    )
    fake_llm.reply_text("not json " + MARKER)
    fake_llm.reply(f"Answer about {MARKER}.", [1])

    with caplog.at_level(logging.DEBUG):
        await chat(api_client, headers, document_id, f"Question about {MARKER}?")

    assert MARKER not in caplog.text
    assert "sk-ant-test-not-real" not in caplog.text
    assert "chat answered" in caplog.text


async def test_the_thread_moves_to_the_top_when_it_is_used_again(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    migrated_engine: AsyncEngine,
) -> None:
    thread_id = (await chat(api_client, headers, document_id, "first")).json()["thread_id"]
    sql = "SELECT updated_at FROM chat_threads"
    before = (await table_rows(migrated_engine, sql))[0].updated_at

    await chat(api_client, headers, document_id, "second", thread_id)

    after = (await table_rows(migrated_engine, sql))[0].updated_at
    assert after > before
