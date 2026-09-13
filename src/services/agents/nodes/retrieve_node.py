import logging
import time
from typing import Dict, Union

from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from ..context import Context
from ..state import AgentState
from .utils import get_latest_query

logger = logging.getLogger(__name__)

#这个函数负责触发论文检索：先检查是否超过最大重试次数，
#没超就生成工具调用去查论文，超了就直接返回失败提示。
async def ainvoke_retrieve_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, Union[int, str, list]]:
    """
    启动检索流程，若达到最大重试次数则返回兜底信息
    该节点创建检索论文的工具调用，若已达到最大重试次数，则直接返回提示消息
    """
    logger.info("执行节点：检索文档")
    start_time = time.time()

    # 获取消息、用户问题、当前已重试次数
    messages = state["messages"]
    question = get_latest_query(messages)
    current_attempts = state.get("retrieval_attempts", 0)

    # 从上下文获取最大重试次数
    max_attempts = runtime.context.max_retrieval_attempts

    # 存储原始问题（仅第一次）
    updates = {}
    if state.get("original_query") is None:
        updates["original_query"] = question
        logger.debug(f"已存储原始问题: {question[:100]}...")

    # 创建检索监控追踪
    span = None
    if runtime.context.langfuse_enabled and runtime.context.trace:
        try:
            span = runtime.context.langfuse_tracer.create_span(
                trace=runtime.context.trace,
                name="document_retrieval_initiation",
                input_data={
                    "query": question,
                    "attempt": current_attempts + 1,
                    "max_attempts": max_attempts,
                },
                metadata={
                    "node": "retrieve",
                    "top_k": runtime.context.top_k,
                },
            )
            logger.debug(f"已创建第 {current_attempts + 1} 次检索监控追踪")
        except Exception as e:
            logger.warning(f"创建检索节点追踪失败: {e}")

    # 判断是否达到最大重试次数
    if current_attempts >= max_attempts:
        logger.warning(f"已达到最大检索次数 ({max_attempts})")
        fallback_msg = (
            f"抱歉，经过 {max_attempts} 次尝试后仍未找到相关的学术论文。\n"
            "可能原因：\n"
            "1. 数据库中没有相关内容\n"
            "2. 查询词与索引内容不匹配\n\n"
            "请尝试使用更专业的术语重新提问。"
        )

        # 更新追踪信息
        if span:
            execution_time = (time.time() - start_time) * 1000
            runtime.context.langfuse_tracer.end_span(
                span,
                output={"status": "max_attempts_reached", "fallback": True},
                metadata={"execution_time_ms": execution_time},
            )

        return {**updates, "messages": [AIMessage(content=fallback_msg)]}

    # 检索次数 +1
    new_attempt_count = current_attempts + 1
    updates["retrieval_attempts"] = new_attempt_count #假设new_attempt_count为1，执行后updates就变为{"retrieval_attempts": 1}
    logger.info(f"第 {new_attempt_count}/{max_attempts} 次检索")

    # 创建检索论文的工具调用
    updates["messages"] = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": f"retrieve_{new_attempt_count}",
                    "name": "retrieve_papers",
                    "args": {"query": question},
                }
            ],
        )
    ]

    logger.debug(f"已创建工具调用，查询问题: {question[:100]}...")

    # 更新追踪信息
    if span:
        execution_time = (time.time() - start_time) * 1000
        runtime.context.langfuse_tracer.end_span(
            span,
            output={
                "status": "tool_call_created",
                "query": question,
                "attempt": new_attempt_count,
            },
            metadata={"execution_time_ms": execution_time},
        )

    return updates