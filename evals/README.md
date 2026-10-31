# Evals

Datasets and golden answers for measuring GapLens quality. Method, metrics and targets are in `docs/ai-engineering.md` (section Evals). The full runner (`run.py`) is built in Sprint 4; until then `retrieval_eval.py` measures retrieval.

| Path | Contents |
|---|---|
| `datasets/sop_refund_escalation.md` | Fictional SOP with seven planted gaps |
| `golden/sop_refund_escalation.gaps.json` | The planted gaps: id, kind, severity, sections, what is wrong |
| `golden/qa.jsonl` | Ten questions about the SOP: answerable, one conflict, three unanswerable |
| `datasets/injection_sample.md` | Fictional checklist with an injected instruction and the canary word `PINEAPPLE` |
| `retrieval_eval.py` | Retrieval eval: recall@k and mean reciprocal rank on `qa.jsonl` against the sample SOP |

Running the retrieval eval needs the embedding model (downloaded the first time) and is not part of `make check` or CI:

```bash
cd backend && .venv/bin/python ../evals/retrieval_eval.py
```

Definitions. The SOP is chunked by the real pipeline, so a chunk's label can be a range such as `3.1-3.5`; a range covers every clause inside it (`3.3`), nothing else. For each question with `expected_sections`, the rank of a section is the position of the first retrieved chunk that covers it. recall@k is the share of all (question, expected section) pairs found in the top k, so the conflict question Q1 counts for two. MRR is, per question, 1 divided by the best rank among its expected sections (0 if none is found), averaged. The unanswerable questions are not scored; the script prints their best similarity score so a cutoff can be chosen from data in Sprint 4. The sample has only eight chunks, so recall@6 is close to automatic; read recall@1 and recall@3.

Rules:
- Only fictional documents. Never add real client data.
- Do not edit a golden file to make a run pass. Change a golden file only when the dataset document changes, and record why in `docs/decisions.md`.
- `evals/results/` is gitignored. Commit only the summary table you paste into pull requests and the README.
