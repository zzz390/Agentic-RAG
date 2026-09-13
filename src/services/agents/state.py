from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from .models import GradingResult, GuardrailScoring, RoutingDecision, SourceItem, ToolArtefact

#智能RAG系统的记忆/状态记录本，数据、中间结果、思考过程都存在这里
class AgentState(TypedDict):
    """
    智能体 RAG 工作流的状态类
    基于 TypedDict，遵循 LangGraph 2025 最佳实践
    用于跟踪所有需要在节点之间传递的数据

    messages: 对话中的消息列表，使用 add_messages 追加消息
    original_query: 未经任何重写的原始用户问题
    rewritten_query: 优化后的重写问题，用于提升检索效果
    retrieval_attempts: 已执行的检索次数（用于最大次数限制）
    guardrail_result: 安全校验结果，包含分数与原因
    routing_decision: 路线决策，决定执行图的下一个节点
    sources: 工具调用输出来源的映射字典
    relevant_sources: 需要展示给用户的相关来源列表
    relevant_tool_artefacts: 工具执行结果与元数据列表
    grading_results: 每篇检索文档的评分结果
    metadata: 用于追踪与分析的运行时元数据
    """

    messages: Annotated[list[AnyMessage], add_messages]#在类型注解上附加额外元数据，不影响实际类型，但可以被框架/工具读取利用。Annotated[基础类型, 元数据1, 元数据2, ...]
    original_query: Optional[str]# 可以是 str，也可以是 None
    rewritten_query: Optional[str]
    retrieval_attempts: int
    guardrail_result: Optional[GuardrailScoring]
    routing_decision: Optional[RoutingDecision]
    sources: Optional[Dict[str, Any]]
    relevant_sources: List[SourceItem]
    relevant_tool_artefacts: Optional[List[ToolArtefact]]
    retrieved_contexts: List[str]
    grading_results: List[GradingResult]
    metadata: Dict[str, Any]
