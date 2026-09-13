from dataclasses import dataclass
from langfuse._client.span import LangfuseSpan
from typing import TYPE_CHECKING, Optional

from src.services.embeddings import EmbeddingsClient
from src.services.langfuse.client import LangfuseTracer
from src.services.ollama.client import OllamaClient
from src.services.opensearch.client import OpenSearchClient


@dataclass
class Context:
    """
    智能体运行时依赖的上下文对象

    包含各个功能节点需要使用的、不可修改的依赖项
    （所有客户端、配置、追踪器都在这里统一管理）

    ollama_client: 大模型生成客户端
    opensearch_client: 文档检索客户端
    embeddings_client: 向量生成客户端
    langfuse_tracer: 可选的链路追踪器（用于监控/可观测性）
    trace: 当前的 Langfuse 追踪 Span 对象（开启追踪时有效）
    langfuse_enabled: 是否启用 Langfuse 链路追踪
    model_name: 大模型调用时使用的模型名称
    temperature: 生成内容的温度参数（控制随机性）
    top_k: 检索时返回的最大文档数量
    max_retrieval_attempts: 最大重试检索次数
    guardrail_threshold: 内容安全校验阈值（0-100）
    """

    ollama_client: OllamaClient
    opensearch_client: OpenSearchClient
    embeddings_client: EmbeddingsClient
    langfuse_tracer: Optional[LangfuseTracer]
    trace: Optional["LangfuseSpan"] = None
    langfuse_enabled: bool = False
    model_name: str = "llama3.2:3b"
    temperature: float = 0.0
    top_k: int = 3
    max_retrieval_attempts: int = 2
    guardrail_threshold: int = 60
