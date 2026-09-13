from uuid import uuid4

from fastapi import APIRouter, HTTPException
from src.dependencies import AgenticRAGDep, CacheDep, LangfuseDep, SessionDep
from src.schemas.api.ask import AgenticAskResponse, AskRequest, FeedbackRequest, FeedbackResponse
from src.services.memory import ConversationMemoryContext, ConversationMemoryService

# 注册路由统一前缀 /api/v1，分类标签 agentic-rag
router = APIRouter(prefix="/api/v1", tags=["智能体RAG"])

#用户提问接口
@router.post("/ask-agentic", response_model=AgenticAskResponse)
async def ask_agentic(
    request: AskRequest,
    agentic_rag: AgenticRAGDep,
    cache_client: CacheDep,
    session: SessionDep,
) -> AgenticAskResponse:
    """
    智能体RAG问答接口，具备智能检索与查询优化能力。

    核心能力:
    - 自动判断是否需要执行文献检索
    - 对检索文档做相关性打分
    - 文档无关时自动重写用户问题
    - 输出完整推理步骤，可追溯来源

    智能体自动执行流程:
    1. 校验问题领域，判断是否需要论文检索
    2. 按需检索相关学术文献
    3. 筛选、评估文档匹配度
    4. 内容不匹配则改写查询并重试检索
    5. 结合引用文献生成规范回答

    :param request: 用户提问与请求参数
    :param agentic_rag: 依赖注入的Agentic RAG核心服务
    :returns: 包含答案、文献来源、推理流程的标准化响应
    :raises HTTPException: 业务异常、服务异常统一抛出Http错误
    """
    try:
        session_id = request.session_id or uuid4().hex
        memory_service = ConversationMemoryService(cache_client, session)
        memory_context = (
            await memory_service.load_context(request.user_id, session_id)
            if request.enable_memory
            else ConversationMemoryContext([], [])
        )
        result = await agentic_rag.ask(
            query=memory_context.as_agent_context(request.query),
            user_id=request.user_id,
            model=request.model,
        )

        if request.enable_memory:
            await memory_service.record_exchange(
                request.user_id,
                session_id,
                request.query,
                result["answer"],
            )

        return AgenticAskResponse(
            query=request.query,
            answer=result["answer"],
            sources=result.get("sources", []),
            chunks_used=request.top_k,
            search_mode="hybrid" if request.use_hybrid else "bm25",
            reasoning_steps=result.get("reasoning_steps", []),
            retrieval_attempts=result.get("retrieval_attempts", 0),
            rewritten_query=result.get("rewritten_query"),
            trace_id=result.get("trace_id"),
            session_id=session_id,
            memory_used=memory_context.has_memory,
            short_term_messages=len(memory_context.short_term),
            long_term_messages=len(memory_context.long_term),
            retrieved_contexts=result.get("retrieved_contexts", []) if request.include_contexts else [],
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理问题失败: {str(e)}")

#用户反馈打分接口
@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    langfuse_tracer: LangfuseDep,
) -> FeedbackResponse:
    """
    提交用户评价反馈，用于优化RAG回答质量。

    支持对单次问答链路打分、填写备注，
    所有反馈数据持久化至Langfuse监控平台。

    :param request: 反馈参数：追踪ID、评分、备注信息
    :param langfuse_tracer: 依赖注入的Langfuse追踪客户端
    :returns: 反馈提交结果状态
    :raises HTTPException: 追踪服务异常、提交失败时抛出错误
    """
    try:
        if not langfuse_tracer:
            raise HTTPException(
                status_code=503,
                detail="Langfuse 追踪未启用，无法提交反馈。"
            )

        success = langfuse_tracer.submit_feedback(
            trace_id=request.trace_id,
            score=request.score,
            comment=request.comment,
        )

        if success:
            # 强制刷新缓冲区，确保反馈即时上报
            langfuse_tracer.flush()

            return FeedbackResponse(
                success=True,
                message="反馈已记录"
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="向 Langfuse 提交反馈失败"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"提交反馈失败: {str(e)}"
        )
