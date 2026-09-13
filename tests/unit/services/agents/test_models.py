import pytest
from pydantic import ValidationError

from src.services.agents.models import (
    GuardrailScoring,
    GradeDocuments,
    SourceItem,
    ToolArtefact,
    RoutingDecision,
    GradingResult,
    ReasoningStep,
)


class TestGuardrailScoring:
    """GuardrailScoring 模型相关测试。"""

    def test_valid_scoring(self):
        """应能创建合法的护栏打分对象。"""
        scoring = GuardrailScoring(score=75, reason="Query is relevant to AI research papers")
        assert scoring.score == 75
        assert scoring.reason == "Query is relevant to AI research papers"

    def test_score_boundaries(self):
        """分数边界校验。"""
        # 合法边界 0/50/100
        GuardrailScoring(score=0, reason="Minimum score")
        GuardrailScoring(score=100, reason="Maximum score")
        GuardrailScoring(score=50, reason="Middle score")

    def test_invalid_score_too_low(self):
        """低于最小分应校验失败。"""
        with pytest.raises(ValidationError):
            GuardrailScoring(score=-1, reason="Invalid")

    def test_invalid_score_too_high(self):
        """高于最大分应校验失败。"""
        with pytest.raises(ValidationError):
            GuardrailScoring(score=101, reason="Invalid")


class TestGradeDocuments:
    """GradeDocuments 模型相关测试。"""

    def test_valid_yes_grade(self):
        """应能创建 binary_score=yes 的打分。"""
        grade = GradeDocuments(binary_score="yes", reasoning="Document is highly relevant")
        assert grade.binary_score == "yes"
        assert grade.reasoning == "Document is highly relevant"

    def test_valid_no_grade(self):
        """应能创建 binary_score=no 的打分。"""
        grade = GradeDocuments(binary_score="no", reasoning="Document is off-topic")
        assert grade.binary_score == "no"
        assert grade.reasoning == "Document is off-topic"

    def test_default_reasoning(self):
        """reasoning 默认应为空字符串。"""
        grade = GradeDocuments(binary_score="yes")
        assert grade.reasoning == ""

    def test_invalid_binary_score(self):
        """非法 binary_score 应校验失败。"""
        with pytest.raises(ValidationError):
            GradeDocuments(binary_score="maybe")


class TestSourceItem:
    """SourceItem 模型相关测试。"""

    def test_valid_source_item(self):
        """应能创建合法来源项。"""
        source = SourceItem(
            arxiv_id="1706.03762",
            title="Attention Is All You Need",
            authors=["Vaswani, A.", "Shazeer, N."],
            url="https://arxiv.org/abs/1706.03762",
            relevance_score=0.95
        )
        assert source.arxiv_id == "1706.03762"
        assert source.title == "Attention Is All You Need"
        assert len(source.authors) == 2
        assert source.url == "https://arxiv.org/abs/1706.03762"
        assert source.relevance_score == 0.95

    def test_default_values(self):
        """字段默认值应符合预期。"""
        source = SourceItem(
            arxiv_id="1234.5678",
            title="Test Paper",
            url="https://arxiv.org/abs/1234.5678"
        )
        assert source.authors == []
        assert source.relevance_score == 0.0

    def test_to_dict_conversion(self):
        """to_dict() 应返回完整字典。"""
        source = SourceItem(
            arxiv_id="1706.03762",
            title="Attention Is All You Need",
            authors=["Vaswani, A."],
            url="https://arxiv.org/abs/1706.03762",
            relevance_score=0.95
        )
        source_dict = source.to_dict()

        assert isinstance(source_dict, dict)
        assert source_dict["arxiv_id"] == "1706.03762"
        assert source_dict["title"] == "Attention Is All You Need"
        assert source_dict["authors"] == ["Vaswani, A."]
        assert source_dict["url"] == "https://arxiv.org/abs/1706.03762"
        assert source_dict["relevance_score"] == 0.95


class TestToolArtefact:
    """ToolArtefact 模型相关测试。"""

    def test_valid_tool_artefact(self):
        """应能创建合法工具产物对象。"""
        artefact = ToolArtefact(
            tool_name="retrieve_papers",
            tool_call_id="call_123",
            content="Retrieved 3 papers",
            metadata={"count": 3, "source": "opensearch"}
        )
        assert artefact.tool_name == "retrieve_papers"
        assert artefact.tool_call_id == "call_123"
        assert artefact.content == "Retrieved 3 papers"
        assert artefact.metadata["count"] == 3

    def test_default_metadata(self):
        """metadata 默认应为空字典。"""
        artefact = ToolArtefact(
            tool_name="test_tool",
            tool_call_id="call_456",
            content="Test content"
        )
        assert artefact.metadata == {}


class TestRoutingDecision:
    """RoutingDecision 模型相关测试。"""

    def test_valid_routing_decisions(self):
        """所有合法路由枚举应可通过校验。"""
        routes = ["retrieve", "out_of_scope", "generate_answer", "rewrite_query"]

        for route in routes:
            decision = RoutingDecision(route=route, reason=f"Testing {route}")
            assert decision.route == route
            assert decision.reason == f"Testing {route}"

    def test_default_reason(self):
        """reason 默认应为空字符串。"""
        decision = RoutingDecision(route="retrieve")
        assert decision.reason == ""

    def test_invalid_route(self):
        """非法 route 应校验失败。"""
        with pytest.raises(ValidationError):
            RoutingDecision(route="invalid_route")


class TestGradingResult:
    """GradingResult 模型相关测试。"""

    def test_valid_grading_result(self):
        """应能创建合法打分结果。"""
        result = GradingResult(
            document_id="doc_123",
            is_relevant=True,
            score=0.87,
            reasoning="Contains relevant information about transformers"
        )
        assert result.document_id == "doc_123"
        assert result.is_relevant is True
        assert result.score == 0.87
        assert "transformers" in result.reasoning

    def test_default_values(self):
        """字段默认值应符合预期。"""
        result = GradingResult(
            document_id="doc_456",
            is_relevant=False
        )
        assert result.score == 0.0
        assert result.reasoning == ""


class TestReasoningStep:
    """ReasoningStep 模型相关测试。"""

    def test_valid_reasoning_step(self):
        """应能创建合法推理步骤。"""
        step = ReasoningStep(
            step_name="retrieve",
            description="Retrieved 3 relevant papers from OpenSearch",
            metadata={"num_docs": 3, "retrieval_time_ms": 150}
        )
        assert step.step_name == "retrieve"
        assert step.description == "Retrieved 3 relevant papers from OpenSearch"
        assert step.metadata["num_docs"] == 3
        assert step.metadata["retrieval_time_ms"] == 150

    def test_default_metadata(self):
        """metadata 默认应为空字典。"""
        step = ReasoningStep(
            step_name="generate",
            description="Generated final answer"
        )
        assert step.metadata == {}
