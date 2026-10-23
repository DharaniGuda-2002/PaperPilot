"""Text embedders. Production uses a local sentence-transformers model on CPU;
tests and CI can use a deterministic hashing embedder that needs no model files."""

import hashlib
import math
import re
from typing import Protocol

from app.documents.models import EMBEDDING_DIMENSIONS

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
# Pinned so the vectors are reproducible; changing it requires re-embedding.
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"


class Embedder(Protocol):
    model_id: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    def __init__(self, name: str = MODEL_NAME, revision: str = MODEL_REVISION) -> None:
        from sentence_transformers import SentenceTransformer  # heavy import, workers only

        self._model = SentenceTransformer(name, revision=revision, device="cpu")
        dimensions = self._model.get_sentence_embedding_dimension()
        if dimensions != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"{name} has {dimensions} dimensions; schema expects {EMBEDDING_DIMENSIONS}"
            )
        self.model_id = f"{name}@{revision[:12]}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, batch_size=32, normalize_embeddings=True)
        return [[float(x) for x in vector] for vector in vectors]


class HashingEmbedder:
    """Deterministic bag-of-words vectors (feature hashing). Captures word overlap
    only, not meaning. For tests and CI, never for real retrieval quality."""

    model_id = "hashing-bow-v1"
    _TOKEN = re.compile(r"[a-z0-9]+")

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIMENSIONS
        for token in self._TOKEN.findall(text.lower()):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
            vector[index] += 1.0 if digest[4] % 2 else -1.0
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]


def make_embedder(kind: str) -> Embedder:
    if kind == "hashing":
        return HashingEmbedder()
    return SentenceTransformerEmbedder()
