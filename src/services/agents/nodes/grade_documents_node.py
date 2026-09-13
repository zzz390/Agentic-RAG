import logging
import time
from typing import Dict

from langgraph.runtime import Runtime

from ..context import Context
from ..models import GradeDocuments, GradingResult
from ..prompts import GRADE_DOCUMENTS_PROMPT
from ..state import AgentState
from .utils import get_latest_context, get_latest_query

logger = logging.getLogger(__name__)

#调用大模型，判断检索到的论文内容和用户问题是否相关，给文档打分
#然后决定：直接生成答案，还是重写问题重新检索。
async def ainvoke_grade_documents_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, str | list]:
    """
    使用大模型对检索到的文档进行相关性评分
    评估文档是否与用户问题相关，并决定是直接生成答案还是重写问题

    返回：包含路由决策和评分结果的字典
    """
    logger.info("执行节点：文档相关性评分")
    start_time = time.time()

    # 获取用户问题和检索到的上下文内容
    question = get_latest_query(state["messages"])
    context = get_latest_context(state["messages"])

    # 提取文档片段用于日志预览
    chunks_preview = []
    if context:
        context_preview = context[:500] + "..." if len(context) > 500 else context
        chunks_preview = [{"文本预览": context_preview, "长度": len(context)}]

    # 创建文档评分监控追踪
    span = None
    if runtime.context.langfuse_enabled and runtime.context.trace:
        try:
            span = runtime.context.langfuse_tracer.create_span(
                trace=runtime.context.trace,
                name="document_grading",
                input_data={
                    "query": question,
                    "context_length": len(context) if context else 0,
                    "has_context": context is not None,
                    "chunks_received": chunks_preview,
                },
                metadata={
                    "node": "grade_documents",
                    "model": runtime.context.model_name,
                },
            )
            logger.debug("已创建文档评分监控追踪")
        except Exception as e:
            logger.warning(f"创建文档评分追踪失败: {e}")

    # 如果没有检索到任何内容，直接路由到重写问题
    if not context:
        logger.warning("未找到任何上下文内容，路由至：重写问题")

        if span:
            execution_time = (time.time() - start_time) * 1000
            runtime.context.langfuse_tracer.end_span(
                span,
                output={"routing_decision": "rewrite_query", "reason": "no_context"},
                metadata={"execution_time_ms": execution_time},
            )

        return {"routing_decision": "rewrite_query", "grading_results": []}

    logger.debug(f"正在评分的内容长度：{len(context)} 字符")

    # 使用大模型进行文档相关性评分
    try:
        # 构造评分提示词
        grading_prompt = GRADE_DOCUMENTS_PROMPT.format(
            context=context,
            question=question,
        )

        # 从运行上下文中获取大模型
        llm = runtime.context.ollama_client.get_langchain_model(
            model=runtime.context.model_name,
            temperature=0.0,
        )

        # 绑定结构化输出格式
        structured_llm = llm.with_structured_output(GradeDocuments)

        # 调用模型进行评分
        logger.info("正在调用模型进行文档相关性评分")
        grading_response = await structured_llm.ainvoke(grading_prompt)

        is_relevant = grading_response.binary_score == "yes"
        score = 1.0 if is_relevant else 0.0

        logger.info(f"模型评分结果: {grading_response.binary_score}, 原因: {grading_response.reasoning}")

        # 创建评分结果记录
        grading_result = GradingResult(
            document_id="retrieved_docs",
            is_relevant=is_relevant,
            score=score,
            reasoning=grading_response.reasoning,
        )

    except Exception as e:
        logger.error(f"模型评分失败: {e}，使用降级策略")
        # 模型失败时使用简单兜底策略
        is_relevant = len(context.strip()) > 50
        grading_result = GradingResult(
            document_id="retrieved_docs",
            is_relevant=is_relevant,
            score=1.0 if is_relevant else 0.0,
            reasoning=f"兜底评分（模型调用失败）: {'内容充足' if is_relevant else '内容不足'}",
        )

    # 决定下一步路由
    route = "generate_answer" if is_relevant else "rewrite_query"

    logger.info(f"文档评分结果: {'相关' if is_relevant else '不相关'}, 路由至: {route}")

    # 更新追踪信息
    if span:
        execution_time = (time.time() - start_time) * 1000
        runtime.context.langfuse_tracer.end_span(
            span,
            output={
                "routing_decision": route,
                "is_relevant": is_relevant,
                "score": score,
                "reasoning": grading_result.reasoning,
            },
            metadata={
                "execution_time_ms": execution_time,
                "context_length": len(context),
            },
        )

    return {
        "routing_decision": route,
        "grading_results": [grading_result],
    }