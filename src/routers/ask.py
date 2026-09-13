import json
import logging
import time
from typing import Dict, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from src.dependencies import CacheDep, EmbeddingsDep, LangfuseDep, OllamaDep, OpenSearchDep, SessionDep
from src.schemas.api.ask import AskRequest, AskResponse
from src.services.langfuse.tracer import RAGTracer
from src.services.memory import ConversationMemoryContext, ConversationMemoryService
from src.utils.document_sources import paper_source_url

logger = logging.getLogger(__name__)

#创建两个独立的fastapi路由实例，把普通问答接口和流式问答接口分开管理
ask_router = APIRouter(tags=["问答"])
stream_router = APIRouter(tags=["流式问答"])

#统一做：向量生成 + 混合检索 + 结果清洗 + 来源整理，返回chunks文本片段，
#sources论文 PDF 链接，展示给前端，arxiv_ids论文编号
async def _prepare_chunks_and_sources(
    request: AskRequest,
    opensearch_client,
    embeddings_service,
    rag_tracer: RAGTracer,
    trace=None,
    retrieval_query: str | None = None,
) -> tuple[List[Dict], List[str], List[str]]:

    search_query = retrieval_query or request.query

    #开启混合检索，生成查询向量，引入tracer监控
    query_embedding = None
    if request.use_hybrid:
        with rag_tracer.trace_embedding(trace, search_query) as embedding_span:
            try:
                query_embedding = await embeddings_service.embed_query(search_query) #如果 use_hybrid=True，调用 embeddings_service.embed_query() 把用户问题转成向量
                logger.info("Generated query embedding for hybrid search")
            except Exception as e:
                logger.warning(f"Failed to generate embeddings, falling back to BM25: {e}")
                if embedding_span:
                    rag_tracer.tracer.update_span(embedding_span, output={"success": False, "error": str(e)})

    #调用 OpenSearch 统一搜索接口
    with rag_tracer.trace_search(trace, search_query, request.top_k) as search_span:
        search_results = opensearch_client.search_unified( #调用 opensearch_client.search_unified() 执行 BM25 或 BM25+kNN 混合搜索
            query=search_query,
            query_embedding=query_embedding,
            size=request.top_k,
            from_=0,
            categories=request.categories,
            use_hybrid=request.use_hybrid and query_embedding is not None,
            min_score=0.0,
        )

        #清洗结果，只保留LLM需要的内容（只保留 arxiv_id + chunk_text，丢掉多余字段）
        chunks = []
        arxiv_ids = []
        sources_set = set()

        for hit in search_results.get("hits", []):
            arxiv_id = hit.get("arxiv_id", "")

            #只保留LLM需要的最小数据
            chunks.append(
                {
                    "arxiv_id": arxiv_id,
                    "chunk_text": hit.get("chunk_text", hit.get("abstract", "")),
                }
            )

            #凭借论文PDF链接
            if arxiv_id:
                arxiv_ids.append(arxiv_id)
                sources_set.add(paper_source_url(arxiv_id))

        #结束监控追踪+返回结果
        rag_tracer.end_search(search_span, chunks, arxiv_ids, search_results.get("total", 0))

    return chunks, list(sources_set), arxiv_ids


def _memory_response_fields(session_id: str, context: ConversationMemoryContext) -> dict:
    return {
        "session_id": session_id,
        "memory_used": context.has_memory,
        "short_term_messages": len(context.short_term),
        "long_term_messages": len(context.long_term),
    }


def _evaluation_contexts(request: AskRequest, chunks: List[Dict]) -> List[str]:
    """只在显式评测模式下返回真正送入生成模型的 chunk 文本。"""
    if not request.include_contexts:
        return []
    return [str(chunk.get("chunk_text", "")) for chunk in chunks if chunk.get("chunk_text")]

#接收用户问题 → 查缓存 → 检索论文 → 构建提示词 → 调用大模型 → 返回完整答案
@ask_router.post("/ask", response_model=AskResponse)
async def ask_question(
    request: AskRequest,
    opensearch_client: OpenSearchDep,
    embeddings_service: EmbeddingsDep,
    ollama_client: OllamaDep,
    langfuse_tracer: LangfuseDep,
    cache_client: CacheDep,
    session: SessionDep,
) -> AskResponse:

    rag_tracer = RAGTracer(langfuse_tracer)
    start_time = time.time()
    session_id = request.session_id or uuid4().hex
    memory_service = ConversationMemoryService(cache_client, session)
    memory_context = (
        await memory_service.load_context(request.user_id, session_id)
        if request.enable_memory
        else ConversationMemoryContext([], [])
    )
    retrieval_query = memory_context.contextualize_query(request.query)

    with rag_tracer.trace_request(request.user_id, request.query, session_id) as trace:
    #创建监控追踪器
        try:
            #查缓存
            cached_response = None
            if cache_client and not request.enable_memory:
                try:
                    cached_response = await cache_client.find_cached_response(request)
                    if cached_response:
                        logger.info("Returning cached response for exact query match")
                        return cached_response
                except Exception as e:
                    logger.warning(f"Cache check failed, proceeding with normal flow: {e}")

            #生成向量，以便于混合检索
            query_embedding = None

            # 检索 chunk 片段
            chunks, sources, _ = await _prepare_chunks_and_sources(
                request,
                opensearch_client,
                embeddings_service,
                rag_tracer,
                trace,
                retrieval_query=retrieval_query,
            )
            #调用_prepare_chunks_and_sources，得到chunks和sources
            #内部已经做了向量生成 + 检索 + 结果清洗

            #没有查到内容就返回提示
            if not chunks:
                if request.enable_memory:
                    with rag_tracer.trace_generation(trace, request.model, request.query) as gen_span:
                        answer = await ollama_client.generate_memory_answer(
                            query=request.query,
                            model=request.model,
                            short_term_history=memory_context.short_term,
                            long_term_history=memory_context.long_term,
                        )
                        rag_tracer.end_generation(gen_span, answer, request.model)
                else:
                    answer = "I couldn't find any relevant information in the papers to answer your question."
                response = AskResponse(
                    query=request.query,
                    answer=answer,
                    sources=[],
                    chunks_used=0,
                    search_mode="bm25" if not request.use_hybrid else "hybrid",
                    retrieved_contexts=[],
                    **_memory_response_fields(session_id, memory_context),
                )
                if request.enable_memory:
                    await memory_service.record_exchange(request.user_id, session_id, request.query, response.answer)
                rag_tracer.end_request(trace, response.answer, time.time() - start_time)
                return response

            #构建RAG提示词
            with rag_tracer.trace_prompt_construction(trace, chunks) as prompt_span:
                from src.services.ollama.prompts import RAGPromptBuilder

                prompt_builder = RAGPromptBuilder()

                try:
                    prompt_data = prompt_builder.create_structured_prompt(
                        request.query,
                        chunks,
                        memory_context.short_term,
                        memory_context.long_term,
                    )
                    final_prompt = prompt_data["prompt"]
                except Exception:
                    final_prompt = prompt_builder.create_rag_prompt(
                        request.query,
                        chunks,
                        memory_context.short_term,
                        memory_context.long_term,
                    )

                rag_tracer.end_prompt(prompt_span, final_prompt)

            #调用大模型生成答案
            with rag_tracer.trace_generation(trace, request.model, final_prompt) as gen_span:
                rag_response = await ollama_client.generate_rag_answer(
                    query=request.query,
                    chunks=chunks,
                    model=request.model,
                    short_term_history=memory_context.short_term,
                    long_term_history=memory_context.long_term,
                )
                answer = rag_response.get("answer", "Unable to generate answer")
                rag_tracer.end_generation(gen_span, answer, request.model)

            #封装返回格式
            response = AskResponse(
                query=request.query,
                answer=answer,
                sources=sources,
                chunks_used=len(chunks),
                search_mode="bm25" if not request.use_hybrid else "hybrid",
                retrieved_contexts=_evaluation_contexts(request, chunks),
                **_memory_response_fields(session_id, memory_context),
            )

            rag_tracer.end_request(trace, answer, time.time() - start_time)

            #存储缓存
            if request.enable_memory:
                await memory_service.record_exchange(request.user_id, session_id, request.query, answer)

            if cache_client and not request.enable_memory:
                try:
                    await cache_client.store_response(request, response)
                except Exception as e:
                    logger.warning(f"Failed to store response in cache: {e}")

            return response

        except Exception as e:
            logger.error(f"Error processing request: {e}")
            raise HTTPException(status_code=500, detail=f"处理请求失败: {str(e)}")

#流式输出一整个完整的问答
@stream_router.post("/stream")
async def ask_question_stream(
    request: AskRequest,
    opensearch_client: OpenSearchDep,
    embeddings_service: EmbeddingsDep,
    ollama_client: OllamaDep,
    langfuse_tracer: LangfuseDep,
    cache_client: CacheDep,
    session: SessionDep,
) -> StreamingResponse:
    session_id = request.session_id or uuid4().hex
    memory_service = ConversationMemoryService(cache_client, session)

    async def generate_stream():
        rag_tracer = RAGTracer(langfuse_tracer)
        start_time = time.time()
        memory_context = (
            await memory_service.load_context(request.user_id, session_id)
            if request.enable_memory
            else ConversationMemoryContext([], [])
        )
        retrieval_query = memory_context.contextualize_query(request.query)

        with rag_tracer.trace_request(request.user_id, request.query, session_id) as trace:
            try:
                if cache_client and not request.enable_memory:
                    try:
                        cached_response = await cache_client.find_cached_response(request)
                        if cached_response:
                            logger.info("Returning cached response for exact streaming query match")

                            metadata_response = {
                                "sources": cached_response.sources,
                                "chunks_used": cached_response.chunks_used,
                                "search_mode": cached_response.search_mode,
                                "retrieved_contexts": cached_response.retrieved_contexts,
                                    **_memory_response_fields(session_id, memory_context),
                                }
                            yield f"data: {json.dumps(metadata_response)}\n\n"

                            for chunk in cached_response.answer.split():
                                yield f"data: {json.dumps({'chunk': chunk + ' '})}\n\n"

                            yield f"data: {json.dumps({'answer': cached_response.answer, 'done': True})}\n\n"
                            return
                    except Exception as e:
                        logger.warning(f"Cache check failed, proceeding with normal flow: {e}")

                chunks, sources, _ = await _prepare_chunks_and_sources(
                    request,
                    opensearch_client,
                    embeddings_service,
                    rag_tracer,
                    trace,
                    retrieval_query=retrieval_query,
                )

                if not chunks:
                    if request.enable_memory:
                        with rag_tracer.trace_generation(trace, request.model, request.query) as gen_span:
                            answer = await ollama_client.generate_memory_answer(
                                query=request.query,
                                model=request.model,
                                short_term_history=memory_context.short_term,
                                long_term_history=memory_context.long_term,
                            )
                            rag_tracer.end_generation(gen_span, answer, request.model)
                    else:
                        answer = "No relevant information found."
                    if request.enable_memory:
                        await memory_service.record_exchange(request.user_id, session_id, request.query, answer)
                    rag_tracer.end_request(trace, answer, time.time() - start_time)
                    event = {
                        "answer": answer,
                        "sources": [],
                        "chunks_used": 0,
                        "search_mode": "bm25" if not request.use_hybrid else "hybrid",
                        "retrieved_contexts": [],
                        "done": True,
                        **_memory_response_fields(session_id, memory_context),
                    }
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    return

                search_mode = "bm25" if not request.use_hybrid else "hybrid"
                metadata_response = {
                    "sources": sources,
                    "chunks_used": len(chunks),
                    "search_mode": search_mode,
                    "retrieved_contexts": _evaluation_contexts(request, chunks),
                    **_memory_response_fields(session_id, memory_context),
                }
                yield f"data: {json.dumps(metadata_response)}\n\n"

                with rag_tracer.trace_prompt_construction(trace, chunks) as prompt_span:
                    from src.services.ollama.prompts import RAGPromptBuilder

                    prompt_builder = RAGPromptBuilder()
                    final_prompt = prompt_builder.create_rag_prompt(
                        request.query,
                        chunks,
                        memory_context.short_term,
                        memory_context.long_term,
                    )
                    rag_tracer.end_prompt(prompt_span, final_prompt)

                with rag_tracer.trace_generation(trace, request.model, final_prompt) as gen_span:
                    full_response = ""
                    async for chunk in ollama_client.generate_rag_answer_stream(
                        query=request.query,
                        chunks=chunks,
                        model=request.model,
                        short_term_history=memory_context.short_term,
                        long_term_history=memory_context.long_term,
                    ):
                        if chunk.get("response"):
                            text_chunk = chunk["response"]
                            full_response += text_chunk
                            yield f"data: {json.dumps({'chunk': text_chunk})}\n\n"

                        if chunk.get("done", False):
                            rag_tracer.end_generation(gen_span, full_response, request.model)
                            yield f"data: {json.dumps({'answer': full_response, 'done': True})}\n\n"
                            break

                rag_tracer.end_request(trace, full_response, time.time() - start_time)

                if request.enable_memory and full_response:
                    await memory_service.record_exchange(request.user_id, session_id, request.query, full_response)

                if cache_client and full_response and not request.enable_memory:
                    try:
                        search_mode = "bm25" if not request.use_hybrid else "hybrid"
                        response_to_cache = AskResponse(
                            query=request.query,
                            answer=full_response,
                            sources=sources,
                            chunks_used=len(chunks),
                            search_mode=search_mode,
                            retrieved_contexts=_evaluation_contexts(request, chunks),
                            **_memory_response_fields(session_id, memory_context),
                        )
                        await cache_client.store_response(request, response_to_cache)
                    except Exception as e:
                        logger.warning(f"Failed to store streaming response in cache: {e}")

            except Exception as e:
                logger.error(f"Streaming error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate_stream(), media_type="text/plain", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
