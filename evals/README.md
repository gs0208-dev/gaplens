# Evals

Datasets and golden answers for measuring GapLens quality. Method, metrics and targets are in `docs/ai-engineering.md` (section Evals). The runner (`run.py`) is built in Sprint 4.

| Path | Contents |
|---|---|
| `datasets/sop_refund_escalation.md` | Fictional SOP with seven planted gaps |
| `golden/sop_refund_escalation.gaps.json` | The planted gaps: id, kind, severity, sections, what is wrong |
| `golden/qa.jsonl` | Ten questions about the SOP: answerable, one conflict, three unanswerable |
| `datasets/injection_sample.md` | Fictional checklist with an injected instruction and the canary word `PINEAPPLE` |

Rules:
- Only fictional documents. Never add real client data.
- Do not edit a golden file to make a run pass. Change a golden file only when the dataset document changes, and record why in `docs/decisions.md`.
- `evals/results/` is gitignored. Commit only the summary table you paste into pull requests and the README.
