"""本地 BGE 向量客户端（基于 sentence-transformers）。"""

import asyncio
import logging
from functools import lru_cache
from pathlib import Path
from typing import List

from sentence_transformers import SentenceTransformer

from src.config import EmbeddingsSettings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_model(model_path: str, device: str) -> SentenceTransformer:
    path = Path(model_path)
    source = str(path) if path.exists() else model_path
    logger.info("Loading BGE model from %s on device=%s", source, device)
    model = SentenceTransformer(source, device=device)
    logger.info("BGE model ready (dimension=%s)", model.get_sentence_embedding_dimension())
    return model


class BGEEmbeddingsClient:
    def __init__(self, settings: EmbeddingsSettings):
        self.settings = settings
        self.model_name = settings.model_name
        self.model_path = settings.resolved_model_path()
        self.device = settings.device
        self.batch_size = settings.batch_size
        self.query_instruction = settings.query_instruction
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = _load_model(self.model_path, self.device)
        return self._model

    @property
    def vector_dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()

    def _encode_sync(self, texts: List[str], *, is_query: bool) -> List[List[float]]:
        if is_query and self.query_instruction:
            texts = [f"{self.query_instruction}{text}" for text in texts]

        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]

    async def embed_passages(self, texts: List[str], batch_size: int | None = None) -> List[List[float]]:
        if not texts:
            return []

        effective_batch = batch_size or self.batch_size
        embeddings: List[List[float]] = []

        for i in range(0, len(texts), effective_batch):
            batch = texts[i : i + effective_batch]
            batch_embeddings = await asyncio.to_thread(self._encode_sync, batch, is_query=False)
            embeddings.extend(batch_embeddings)

        logger.info("Embedded %s passages with BGE", len(texts))
        return embeddings

    async def embed_query(self, query: str) -> List[float]:
        vectors = await asyncio.to_thread(self._encode_sync, [query], is_query=True)
        return vectors[0]
