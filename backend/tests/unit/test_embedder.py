from collections.abc import Iterable
from typing import Any, ClassVar

import numpy
import onnxruntime
import pytest

from app.modules.ingestion import embedder as embedder_module
from app.modules.ingestion.embedder import (
    EMBEDDING_DIMENSIONS,
    FastEmbedEmbedder,
    WrongEmbeddingSize,
    get_embedder,
)


class StubTextEmbedding:
    """Stands in for fastembed's model, which would need a download."""

    created: ClassVar[list[dict[str, Any]]] = []
    size: ClassVar[int] = EMBEDDING_DIMENSIONS

    def __init__(self, model_name: str, cache_dir: str | None = None) -> None:
        self.created.append({"model_name": model_name, "cache_dir": cache_dir})
        self.calls: list[tuple[str, object]] = []

    def passage_embed(self, texts: Iterable[str]) -> Iterable[Any]:
        texts = list(texts)
        self.calls.append(("passage", texts))
        return (numpy.full(self.size, 0.5, dtype=numpy.float32) for _ in texts)

    def query_embed(self, query: str | Iterable[str]) -> Iterable[Any]:
        self.calls.append(("query", query))
        return (numpy.full(self.size, 0.25, dtype=numpy.float32) for _ in [query])


@pytest.fixture(autouse=True)
def stub_model(monkeypatch: pytest.MonkeyPatch) -> None:
    StubTextEmbedding.created = []
    StubTextEmbedding.size = EMBEDDING_DIMENSIONS
    monkeypatch.setattr(embedder_module, "TextEmbedding", StubTextEmbedding)


def test_the_model_is_not_loaded_until_it_is_needed() -> None:
    FastEmbedEmbedder("some/model", "/models")

    assert StubTextEmbedding.created == []


def test_telemetry_is_switched_off_before_the_model_loads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    monkeypatch.setattr(onnxruntime, "disable_telemetry_events", lambda: order.append("telemetry"))
    monkeypatch.setattr(
        embedder_module,
        "TextEmbedding",
        lambda *args, **kwargs: order.append("model") or StubTextEmbedding(*args, **kwargs),
    )

    FastEmbedEmbedder("some/model", None).embed_passages(["a"])

    assert order == ["telemetry", "model"]


def test_the_model_loads_once_with_its_name_and_cache_folder() -> None:
    embedder = FastEmbedEmbedder("some/model", "/models")

    embedder.embed_passages(["a"])
    embedder.embed_passages(["b"])
    embedder.embed_query("c")

    assert StubTextEmbedding.created == [{"model_name": "some/model", "cache_dir": "/models"}]


def test_passages_use_the_passage_method_and_come_back_as_plain_floats() -> None:
    embedder = FastEmbedEmbedder("some/model", None)

    vectors = embedder.embed_passages(["first", "second"])

    assert len(vectors) == 2
    assert all(len(vector) == EMBEDDING_DIMENSIONS for vector in vectors)
    assert all(type(value) is float for value in vectors[0])
    assert vectors[0][0] == 0.5


def test_a_query_uses_the_query_method_and_returns_one_vector() -> None:
    embedder = FastEmbedEmbedder("some/model", None)

    vector = embedder.embed_query("what is the limit?")

    assert len(vector) == EMBEDDING_DIMENSIONS
    assert vector[0] == 0.25
    model = embedder._model
    assert isinstance(model, StubTextEmbedding)
    assert model.calls == [("query", "what is the limit?")]


def test_vectors_of_the_wrong_size_are_refused() -> None:
    StubTextEmbedding.size = 768
    embedder = FastEmbedEmbedder("some/model", None)

    with pytest.raises(WrongEmbeddingSize):
        embedder.embed_passages(["a"])


def test_get_embedder_is_one_shared_instance_built_from_the_settings() -> None:
    get_embedder.cache_clear()

    first, second = get_embedder(), get_embedder()

    assert first is second
    assert isinstance(first, FastEmbedEmbedder)
    get_embedder.cache_clear()
