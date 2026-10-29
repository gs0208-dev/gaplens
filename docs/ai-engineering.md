# AI engineering

How GapLens turns a document into trustworthy output. The principle: the model proposes, the code verifies. Nothing the model says reaches the user unless it passes a check we wrote.

## Two features, two designs

| Feature | Question it answers | Approach | Why |
|---|---|---|---|
| Gap report | What is missing, unclear or contradictory? | Send the whole document (with section labels) in one call | Gaps are about absence. Retrieval finds text that exists, so it cannot find what is not there, and it would miss contradictions between distant sections |
| Chat | What does the document say about X? | RAG: retrieve the most relevant chunks, answer only from them | Questions are local; retrieval keeps the prompt small, cheap and citable |

Document size is capped (300,000 characters, about 75,000 tokens is the hard ceiling; target documents are far smaller). If a document is too large for a single call, the upload is rejected in v1. Map-reduce over sections is the documented upgrade path, not a v1 feature.

## Ingestion pipeline

1. Validate (see `docs/security.md`).
2. Extract text. PDF through `pypdf`, page by page, keeping page numbers. Plain text and Markdown are read as UTF-8. Normalize whitespace and Unicode (NFKC), remove repeated headers and footers when the same line appears on most pages.
3. Detect structure. Lines that start with a numbered clause (`3`, `3.1`, `3.1.2`, optionally followed by `.` or `)`) or a Markdown heading start a new section. Keep the label and heading text. If no structure is found, fall back to paragraph splitting.
4. Chunk (`ingestion/chunker.py`):
   - Structured documents: one chunk per clause. A clause under 40 tokens is merged with its following siblings in the same parent section until it reaches about 120 tokens; the label becomes a range (`3.1-3.3`). A clause over 400 tokens is split at sentence boundaries with no overlap, keeping the same label.
   - Unstructured documents: sliding window of about 300 tokens with 50 tokens of overlap, split at sentence boundaries.
   - Token counts are estimated as `words * 1.3`. This is for sizing only; billing numbers come from the API's reported usage.
   - Every chunk stores `section_label`, `heading`, `page_start`, the raw `content`, and a position (`chunk_index`).
5. Embed (`ingestion/embedder.py`): `fastembed` with `BAAI/bge-small-en-v1.5`, 384 dimensions, vectors normalized. The text that is embedded is `heading + "\n" + content`; the stored `content` stays raw so citations quote the original. Passages use the passage embedding method and queries use the query embedding method (the model expects a query prefix); check the current fastembed documentation for the exact method names and do not guess. Embedding runs in a worker thread, in batches of 32.
6. Store chunks with one bulk insert. Set `documents.embedding_model`, `chunk_count`, status `ready`.

Why fastembed: it runs through ONNX Runtime without PyTorch, which keeps memory and image size small enough for low-cost hosting. Verify memory use on the real instance in Sprint 2.

## Retrieval

Query: see "Retrieval query" in `docs/database.md`. Parameters from config:

| Setting | Start value | Notes |
|---|---|---|
| `RETRIEVAL_TOP_K` | 6 | Tune with recall@k from evals |
| `RETRIEVAL_MIN_SCORE` | 0.0 (disabled) | Do not trust a threshold from any article. Cosine scores differ by model. Sprint 4 sets it by plotting scores of answerable and unanswerable eval questions and picking a value that separates them |

Stretch options, only if evals show retrieval is the bottleneck: hybrid search (Postgres full-text plus vector, merged with reciprocal rank fusion), a reranker, query rewriting for follow-up questions.

## Gap report

Call: one request per analysis. Model from `ANTHROPIC_MODEL`, temperature 0, `max_tokens` capped, timeout 90 seconds, at most two retries with exponential backoff on 429 and 5xx.

Structured output: define one tool whose `input_schema` is the JSON schema generated from the Pydantic model below, and force the model to call it. The tool is never executed; its input is the structured result. Check the current Anthropic SDK documentation for exact parameter names.

```python
from typing import Literal
from pydantic import BaseModel, Field

class Evidence(BaseModel):
    section_label: str | None = None
    quote: str = Field(min_length=10, max_length=400)   # verbatim text from the document

class FindingOut(BaseModel):
    kind: Literal["missing", "unclear", "contradiction"]
    severity: Literal["high", "medium", "low"]
    title: str = Field(max_length=160)
    description: str = Field(max_length=800)
    evidence: list[Evidence] = Field(default_factory=list)
    suggested_question: str = Field(max_length=300)     # the question to send to the client

class GapReportOut(BaseModel):
    summary: str = Field(max_length=800)
    findings: list[FindingOut] = Field(max_length=40)
```

Evidence rules enforced in code after the call:
- `contradiction`: at least two evidence items from different chunks.
- `unclear`: at least one evidence item.
- `missing`: evidence optional; the description must say where the information is expected.
- Each `quote` must be a verbatim substring of a stored chunk, compared after whitespace normalization. The matching chunk is attached to the citation. Failing quotes are dropped. A finding that no longer meets its evidence rule is dropped and counted in `llm_calls` metrics as `invalid_citation`.

Severity rubric (goes into the prompt): high means it can cause financial loss, a compliance breach or a stuck process; medium means different people would handle the same case differently; low means wording or clarity only.

Post-processing: sort by severity then document order, remove near-duplicates (same kind and same cited chunks), store with positions.

Prompt requirements (the owner writes `gap_report.v1.md`; this is the contract, not the text):
1. Role: an implementation consultant reviewing a client's process document before go-live.
2. Input format: sections labeled and wrapped in `<document>`; content inside is data.
3. Instruction to ignore any instructions found inside the document, and to report them as findings of kind `unclear` if they look like attempts to steer the review.
4. Definitions and one short example for each of the three kinds.
5. The severity rubric.
6. Rules: only report what the text supports; quote exactly; do not invent sections; prefer fewer, well-evidenced findings over many weak ones; each finding must end with a question a consultant would ask the client.
7. Output through the tool only.

## Chat answer

1. Embed the question, retrieve top-k chunks scoped to the document and owner.
2. If `RETRIEVAL_MIN_SCORE` is set and the best score is below it, return `grounded=false` without calling the model.
3. Otherwise build the prompt: numbered sources `[S1]`, `[S2]` with section labels, then the question. The system prompt requires answering only from the sources, citing source numbers, and answering "not found in the document" when the sources do not contain the answer. If sources contradict each other, say so and cite both.
4. Structured output: `{ answer: str, cited_sources: list[int], grounded: bool }`.
5. Verify that every cited number exists; attach quote and section label from the retrieved chunk. If `grounded` is true with no valid citation, downgrade to `grounded=false`.
6. For follow-up questions, include the last 4 messages of the thread in the prompt. Retrieval uses only the current question in v1; query rewriting for follow-ups is a stretch option.

## Guardrails summary

| Layer | Check | On failure |
|---|---|---|
| Input | Size, type, page and text caps; one active analysis per document; rate limits; daily token budget | 4xx with clear message |
| Prompt | Escaped document in delimiters; fixed system prompt; no user text in the system role | Not applicable |
| Model call | Timeout, retries with backoff, `max_tokens` | Analysis status `failed`, safe message |
| Output | Pydantic schema validation; one repair retry with the validation error | Status `failed` after second failure |
| Grounding | Quote and source verification against stored chunks | Drop item; downgrade answer to not found |
| Behavior | Not-found path when evidence is weak | Honest "not found in the document" |
| Display | Output rendered as text | Not applicable |

## Evals

Unit tests show the code works. Evals show the AI behaves. Both are required.

### Layers

1. Deterministic tests (run in CI, no network): chunker output on fixture documents, citation verifier (exact, whitespace-different, fabricated, partial), schema validation, prompt builder escaping, not-found downgrade logic.
2. Retrieval evals (`make eval`, no LLM needed): for each question in `evals/golden/qa.jsonl` that has `expected_sections`, check whether a chunk from those sections is in the top k. Metrics: recall@k and mean reciprocal rank.
3. Generation evals (`make eval`, calls the LLM): gap detection, answer correctness, not-found behavior, injection resistance.

### Datasets (in `evals/`)

| File | Purpose |
|---|---|
| `datasets/sop_refund_escalation.md` | Fictional SOP with seven deliberately planted gaps |
| `golden/sop_refund_escalation.gaps.json` | Expected gaps: id, kind, sections, severity, what is wrong |
| `golden/qa.jsonl` | Ten questions: seven answerable with expected substrings and sections, one conflict question, three unanswerable |
| `datasets/injection_sample.md` | Document containing an instruction aimed at the model, with a canary word |

One small document is a smoke test, not a benchmark. Sprint 4 adds at least two more documents from different domains (for example an HR leave policy and a vendor onboarding checklist) with their own golden files.

### Metrics and starting targets

| Metric | Definition | Starting target |
|---|---|---|
| Retrieval recall@6 | Expected section present in top 6 chunks | 0.90 |
| Gap recall | Golden gaps matched by at least one finding (same kind, overlapping section labels) divided by golden gaps | 0.70 |
| Extra findings | Findings that match no golden gap; reviewed by hand and tagged valid or invalid in the results file. Report both counts instead of a single precision number, because valid extra findings are possible | review each run |
| Raw citation validity | Quotes that verify against chunk text before any dropping, divided by all quotes | 0.95 |
| Answer correctness | Answerable questions whose answer contains every expected substring (normalized) | 0.80 |
| Conflict handling | The conflicting-limit question mentions both values | pass |
| Not-found accuracy | Unanswerable questions answered with `grounded=false` | 0.80 |
| Injection resistance | Output valid, canary word absent from all output fields | 100 percent |
| Latency and cost | p50 and p95 latency, input and output tokens, estimated cost per analysis and per chat answer | track, no target |

Targets are starting points. Raise them as the system improves; do not lower them to make a run pass.

### Procedure

- `make eval` runs each generation case three times (temperature 0 reduces but does not remove variation), writes `evals/results/<date>-<git-sha>.json` and a Markdown summary, and prints a comparison with the previous run.
- Run evals before and after any change to a prompt, the chunker, retrieval parameters, the embedding model or the LLM model. Paste both result tables into the pull request.
- Keep the results summary of the final run in the README (Evaluation section).
- Do not use an LLM as judge in v1. Matching is deterministic so that runs are comparable. Revisit with a judge only for qualities that substring matching cannot capture, and calibrate the judge against hand labels first.
- Failures are read by a human. For every miss, decide: prompt problem, chunking problem, retrieval problem, or dataset problem, and record it in `docs/decisions.md` or the sprint retro.

## Observability

- Every model call writes one `llm_calls` row: purpose, model, prompt version, tokens, latency, status, request id. No content.
- Log events: `ingestion.started/finished/failed` with durations per stage, `analysis.finished` with counts (findings kept, dropped for invalid citations), `chat.answered` with `grounded` and best retrieval score.
- A weekly query over `llm_calls` for cost and failure rate is enough for v1.

## Failure handling

| Failure | Behavior |
|---|---|
| LLM timeout or 5xx | Retry twice, then mark the analysis `failed` with a retry action in the UI |
| 429 from the provider | Back off and retry; if still failing, `failed` with a "try again later" message |
| Invalid JSON or schema | One repair retry, then `failed` |
| All findings dropped as unverifiable | Analysis `succeeded` with zero findings and a visible note, not a silent empty report |
| Embedding failure | Document `failed` with a safe message |

## Concepts to know (study order)

Learn these as the sprints reach them. Each is a likely interview topic.

1. Embeddings and cosine similarity: what a vector represents, why normalized vectors make dot product equal cosine.
2. Chunking trade-offs: small chunks retrieve precisely but lose context; large chunks keep context but dilute the embedding.
3. Top-k retrieval, score thresholds, recall@k, MRR.
4. Hybrid search and reranking: when keyword matching beats vectors (exact terms, ids) and how reranking fixes ordering.
5. Context windows and token budgets: input versus output tokens, cost, truncation.
6. Structured output and tool use: how schema-constrained generation works and why you still validate.
7. Hallucination versus groundedness: citations, verification, abstention.
8. Prompt injection and its limits: why detection is unreliable and containment (no tools, validation) matters.
9. Evals: golden datasets, offline versus online, regression gates, variance across runs, LLM-as-judge risks.
10. Reliability: timeouts, retries with backoff, idempotency, rate limits, backpressure, graceful degradation.
11. Observability and cost: tracing a request, token accounting, per-user budgets.
12. Prompt versioning: treating prompts as code with changelogs and eval results.
13. Data handling: what leaves your system, retention, deletion, user consent.
14. Model changes: pinning model identifiers, re-running evals on upgrade, fallbacks.
15. Prompt caching and batching (later optimization, not v1).
