"""Embeddings + a tiny in-memory vector index with an on-disk cache.

The KB is ~30 short articles, so a brute-force cosine search is instant and a
vector database would be pure overhead. Article vectors are cached by
(model, content hash): only new or edited articles are re-embedded.
"""

import hashlib
import json
import math
import re
from abc import ABC, abstractmethod
from pathlib import Path

import ollama

from assistant.kb import Article
from classifier.config import DATA_DIR

CACHE_FILE = DATA_DIR / "kb_embeddings_cache.json"

# Qwen3-Embedding expects an instruction on the query side only.
QUERY_INSTRUCTION = "Instruct: Given a customer support ticket, retrieve knowledge base articles that help answer it\nQuery: "


class Embedder(ABC):
    model: str

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]


class OllamaEmbedder(Embedder):
    def __init__(self, model: str = "qwen3-embedding", host: str = "http://localhost:11434",
                 query_instruction: str = QUERY_INSTRUCTION):
        self.model = model
        self.query_instruction = query_instruction
        self._client = ollama.Client(host=host)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(v) for v in self._client.embed(model=self.model, input=texts).embeddings]

    def embed_query(self, text: str) -> list[float]:
        return self.embed([self.query_instruction + text])[0]


class HashEmbedder(Embedder):
    """Deterministic bag-of-words embedder for tests (no model needed)."""

    model = "hash"

    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.dim
            for w in re.findall(r"\w+", t.lower()):
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % self.dim] += 1.0
            out.append(v)
        return out


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class VectorIndex:
    def __init__(self, articles: list[Article], embedder: Embedder, cache_file: Path | None = CACHE_FILE):
        self.articles = articles
        self.embedder = embedder
        self.vectors = self._load_or_embed(cache_file)

    def _load_or_embed(self, cache_file: Path | None) -> dict[str, list[float]]:
        cache = {}
        if cache_file and cache_file.exists():
            cache = json.loads(cache_file.read_text()).get(self.embedder.model, {})
        missing = [a for a in self.articles if a.content_hash not in cache]
        if missing:
            for a, vec in zip(missing, self.embedder.embed([a.text_for_embedding for a in missing])):
                cache[a.content_hash] = vec
            if cache_file:
                full = json.loads(cache_file.read_text()) if cache_file.exists() else {}
                live = {a.content_hash for a in self.articles}
                full[self.embedder.model] = {h: v for h, v in cache.items() if h in live}  # drop stale entries
                cache_file.write_text(json.dumps(full))
        self.newly_embedded = len(missing)
        return {a.id: cache[a.content_hash] for a in self.articles}

    def search(self, query: str, k: int = 3) -> list[tuple[Article, float]]:
        q = self.embedder.embed_query(query)
        scored = [(a, cosine(q, self.vectors[a.id])) for a in self.articles]
        return sorted(scored, key=lambda x: -x[1])[:k]
