import logging
import time
from typing import Dict, List

from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from ..context import Context
from ..prompts import REWRITE_PROMPT
from ..state import AgentState

logger = logging.getLogger(__name__)

#这个函数调用大模型把用户的原始问题优化重写，让检索能查到更相关的论文，失败了就用兜底方案。
class QueryRewriteOutput(BaseModel):
    """查询重写的结构化输出格式"""

    rewritten_query: str = Field(
        description="优化后的查询语句，用于提升文档检索效果"
    )
    reasoning: str = Field(
        description="对查询优化方式的简要说明"
    )


async def ainvoke_rewrite_query_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, str | List]:
    """
    使用大模型重写原始查询，以获得更好的文档检索效果
    该节点通过大模型智能优化用户问题，提高找到相关文档的概率
    """
    logger.info("执行节点：重写查询")
    start_time = time.time()

    # 获取原始用户问题
    original_question = state.get("original_query") or state["messages"][0].content
    current_attempt = state.get("retrieval_attempts", 0)

    logger.debug(f"使用大模型重写查询: {original_question[:100]}...")

    # 创建查询重写监控追踪
    span = None
    if runtime.context.langfuse_enabled and runtime.context.trace:
        try:
            span = runtime.context.langfuse_tracer.create_span(
                trace=runtime.context.trace,
                name="query_rewriting",
                input_data={
                    "original_query": original_question,
                    "attempt": current_attempt,
                },
                metadata={
                    "node": "rewrite_query",
                    "strategy": "llm_based_expansion",
                    "model": runtime.context.model_name,
                },
            )
            logger.debug("已创建查询重写监控追踪")
        except Exception as e:
            logger.warning(f"创建查询重写追踪失败: {e}")

    # 使用大模型智能重写查询
    try:
        # 创建用于查询重写的结构化大模型
        llm = runtime.context.ollama_client.get_langchain_model(
            model=runtime.context.model_name,
            temperature=0.3,  # 较低温度让重写结果更精准
        )
        structured_llm = llm.with_structured_output(QueryRewriteOutput) #with_structured_output 是 LangChain 框架内置的方法，定义在 langchain_core 的基类中。这个方法把一个普通的 LLM 转换成一个结构化输出 LLM，强制大模型按照你指定的格式返回数据

        # 用原始问题构造提示词
        prompt = REWRITE_PROMPT.format(question=original_question)

        logger.debug(f"调用大模型进行查询重写 (模型: {runtime.context.model_name})")
        llm_start = time.time()

        # 获取大模型返回的重写后查询
        result: QueryRewriteOutput = await structured_llm.ainvoke(prompt) #ainvoke 是 LangChain 中 LLM/Chain 的异步调用方法。

        # 校验大模型输出
        if not result or not result.rewritten_query:
            raise ValueError("大模型未能返回有效的查询重写结果") #raise 是 Python 的抛出异常关键字。

        rewritten_query = result.rewritten_query.strip()#strip() 是 Python 字符串的内置方法，作用是去除字符串首尾的空白字符（空格、换行符 \n、制表符 \t 等）。
        if not rewritten_query:
            raise ValueError("大模型返回了空的重写查询")

        reasoning = result.reasoning

        llm_duration = time.time() - llm_start
        logger.info(
            f"查询重写耗时 {llm_duration:.2f}s: "
            f"'{original_question[:50]}...' -> '{rewritten_query[:50]}...'"
        )
        logger.debug(f"重写原因: {reasoning}")

    except Exception as e:
        logger.error(f"大模型重写查询失败: {e}")
        logger.warning("使用兜底策略：简单关键词扩展")
        # 大模型失败时使用简单兜底策略
        rewritten_query = f"{original_question} research paper arxiv machine learning"
        reasoning = "兜底方案：因大模型错误，使用简单关键词扩展"

    # 更新追踪信息
    if span:
        execution_time = (time.time() - start_time) * 1000
        runtime.context.langfuse_tracer.end_span(
            span,
            output={
                "rewritten_query": rewritten_query,
                "reasoning": reasoning,
                "original_query": original_question,
            },
            metadata={
                "execution_time_ms": execution_time,
                "original_length": len(original_question),
                "rewritten_length": len(rewritten_query),
                "llm_duration_seconds": llm_duration if 'llm_duration' in locals() else None,
            },
        )

    return {
        "messages": [HumanMessage(content=rewritten_query)],
        "rewritten_query": rewritten_query,
    }