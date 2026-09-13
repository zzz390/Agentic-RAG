## Tracer

- 专门给 RAG 系统做全流程追踪的 “安全封装层”,基于底层的 LangfuseTracer，
- 把一次完整的 RAG 请求拆成 5 个标准步骤，自动记录每一步的输入、输出、耗时，全程安全不崩溃、不影响主业务。

- 核心安全底座：_safe_span
- 一次 RAG 请求的完整生命周期
  - trace_request顶层总追踪
    - trace_embedding追踪向量嵌入
    - trace_search追踪搜索
    - trace_prompt_construct拼接prompt，end_prompt
    - trace_generation，LLM生成，end_generation
  - end_request收尾总记录

## Client

- LangfuseTracer,Langfuse 追踪封装类,给 LangChain + LangGraph + 自定义 LLM / 检索流程
- 提供全自动、无侵入、可关闭的日志监控、耗时统计、用户反馈、错误追踪能力。

- 1.初始化，__init__，初始化 langfuse 客户端 self.client
- 2.自动化链路追踪（对接 LangChain / LangGraph）
  - get_callback_handler，创建langfuse回调器，把LangChain/LangGraph 的所有调用都自动接入追踪
  - trace_langgraph_agent，内部调用 get_callback_handler，给整个智能体流程套上顶层追踪
- 3.通用辅助工具方法
  - get_trace_id获取当前追踪ID
  - submit_feedback依赖 trace_id 提交评分反馈
  - flush强制把 Langfuse 客户端缓存的追踪数据立即上传到服务器，避免数据丢失。
  - shutdown服务退出前的安全收尾，先 flush() 刷完所有数据，再关闭客户端，保证日志完整。
- 4.LLM 专用手动追踪（成对使用）
  - start_generation开启LLM追踪，监控各种数据
  - update_generation回填 LLM 的输出结果、Token 用量、耗时，然后自动结束本次追踪。
- 5.通用业务步骤手动追踪（成对使用）
  - start_span非 LLM 的业务步骤（如检索、排序、工具调用）开启追踪，记录输入数据和配置。
  - update_span配合 start_span 使用，回填步骤的输出结果、元数据、错误信息，
    支持设置日志级别和状态消息，然后自动结束追踪。

## Factory

- 从环境变量获取配置，并只缓存一次，避免重复缓存
