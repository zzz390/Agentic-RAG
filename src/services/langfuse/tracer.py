'''
专门给 RAG 系统做全流程追踪的 “安全封装层”,基于底层的 LangfuseTracer，
把一次完整的 RAG 请求拆成 5 个标准步骤，自动记录每一步的输入、输出、耗时，全程安全不崩溃、不影响主业务。

核心安全底座：_safe_span
一次 RAG 请求的完整生命周期
    trace_request顶层总追踪
        trace_embedding追踪向量嵌入
        trace_search追踪搜索
        trace_prompt_construct拼接prompt，end_prompt
        trace_generation，LLM生成，end_generation
    end_request
'''
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from .client import LangfuseTracer


class RAGTracer:
    def __init__(self, tracer: LangfuseTracer):
        self.tracer = tracer

    #安全的span创建工具，无论追踪是否开启、是否报错，
    #都不会崩溃，自动创建并保证最终关闭 span
    @contextmanager
    def _safe_span(self, trace, name: str, input_data: Dict[str, Any]):
        span = None
        try:
            if hasattr(self.tracer, "create_span"):
            #检查底层tracer有没有create_span方法，有的话就创建span，没有就跳过
                span = self.tracer.create_span(trace=trace, name=name, input_data=input_data)
        except Exception:
            span = None

        try:
            yield span
            #把创建好的span抛出去
        finally:
            if span and hasattr(span, "end"):
                try:
                    span.end()
                #span不是None，且span有end()方法，就关闭span，结束这个步骤的追踪
                except Exception:
                    pass

    #RAG 请求的顶层追踪管理器，负责创建整个请求的 trace，
    #并在最后自动刷新数据，保证日志不丢失，且全程安全不报错。
    @contextmanager
    def trace_request(self, user_id: str, query: str, session_id: Optional[str] = None):
        trace = None
        try:
            if hasattr(self.tracer, "trace_rag_request"):
            #检查底层追中期有没有trace_rag_request方法，有的话开启追踪，没有的话直接跳过
                with self.tracer.trace_rag_request(
                    query=query,
                    user_id=user_id,
                    session_id=session_id or f"session_{user_id}",
                    metadata={"simplified_tracing": True},
                ) as trace:
                    yield trace
            else:
                yield None
        finally:
            if trace and hasattr(self.tracer, "flush"):
                self.tracer.flush()
                #强制把追踪数据刷到Langfuse里面，防止数据丢失

    #向量嵌入步骤的追踪器，自动记录开始时间、创建安全span，并在步骤结束时自动计算耗时、回填日志
    @contextmanager
    def trace_embedding(self, trace, query: str):
        start_time = time.time()
        with self._safe_span(trace, "query_embedding", {"query": query, "query_length": len(query)}) as span:
            try:
                yield span
            finally:
                duration = time.time() - start_time
                if span:
                    self.tracer.update_span(
                        span=span, output={"embedding_duration_ms": round(duration * 1000, 2), "success": True}
                    )

    #检索步骤的追踪器，通过安全 span 记录查询和返回条数，不影响业务、不会崩溃、自动管理生命周期。
    @contextmanager
    def trace_search(self, trace, query: str, top_k: int):
        with self._safe_span(trace, "search_retrieval", {"query": query, "top_k": top_k}) as span:
            yield span

    #结束检索追踪，并把检索结果数据记录到 span 里
    def end_search(self, span, chunks: List[Dict], arxiv_ids: List[str], total_hits: int):
        if not span:
            return

        self.tracer.update_span(
            span=span,
            output={
                "chunks_returned": len(chunks),
                "unique_papers": len(set(arxiv_ids)),
                "total_hits": total_hits,
                "arxiv_ids": list(set(arxiv_ids)),
            },
        )

    #开始追踪 “拼接 Prompt”
    @contextmanager
    def trace_prompt_construction(self, trace, chunks: List[Dict]):
        with self._safe_span(trace, "prompt_construction", {"chunk_count": len(chunks)}) as span:
            yield span

    #结束 Prompt 拼接追踪，并记录结果
    def end_prompt(self, span, prompt: str):
        if not span:
            return

        self.tracer.update_span(
            span=span,
            output={
                "prompt_length": len(prompt),
                "prompt_preview": prompt[:200] + "..." if len(prompt) > 200 else prompt,
            },
        )

    #追踪 LLM 生成回答
    @contextmanager
    def trace_generation(self, trace, model: str, prompt: str):
        with self._safe_span(trace, "llm_generation", {"model": model, "prompt_length": len(prompt), "prompt": prompt}) as span:
            yield span

    #回填 LLM 生成结果
    def end_generation(self, span, response: str, model: str):
        if not span:
            return

        self.tracer.update_span(span=span, output={"response": response, "response_length": len(response), "model_used": model})

    #整个请求最后一步，收尾总记录
    def end_request(self, trace, response: str, total_duration: float):
        if not trace:
            return

        try:
            trace.update(
                output={"answer": response, "total_duration_seconds": round(total_duration, 3), "response_length": len(response)}
            )
        except Exception:
            pass
