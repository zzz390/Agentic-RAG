import logging
import time
from typing import Dict, List

from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from ..context import Context
from ..prompts import GENERATE_ANSWER_PROMPT
from ..state import AgentState
from .utils import get_latest_context, get_latest_query

logger = logging.getLogger(__name__)

#这个函数根据检索到的论文内容，调用大模型生成最终的回答，并返回给用户。
async def ainvoke_generate_answer_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, list]:
    """
    根据检索到的文档生成最终答案
    该节点使用大模型，基于检索到的上下文生成完整回答
    """
    logger.info("执行节点：生成答案")
    start_time = time.time()

    # 获取用户问题和上下文内容
    question = get_latest_query(state["messages"])
    context = get_latest_context(state["messages"])

    # 统计相关来源数量
    sources_count = len(state.get("relevant_sources", []))

    # 如果没有上下文，使用默认提示
    if not context:
        context = "未找到相关文档。"
        logger.warning("没有可用的上下文来生成答案")

    logger.debug(f"正在为问题生成答案：{question[:100]}...")
    logger.debug(f"使用的上下文长度：{len(context)} 字符")

    # 提取文档片段用于日志预览
    chunks_preview = []
    if context:
        context_preview = context[:1000] + "..." if len(context) > 1000 else context
        chunks_preview = [{"文本预览": context_preview, "长度": len(context)}]

    # 创建答案生成的监控追踪
    span = None
    if runtime.context.langfuse_enabled and runtime.context.trace:
        try:
            span = runtime.context.langfuse_tracer.create_span(
                trace=runtime.context.trace,
                name="answer_generation",
                input_data={
                    "query": question,
                    "context_length": len(context),
                    "sources_count": sources_count,
                    "chunks_used": chunks_preview,
                },
                metadata={
                    "node": "generate_answer",
                    "model": runtime.context.model_name,
                    "temperature": runtime.context.temperature,
                },
            )
            logger.debug("已创建答案生成监控追踪")
        except Exception as e:
            logger.warning(f"创建答案生成追踪失败：{e}")

    try:
        # 构造答案生成提示词
        answer_prompt = GENERATE_ANSWER_PROMPT.format(
            context=context,
            question=question,
        )

        # 从运行上下文中获取大模型
        llm = runtime.context.ollama_client.get_langchain_model(
            model=runtime.context.model_name,
            temperature=runtime.context.temperature,
        )

        # 调用模型生成答案
        logger.info("正在调用模型生成答案")
        response = await llm.ainvoke(answer_prompt)

        # 从响应中提取答案内容
        answer = response.content if hasattr(response, 'content') else str(response)
        logger.info(f"生成的答案长度：{len(answer)} 字符")

        # 更新监控追踪结果
        if span:
            execution_time = (time.time() - start_time) * 1000
            runtime.context.langfuse_tracer.end_span(
                span,
                output={
                    "answer_length": len(answer),
                    "sources_used": sources_count,
                },
                metadata={
                    "execution_time_ms": execution_time,
                    "context_length": len(context),
                },
            )

    except Exception as e:
        logger.error(f"模型生成答案失败：{e}，使用兜底回复")

        # 模型调用失败时使用兜底错误信息
        answer = f"抱歉，生成答案时出现错误：{str(e)}\n\n请重试或换一种提问方式。"

        # 记录错误到监控
        if span:
            execution_time = (time.time() - start_time) * 1000
            runtime.context.langfuse_tracer.update_span(
                span,
                output={"error": str(e), "fallback": True},
                metadata={"execution_time_ms": execution_time},
                level="ERROR",
            )
            runtime.context.langfuse_tracer.end_span(span)

    return {
        "messages": [AIMessage(content=answer)],
        # Ragas 必须评估模型真正看到的上下文。Agentic 工具消息已由
        # LangGraph 序列化，因此按一次检索上下文整体保留最可靠。
        "retrieved_contexts": [context] if context and context != "未找到相关文档。" else [],
    }
