import logging
from typing import Dict, List

from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from ..context import Context
from ..state import AgentState
from .utils import get_latest_query

logger = logging.getLogger(__name__)

#处理用户超出 AI/ML/CS 领域的问题，直接返回一段礼貌的拒绝回复。
async def ainvoke_out_of_scope_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, List[AIMessage]]:
    """
    处理超出范围的查询，返回友好提示
    该节点用于响应用户超出 CS/AI/ML 论文领域的问题
    返回礼貌的说明信息
    """
    logger.info("执行节点：超出处理范围")

    # 获取用户最新问题
    question = get_latest_query(state["messages"])

    # 生成超出范围的回复
    response_text = (
        "I apologize, but I can only help with questions about academic research papers "
        "in Computer Science, Artificial Intelligence, and Machine Learning from arXiv.\n\n"
        f"Your question: '{question}'\n\n"
        "This appears to be outside my domain of expertise. For questions like this, you might want to try:\n"
        "- General-purpose AI assistants for broad knowledge questions\n"
        "- Domain-specific resources for topics outside CS/AI/ML\n"
        "- Technical documentation if asking about specific software/tools\n\n"
        "If you have a question about AI/ML research papers, I'd be happy to help!"
    )

    logger.info("返回超出领域的提示消息")

    return {"messages": [AIMessage(content=response_text)]}