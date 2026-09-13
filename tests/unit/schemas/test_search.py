import pytest
from pydantic import ValidationError
from src.schemas.api.search import SearchHit, SearchRequest, SearchResponse


def test_search_request_valid():
    """应能创建合法的 SearchRequest。"""
    request = SearchRequest(query="neural networks", size=10, latest_papers=True, categories=["cs.AI", "cs.LG"])

    assert request.query == "neural networks"
    assert request.size == 10
    assert request.from_ == 0  # 默认值
    assert request.latest_papers is True
    assert request.categories == ["cs.AI", "cs.LG"]


def test_search_request_defaults():
    """SearchRequest 默认值应符合预期。"""
    request = SearchRequest(query="test query")

    assert request.query == "test query"
    assert request.size == 10
    assert request.from_ == 0
    assert request.latest_papers is False
    assert request.categories is None


def test_search_request_validation_errors():
    """SearchRequest 非法输入应触发校验错误。"""

    # 空 query 应校验失败
    with pytest.raises(ValidationError):
        SearchRequest(query="")

    # 过长 query 应校验失败
    with pytest.raises(ValidationError):
        SearchRequest(query="a" * 501)

    # 非法 size 应校验失败
    with pytest.raises(ValidationError):
        SearchRequest(query="test", size=0)

    with pytest.raises(ValidationError):
        SearchRequest(query="test", size=51)

    # 负数 from_ 会被约束为 0
    request = SearchRequest(query="test", from_=-1)
    assert request.from_ == 0  # Pydantic 将负数约束为最小值 0


def test_search_hit_creation():
    """应能创建 SearchHit。"""
    hit = SearchHit(
        arxiv_id="2024.12345v1",
        title="Test Paper",
        authors="John Doe, Jane Smith",
        abstract="This is a test paper about machine learning.",
        published_date="2024-01-01T00:00:00Z",
        pdf_url="https://arxiv.org/pdf/2024.12345v1.pdf",
        score=1.5,
        highlights={"title": ["<mark>Test</mark> Paper"]},
    )

    assert hit.arxiv_id == "2024.12345v1"
    assert hit.title == "Test Paper"
    assert hit.score == 1.5
    assert hit.highlights == {"title": ["<mark>Test</mark> Paper"]}


def test_search_response_creation():
    """应能创建 SearchResponse。"""
    hits = [
        SearchHit(
            arxiv_id="2024.12345v1",
            title="Test Paper",
            authors="John Doe",
            abstract="Test abstract",
            published_date="2024-01-01",
            pdf_url="https://test.pdf",
            score=1.0,
        )
    ]

    response = SearchResponse(query="test query", total=1, hits=hits, size=10, **{"from": 0})

    assert response.query == "test query"
    assert response.total == 1
    assert len(response.hits) == 1
    assert response.error is None
