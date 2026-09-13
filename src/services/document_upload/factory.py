from functools import lru_cache

from src.config import Settings, get_settings
from src.services.embeddings import EmbeddingsClient
from src.services.indexing.factory import make_hybrid_indexing_service_with_clients
from src.services.opensearch.client import OpenSearchClient

from .ingest import DocumentUploadIngestService
from .service import UploadDocumentService


@lru_cache(maxsize=1)
def make_upload_document_service() -> UploadDocumentService:
    settings = get_settings()
    from src.services.pdf_parser.factory import make_pdf_parser_service

    return UploadDocumentService(
        pdf_parser=make_pdf_parser_service(),
        upload_settings=settings.upload,
    )


def make_document_upload_ingest_service(
    opensearch_client: OpenSearchClient,
    embeddings_client: EmbeddingsClient,
    settings: Settings | None = None,
) -> DocumentUploadIngestService:
    if settings is None:
        settings = get_settings()

    return DocumentUploadIngestService(
        upload_parser=make_upload_document_service(),
        upload_settings=settings.upload,
        indexing_service=make_hybrid_indexing_service_with_clients(
            opensearch_client=opensearch_client,
            embeddings_client=embeddings_client,
            settings=settings,
        ),
    )
