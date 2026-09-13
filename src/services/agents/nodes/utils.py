#这个文件是 Agentic RAG 节点的工具函数集，主要服务于 LangGraph 编排中各个节点的消息处理和数据提取。
import logging
from typing import Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from ..models import ReasoningStep, SourceItem, ToolArtefact

logger = logging.getLogger(__name__)

#从工具返回的消息里，提取论文来源（参考文献）
def extract_sources_from_tool_messages(messages: List) -> List[SourceItem]:
    sources = []

    for msg in messages:
        if isinstance(msg, ToolMessage) and hasattr(msg, "name"):
            if msg.name == "retrieve_papers":
                pass

    return sources

#从消息里提取所有工具调用的结果
def extract_tool_artefacts(messages: List) -> List[ToolArtefact]:
    artefacts = []

    for msg in messages:
        if isinstance(msg, ToolMessage):
            artefact = ToolArtefact(
                tool_name=getattr(msg, "name", "unknown"),
                tool_call_id=getattr(msg, "tool_call_id", ""),
                content=msg.content,
                metadata={},
            )
            artefacts.append(artefact)

    return artefacts

#创建一条 “AI 思考步骤记录”
def create_reasoning_step(
    step_name: str,
    description: str,
    metadata: Optional[Dict] = None,
) -> ReasoningStep:
    return ReasoningStep(
        step_name=step_name,
        description=description,
        metadata=metadata or {},
    )

#过滤消息，只保留用户消息和 AI 消息
def filter_messages(messages: List) -> List[AIMessage | HumanMessage]:
    return [msg for msg in messages if isinstance(msg, (HumanMessage, AIMessage))]

#从消息里拿到最新的用户问题
def get_latest_query(messages: List) -> str:
    for msg in reversed(messages):#reversed() 是 Python 内置函数，作用是将序列反向迭代（从最后一个元素开始，倒序遍历到第一个元素）
                                #消息列表是按时间顺序排列的（最早的消息在前，最新的在后）。用 reversed() 倒序遍历，目的是找到最近（最新）的一条工具返回消息，而不是最早的那条。
        if isinstance(msg, HumanMessage):
            return msg.content
        if isinstance(msg, HumanMessage):
            return msg.content

    raise ValueError("No user query found in messages")

#获取最新的工具返回内容（论文片段）
def get_latest_context(messages: List) -> str:
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            return msg.content if hasattr(msg, "content") else ""

    return ""
