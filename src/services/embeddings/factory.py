from typing import Optional

from src.config import Settings, get_settings

from .bge_client import BGEEmbeddingsClient


def make_embeddings_service(settings: Optional[Settings] = None) -> BGEEmbeddingsClient:
    if settings is None:
        settings = get_settings()
    return BGEEmbeddingsClient(settings.embeddings)


def make_embeddings_client(settings: Optional[Settings] = None) -> BGEEmbeddingsClient:
    return make_embeddings_service(settings)
