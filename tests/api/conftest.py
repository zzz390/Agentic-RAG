from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from src.main import app


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """异步测试后端（asyncio）。"""
    return "asyncio"


@pytest.fixture
async def client():
    """带服务 mock 的 HTTP 测试客户端。"""
    # main.py 已把工厂函数导入到模块命名空间，因此必须 patch 实际调用位置，
    # 确保 API 测试不会访问开发机上的 PostgreSQL/OpenSearch/Redis/Langfuse。
    with (
        patch("src.main.make_database") as mock_database_factory,
        patch("src.main.make_opensearch_client") as mock_os,
        patch("src.main.make_arxiv_client") as mock_arxiv,
        patch("src.main.make_pdf_parser_service") as mock_pdf,
        patch("src.main.make_embeddings_service") as mock_embeddings,
        patch("src.main.make_ollama_client") as mock_ollama,
        patch("src.main.make_langfuse_tracer") as mock_langfuse,
        patch("src.main.make_cache_client") as mock_cache,
        patch("src.repositories.paper.PaperRepository.get_by_arxiv_id") as mock_get_by_id,
    ):
        mock_database = MagicMock()
        mock_session = MagicMock()
        mock_database.get_session.return_value.__enter__.return_value = mock_session
        mock_database.get_session.return_value.__exit__.return_value = None
        mock_database_factory.return_value = mock_database

        # 默认 mock 仓储查询为未找到
        mock_get_by_id.return_value = None

        # 配置其余服务 mock 返回值
        mock_opensearch = MagicMock()
        mock_opensearch.health_check.return_value = True
        mock_opensearch.get_index_embedding_dimension.return_value = None
        mock_opensearch.setup_indices.return_value = {"hybrid_index": False}
        mock_opensearch.client.count.return_value = {"count": 0}
        mock_opensearch.search_unified.return_value = {"hits": [], "total": 0}
        mock_os.return_value = mock_opensearch
        mock_arxiv.return_value = AsyncMock()
        mock_pdf.return_value = AsyncMock()
        mock_embeddings.return_value = AsyncMock()
        mock_ollama.return_value = AsyncMock()
        mock_langfuse.return_value = None
        mock_cache.return_value = None

        async with LifespanManager(app) as manager:
            async with AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as client:
                yield client
