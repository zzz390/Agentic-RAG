'''
LangfuseTracer,Langfuse 追踪封装类,给 LangChain + LangGraph + 自定义 LLM / 检索流程
提供全自动、无侵入、可关闭的日志监控、耗时统计、用户反馈、错误追踪能力。

1.初始化，__init__，初始化 langfuse 客户端 self.client
2.自动化链路追踪（对接 LangChain / LangGraph）
    get_callback_handler，创建langfuse回调器，把LangChain/LangGraph 的所有调用都自动接入追踪
    trace_langgraph_agent，内部调用 get_callback_handler，给整个智能体流程套上顶层追踪
3.通用辅助工具方法
    get_trace_id获取当前追踪ID
    submit_feedback依赖 trace_id 提交评分反馈
    flush强制把 Langfuse 客户端缓存的追踪数据立即上传到服务器，避免数据丢失。
    shutdown服务退出前的安全收尾，先 flush() 刷完所有数据，再关闭客户端，保证日志完整。
4.LLM 专用手动追踪（成对使用）
     start_generation开启LLM追踪，监控各种数据
     update_generation回填 LLM 的输出结果、Token 用量、耗时，然后自动结束本次追踪。
5.通用业务步骤手动追踪（成对使用）
    start_span非 LLM 的业务步骤（如检索、排序、工具调用）开启追踪，记录输入数据和配置。
    update_span配合 start_span 使用，回填步骤的输出结果、元数据、错误信息，
        支持设置日志级别和状态消息，然后自动结束追踪。
'''
import logging
from contextlib import contextmanager
from typing import Any, Dict, Optional

from langfuse import Langfuse
from src.config import Settings

logger = logging.getLogger(__name__)


class LangfuseTracer:
    def __init__(self, settings: Settings):
        self.settings = settings.langfuse
        self.client: Optional[Langfuse] = None

        if self.settings.enabled and self.settings.public_key and self.settings.secret_key:
        #判断是否要开启追踪，必须满足三个条件：enable配置里开启了追踪，有公钥和私钥
            try:
                self.client = Langfuse(
                    public_key=self.settings.public_key,
                    secret_key=self.settings.secret_key,
                    host=self.settings.host,
                    flush_at=self.settings.flush_at,
                    flush_interval=self.settings.flush_interval,
                    debug=self.settings.debug,
                )
                '''
                创建langfuse客户端
                host，langfuse服务的地址
                flush_at缓存多少条数据后自动上传，interval上传间隔
                '''
                logger.info(f"Langfuse v3 tracing initialized (host: {self.settings.host})")
            except Exception as e:
                logger.error(f"Failed to initialize Langfuse: {e}")
                self.client = None
        else:
            logger.info("Langfuse tracing disabled or missing credentials")

    #用于创建并返回Langfuse回调处理器，
    #让LangChain/LangGraph自动追踪并上传运行日志,未启用追踪时直接返回 None。
    def get_callback_handler(
        self,
        trace_name: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[list[str]] = None,
    ):
        '''
        创建并返回一个langfuse回调处理器
        trace_name：追踪名称
        user_id：用户 ID
        session_id：会话 ID
        metadata：额外信息
        tags：标签
        '''
        if not self.client:
            return None

        try:
            from langfuse.langchain import CallbackHandler

            # SDK 4.x 从已初始化的 Langfuse 客户端获取连接配置；
            # CallbackHandler 不再接收旧版 trace_name/user_id 等参数。
            handler = CallbackHandler(public_key=self.settings.public_key)
            return handler
        except Exception as e:
            logger.error(f"Error creating CallbackHandler: {e}")
            return None

    # Python 装饰器，让这个函数可以用 with 语句调用，进入 / 退出上下文时自动执行逻辑。
    @contextmanager
    #一个用于包裹 LangGraph 智能体执行流程的上下文管理器，
    # 它会自动创建追踪处理器，让整个 Agent 运行过程被 Langfuse 监控记录。
    def trace_langgraph_agent(
        self,
        name: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[list[str]] = None,
    ):
        if not self.client:
            yield (None, None)
            return

        trace_metadata = dict(metadata or {})
        trace_metadata.update({"user_id": user_id, "session_id": session_id, "tags": tags or []})
        with self.client.start_as_current_observation(
            name=name,
            as_type="agent",
            metadata=trace_metadata,
        ) as trace:
            yield (trace, self.get_callback_handler())

    @contextmanager
    def trace_rag_request(
        self,
        query: str,
        user_id: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Create the root observation for one standard RAG request."""
        if not self.client:
            yield None
            return

        trace_metadata = dict(metadata or {})
        trace_metadata.update({"user_id": user_id, "session_id": session_id})
        try:
            with self.client.start_as_current_observation(
                name="rag_request",
                as_type="chain",
                input={"query": query},
                metadata=trace_metadata,
            ) as trace:
                yield trace
        finally:
            self.flush()

    def create_span(
        self,
        trace,
        name: str,
        input_data: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
        as_type: str = "span",
    ):
        """Create a child observation using the Langfuse SDK 4.x API."""
        if not self.client:
            return None
        try:
            creator = trace.start_observation if trace is not None else self.client.start_observation
            return creator(
                name=name,
                as_type=as_type,
                input=input_data,
                metadata=metadata or {},
            )
        except Exception as e:
            logger.error(f"Error creating span: {e}")
            return None

    def end_span(self, span, **update_data):
        if not span:
            return
        try:
            if update_data:
                span.update(**update_data)
            span.end()
        except Exception as e:
            logger.error(f"Error ending span: {e}")

    #获取当前正在执行的 Trace 的 ID
    def get_trace_id(self, trace=None) -> Optional[str]:
        if not self.client:
            return None

        try:
            trace_id = self.client.get_current_trace_id()
            return trace_id
        except Exception as e:
            logger.error(f"Error getting trace ID: {e}")
            return None

    #向 Langfuse 提交用户对某次回答的评分反馈，
    # 需要传入 trace_id 和评分，成功记录后返回 True，追踪未启用或失败则返回 False。
    def submit_feedback(
        self,
        trace_id: str,
        score: float,
        name: str = "user-feedback",
        comment: Optional[str] = None,
    ) -> bool:
        if not self.client:
            logger.warning("Cannot submit feedback: Langfuse is disabled")
            return False

        try:
            self.client.create_score(
                trace_id=trace_id,
                name=name,
                value=score,
                comment=comment,
            )
            logger.info(f"Submitted feedback for trace {trace_id}: score={score}")
            return True
        except Exception as e:
            logger.error(f"Error submitting feedback: {e}")
            return False

    #强制将 Langfuse 客户端中缓存的追踪数据立即上传到服务器。
    def flush(self):
        if self.client:
            try:
                self.client.flush()
            except Exception as e:
                logger.error(f"Error flushing Langfuse: {e}")

    #关闭 Langfuse 客户端，先 flush() 再 shutdown()
    def shutdown(self):
        if self.client:
            try:
                self.client.flush()
                self.client.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down Langfuse: {e}")

    #上下文管理器，用于为 LLM 调用创建 Langfuse 的 generation span，
    # 专门追踪模型名称、输入、token 用量和耗时等关键信息，方便后续分析和调试。
    @contextmanager
    def start_generation(
        self,
        name: str,
        model: str,
        input_data: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        if not self.client:
            yield None
            return

        try:
            generation = self.client.start_observation(
                name=name,
                as_type="generation",
                model=model,
                input=input_data,
                metadata=metadata or {},
            )
            yield generation
        except Exception as e:
            logger.error(f"Error creating generation span: {e}")
            yield None

    #上下文管理器，用于为非LLM的通用业务步骤（如检索、工具调用）创建Langfuse追踪节点，
    # 方便记录执行耗时、输入输出和状态。
    @contextmanager
    def start_span(
        self,
        name: str,
        input_data: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        if not self.client:
            yield None
            return

        try:
            span = self.client.start_observation(
                name=name,
                as_type="span",
                input=input_data,
                metadata=metadata or {},
            )
            yield span
        except Exception as e:
            logger.error(f"Error creating span: {e}")
            yield None

    #给 LLM 模型调用的追踪记录补充结果、token 用量和耗时，然后自动结束本次追踪。
    def update_generation(
        self,
        generation,
        output: Any,
        usage_metadata: Optional[Dict[str, Any]] = None,
        completion_start_time: Optional[float] = None,
    ):
        if not generation:
            return

        try:
            update_data = {"output": output}

            if usage_metadata:
                if "prompt_tokens" in usage_metadata:
                    update_data["usage_details"] = {
                        "input": usage_metadata.get("prompt_tokens", 0),
                        "output": usage_metadata.get("completion_tokens", 0),
                        "total": usage_metadata.get("total_tokens", 0),
                    }

                if "latency_ms" in usage_metadata:
                    update_data["metadata"] = update_data.get("metadata", {})
                    update_data["metadata"]["latency_ms"] = usage_metadata["latency_ms"]

            generation.update(**update_data)
            generation.end()
        except Exception as e:
            logger.error(f"Error updating generation: {e}")

    #给普通追踪节点（span）补充输出结果、元数据、日志级别和状态信息。
    #span 的生命周期由调用方的上下文管理器或 end_span 统一结束，避免 SDK 4.x 重复 end。
    def update_span(
        self,
        span,
        output: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
        level: Optional[str] = None,
        status_message: Optional[str] = None,
    ):
        if not span:
            return

        try:
            update_data = {}
            if output is not None:
                update_data["output"] = output
            if metadata:
                update_data["metadata"] = metadata
            if level:
                update_data["level"] = level
            if status_message:
                update_data["status_message"] = status_message

            if update_data:
                span.update(**update_data)
        except Exception as e:
            logger.error(f"Error updating span: {e}")
