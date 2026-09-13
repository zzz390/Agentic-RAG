"""Agentic RAG 单元测试共享 fixture。"""

from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


DEFAULT_SEARCH_HITS = [
    {
        "chunk_text": "Transformers are neural network architectures based on self-attention mechanisms.",
        "arxiv_id": "1706.03762",
        "title": "Attention Is All You Need",
        "authors": "Vaswani et al.",
        "score": 0.95,
        "section_name": "Introduction",
    },
    {
        "chunk_text": "BERT uses bidirectional transformers for language understanding.",
        "arxiv_id": "1810.04805",
        "title": "BERT: Pre-training of Deep Bidirectional Transformers",
        "authors": "Devlin et al.",
        "score": 0.88,
        "section_name": "Abstract",
    },
]


@pytest.fixture
def mock_opensearch_client():
    client = Mock()
    client.search_unified = Mock(return_value={"hits": DEFAULT_SEARCH_HITS, "total": 2})
    return client


@pytest.fixture
def mock_embeddings_client():
    client = Mock()
    client.model_name = "BAAI/bge-small-zh-v1.5"
    client.embed_query = AsyncMock(return_value=[0.1] * 512)
    client.embed_passages = AsyncMock(return_value=[[0.1] * 512])
    return client


@pytest.fixture
def mock_ollama_client():
    client = Mock()
    client.get_langchain_model = Mock(return_value=Mock())
    client.generate = AsyncMock(return_value={"response": "test"})
    client.create_llm = Mock(return_value=Mock())
    return client


@pytest.fixture
def sample_human_message():
    return HumanMessage(content="What is machine learning?")


@pytest.fixture
def sample_ai_message():
    return AIMessage(content="Machine learning is a subset of AI.")


@pytest.fixture
def sample_tool_message():
    return ToolMessage(
        content="Transformers are neural network architectures based on self-attention.",
        tool_call_id="call_123",
        name="retrieve_papers",
    )


@pytest.fixture
def test_context(mock_opensearch_client, mock_ollama_client, mock_embeddings_client):
    from src.services.agents.context import Context

    return Context(
        ollama_client=mock_ollama_client,
        opensearch_client=mock_opensearch_client,
        embeddings_client=mock_embeddings_client,
        langfuse_tracer=None,
        langfuse_enabled=False,
        model_name="deepseek-r1:7b",
        temperature=0.0,
        top_k=3,
        max_retrieval_attempts=2,
        guardrail_threshold=60,
    )
