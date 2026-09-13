'''
1.__init__ 初始化
    调用_build_graph()
2._build_graph() 搭建整条工作流+所有节点连线
3.对外接口ask()
    调用_run_workflow()
        运行 graph 工作流
        调用_extract_answer()
        调用_extract_sources()
        调用_extract_reasoning_steps()
4.流程图可视化工具
    get_graph_visualization（PNG）
    get_graph_mermaid（文本图）
    get_graph_ascii（字符画）
'''
import logging
import time
from typing import Dict, List, Optional

from langchain_core.messages import HumanMessage
from langfuse.langchain import CallbackHandler
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.services.embeddings import EmbeddingsClient
from src.services.langfuse.client import LangfuseTracer
from src.services.ollama.client import OllamaClient
from src.services.opensearch.client import OpenSearchClient

from .config import GraphConfig
from .context import Context
from .nodes import (
    ainvoke_generate_answer_step,
    ainvoke_grade_documents_step,
    ainvoke_guardrail_step,
    ainvoke_out_of_scope_step,
    ainvoke_retrieve_step,
    ainvoke_rewrite_query_step,
    continue_after_guardrail,
)
from .state import AgentState
from .tools import create_retriever_tool

logger = logging.getLogger(__name__)

#agentic RAG服务
class AgenticRAGService:
    def __init__(
        self,
        opensearch_client: OpenSearchClient,
        ollama_client: OllamaClient,
        embeddings_client: EmbeddingsClient,
        langfuse_tracer: Optional[LangfuseTracer] = None,
        graph_config: Optional[GraphConfig] = None,
    ):
        self.opensearch = opensearch_client
        self.ollama = ollama_client
        self.embeddings = embeddings_client
        self.langfuse_tracer = langfuse_tracer
        self.graph_config = graph_config or GraphConfig()

        logger.info("Initializing AgenticRAGService with configuration:")
        logger.info(f"  Model: {self.graph_config.model}")
        logger.info(f"  Top-k: {self.graph_config.top_k}")
        logger.info(f"  Hybrid search: {self.graph_config.use_hybrid}")
        logger.info(f"  Max retrieval attempts: {self.graph_config.max_retrieval_attempts}")
        logger.info(f"  Guardrail threshold: {self.graph_config.guardrail_threshold}")

        self.graph = self._build_graph()
        logger.info("✓ AgenticRAGService initialized successfully")
        #调用_build_graph把整个工作流搭好

    #创建流水线，把七个节点组装成一个流水线
    def _build_graph(self):
        logger.info("Building LangGraph workflow with context_schema")

        #1.创建工作流
        workflow = StateGraph(AgentState, context_schema=Context)

        #2.创建检索工具
        retriever_tool = create_retriever_tool(
            opensearch_client=self.opensearch,
            embeddings_client=self.embeddings,
            top_k=self.graph_config.top_k,
            use_hybrid=self.graph_config.use_hybrid,
        )
        tools = [retriever_tool]

        #3.添加七个节点
        logger.info("Adding nodes to workflow graph")
        workflow.add_node("guardrail", ainvoke_guardrail_step)
        workflow.add_node("out_of_scope", ainvoke_out_of_scope_step)
        workflow.add_node("retrieve", ainvoke_retrieve_step)
        workflow.add_node("tool_retrieve", ToolNode(tools))
        workflow.add_node("grade_documents", ainvoke_grade_documents_step)
        workflow.add_node("rewrite_query", ainvoke_rewrite_query_step)
        workflow.add_node("generate_answer", ainvoke_generate_answer_step)

        logger.info("Configuring graph edges and routing logic")

        #开始，安全校验
        #add_edge()是stategraph自带的的方法，作用是给流程图连线，规定谁做完了走下一步
        #A 执行完 → 自动去执行 B
        workflow.add_edge(START, "guardrail")

        #add_conditional_edges 是 LangGraph 里的条件分支连线方法，
        # 专门用来做 “根据判断结果，走不同的路” 的逻辑。
        #这里的意思是从guardrail节点出来后，
        # 根据continue_after_guardrail 函数的返回值，决定下一步去哪个节点。
        workflow.add_conditional_edges(
            "guardrail",
            continue_after_guardrail,
            {
                "continue": "retrieve",
                "out_of_scope": "out_of_scope",
            },
        )

        #out_of_scope如果走这条路，直接结束
        workflow.add_edge("out_of_scope", END)

        #如果结果是retrieve，继续分支
        workflow.add_conditional_edges(
            "retrieve",
            tools_condition,
            {
                "tools": "tool_retrieve",
                END: END,
            },
        )

        #如果结果是tool_retrieve，就grade_documents
        workflow.add_edge("tool_retrieve", "grade_documents")

        #给文本打分之后，决定是直接生成答案或者重写问题
        workflow.add_conditional_edges(
            "grade_documents",
            lambda state: state.get("routing_decision", "generate_answer"),
            {
                "generate_answer": "generate_answer",
                "rewrite_query": "rewrite_query",
            },
        )

        #问题重写就重新检索
        workflow.add_edge("rewrite_query", "retrieve")

        #直接进入生成答案然后结束
        workflow.add_edge("generate_answer", END)

        #workflow.compile()：LangGraph 会根据你所有的节点和边，
        # 把定义好的流程图编译成一个可以直接调用的对象。
        logger.info("Compiling LangGraph workflow")
        compiled_graph = workflow.compile()
        logger.info("✓ Graph compilation successful")

        return compiled_graph

    #整个 Agentic RAG 服务的对外入口方法，
    # 负责接收用户提问、参数校验、初始化监控追踪，最终调用工作流执行函数并返回完整回答结果。
    async def ask(
        self,
        query: str,
        user_id: str = "api_user",
        model: Optional[str] = None,
    ) -> dict:
        model_to_use = model or self.graph_config.model

        logger.info("=" * 80)
        logger.info("Starting Agentic RAG Request")
        logger.info(f"Query: {query}")
        logger.info(f"User ID: {user_id}")
        logger.info(f"Model: {model_to_use}")
        logger.info("=" * 80)

        if not query or len(query.strip()) == 0:
            logger.error("Empty query received")
            raise ValueError("Query cannot be empty")

        #创建一个追踪对象
        trace = None
        if self.langfuse_tracer and self.langfuse_tracer.client:
            logger.info("Creating Langfuse trace (v3 SDK)")
            metadata = {
                "env": self.graph_config.settings.environment,
                "service": "agentic_rag",
                "top_k": self.graph_config.top_k,
                "use_hybrid": self.graph_config.use_hybrid,
                "model": model_to_use,
            }
            trace = self.langfuse_tracer.client.start_as_current_observation(
                name="agentic_rag_request",
                as_type="agent",
                input={"query": query},
                metadata={
                    **metadata,
                    "user_id": user_id,
                    "session_id": f"session_{user_id}",
                },
            )

        #定义执行函数
        async def _execute_with_trace():
            #有追踪就带追踪执行，没有就直接执行
            if trace is not None:
                with trace as trace_obj:
                    logger.debug(f"Trace created: {trace_obj}")
                    return await self._run_workflow(query, model_to_use, user_id, trace_obj)
            else:
                return await self._run_workflow(query, model_to_use, user_id, None)

        try:
            return await _execute_with_trace()
        except Exception as e:
            logger.error(f"Error in Agentic RAG execution: {str(e)}")
            logger.exception("Full traceback:")
            raise

    async def _run_workflow(self, query: str, model_to_use: str, user_id: str, trace) -> dict:
        #执行整个 AI 工作流
        try:
            start_time = time.time()

            logger.info("Invoking LangGraph workflow")

            #初始化状态
            state_input = {
                "messages": [HumanMessage(content=query)],
                "retrieval_attempts": 0,
                "guardrail_result": None,
                "routing_decision": None,
                "sources": None,
                "relevant_sources": [],
                "relevant_tool_artefacts": None,
                "retrieved_contexts": [],
                "grading_results": [],
                "metadata": {},
                "original_query": None,
                "rewritten_query": None,
            }

            #创建运行上下文，把所有工具传给节点
            runtime_context = Context(
                ollama_client=self.ollama,
                opensearch_client=self.opensearch,
                embeddings_client=self.embeddings,
                langfuse_tracer=self.langfuse_tracer,
                trace=trace,
                langfuse_enabled=self.langfuse_tracer is not None and self.langfuse_tracer.client is not None,
                model_name=model_to_use,
                temperature=self.graph_config.temperature,
                top_k=self.graph_config.top_k,
                max_retrieval_attempts=self.graph_config.max_retrieval_attempts,
                guardrail_threshold=self.graph_config.guardrail_threshold,
            )

            #创建会话 ID，用于追踪对话。
            config = {"thread_id": f"user_{user_id}_session_{int(time.time())}"}

            #如果开启监控，添加监控器
            if self.langfuse_tracer and trace:
                try:
                    callback_handler = CallbackHandler()
                    config["callbacks"] = [callback_handler]
                    logger.info("✓ CallbackHandler added (will auto-link to current trace)")
                except Exception as e:
                    logger.warning(f"Failed to create CallbackHandler: {e}")

            #启动整个流水线
            result = await self.graph.ainvoke(
                state_input,
                config=config,
                context=runtime_context,
            )

            execution_time = time.time() - start_time
            logger.info(f"✓ Graph execution completed in {execution_time:.2f}s")

            answer = self._extract_answer(result)
            #把回答从文本里抠出来
            sources = self._extract_sources(result)
            #把来源提取出来
            retrieval_attempts = result.get("retrieval_attempts", 0)
            #提取检索次数
            reasoning_steps = self._extract_reasoning_steps(result)
            #提取思考步骤

            #更新监控日志
            if trace:
                trace.update(
                    output={
                        "answer": answer,
                        "sources_count": len(sources),
                        "retrieval_attempts": retrieval_attempts,
                        "reasoning_steps": reasoning_steps,
                        "execution_time": execution_time,
                    }
                )
                self.langfuse_tracer.flush()

            logger.info("=" * 80)
            logger.info("Agentic RAG Request Completed Successfully")
            logger.info(f"Answer length: {len(answer)} characters")
            logger.info(f"Sources found: {len(sources)}")
            logger.info(f"Retrieval attempts: {retrieval_attempts}")
            logger.info(f"Execution time: {execution_time:.2f}s")
            logger.info("=" * 80)

            return {
                "query": query,
                "answer": answer,
                "sources": sources,
                "reasoning_steps": reasoning_steps,
                "retrieval_attempts": retrieval_attempts,
                "rewritten_query": result.get("rewritten_query"),
                "execution_time": execution_time,
                "guardrail_score": result.get("guardrail_result").score if result.get("guardrail_result") else None,
                "retrieved_contexts": result.get("retrieved_contexts", []),
            }

        except Exception as e:
            logger.error(f"Error in workflow execution: {str(e)}")
            logger.exception("Full traceback:")

            #出错时更新日志
            if trace:
                trace.update(output={"error": str(e)}, level="ERROR")
                self.langfuse_tracer.flush()

            raise

    #从工作流返回的结果里，把最终的回答文本抠出来。
    def _extract_answer(self, result: dict) -> str:
        messages = result.get("messages", [])
        if not messages:
            return "No answer generated."

        final_message = messages[-1]
        #取列表里最后一条消息，也就是AI最终返回的回答
        return final_message.content if hasattr(final_message, "content") else str(final_message)
        #hasattr(final_message, "content")判断这条消息有没有 content 属性（也就是文本内容）
        #如果有就返回final_message.content，也就是回答文本
        #如果没有，直接转字符串，防止程序奔溃

    #从结果里提取参考文献（论文来源），并统一转成字典格式。
    def _extract_sources(self, result: dict) -> List[dict]:
        sources = []
        relevant_sources = result.get("relevant_sources", [])

        for source in relevant_sources:
            if hasattr(source, "to_dict"):
                sources.append(source.to_dict())
            elif isinstance(source, dict):
                sources.append(source)

        return sources

    #从流程结果里提取关键信息，拼接成一段清晰、可读的「AI思考步骤日志」返回给前端展示。
    def _extract_reasoning_steps(self, result: dict) -> List[str]:
        steps = []
        retrieval_attempts = result.get("retrieval_attempts", 0)
        guardrail_result = result.get("guardrail_result")
        grading_results = result.get("grading_results", [])

        if guardrail_result:
            steps.append(f"Validated query scope (score: {guardrail_result.score}/100)")

        if retrieval_attempts > 0:
            steps.append(f"Retrieved documents ({retrieval_attempts} attempt(s))")

        if grading_results:
            relevant_count = sum(1 for g in grading_results if g.is_relevant)
            steps.append(f"Graded documents ({relevant_count} relevant)")

        if result.get("rewritten_query"):
            steps.append("Rewritten query for better results")

        steps.append("Generated answer from context")

        return steps

    #get_graph_visualization：生成并返回工作流程图的 PNG 图片字节数据，缺少依赖时会提示安装。
    def get_graph_visualization(self) -> bytes:
        try:
            logger.info("Generating graph visualization as PNG")
            png_bytes = self.graph.get_graph().draw_mermaid_png()
            logger.info(f"✓ Generated PNG visualization ({len(png_bytes)} bytes)")
            return png_bytes
        except ImportError as e:
            logger.error(f"Failed to generate visualization - missing dependencies: {e}")
            logger.error("Install with: pip install pygraphviz or apt-get install graphviz")
            raise ImportError(
                "Graph visualization requires pygraphviz. "
                "Install with: pip install pygraphviz (requires graphviz system package)"
            ) from e
        except Exception as e:
            logger.error(f"Failed to generate graph visualization: {e}")
            raise

    #get_graph_mermaid：生成并返回工作流程图的 Mermaid 文本格式，
    # 用于在支持 Markdown 的地方显示流程图。
    def get_graph_mermaid(self) -> str:
        try:
            logger.info("Generating graph as mermaid diagram")
            mermaid_str = self.graph.get_graph().draw_mermaid()
            logger.info(f"✓ Generated mermaid diagram ({len(mermaid_str)} characters)")
            return mermaid_str
        except Exception as e:
            logger.error(f"Failed to generate mermaid diagram: {e}")
            raise

    #get_graph_ascii：生成并返回工作流程图的 ASCII 字符画格式，用于在终端直接查看流程结构。
    def get_graph_ascii(self) -> str:
        try:
            logger.info("Generating ASCII graph representation")
            ascii_str = self.graph.get_graph().print_ascii()
            logger.info("✓ Generated ASCII graph representation")
            return ascii_str
        except Exception as e:
            logger.error(f"Failed to generate ASCII graph: {e}")
            raise
