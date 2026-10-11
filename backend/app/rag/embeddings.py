"""Embeddings and meaning search (RAG stage 66).

BM25 (stage 65) matches WORDS. It can't see that "container orchestration" means
"Kubernetes", or that "jobs" is "job". Embeddings fix that:

1. An EMBEDDING model turns a text into a list of numbers (a vector; nomic-embed-text
   gives 768 of them). It's trained so texts with similar MEANING get vectors that point
   in similar directions, even with no words in common.

2. COSINE SIMILARITY measures how close two vectors point: the cosine of the angle
   between them.
       cos(a, b) = (a · b) / (|a| * |b|)       a · b = sum of a[i] * b[i]
   1.0 = same direction (same meaning), 0 = unrelated, -1 = opposite. It ignores length,
   so a long note and a short question can still match.

3. Meaning search = embed every note once, embed the question, return the notes with the
   highest cosine. This is what a "vector database" (like pgvector) does at scale; at our
   size (dozens of notes) a plain Python loop is instant.

The model runs locally in Ollama (free, nothing leaves the computer). nomic-embed-text
expects a task prefix: "search_document: " for the notes and "search_query: " for the
question, so the two sides are embedded "for retrieval" in a matched way.

Embedding is the slow part, so vectors are CACHED by (model, text): a note is only
re-embedded when its text changes. The cache is in memory (it empties when the backend
restarts); storing vectors in PostgreSQL with pgvector would be the production step.
"""

import hashlib
import math
import threading
from collections import OrderedDict
from typing import Protocol

import httpx

from app.rag.warmup import keep_alive

DEFAULT_MODEL = "nomic-embed-text"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"
TIMEOUT_SECONDS = 60.0
DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
CACHE_SIZE = 5000


class EmbeddingUnavailableError(Exception):
    """The embedding model couldn't be used (Ollama not running, model not pulled...)."""


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class OllamaEmbedder:
    """Calls a local Ollama embedding model. One HTTP call per batch of texts."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx.BaseTransport | None = None,  # tests only
    ) -> None:
        self.name = model
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            with httpx.Client(transport=self._transport, timeout=TIMEOUT_SECONDS) as client:
                response = client.post(f"{self._base_url}/api/embed", json={"model": self.name, "input": texts, "keep_alive": keep_alive()})
        except httpx.HTTPError as error:
            raise EmbeddingUnavailableError(f"Ollama isn't reachable ({type(error).__name__}).") from error
        if response.status_code != 200:
            raise EmbeddingUnavailableError(
                f"Ollama answered {response.status_code}. Is the model pulled? Run: ollama pull {self.name}"
            )
        try:
            vectors = response.json()["embeddings"]
        except (ValueError, KeyError, TypeError) as error:
            raise EmbeddingUnavailableError("Ollama's answer wasn't in the expected format.") from error
        if len(vectors) != len(texts):
            raise EmbeddingUnavailableError("Ollama returned the wrong number of embeddings.")
        return vectors


class CachedEmbedder:
    """Wraps an embedder: each distinct text is embedded once (least-recently-used cache)."""

    def __init__(self, inner: Embedder, size: int = CACHE_SIZE) -> None:
        self.inner = inner
        self.name = inner.name
        self._size = size
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self.calls = 0  # texts actually sent to the model (for tests and curiosity)
        # The startup warm-up fills the cache from a background thread while requests may
        # read it, so one embed() at a time.
        self._lock = threading.Lock()

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.name}\n{text}".encode()).hexdigest()

    def embed(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            return self._embed(texts)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        keys = [self._key(t) for t in texts]
        todo = [(k, t) for k, t in dict(zip(keys, texts)).items() if k not in self._cache]
        if todo:
            vectors = self.inner.embed([t for _, t in todo])
            self.calls += len(todo)
            for (key, _), vector in zip(todo, vectors):
                self._cache[key] = vector
        out = []
        for key in keys:
            self._cache.move_to_end(key)
            out.append(self._cache[key])
        while len(self._cache) > self._size:
            self._cache.popitem(last=False)
        return out


class VectorIndex:
    """Meaning search over a list of texts: embed them, then rank by cosine to the query."""

    def __init__(self, texts: list[str], embedder: Embedder) -> None:
        self.embedder = embedder
        self.vectors = embedder.embed([DOC_PREFIX + t for t in texts])

    def search(self, query: str, top_k: int = 5) -> list[tuple[int, float]]:
        """(index, cosine) of the best `top_k` texts, best first."""
        [query_vector] = self.embedder.embed([QUERY_PREFIX + query])
        scored = [(i, cosine(query_vector, v)) for i, v in enumerate(self.vectors)]
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:top_k]


# --- hybrid: Reciprocal Rank Fusion ------------------------------------------------------------

RRF_K = 60  # the constant from the original RRF paper (Cormack et al., 2009)


def reciprocal_rank_fusion(rankings: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Merge several best-first rankings of chunk indexes into one.

    Each ranking gives a chunk 1 / (k + rank) points (rank 1 = best); points are added up.
    Why ranks and not raw scores: BM25 scores (0..~20) and cosines (-1..1) are on
    different scales, but "1st place" means the same in both. k = 60 keeps one list's
    1st place from overpowering everything: 1/61 vs 1/62 is a small step, so a chunk that
    is decent in BOTH lists beats one that's great in only one.
    """
    points: dict[int, float] = {}
    for ranking in rankings:
        for rank, index in enumerate(ranking, start=1):
            points[index] = points.get(index, 0.0) + 1 / (k + rank)
    return sorted(points.items(), key=lambda item: (-item[1], item[0]))
