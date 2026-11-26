"""Embedding vectors cached per kind of text, so only new or changed text is ever sent.

One file per kind (passages, evidence, summaries) in processed_data/retrieval/embeddings/, holding
the model's name and a vector per text, keyed by a hash of the text. A changed model embeds
everything again; a text no longer used is dropped from the cache.
"""

import hashlib
import json

from src.source_data_collection.storage import read_json
from src.source_data_collection.tier_titles import PROJECT_ROOT

EMBEDDINGS_DIR = PROJECT_ROOT / "processed_data" / "retrieval" / "embeddings"


def text_key(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def embed_new(texts, cache, embedder):
    """(cache with a vector for exactly these texts, how many were embedded now)."""
    vectors = cache["vectors"] if cache.get("model") == embedder.embedding_model else {}
    keys = [text_key(t) for t in texts]
    new = list(dict.fromkeys(k for k in keys if k not in vectors))
    if new:
        by_key = dict(zip(keys, texts))
        vectors = {**vectors, **dict(zip(new, embedder.embed([by_key[k] for k in new])))}
    return {"model": embedder.embedding_model, "vectors": {k: vectors[k] for k in keys}}, len(new)


def vectors_for(kind, texts, embedder, cache_dir=EMBEDDINGS_DIR):
    """([a vector per text, in order], how many were embedded now), through kind's cache."""
    path = cache_dir / f"{kind}.json"
    cache = read_json(path) if path.exists() else {"model": None, "vectors": {}}
    updated, embedded = embed_new(texts, cache, embedder)
    if updated != cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(updated), encoding="utf-8")      # compact: 1,536 floats per text
    return [updated["vectors"][text_key(t)] for t in texts], embedded
