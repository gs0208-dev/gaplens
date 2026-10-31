"""Retrieval eval: does the right chunk come back for each golden question?

Runs the real pipeline (extract, chunk, embed with the real model) on the sample SOP, ranks the
chunks for every question in golden/qa.jsonl and prints recall@k and mean reciprocal rank. It
needs the embedding model, which is downloaded the first time, so it is not part of make check
or CI. Run it from the backend folder:

    .venv/bin/python ../evals/retrieval_eval.py

Definitions are in evals/README.md. The ranking here is a plain dot product, which for the
unit-length vectors the model produces is the same order as the SQL cosine query in
app/modules/retrieval/repository.py.
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from app.modules.ingestion.chunker import Chunk, chunk_document
from app.modules.ingestion.embedder import FastEmbedEmbedder
from app.modules.ingestion.service import text_to_embed
from app.modules.ingestion.structure import extract_document

EVALS_DIR = Path(__file__).resolve().parent
DATASET = EVALS_DIR / "datasets" / "sop_refund_escalation.md"
GOLDEN = EVALS_DIR / "golden" / "qa.jsonl"
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
KS = (1, 3, 6)


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    type: str
    expected_sections: list[str]


@dataclass(frozen=True)
class Metrics:
    recall_at: dict[int, float]
    mean_reciprocal_rank: float
    # Per question: the rank of the first chunk covering each expected section (None = not found).
    ranks: dict[str, dict[str, int | None]]


def _numbers(label: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(part) for part in label.split("."))
    except ValueError:
        return None


def label_covers(chunk_label: str | None, section: str) -> bool:
    """Whether a chunk's label stands for a clause. A merged chunk is labeled with a range, so
    "3.1-3.5" covers "3.3", but not "4.1", "3.6" or "3"."""
    if chunk_label is None:
        return False
    if chunk_label == section:
        return True
    first, dash, last = chunk_label.partition("-")
    if not dash:
        return False
    low, high, target = _numbers(first), _numbers(last), _numbers(section)
    if low is None or high is None or target is None:
        return False
    same_depth = len(low) == len(high) == len(target)
    return same_depth and low[:-1] == high[:-1] == target[:-1] and low[-1] <= target[-1] <= high[-1]


def first_rank(ranked_labels: list[str | None], section: str) -> int | None:
    """1-based position of the first chunk that covers the section."""
    for position, label in enumerate(ranked_labels, start=1):
        if label_covers(label, section):
            return position
    return None


def rank_chunks(query: list[float], vectors: list[list[float]]) -> list[int]:
    """Chunk positions, closest to the query first. Ties keep document order."""
    scores = [sum(q * v for q, v in zip(query, vector, strict=True)) for vector in vectors]
    return sorted(range(len(vectors)), key=lambda index: (-scores[index], index))


def score_questions(
    rankings: dict[str, list[str | None]], expected: dict[str, list[str]]
) -> Metrics:
    """recall@k: of all (question, expected section) pairs, the share found in the top k.
    A question that needs two sections counts for two. Mean reciprocal rank: for each question,
    1 / the best rank among its expected sections (0 if none is found), averaged."""
    ranks = {
        question: {section: first_rank(rankings[question], section) for section in sections}
        for question, sections in expected.items()
        if sections
    }
    pairs = [rank for per_question in ranks.values() for rank in per_question.values()]
    recall_at = {
        k: sum(1 for rank in pairs if rank is not None and rank <= k) / len(pairs) for k in KS
    }
    reciprocal = [
        1 / min(found) if (found := [r for r in per_question.values() if r is not None]) else 0.0
        for per_question in ranks.values()
    ]
    return Metrics(recall_at, sum(reciprocal) / len(reciprocal), ranks)


def load_questions() -> list[Question]:
    return [
        Question(row["id"], row["question"], row["type"], row["expected_sections"])
        for row in (json.loads(line) for line in GOLDEN.read_text().splitlines() if line.strip())
    ]


def run(model: str, cache_dir: str | None) -> None:
    document = extract_document(DATASET.read_bytes(), "text/markdown")
    chunks: list[Chunk] = chunk_document(document)
    embedder = FastEmbedEmbedder(model, cache_dir)
    vectors = embedder.embed_passages([text_to_embed(chunk) for chunk in chunks])

    questions = load_questions()
    order: dict[str, list[int]] = {}
    best_score: dict[str, tuple[float, str | None]] = {}
    for question in questions:
        query = embedder.embed_query(question.text)
        order[question.id] = rank_chunks(query, vectors)
        top = order[question.id][0]
        best_score[question.id] = (
            sum(q * v for q, v in zip(query, vectors[top], strict=True)),
            chunks[top].section_label,
        )

    rankings = {
        question_id: [chunks[index].section_label for index in indexes]
        for question_id, indexes in order.items()
    }
    metrics = score_questions(rankings, {q.id: q.expected_sections for q in questions})

    print(f"model: {model}")
    print(f"chunks: {len(chunks)} ({', '.join(str(chunk.section_label) for chunk in chunks)})")
    print(f"questions with expected sections: {len(metrics.ranks)}")
    for k in KS:
        print(f"recall@{k}: {metrics.recall_at[k]:.2f}")
    print(f"MRR: {metrics.mean_reciprocal_rank:.2f}")
    print("\nrank of the first chunk covering each expected section:")
    for question_id, per_section in metrics.ranks.items():
        print(f"  {question_id}: {per_section}")
    print("\nbest score per question (raw data for choosing a cutoff in Sprint 4):")
    for question in questions:
        score, label = best_score[question.id]
        print(f"  {question.id} {question.type:12} {score:.3f} chunk {label}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--cache-dir", default=None)
    arguments = parser.parse_args()
    run(arguments.model, arguments.cache_dir)


if __name__ == "__main__":
    main()
