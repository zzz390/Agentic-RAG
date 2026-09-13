import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, Mock

from src.main import app
from src.services.agents.agentic_rag import AgenticRAGService
from src import dependencies


@pytest.fixture
def mock_agentic_rag_service():
    """为 API 测试 mock AgenticRAGService。"""
    service = Mock(spec=AgenticRAGService)
    service.ask = AsyncMock(return_value={
        "query": "What is machine learning?",
        "answer": "Machine learning is a subset of AI that enables systems to learn from data.",
        "sources": ["https://arxiv.org/pdf/2301.00001.pdf"],
        "reasoning_steps": [
            "Validated query is about AI research",
            "Retrieved 3 relevant papers",
            "Generated answer from sources"
        ],
        "retrieval_attempts": 1,
        "rewritten_query": None,
    })
    return service


@pytest.fixture
def client(mock_agentic_rag_service):
    """带依赖注入覆盖的 FastAPI 测试客户端。"""
    # 覆盖依赖注入为 mock 服务
    def override_get_agentic_rag_service():
        return mock_agentic_rag_service

    def override_get_db_session():
        session = Mock()
        session.scalars.return_value = []
        yield session

    app.dependency_overrides[dependencies.get_agentic_rag_service] = override_get_agentic_rag_service
    app.dependency_overrides[dependencies.get_db_session] = override_get_db_session
    app.dependency_overrides[dependencies.get_cache_client] = lambda: None

    yield TestClient(app)

    # 测试结束后清理 dependency_overrides
    app.dependency_overrides.clear()


class TestAgenticAskEndpoint:
    """POST /api/v1/ask-agentic 接口测试。"""

    def test_ask_agentic_success(self, client, mock_agentic_rag_service):
        """Agentic 问答成功应返回完整字段。"""
        response = client.post(
            "/api/v1/ask-agentic",
            json={
                "query": "What is machine learning?",
                "model": "deepseek-r1:7b",
                "top_k": 3,
                "use_hybrid": True
            }
        )

        assert response.status_code == 200
        data = response.json()

        # 校验响应结构字段
        assert "query" in data
        assert "answer" in data
        assert "sources" in data
        assert "reasoning_steps" in data
        assert "retrieval_attempts" in data
        assert "chunks_used" in data
        assert "search_mode" in data

        # 校验响应内容
        assert data["query"] == "What is machine learning?"
        assert "machine learning" in data["answer"].lower()
        assert len(data["sources"]) > 0
        assert len(data["reasoning_steps"]) > 0
        assert data["retrieval_attempts"] == 1

    def test_ask_agentic_includes_contexts_only_for_evaluation(self, client, mock_agentic_rag_service):
        mock_agentic_rag_service.ask.return_value["retrieved_contexts"] = ["retrieved paper chunk"]

        hidden = client.post("/api/v1/ask-agentic", json={"query": "What is ML?"})
        included = client.post(
            "/api/v1/ask-agentic",
            json={"query": "What is ML?", "include_contexts": True, "enable_memory": False},
        )

        assert hidden.json()["retrieved_contexts"] == []
        assert included.json()["retrieved_contexts"] == ["retrieved paper chunk"]

    def test_ask_agentic_minimal_request(self, client, mock_agentic_rag_service):
        """仅传 query 时应成功。"""
        response = client.post(
            "/api/v1/ask-agentic",
            json={"query": "What is neural network?"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data

    def test_ask_agentic_empty_query(self, client, mock_agentic_rag_service):
        """空 query 应返回 422。"""
        mock_agentic_rag_service.ask = AsyncMock(side_effect=ValueError("Query cannot be empty"))

        response = client.post(
            "/api/v1/ask-agentic",
            json={"query": ""}
        )

        assert response.status_code == 422

    def test_ask_agentic_missing_query(self, client):
        """缺少 query 应返回 422。"""
        response = client.post(
            "/api/v1/ask-agentic",
            json={"model": "deepseek-r1:7b"}
        )

        assert response.status_code == 422

    def test_ask_agentic_service_error(self, client, mock_agentic_rag_service):
        """服务异常应返回 500。"""
        mock_agentic_rag_service.ask = AsyncMock(side_effect=Exception("Service error"))

        response = client.post(
            "/api/v1/ask-agentic",
            json={"query": "Test query"}
        )

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data

    def test_ask_agentic_with_sources(self, client, mock_agentic_rag_service):
        """响应应包含 sources 列表。"""
        mock_agentic_rag_service.ask = AsyncMock(return_value={
            "query": "What is transformer architecture?",
            "answer": "Transformers use self-attention mechanisms.",
            "sources": ["https://arxiv.org/pdf/1706.03762.pdf"],
            "reasoning_steps": ["Retrieved papers", "Generated answer"],
            "retrieval_attempts": 1,
            "rewritten_query": None,
        })

        response = client.post(
            "/api/v1/ask-agentic",
            json={"query": "What is transformer architecture?"}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["sources"]) == 1
        assert "1706.03762" in data["sources"][0]

    def test_ask_agentic_reasoning_steps(self, client, mock_agentic_rag_service):
        """响应应包含 reasoning_steps。"""
        mock_agentic_rag_service.ask = AsyncMock(return_value={
            "query": "What is deep learning?",
            "answer": "Deep learning is...",
            "sources": [],
            "reasoning_steps": [
                "Query validation passed",
                "Retrieved 3 papers",
                "Graded documents as relevant",
                "Generated final answer"
            ],
            "retrieval_attempts": 1,
            "rewritten_query": None,
        })

        response = client.post(
            "/api/v1/ask-agentic",
            json={"query": "What is deep learning?"}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["reasoning_steps"]) == 4
        assert "Query validation passed" in data["reasoning_steps"]

    def test_ask_agentic_with_rewritten_query(self, client, mock_agentic_rag_service):
        """查询被改写时应返回 rewritten_query。"""
        mock_agentic_rag_service.ask = AsyncMock(return_value={
            "query": "ML stuff",
            "answer": "Machine learning...",
            "sources": [],
            "reasoning_steps": ["Query rewritten", "Retrieved papers"],
            "retrieval_attempts": 2,
            "rewritten_query": "What are the key concepts in machine learning?",
        })

        response = client.post(
            "/api/v1/ask-agentic",
            json={"query": "ML stuff"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["rewritten_query"] == "What are the key concepts in machine learning?"
        assert data["retrieval_attempts"] == 2

    def test_ask_agentic_custom_model(self, client, mock_agentic_rag_service):
        """自定义 model 应传入 ask()。"""
        response = client.post(
            "/api/v1/ask-agentic",
            json={
                "query": "What is AI?",
                "model": "deepseek-r1:7b"
            }
        )

        assert response.status_code == 200
        # 确认 ask() 收到自定义 model
        mock_agentic_rag_service.ask.assert_called_once()
        call_kwargs = mock_agentic_rag_service.ask.call_args.kwargs
        assert call_kwargs["model"] == "deepseek-r1:7b"

    def test_ask_agentic_search_mode_hybrid(self, client, mock_agentic_rag_service):
        """use_hybrid=true 时 search_mode 应为 hybrid。"""
        response = client.post(
            "/api/v1/ask-agentic",
            json={
                "query": "What is AI?",
                "use_hybrid": True
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["search_mode"] == "hybrid"

    def test_ask_agentic_search_mode_bm25(self, client, mock_agentic_rag_service):
        """use_hybrid=false 时 search_mode 应为 bm25。"""
        response = client.post(
            "/api/v1/ask-agentic",
            json={
                "query": "What is AI?",
                "use_hybrid": False
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["search_mode"] == "bm25"
