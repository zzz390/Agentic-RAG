import logging
import time
from typing import Dict, Literal

from langgraph.runtime import Runtime

from ..context import Context
from ..models import GuardrailScoring
from ..prompts import GUARDRAIL_PROMPT
from ..state import AgentState
from .utils import get_latest_query

logger = logging.getLogger(__name__)

#安全校验后的路由决策（判断走哪条路）
def continue_after_guardrail(state: AgentState, runtime: Runtime[Context]) -> Literal["continue", "out_of_scope"]:
    guardrail_result = state.get("guardrail_result")
    if not guardrail_result:
        logger.warning("No guardrail result found, defaulting to continue")
        return "continue"

    score = guardrail_result.score
    threshold = runtime.context.guardrail_threshold

    logger.info(f"Guardrail score: {score}, threshold: {threshold}")

    return "continue" if score >= threshold else "out_of_scope"

#执行【安全校验】节点（给用户问题打分）
async def ainvoke_guardrail_step(
    state: AgentState,
    runtime: Runtime[Context], #Runtime[Context]：一个泛型类型，表示携带 Context 类型数据的 Runtime 对象。
) -> Dict[str, GuardrailScoring]:
    logger.info("NODE: guardrail_validation")
    start_time = time.time()

    query = get_latest_query(state["messages"])
    logger.debug(f"Evaluating query: {query[:100]}...")

    span = None
    if runtime.context.langfuse_enabled and runtime.context.trace:
        try:
            span = runtime.context.langfuse_tracer.create_span(
                trace=runtime.context.trace,
                name="guardrail_validation",
                input_data={
                    "query": query,
                    "threshold": runtime.context.guardrail_threshold,
                },
                metadata={
                    "node": "guardrail",
                    "model": runtime.context.model_name,
                },
            )
            logger.debug("Created Langfuse span for guardrail validation (v2 SDK)")
        except Exception as e:
            logger.warning(f"Failed to create span for guardrail validation: {e}")

    try:
        guardrail_prompt = GUARDRAIL_PROMPT.format(question=query)

        llm = runtime.context.ollama_client.get_langchain_model(
            model=runtime.context.model_name,
            temperature=0.0,
        )

        structured_llm = llm.with_structured_output(GuardrailScoring)

        logger.info("Invoking LLM for guardrail validation")
        response = await structured_llm.ainvoke(guardrail_prompt)

        logger.info(f"Guardrail result - Score: {response.score}, Reason: {response.reason}")

        if span:
            execution_time = (time.time() - start_time) * 1000  # 转为毫秒
            runtime.context.langfuse_tracer.end_span(
                span,
                output={
                    "score": response.score,
                    "reason": response.reason,
                    "decision": "continue" if response.score >= runtime.context.guardrail_threshold else "out_of_scope",
                },
                metadata={
                    "execution_time_ms": execution_time,
                    "threshold": runtime.context.guardrail_threshold,
                },
            )

    except Exception as e:
        logger.error(f"LLM guardrail validation failed: {e}, falling back to default")

        response = GuardrailScoring(
            score=50,
            reason=f"LLM validation failed, using conservative default: {str(e)}"
        )

        if span:
            execution_time = (time.time() - start_time) * 1000
            runtime.context.langfuse_tracer.update_span(
                span,
                output={"score": response.score, "reason": response.reason, "error": str(e)},
                metadata={"execution_time_ms": execution_time, "fallback": True},
                level="WARNING",
            )
            runtime.context.langfuse_tracer.end_span(span)

    return {"guardrail_result": response}
