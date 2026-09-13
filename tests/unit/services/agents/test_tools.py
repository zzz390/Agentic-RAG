import pytest
from unittest.mock import AsyncMock
from langchain_core.documents import Document

from src.services.agents.tools import create_retriever_tool


@pytest.mark.asyncio
async def test_create_retriever_tool_basic(mock_opensearch_client, mock_embeddings_client):
    """检索工具应能创建并正常调用。"""
    tool = create_retriever_tool(
        opensearch_client=mock_opensearch_client,
        embeddings_client=mock_embeddings_client,
        top_k=2,
        use_hybrid=True,
    )

    # 校验工具名称与描述
    assert tool.name == "retrieve_papers"
    assert "arXiv" in tool.description

    # 调用工具
    result = await tool.ainvoke({"query": "machine learning"})

    # 校验返回文档列表
    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(doc, Document) for doc in result)

    # 校验首条文档内容与 metadata
    first_doc = result[0]
    assert first_doc.page_content == "Transformers are neural network architectures based on self-attention mechanisms."
    assert first_doc.metadata["arxiv_id"] == "1706.03762"
    assert first_doc.metadata["title"] == "Attention Is All You Need"
    assert first_doc.metadata["score"] == 0.95

    # 确认已生成查询向量
    mock_embeddings_client.embed_query.assert_called_once_with("machine learning")

    # 确认 search_unified 调用参数
    mock_opensearch_client.search_unified.assert_called_once()
    call_args = mock_opensearch_client.search_unified.call_args
    assert call_args.kwargs["query"] == "machine learning"
    assert call_args.kwargs["size"] == 2  # search_unified 使用 size
    assert call_args.kwargs["use_hybrid"] is True


@pytest.mark.asyncio
async def test_retriever_tool_empty_results(mock_opensearch_client, mock_embeddings_client):
    """无检索结果时应返回空列表。"""
    from unittest.mock import Mock
    mock_opensearch_client.search_unified = Mock(return_value={"hits": []})

    tool = create_retriever_tool(
        opensearch_client=mock_opensearch_client,
        embeddings_client=mock_embeddings_client,
    )

    result = await tool.ainvoke({"query": "nonexistent topic"})

    assert isinstance(result, list)
    assert len(result) == 0


@pytest.mark.asyncio
async def test_retriever_tool_custom_top_k(mock_opensearch_client, mock_embeddings_client):
    """自定义 top_k 应映射为 search_unified 的 size。"""
    tool = create_retriever_tool(
        opensearch_client=mock_opensearch_client,
        embeddings_client=mock_embeddings_client,
        top_k=5,
        use_hybrid=False,
    )

    await tool.ainvoke({"query": "test query"})

    call_args = mock_opensearch_client.search_unified.call_args
    # search_unified 使用 size 而非 top_k
    assert call_args.kwargs["size"] == 5
    assert call_args.kwargs["use_hybrid"] is False


@pytest.mark.asyncio
async def test_retriever_tool_embedding_fallback(mock_opensearch_client, mock_embeddings_client):
    """嵌入失败时 Agentic 检索应降级为 BM25（与标准 /ask 一致）。"""
    mock_embeddings_client.embed_query = AsyncMock(side_effect=RuntimeError("embedding unavailable"))

    tool = create_retriever_tool(
        opensearch_client=mock_opensearch_client,
        embeddings_client=mock_embeddings_client,
        top_k=2,
        use_hybrid=True,
    )

    result = await tool.ainvoke({"query": "machine learning"})

    assert len(result) == 2
    call_args = mock_opensearch_client.search_unified.call_args
    assert call_args.kwargs["use_hybrid"] is False
    assert result[0].metadata["search_mode"] == "bm25"


@pytest.mark.asyncio
async def test_retriever_tool_metadata_fields(mock_opensearch_client, mock_embeddings_client):
    """返回文档应包含全部预期 metadata 字段。"""
    from unittest.mock import Mock
    mock_opensearch_client.search_unified = Mock(return_value={
        "hits": [
            {
                "chunk_text": "Test content",
                "arxiv_id": "2301.00001",
                "title": "Test Paper",
                "authors": "Author One, Author Two",
                "score": 0.95,
                "section_name": "Introduction",
            }
        ]
    })

    tool = create_retriever_tool(
        opensearch_client=mock_opensearch_client,
        embeddings_client=mock_embeddings_client,
    )

    result = await tool.ainvoke({"query": "test"})

    doc = result[0]
    assert "arxiv_id" in doc.metadata
    assert "title" in doc.metadata
    assert "authors" in doc.metadata
    assert "score" in doc.metadata
    assert "source" in doc.metadata
    assert "section" in doc.metadata
