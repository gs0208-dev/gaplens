import hashlib
import math
import threading

from app.modules.ingestion.embedder import EMBEDDING_DIMENSIONS


def vector_for(text: str) -> list[float]:
    """A repeatable unit vector for a text: the same text always gives the same vector, and
    different texts give different ones. It means nothing, which is fine: tests of the pipeline
    need vectors of the right shape, not vectors that capture meaning."""
    raw = hashlib.shake_256(text.encode()).digest(EMBEDDING_DIMENSIONS)
    values = [(byte - 127.5) / 127.5 for byte in raw]
    length = math.sqrt(sum(value * value for value in values))
    return [value / length for value in values]


class FakeEmbedder:
    """Stands in for the real model, which would need a download. Records what it was given."""

    def __init__(self) -> None:
        self.passage_batch_sizes: list[int] = []
        self.passage_texts: list[str] = []
        self.queries: list[str] = []
        self.query_thread_names: list[str] = []
        # Set to an exception to make the next calls fail.
        self.failure: Exception | None = None

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        if self.failure is not None:
            raise self.failure
        self.passage_batch_sizes.append(len(texts))
        self.passage_texts.extend(texts)
        return [vector_for(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        if self.failure is not None:
            raise self.failure
        self.queries.append(text)
        self.query_thread_names.append(threading.current_thread().name)
        return vector_for(text)
