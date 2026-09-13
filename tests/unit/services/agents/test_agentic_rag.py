"""AgenticRAGService 单元测试（LangGraph 2.0 Runtime）。"""

import pytest
from unittest.mock import AsyncMock, Mock
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.services.agents.agentic_rag import AgenticRAGService
from src.services.agents.config import GraphConfig
from src.services.agents.models import GuardrailScoring


@pytest.fixture
def test_service(mock_opensearch_client, mock_ollama_client, mock_embeddings_client):
    """创建带 mock 依赖的 AgenticRAGService。"""
    config = GraphConfig(
        model="deepseek-r1:7b",
        temperature=0.0,
        top_k=3,
        use_hybrid=True,
        max_retrieval_attempts=2,
        guardrail_threshold=60,
    )
    return AgenticRAGService(
        opensearch_client=mock_opensearch_client,
        ollama_client=mock_ollama_client,
        embeddings_client=mock_embeddings_client,
        langfuse_tracer=None,
        graph_config=config,
    )


class TestAgenticRAGServiceInitialization:
    """服务初始化相关测试。"""

    def test_service_initialization(self, test_service):
        """服务应能正确初始化。"""
        assert test_service.opensearch is not None
        assert test_service.ollama is not None
        assert test_service.embeddings is not None
        assert test_service.graph is not None
        assert test_service.graph_config is not None

    def test_graph_config_values(self, test_service):
        """图配置项取值应符合预期。"""
        assert test_service.graph_config.model == "deepseek-r1:7b"
        assert test_service.graph_config.top_k == 3
        assert test_service.graph_config.use_hybrid is True
        assert test_service.graph_config.max_retrieval_attempts == 2
        assert test_service.graph_config.guardrail_threshold == 60


class TestAgenticRAGAskMethod:
    """ask() 方法相关测试。"""

    @pytest.mark.asyncio
    async def test_ask_empty_query_validation(self, test_service):
        """空查询应抛出 ValueError。"""
        with pytest.raises(ValueError, match="Query cannot be empty"):
            await test_service.ask(query="")

        with pytest.raises(ValueError, match="Query cannot be empty"):
            await test_service.ask(query="   ")

    @pytest.mark.asyncio
    async def test_ask_with_model_override(self, test_service):
        """ask() 应支持 model 参数覆盖。"""
        mock_final_state = {
            "messages": [
                HumanMessage(content="Test query"),
                AIMessage(content="Test answer"),
            ],
            "retrieval_attempts": 0,
            "guardrail_result": GuardrailScoring(score=85, reason="Relevant"),
            "sources": [],
            "relevant_sources": [],
            "grading_results": [],
            "metadata": {},
            "original_query": "Test query",
            "rewritten_query": None,
            "routing_decision": "generate_answer",
            "relevant_tool_artefacts": None,
        }

        test_service.graph.ainvoke = AsyncMock(return_value=mock_final_state)

        result = await test_service.ask(query="Test query", model="deepseek-r1:7b")

        assert result is not None
        # 确认已调用图执行
        test_service.graph.ainvoke.assert_called_once()


class TestAgenticRAGGraphVisualization:
    """图可视化相关测试。"""

    def test_get_graph_mermaid(self, test_service):
        """应能生成 Mermaid 图。"""
        mermaid = test_service.get_graph_mermaid()

        assert isinstance(mermaid, str)
        assert len(mermaid) > 0
        assert "graph" in mermaid.lower() or "flowchart" in mermaid.lower()


class TestAgenticRAGErrorHandling:
    """错误处理相关测试。"""

    @pytest.mark.asyncio
    async def test_ask_with_graph_execution_error(self, test_service):
        """图执行失败时应正确抛错。"""
        # mock 图执行抛异常
        test_service.graph.ainvoke = AsyncMock(side_effect=Exception("Graph execution failed"))

        with pytest.raises(Exception, match="Graph execution failed"):
            await test_service.ask(query="Test query")
