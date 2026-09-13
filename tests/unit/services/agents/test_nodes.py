"""Agentic RAG 图节点单元测试（Runtime[Context] 模式）。"""

import pytest
from unittest.mock import AsyncMock, Mock
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from src.services.agents.nodes import (
    ainvoke_retrieve_step,
    ainvoke_grade_documents_step,
    ainvoke_rewrite_query_step,
    ainvoke_generate_answer_step,
    ainvoke_out_of_scope_step,
    continue_after_guardrail,
)
from src.services.agents.nodes.utils import get_latest_query, get_latest_context
from src.services.agents.models import GuardrailScoring, GradeDocuments
from src.services.agents.state import AgentState


class TestGuardrailNode:
    """问题范围校验节点相关测试。"""

    def test_continue_after_guardrail_pass(self, test_context):
        """校验通过时应路由到 continue。"""
        state: AgentState = {
            "messages": [],
            "retrieval_attempts": 0,
            "guardrail_result": GuardrailScoring(score=75, reason="Pass"),
        }
        runtime = Mock(spec=Runtime)
        runtime.context = test_context

        result = continue_after_guardrail(state, runtime)

        assert result == "continue"

    def test_continue_after_guardrail_fail(self, test_context):
        """校验未通过时应路由到 out_of_scope。"""
        state: AgentState = {
            "messages": [],
            "retrieval_attempts": 0,
            "guardrail_result": GuardrailScoring(score=30, reason="Fail"),
        }
        runtime = Mock(spec=Runtime)
        runtime.context = test_context

        result = continue_after_guardrail(state, runtime)

        assert result == "out_of_scope"


class TestRetrieveNode:
    """文档检索节点相关测试。"""

    @pytest.mark.asyncio
    async def test_retrieve_creates_tool_call(self, test_context, sample_human_message):
        """检索节点应创建 retrieve_papers 工具调用。"""
        state: AgentState = {
            "messages": [sample_human_message],
            "retrieval_attempts": 0,
        }
        runtime = Mock(spec=Runtime)
        runtime.context = test_context

        result = await ainvoke_retrieve_step(state, runtime)

        assert "retrieval_attempts" in result
        assert result["retrieval_attempts"] == 1
        assert "messages" in result
        assert isinstance(result["messages"][0], AIMessage)
        assert len(result["messages"][0].tool_calls) > 0
        assert result["messages"][0].tool_calls[0]["name"] == "retrieve_papers"

    @pytest.mark.asyncio
    async def test_retrieve_max_attempts_reached(self, test_context, sample_human_message):
        """达到最大检索次数时应返回未找到提示。"""
        state: AgentState = {
            "messages": [sample_human_message],
            "retrieval_attempts": 2,  # 已达上限
        }
        runtime = Mock(spec=Runtime)
        runtime.context = test_context

        result = await ainvoke_retrieve_step(state, runtime)

        assert "messages" in result
        assert isinstance(result["messages"][0], AIMessage)
        # 消息应提示未找到论文
        content_lower = result["messages"][0].content.lower()
        assert (
            "apologize" in content_lower
            or "unable" in content_lower
            or "couldn't find" in content_lower
            or "抱歉" in result["messages"][0].content
        )


class TestGradeDocumentsNode:
    """文档相关性打分节点相关测试。"""

    @pytest.mark.asyncio
    async def test_grade_documents_relevant(self, test_context, sample_human_message, sample_tool_message):
        """相关文档打分应写入 grading_results。"""
        mock_llm = Mock()
        mock_llm.ainvoke = AsyncMock(return_value=GradeDocuments(
            binary_score="yes",
            reasoning="Document discusses transformers which is relevant"
        ))
        test_context.ollama_client.create_llm = Mock(return_value=mock_llm)

        state: AgentState = {
            "messages": [sample_human_message, sample_tool_message],
            "retrieval_attempts": 1,
        }
        runtime = Mock(spec=Runtime)
        runtime.context = test_context

        result = await ainvoke_grade_documents_step(state, runtime)

        assert "grading_results" in result

    @pytest.mark.asyncio
    async def test_grade_documents_not_relevant(self, test_context, sample_human_message, sample_tool_message):
        """不相关文档打分应写入 grading_results。"""
        mock_llm = Mock()
        mock_llm.ainvoke = AsyncMock(return_value=GradeDocuments(
            binary_score="no",
            reasoning="Document is not relevant to the query"
        ))
        test_context.ollama_client.create_llm = Mock(return_value=mock_llm)

        state: AgentState = {
            "messages": [sample_human_message, sample_tool_message],
            "retrieval_attempts": 1,
        }
        runtime = Mock(spec=Runtime)
        runtime.context = test_context

        result = await ainvoke_grade_documents_step(state, runtime)

        assert "grading_results" in result


class TestRewriteQueryNode:
    """查询改写节点相关测试。"""

    @pytest.mark.asyncio
    async def test_rewrite_query_success(self, test_context, sample_human_message):
        """应通过 LLM 改写查询并写入 rewritten_query。"""
        mock_llm = Mock()
        mock_llm.ainvoke = AsyncMock(return_value=Mock(
            content="What are the key concepts in transformer neural network architectures?"
        ))
        test_context.ollama_client.create_llm = Mock(return_value=mock_llm)

        state: AgentState = {
            "messages": [sample_human_message],
            "retrieval_attempts": 1,
        }
        runtime = Mock(spec=Runtime)
        runtime.context = test_context

        result = await ainvoke_rewrite_query_step(state, runtime)

        assert "messages" in result
        assert isinstance(result["messages"][0], HumanMessage)
        assert len(result["messages"][0].content) > 0
        assert "rewritten_query" in result


class TestGenerateAnswerNode:
    """答案生成节点相关测试。"""

    @pytest.mark.asyncio
    async def test_generate_answer_success(self, test_context, sample_human_message, sample_tool_message):
        """有检索上下文时应生成 AIMessage 答案。"""
        mock_llm = Mock()
        mock_llm.ainvoke = AsyncMock(return_value=Mock(
            content="Based on the papers, transformers are neural network architectures."
        ))
        test_context.ollama_client.create_llm = Mock(return_value=mock_llm)

        state: AgentState = {
            "messages": [sample_human_message, sample_tool_message],
            "retrieval_attempts": 1,
        }
        runtime = Mock(spec=Runtime)
        runtime.context = test_context

        result = await ainvoke_generate_answer_step(state, runtime)

        assert "messages" in result
        assert isinstance(result["messages"][0], AIMessage)
        assert len(result["messages"][0].content) > 0
        assert result["retrieved_contexts"] == [sample_tool_message.content]


class TestOutOfScopeNode:
    """超范围问题处理节点相关测试。"""

    @pytest.mark.asyncio
    async def test_out_of_scope_response(self, test_context, sample_human_message):
        """超范围问题应返回友好拒答。"""
        mock_llm = Mock()
        mock_llm.ainvoke = AsyncMock(return_value=Mock(
            content="I'm designed to help with AI research papers."
        ))
        test_context.ollama_client.create_llm = Mock(return_value=mock_llm)

        state: AgentState = {
            "messages": [sample_human_message],
            "retrieval_attempts": 0,
        }
        runtime = Mock(spec=Runtime)
        runtime.context = test_context

        result = await ainvoke_out_of_scope_step(state, runtime)

        assert "messages" in result
        assert isinstance(result["messages"][0], AIMessage)


class TestNodeUtils:
    """节点工具函数相关测试。"""

    def test_get_latest_query(self, sample_human_message, sample_ai_message):
        """应从消息列表提取最新用户问题。"""
        messages = [sample_human_message, sample_ai_message]
        query = get_latest_query(messages)

        assert query == "What is machine learning?"

    def test_get_latest_query_with_multiple_human_messages(self):
        """多条 HumanMessage 时应取最后一条。"""
        messages = [
            HumanMessage(content="First query"),
            AIMessage(content="First response"),
            HumanMessage(content="Second query"),
        ]
        query = get_latest_query(messages)

        assert query == "Second query"

    def test_get_latest_context(self, sample_tool_message):
        """应能从 ToolMessage 提取检索上下文。"""
        messages = [HumanMessage(content="Query"), sample_tool_message]
        context = get_latest_context(messages)

        assert context is not None
        assert "Transformers" in context

    def test_get_latest_context_no_tool_messages(self, sample_human_message):
        """无 ToolMessage 时上下文应为空字符串。"""
        messages = [sample_human_message]
        context = get_latest_context(messages)

        assert context == ""
