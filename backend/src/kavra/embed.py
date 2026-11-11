"""Sentence embeddings for duplicate detection, topic assignment and open-answer grading.

`minilm` = paraphrase-multilingual-MiniLM-L12-v2 (TR+EN, ~120 MB, CPU friendly).
`hash`   = dependency-free char n-gram hashing; used in tests/CI and as a fallback.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from typing import Protocol

import numpy as np

log = logging.getLogger("kavra.embed")


class Embedder(Protocol):
    name: str

    def encode(self, texts: list[str]) -> np.ndarray: ...


class HashEmbedder:
    name = "hash"

    def __init__(self, dim: int = 512):
        self.dim = dim

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            t = re.sub(r"\s+", " ", t.lower())
            grams = [t[j : j + 3] for j in range(max(1, len(t) - 2))] + t.split()
            for g in grams:
                h = int.from_bytes(hashlib.blake2b(g.encode(), digest_size=4).digest(), "little")
                out[i, h % self.dim] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.maximum(norms, 1e-9)


class MiniLMEmbedder:
    name = "minilm"

    def __init__(self, model: str):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model, device="cpu")

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 384), dtype=np.float32)
        v = self.model.encode(
            texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(v, dtype=np.float32)


_lock = threading.Lock()
_instance: Embedder | None = None


def get_embedder() -> Embedder:
    global _instance
    with _lock:
        if _instance is None:
            from kavra.config import get_settings

            s = get_settings()
            if s.embedder == "minilm":
                try:
                    _instance = MiniLMEmbedder(s.embed_model)
                except Exception as e:  # missing extra, offline, slow HF ...
                    log.warning("MiniLM unavailable (%s); using hash embedder", e)
                    _instance = HashEmbedder()
            else:
                _instance = HashEmbedder()
        return _instance


def set_embedder(e: Embedder | None) -> None:
    global _instance
    _instance = e


def to_blob(v: np.ndarray) -> bytes:
    return np.asarray(v, dtype=np.float32).tobytes()


def from_blob(b: bytes | None) -> np.ndarray | None:
    return None if b is None else np.frombuffer(b, dtype=np.float32)


def cosine_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if a.size == 0 or b.size == 0:
        return np.zeros((a.shape[0], b.shape[0] if b.ndim > 1 else 0), dtype=np.float32)
    return a @ b.T
