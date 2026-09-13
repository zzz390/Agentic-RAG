import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from langchain_community.chat_models.openai import ChatOpenAI

from src.config import get_settings
from src.db.factory import make_database
from src.routers import agentic_ask, hybrid_search, papers, ping, upload
from src.routers.ask import ask_router, stream_router
from src.services.arxiv.factory import make_arxiv_client
from src.services.cache.factory import make_cache_client
from src.services.embeddings.factory import make_embeddings_service
from src.services.langfuse.factory import make_langfuse_tracer
from src.services.ollama.factory import make_ollama_client
from src.services.opensearch.factory import make_opensearch_client
from src.services.pdf_parser.factory import make_pdf_parser_service

logging.basicConfig(
    level=logging.INFO,
    #设置日志为最低输出级别为info，低于info的日志不会输出
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    #发生的时间+所属模块的名字+日志级别+具体内容
)
logger = logging.getLogger(__name__)
#会创建一个模块级别的日志器，命名由系统自动命名


@asynccontextmanager
#异步上下文管理器，启动时执行yield之前的代码，关闭时执行yield之后的代码
async def lifespan(app: FastAPI):
#lifespan用来管理应用启动和关闭生命周期的函数
    logger.info("Starting RAG API...")

    settings = get_settings()
    app.state.settings = settings

    database = make_database()
    app.state.database = database
    logger.info("Database connected")

    #初始化 OpenSearch 检索客户端
    opensearch_client = make_opensearch_client()
    app.state.opensearch_client = opensearch_client

    # 检查 OpenSearch 连通性并按需创建索引
    if opensearch_client.health_check():
        logger.info("OpenSearch connected successfully")

        existing_dimension = opensearch_client.get_index_embedding_dimension()
        expected_dimension = settings.opensearch.vector_dimension
        if existing_dimension is not None and existing_dimension != expected_dimension:
            logger.warning(
                "OpenSearch index %s has embedding dimension %s but config expects %s. "
                "Run: uv run python scripts/reindex_opensearch.py",
                opensearch_client.index_name,
                existing_dimension,
                expected_dimension,
            )

        # 创建/准备混合检索索引（支持 BM25 + 向量等多种检索模式）
        setup_results = opensearch_client.setup_indices(force=False)
        if setup_results.get("hybrid_index"):
            logger.info("Hybrid index created")
        else:
            logger.info("Hybrid index already exists")

        # 获取索引文档数量等简单统计
        try:
            stats = opensearch_client.client.count(index=opensearch_client.index_name)
            logger.info(f"OpenSearch ready: {stats['count']} documents indexed")
        except Exception:
            logger.info("OpenSearch index ready (stats unavailable)")
    else:
        logger.warning("OpenSearch connection failed - search features will be limited")

    # 初始化其余服务（供 API、Gradio 与 notebook 演示使用）
    app.state.arxiv_client = make_arxiv_client()
    app.state.pdf_parser = make_pdf_parser_service()
    app.state.embeddings_service = make_embeddings_service()
    app.state.ollama_client = make_ollama_client()
    app.state.langfuse_tracer = make_langfuse_tracer()
    app.state.cache_client = make_cache_client(settings)
    logger.info("Services initialized: arXiv API client, PDF parser, OpenSearch, Embeddings, LLM, Langfuse, Cache")

    logger.info("API ready")
    yield

    database.teardown()
    logger.info("API shutdown complete")


app = FastAPI(
    title="arXiv Paper Curator API",
    description="arXiv 与私有文档的生产级 RAG：混合检索、标准/智能体双模式问答",
    version=os.getenv("APP_VERSION", "0.1.0"),
    lifespan=lifespan,
)

#注册路由：健康检查、混合检索、问答/流式、智能体问答
#/api表示这是一个API接口，用来和前端、客户端交互的后端服务，/v1表示这是第一版接口
# prefix表示的是一个路径前缀，后面@router.get("/ping")路径就会自动变成/api/v1/ping
app.include_router(ping.router, prefix="/api/v1")  # 健康检查
app.include_router(hybrid_search.router, prefix="/api/v1")  # BM25/混合检索分块
app.include_router(ask_router, prefix="/api/v1")  # 标准 RAG 问答
app.include_router(stream_router, prefix="/api/v1")  # 流式 RAG
app.include_router(upload.router, prefix="/api/v1")  # 用户文档上传
app.include_router(papers.router, prefix="/api/v1")  # 全文浏览 / 文档元数据
app.include_router(agentic_ask.router)  # LangGraph 智能体 RAG


if __name__ == "__main__":
    uvicorn.run(app, port=8000, host="0.0.0.0")
