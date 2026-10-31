import importlib
import threading
from collections.abc import Iterable
from functools import lru_cache
from typing import Protocol

from fastembed import TextEmbedding

from app.core.config import get_settings

EMBEDDING_DIMENSIONS = 384


class Embedder(Protocol):
    """Turns text into vectors. Passages (document chunks) and queries are embedded differently
    by this kind of model, so they are two methods."""

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class WrongEmbeddingSize(Exception):
    """The model returned vectors that do not fit the vector(384) column."""


class FastEmbedEmbedder:
    """The local ONNX model (ADR-004). The model loads on first use, not at import, so the app
    and its tests start fast and a missing model fails the one document, not the whole app."""

    def __init__(self, model_name: str, cache_dir: str | None) -> None:
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._model: TextEmbedding | None = None
        self._load_lock = threading.Lock()

    def _loaded_model(self) -> TextEmbedding:
        # Embedding runs in worker threads, so two could ask for the model at once.
        with self._load_lock:
            if self._model is None:
                # AGENTS.md: no telemetry. onnxruntime can send usage events unless told not to.
                # Imported by name because the package ships no type information.
                importlib.import_module("onnxruntime").disable_telemetry_events()
                self._model = TextEmbedding(self._model_name, cache_dir=self._cache_dir)
            return self._model

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return _to_lists(self._loaded_model().passage_embed(texts))

    def embed_query(self, text: str) -> list[float]:
        return _to_lists(self._loaded_model().query_embed(text))[0]


def _to_lists(vectors: Iterable[Iterable[float]]) -> list[list[float]]:
    result = [[float(value) for value in vector] for vector in vectors]
    for vector in result:
        # A different model would write vectors of another size; fail here, not in the database.
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise WrongEmbeddingSize
    return result


@lru_cache
def get_embedder() -> Embedder:
    """FastAPI dependency. One model per process; tests override it with a fake."""
    settings = get_settings()
    return FastEmbedEmbedder(settings.embedding_model, settings.embedding_cache_dir)
