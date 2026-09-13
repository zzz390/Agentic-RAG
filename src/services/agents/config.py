from typing import Any, Dict

from pydantic import BaseModel, Field

from src.config import Settings, get_settings


class GraphConfig(BaseModel):
    """
    整个执行图的配置类
    由智能体 RAG 服务使用，用于控制执行图行为、检索配置和运行参数

    max_retrieval_attempts: 触发降级前的最大重试检索次数
    guardrail_threshold: 内容安全校验阈值（0-100）
    model: LLM 调用使用的默认模型（例如 "deepseek-r1:7b"）
    temperature: 大模型生成温度（0.0 = 确定性输出）
    top_k: 从搜索引擎中获取的文档数量
    use_hybrid: 是否使用混合检索（关键词 + 向量）
    enable_tracing: 是否启用 Langfuse 链路追踪
    metadata: 用于跟踪和分析的额外运行时元数据
    settings: 应用配置实例，用于环境与服务配置
    """

    max_retrieval_attempts: int = 2
    guardrail_threshold: int = 60
    model: str = "qwen3.8-flash"
    temperature: float = 0.0
    top_k: int = 3
    use_hybrid: bool = True
    enable_tracing: bool = True
    metadata: Dict[str, Any] = {}
    settings: Settings = Field(default_factory=get_settings)
