from functools import lru_cache
from typing import TYPE_CHECKING, Annotated, Generator

if TYPE_CHECKING:
    from fastapi import Depends, Request
    from sqlalchemy.orm import Session
else:
    try:
        from fastapi import Depends, Request
        from sqlalchemy.orm import Session
    except ImportError:
        pass

from src.config import Settings
from src.db.interfaces.base import BaseDatabase
from src.services.arxiv.client import ArxivClient
from src.services.cache.client import CacheClient
from src.services.embeddings import EmbeddingsClient
from src.services.langfuse.client import LangfuseTracer
from src.services.ollama.client import OllamaClient
from src.services.opensearch.client import OpenSearchClient
from src.services.pdf_parser.parser import PDFParserService
from src.services.agents.agentic_rag import AgenticRAGService
from src.services.agents.factory import make_agentic_rag_service
from src.services.document_upload.factory import make_document_upload_ingest_service
from src.services.document_upload.ingest import DocumentUploadIngestService


@lru_cache
#@lru_cache可以做一个缓存，第一次调用从头开始，第二次就可以从缓存拿出来用了
def get_settings() -> Settings:
    return Settings()

def get_request_settings(request: Request) -> Settings:
    return request.app.state.settings #app.state 是 FastAPI（底层 Starlette）提供的一个全局共享的命名空间对象，专门用来存放应用级别的单例资源
"""
应用启动 → lifespan() 里写入 app.state.xxx
每个请求 → 通过 request.app.state.xxx 读取
应用关闭 → lifespan() yield 之后执行清理

"""

def get_database(request: Request) -> BaseDatabase:
    return request.app.state.database

def get_db_session(database: Annotated[BaseDatabase, Depends(get_database)]) -> Generator[Session, None, None]:
    with database.get_session() as session:
        yield session

def get_opensearch_client(request: Request) -> OpenSearchClient:
    return request.app.state.opensearch_client


def get_arxiv_client(request: Request) -> ArxivClient:
    return request.app.state.arxiv_client


def get_pdf_parser(request: Request) -> PDFParserService:
    return request.app.state.pdf_parser


def get_embeddings_service(request: Request) -> EmbeddingsClient:
    return request.app.state.embeddings_service


def get_ollama_client(request: Request) -> OllamaClient:
    return request.app.state.ollama_client


def get_langfuse_tracer(request: Request) -> LangfuseTracer:
    return request.app.state.langfuse_tracer


def get_cache_client(request: Request) -> CacheClient | None:
    return getattr(request.app.state, "cache_client", None)


SettingsDep = Annotated[Settings, Depends(get_settings)]
DatabaseDep = Annotated[BaseDatabase, Depends(get_database)]
SessionDep = Annotated[Session, Depends(get_db_session)]
OpenSearchDep = Annotated[OpenSearchClient, Depends(get_opensearch_client)]
ArxivDep = Annotated[ArxivClient, Depends(get_arxiv_client)]
PDFParserDep = Annotated[PDFParserService, Depends(get_pdf_parser)]
EmbeddingsDep = Annotated[EmbeddingsClient, Depends(get_embeddings_service)]
OllamaDep = Annotated[OllamaClient, Depends(get_ollama_client)]
LangfuseDep = Annotated[LangfuseTracer, Depends(get_langfuse_tracer)]
CacheDep = Annotated[CacheClient | None, Depends(get_cache_client)]


def get_agentic_rag_service(
    opensearch: OpenSearchDep,
    ollama: OllamaDep,
    embeddings: EmbeddingsDep,
    langfuse: LangfuseDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgenticRAGService:
    return make_agentic_rag_service(
        opensearch_client=opensearch,
        ollama_client=ollama,
        embeddings_client=embeddings,
        langfuse_tracer=langfuse,
        use_hybrid=settings.use_hybrid_search,
    )


AgenticRAGDep = Annotated[AgenticRAGService, Depends(get_agentic_rag_service)]


def get_upload_ingest_service(
    request: Request,
    opensearch: OpenSearchDep,
    embeddings: EmbeddingsDep,
    settings: Annotated[Settings, Depends(get_request_settings)],
) -> DocumentUploadIngestService:
    return make_document_upload_ingest_service(
        opensearch_client=opensearch,
        embeddings_client=embeddings,
        settings=settings,
    )


UploadIngestDep = Annotated[DocumentUploadIngestService, Depends(get_upload_ingest_service)]
