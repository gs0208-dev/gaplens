import json
import logging
import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.ai.errors import LLMInvalidOutput, LLMTimeout, LLMUnavailable
from app.core.config import get_settings
from app.modules.analysis import repository as analysis_repository
from app.modules.analysis import service as analysis_service
from app.modules.analysis.errors import (
    FAILURE_GENERIC,
    FAILURE_INVALID_OUTPUT,
    FAILURE_TIMEOUT,
    FAILURE_UNAVAILABLE,
)
from tests.api.helpers import (
    DOCUMENTS_URL,
    Account,
    audit_rows,
    auth_headers,
    spend_tokens,
    upload,
    without_request_id,
)
from tests.fakes.llm import FakeLLM
from tests.sop_fixtures import SOP_TEXT

ANALYSES_URL = DOCUMENTS_URL + "/{document_id}/analyses"
LATEST_URL = ANALYSES_URL + "/latest"
ANALYSIS_URL = "/api/v1/analyses/{analysis_id}"
FINDING_URL = "/api/v1/findings/{finding_id}"
MARKER = "QX-MODEL-ONLY-TEXT-4471"


async def make_document(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await upload(client, headers, SOP_TEXT.encode(), "sop.md")
    return str(response.json()["document"]["id"])


@pytest.fixture
async def document_id(api_client: AsyncClient, headers: dict[str, str]) -> str:
    return await make_document(api_client, headers)


async def rows(engine: AsyncEngine, sql: str, **params: Any) -> list[Any]:
    async with engine.connect() as connection:
        return list((await connection.execute(text(sql), params)).all())


async def chunks(engine: AsyncEngine, document_id: str) -> list[Any]:
    return await rows(
        engine,
        "SELECT id, chunk_index, section_label, content FROM document_chunks "
        "WHERE document_id = :id ORDER BY chunk_index",
        id=document_id,
    )


def quote_of(content: str) -> str:
    """A verbatim piece of a chunk: its first line, cut to a size the schema accepts."""
    return content.split("\n")[0][:120].strip()


def finding(kind: str, severity: str, *quotes: str, title: str = "A gap") -> dict[str, Any]:
    return {
        "kind": kind,
        "severity": severity,
        "title": title,
        "description": "The document does not say this.",
        "evidence": [{"section_label": None, "quote": quote} for quote in quotes],
        "suggested_question": "Who decides this?",
    }


def report(*findings: dict[str, Any]) -> str:
    return json.dumps({"summary": "A short SOP for refunds.", "findings": list(findings)})


async def start(client: AsyncClient, headers: dict[str, str], document_id: str) -> Response:
    return await client.post(ANALYSES_URL.format(document_id=document_id), headers=headers)


async def latest(client: AsyncClient, headers: dict[str, str], document_id: str) -> Response:
    return await client.get(LATEST_URL.format(document_id=document_id), headers=headers)


async def insert_analysis(engine: AsyncEngine, document_id: str, status: str) -> uuid.UUID:
    async with engine.begin() as connection:
        result = await connection.execute(
            text(
                "INSERT INTO analyses (document_id, owner_id, prompt_version, model, status) "
                "SELECT id, owner_id, 'gap_report.v1', 'm', :status FROM documents "
                "WHERE id = :id RETURNING id"
            ),
            {"id": document_id, "status": status},
        )
        return result.scalar_one()


async def test_a_started_analysis_is_queued_then_stored_verified_and_ordered(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    fake_llm: FakeLLM,
    migrated_engine: AsyncEngine,
) -> None:
    stored = await chunks(migrated_engine, document_id)
    early, late = stored[1], stored[-1]
    fake_llm.reply_text(
        report(
            finding("unclear", "low", quote_of(stored[2].content), title="Low middle"),
            finding("unclear", "high", quote_of(late.content), title="High late"),
            finding("unclear", "high", quote_of(early.content), title="High early"),
            finding("missing", "high", title="High missing"),
        ),
        input_tokens=900,
        output_tokens=300,
    )

    response = await start(api_client, headers, document_id)

    assert response.status_code == 202
    started = response.json()["analysis"]
    assert started["status"] == "queued" and started["findings"] == []
    assert started["document_id"] == document_id

    body = (await latest(api_client, headers, document_id)).json()["analysis"]
    assert body["id"] == started["id"] and body["status"] == "succeeded"
    assert body["summary"] == "A short SOP for refunds."
    assert (body["findings_count"], body["dropped_findings_count"]) == (4, 0)
    assert body["completed_at"] is not None and body["error_message"] is None
    assert [f["title"] for f in body["findings"]] == [
        "High early",
        "High late",
        "High missing",
        "Low middle",
    ]
    first = body["findings"][0]
    assert first["review_status"] == "open"
    assert first["citations"] == [
        {
            "chunk_id": str(early.id),
            "section_label": early.section_label,
            "quote": quote_of(early.content),
        }
    ]
    assert body["findings"][2]["citations"] == []


async def test_the_start_is_audited_and_the_model_call_recorded_without_content(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    fake_llm: FakeLLM,
    migrated_engine: AsyncEngine,
) -> None:
    fake_llm.reply_text(report(finding("missing", "low", title=MARKER)))

    analysis_id = (await start(api_client, headers, document_id)).json()["analysis"]["id"]

    (event,) = await audit_rows(migrated_engine, "analysis.start")
    assert (event.resource_type, str(event.resource_id)) == ("analysis", analysis_id)
    (call,) = await rows(
        migrated_engine, "SELECT row_to_json(c)::text AS dump, purpose, status FROM llm_calls c"
    )
    assert (call.purpose, call.status) == ("gap_report", "ok")
    assert MARKER not in call.dump
    (analysis,) = await rows(migrated_engine, "SELECT prompt_version, model FROM analyses")
    assert tuple(analysis) == ("gap_report.v1", "fake-model")


async def test_unverifiable_findings_are_dropped_and_counted(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    fake_llm: FakeLLM,
    migrated_engine: AsyncEngine,
) -> None:
    stored = await chunks(migrated_engine, document_id)
    fake_llm.reply_text(
        report(
            finding("unclear", "high", "a sentence the document never contains"),
            finding("contradiction", "high", quote_of(stored[1].content)),
            finding("unclear", "medium", quote_of(stored[2].content)),
        )
    )

    await start(api_client, headers, document_id)

    body = (await latest(api_client, headers, document_id)).json()["analysis"]
    assert (body["findings_count"], body["dropped_findings_count"]) == (1, 2)
    assert [f["severity"] for f in body["findings"]] == ["medium"]


async def test_when_every_finding_is_dropped_the_report_succeeds_empty_and_says_so(
    api_client: AsyncClient, headers: dict[str, str], document_id: str, fake_llm: FakeLLM
) -> None:
    fake_llm.reply_text(report(finding("unclear", "high", "a sentence the document never has")))

    await start(api_client, headers, document_id)

    body = (await latest(api_client, headers, document_id)).json()["analysis"]
    assert body["status"] == "succeeded" and body["findings"] == []
    assert (body["findings_count"], body["dropped_findings_count"]) == (0, 1)


async def test_near_duplicate_findings_are_stored_once(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    fake_llm: FakeLLM,
    migrated_engine: AsyncEngine,
) -> None:
    quote = quote_of((await chunks(migrated_engine, document_id))[1].content)
    fake_llm.reply_text(
        report(
            finding("unclear", "low", quote, title="Said twice, low"),
            finding("unclear", "high", quote, title="Said twice, high"),
        )
    )

    await start(api_client, headers, document_id)

    body = (await latest(api_client, headers, document_id)).json()["analysis"]
    assert [f["title"] for f in body["findings"]] == ["Said twice, high"]
    assert body["findings_count"] == 1


async def test_a_second_start_while_one_is_active_is_409(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    fake_llm: FakeLLM,
    migrated_engine: AsyncEngine,
) -> None:
    for status in ("queued", "running"):
        active = await insert_analysis(migrated_engine, document_id, status)

        response = await start(api_client, headers, document_id)

        assert without_request_id(response) == (
            409,
            {
                "type": "about:blank",
                "title": "Analysis already running",
                "status": 409,
                "code": "analysis_already_running",
                "detail": "An analysis of this document is already running. Wait for it to finish.",
            },
        )
        async with migrated_engine.begin() as connection:
            await connection.execute(
                text("UPDATE analyses SET status = 'failed' WHERE id = :id"), {"id": active}
            )
    assert fake_llm.calls == []
    assert await audit_rows(migrated_engine, "analysis.start") == []


async def test_a_new_analysis_can_start_after_the_last_one_finished(
    api_client: AsyncClient, headers: dict[str, str], document_id: str, fake_llm: FakeLLM
) -> None:
    fake_llm.reply_text(report())
    fake_llm.reply_text(report(finding("missing", "low", title="Second run")))

    first = (await start(api_client, headers, document_id)).json()["analysis"]["id"]
    second = await start(api_client, headers, document_id)

    assert second.status_code == 202
    body = (await latest(api_client, headers, document_id)).json()["analysis"]
    assert body["id"] == second.json()["analysis"]["id"] != first
    assert [f["title"] for f in body["findings"]] == ["Second run"]


async def test_over_the_daily_budget_a_start_is_refused_and_leaves_nothing_behind(
    api_client: AsyncClient,
    headers: dict[str, str],
    account: Account,
    document_id: str,
    fake_llm: FakeLLM,
    migrated_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "daily_token_budget", 1000)
    await spend_tokens(migrated_engine, account.email, 1000)

    response = await start(api_client, headers, document_id)

    assert response.status_code == 429
    assert response.json()["code"] == "daily_budget_exceeded"
    assert int(response.headers["retry-after"]) >= 1
    assert fake_llm.calls == []
    assert await rows(migrated_engine, "SELECT id FROM analyses") == []
    assert await audit_rows(migrated_engine, "analysis.start") == []


async def test_the_sixth_start_in_an_hour_is_rate_limited(
    api_client: AsyncClient, headers: dict[str, str], document_id: str, fake_llm: FakeLLM
) -> None:
    for _ in range(5):
        fake_llm.reply_text(report())
        # Each run finishes before the next start, so the one-active rule never refuses one.
        assert (await start(api_client, headers, document_id)).status_code == 202

    response = await start(api_client, headers, document_id)

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
    assert response.headers["retry-after"] == "3600"
    assert len(fake_llm.calls) == 5


@pytest.mark.parametrize("status", ["processing", "failed"])
async def test_a_document_that_is_not_ready_cannot_be_analyzed(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    migrated_engine: AsyncEngine,
    status: str,
) -> None:
    async with migrated_engine.begin() as connection:
        await connection.execute(
            text("UPDATE documents SET status = :status WHERE id = :id"),
            {"status": status, "id": document_id},
        )

    response = await start(api_client, headers, document_id)

    assert response.status_code == 409 and response.json()["code"] == "document_not_ready"


async def test_a_missing_or_deleted_document_is_404(
    api_client: AsyncClient, headers: dict[str, str], document_id: str
) -> None:
    missing = await start(api_client, headers, str(uuid.uuid4()))
    await api_client.delete(f"{DOCUMENTS_URL}/{document_id}", headers=headers)
    deleted = await start(api_client, headers, document_id)

    for response in (missing, deleted):
        assert response.status_code == 404 and response.json()["code"] == "document_not_found"


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (LLMTimeout(), FAILURE_TIMEOUT),
        (LLMUnavailable(), FAILURE_UNAVAILABLE),
        (LLMInvalidOutput(), FAILURE_INVALID_OUTPUT),
        (RuntimeError(MARKER), FAILURE_GENERIC),
    ],
)
async def test_a_failed_model_call_ends_failed_with_a_fixed_message(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    fake_llm: FakeLLM,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    message: str,
) -> None:
    fake_llm.fail(error)

    with caplog.at_level(logging.INFO):
        await start(api_client, headers, document_id)

    body = (await latest(api_client, headers, document_id)).json()["analysis"]
    assert (body["status"], body["error_message"]) == ("failed", message)
    assert body["findings"] == [] and body["completed_at"] is not None
    assert MARKER not in caplog.text


async def test_model_text_never_reaches_the_error_message(
    api_client: AsyncClient, headers: dict[str, str], document_id: str, fake_llm: FakeLLM
) -> None:
    fake_llm.reply_text(f"not json {MARKER}")
    fake_llm.reply_text(f"still not json {MARKER}")

    await start(api_client, headers, document_id)

    body = (await latest(api_client, headers, document_id)).json()["analysis"]
    assert (body["status"], body["error_message"]) == ("failed", FAILURE_INVALID_OUTPUT)
    assert MARKER not in json.dumps(body)


async def test_latest_and_by_id_return_the_same_report_and_404_when_there_is_none(
    api_client: AsyncClient, headers: dict[str, str], document_id: str, fake_llm: FakeLLM
) -> None:
    before = await latest(api_client, headers, document_id)
    fake_llm.reply_text(report(finding("missing", "medium")))
    analysis_id = (await start(api_client, headers, document_id)).json()["analysis"]["id"]

    by_id = await api_client.get(ANALYSIS_URL.format(analysis_id=analysis_id), headers=headers)
    missing = await api_client.get(ANALYSIS_URL.format(analysis_id=uuid.uuid4()), headers=headers)

    assert before.status_code == 404 and before.json()["code"] == "analysis_not_found"
    assert by_id.json() == (await latest(api_client, headers, document_id)).json()
    assert missing.status_code == 404 and missing.json()["code"] == "analysis_not_found"


async def test_latest_shows_an_analysis_that_is_still_running(
    api_client: AsyncClient, headers: dict[str, str], document_id: str, migrated_engine: AsyncEngine
) -> None:
    await insert_analysis(migrated_engine, document_id, "running")

    body = (await latest(api_client, headers, document_id)).json()["analysis"]

    assert body["status"] == "running" and body["findings"] == []


async def first_finding_id(
    client: AsyncClient, headers: dict[str, str], document_id: str, fake_llm: FakeLLM
) -> str:
    fake_llm.reply_text(report(finding("missing", "high")))
    await start(client, headers, document_id)
    return str((await latest(client, headers, document_id)).json()["analysis"]["findings"][0]["id"])


async def test_the_review_status_of_a_finding_can_be_set(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    fake_llm: FakeLLM,
    migrated_engine: AsyncEngine,
) -> None:
    finding_id = await first_finding_id(api_client, headers, document_id, fake_llm)
    (before,) = await rows(migrated_engine, "SELECT updated_at FROM findings")

    for status in ("confirmed", "dismissed", "open"):
        response = await api_client.patch(
            FINDING_URL.format(finding_id=finding_id),
            headers=headers,
            json={"review_status": status},
        )
        assert response.status_code == 200
        assert response.json()["finding"]["review_status"] == status
        assert response.json()["finding"]["id"] == finding_id

    (after,) = await rows(migrated_engine, "SELECT updated_at FROM findings")
    assert after.updated_at > before.updated_at


@pytest.mark.parametrize(
    "body",
    [{"review_status": "done"}, {"review_status": "open", "title": "x"}, {}],
    ids=["unknown_status", "extra_field", "empty"],
)
async def test_an_invalid_review_update_is_422(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    fake_llm: FakeLLM,
    body: dict[str, Any],
) -> None:
    finding_id = await first_finding_id(api_client, headers, document_id, fake_llm)

    response = await api_client.patch(
        FINDING_URL.format(finding_id=finding_id), headers=headers, json=body
    )

    assert response.status_code == 422 and response.json()["code"] == "validation_error"


async def test_another_user_gets_404_for_every_analysis_route(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    fake_llm: FakeLLM,
    other_account: Account,
    migrated_engine: AsyncEngine,
) -> None:
    finding_id = await first_finding_id(api_client, headers, document_id, fake_llm)
    analysis_id = (await latest(api_client, headers, document_id)).json()["analysis"]["id"]
    other = await auth_headers(api_client, other_account)

    responses = {
        "start": await start(api_client, other, document_id),
        "latest": await latest(api_client, other, document_id),
        "by_id": await api_client.get(ANALYSIS_URL.format(analysis_id=analysis_id), headers=other),
        "patch": await api_client.patch(
            FINDING_URL.format(finding_id=finding_id),
            headers=other,
            json={"review_status": "dismissed"},
        ),
    }

    codes = {name: (r.status_code, r.json()["code"]) for name, r in responses.items()}
    assert codes == {
        "start": (404, "document_not_found"),
        "latest": (404, "document_not_found"),
        "by_id": (404, "analysis_not_found"),
        "patch": (404, "finding_not_found"),
    }
    assert [
        tuple(r) for r in await rows(migrated_engine, "SELECT review_status FROM findings")
    ] == [("open",)]
    assert len(await rows(migrated_engine, "SELECT id FROM analyses")) == 1


async def test_the_analysis_routes_need_a_token(api_client: AsyncClient, document_id: str) -> None:
    responses = [
        await api_client.post(ANALYSES_URL.format(document_id=document_id)),
        await api_client.get(LATEST_URL.format(document_id=document_id)),
        await api_client.get(ANALYSIS_URL.format(analysis_id=uuid.uuid4())),
        await api_client.patch(
            FINDING_URL.format(finding_id=uuid.uuid4()), json={"review_status": "open"}
        ),
    ]

    assert [r.status_code for r in responses] == [401] * 4


async def test_an_analysis_deleted_while_running_writes_nothing(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    fake_llm: FakeLLM,
    migrated_engine: AsyncEngine,
) -> None:
    analysis_id = await insert_analysis(migrated_engine, document_id, "queued")
    owner_id = (await rows(migrated_engine, "SELECT owner_id FROM documents"))[0].owner_id
    fake_llm.reply_text(report(finding("missing", "high")))
    original = fake_llm.complete

    async def delete_during_the_call(**kwargs: Any) -> Any:
        async with migrated_engine.begin() as connection:
            await connection.execute(text("DELETE FROM analyses"))
        return await original(**kwargs)

    fake_llm.complete = delete_during_the_call  # type: ignore[method-assign]

    await analysis_service.run_analysis(
        async_sessionmaker(migrated_engine),
        fake_llm,
        analysis_id=analysis_id,
        owner_id=owner_id,
        document_id=uuid.UUID(document_id),
    )

    assert await rows(migrated_engine, "SELECT id FROM analyses") == []
    assert await rows(migrated_engine, "SELECT id FROM findings") == []
    # The call was made and paid for, so its record stays.
    assert len(await rows(migrated_engine, "SELECT id FROM llm_calls")) == 1


async def test_an_analysis_swept_while_running_stays_failed_and_gets_no_findings(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    fake_llm: FakeLLM,
    migrated_engine: AsyncEngine,
) -> None:
    fake_llm.reply_text(report(finding("missing", "high")))
    original = fake_llm.complete

    async def sweep_during_the_call(**kwargs: Any) -> Any:
        async with migrated_engine.begin() as connection:
            await connection.execute(
                text("UPDATE analyses SET status = 'failed', error_message = 'swept'")
            )
        return await original(**kwargs)

    fake_llm.complete = sweep_during_the_call  # type: ignore[method-assign]

    await start(api_client, headers, document_id)

    body = (await latest(api_client, headers, document_id)).json()["analysis"]
    assert (body["status"], body["error_message"], body["findings"]) == ("failed", "swept", [])


async def test_the_findings_queries_filter_on_the_owner_themselves(
    api_client: AsyncClient,
    headers: dict[str, str],
    document_id: str,
    fake_llm: FakeLLM,
    other_account: Account,
    migrated_engine: AsyncEngine,
) -> None:
    finding_id = await first_finding_id(api_client, headers, document_id, fake_llm)
    (analysis,) = await rows(migrated_engine, "SELECT id, owner_id FROM analyses")
    await auth_headers(api_client, other_account)
    other_id = (
        await rows(migrated_engine, "SELECT id FROM users WHERE id <> :id", id=analysis.owner_id)
    )[0].id

    async with async_sessionmaker(migrated_engine)() as session:
        for owner, expected in ((analysis.owner_id, 1), (other_id, 0)):
            listed = await analysis_repository.list_findings(
                session, owner_id=owner, analysis_id=analysis.id
            )
            one = await analysis_repository.get_finding(
                session, owner_id=owner, finding_id=uuid.UUID(finding_id)
            )
            assert (len(listed), len(one)) == (expected, expected)
