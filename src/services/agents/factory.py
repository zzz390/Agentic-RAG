from typing import Optional

from src.services.embeddings import EmbeddingsClient
from src.services.langfuse.client import LangfuseTracer
from src.services.ollama.client import OllamaClient
from src.services.opensearch.client import OpenSearchClient

from .agentic_rag import AgenticRAGService
from .config import GraphConfig


def make_agentic_rag_service(
    opensearch_client: OpenSearchClient,
    ollama_client: OllamaClient,
    embeddings_client: EmbeddingsClient,
    langfuse_tracer: Optional[LangfuseTracer] = None,
    top_k: int = 3,
    use_hybrid: bool = True,
) -> AgenticRAGService:
    """
    创建智能体 RAG 服务（通过依赖注入）

    opensearch_client: 文档检索客户端
    ollama_client: 大模型生成客户端
    embeddings_client: 向量生成客户端
    langfuse_tracer: 可选的链路追踪器
    top_k: 检索返回的文档数量
    use_hybrid: 是否使用混合检索

    返回: 已配置完成的智能体 RAG 服务实例
    """
    # 使用传入参数创建执行图配置
    graph_config = GraphConfig(
        top_k=top_k,
        use_hybrid=use_hybrid,
    )

    return AgenticRAGService(
        opensearch_client=opensearch_client,
        ollama_client=ollama_client,
        embeddings_client=embeddings_client,
        langfuse_tracer=langfuse_tracer,
        graph_config=graph_config,
    )