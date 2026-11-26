"""Unit tests for src/retrieval/embeddings.py (fake embedder, temporary cache folder)."""

from src.retrieval.embeddings import embed_new, text_key, vectors_for


class FakeEmbedder:
    embedding_model = "embed/model"

    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.append(texts)
        return [[float(len(t))] for t in texts]


def test_only_texts_without_a_vector_from_this_model_are_embedded_and_old_ones_dropped():
    cache = {"model": "embed/model", "vectors": {text_key("a"): [9.0], "gone": [1.0]}}
    embedder = FakeEmbedder()
    cache, embedded = embed_new(["a", "bb"], cache, embedder)
    assert embedded == 1 and embedder.calls == [["bb"]]
    assert cache["vectors"] == {text_key("a"): [9.0], text_key("bb"): [2.0]}


def test_a_repeated_text_is_embedded_once():
    embedder = FakeEmbedder()
    _, embedded = embed_new(["a", "a"], {"model": None, "vectors": {}}, embedder)
    assert embedded == 1 and embedder.calls == [["a"]]


def test_a_new_embedding_model_embeds_everything_again():
    cache = {"model": "old/model", "vectors": {text_key("a"): [9.0]}}
    cache, embedded = embed_new(["a"], cache, FakeEmbedder())
    assert embedded == 1 and cache == {"model": "embed/model", "vectors": {text_key("a"): [1.0]}}


def test_vectors_come_back_in_order_and_a_second_run_sends_nothing(tmp_path):
    embedder = FakeEmbedder()
    assert vectors_for("facts", ["ccc", "a"], embedder, tmp_path) == ([[3.0], [1.0]], 2)
    assert (tmp_path / "facts.json").exists()
    assert vectors_for("facts", ["a", "ccc"], embedder, tmp_path) == ([[1.0], [3.0]], 0)
    assert len(embedder.calls) == 1
