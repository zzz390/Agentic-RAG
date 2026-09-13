## Config

- 整个执行图的配置类，由智能体 RAG 服务使用，用于控制执行图行为、检索配置和运行参数

## State

- AgentState能RAG系统的记忆/状态记录本，数据、中间结果、思考过程都存在这里

## Prompts

- 评分文档相关性，提供REWRITE_PROMPT优化重写查询问题，提升检索效果提示词、SYSTEM_MESSAGE生成回答的系统消息、DECISION_PROMPT路由决策提示词（决定下一步：检索 or 直接回答）、DIRECT_RESPONSE_PROMPT直接回复提示词（无需检索，超出领域时使用）、GUARDRAIL_PROMPT安全护栏校验提示词（在 guardrail_node 中使用）、GENERATE_ANSWER_PROMPT最终答案生成提示词（在 generate_answer_node 中使用）

## Models

- GuardrailScoring用户提问的安全校验评分结果，判断问题是否合规、违规等。
- GradeDocuments判断检索回来的论文是否有用，告诉系统要不要用这篇论文来生成答案。
- SourceItem一条论文来源信息，把论文的信息返回给前端。
- ToolArtefact工具调用返回的结果包，智能体调用工具之后把工具、结果元数据打包，让系统知道谁在干活
- RoutingDecision智能体路线决策，决定智能体下一步做什么，是智能体的大脑决策
- GradingResult文档评分详细结果
- ReasoningStep记录智能体的思考步骤

## Context

- 智能体运行时依赖的上下文对象，包含各个功能节点需要使用的、不可修改的依赖项（所有客户端、配置、追踪器都在这里统一管理）

## Tools

- 它用来创建一个「论文检索工具」，让 AI 智能体可以调用它去查 arXiv 论文。
- LangChain 工具（Tool），智能体看到问题需要查资料时，就会自动调用它。

## Agentic RAG

- 1.__init__ 初始化
  - 调用_build_graph()
- 2._build_graph() 搭建整条工作流+所有节点连线
- 3.对外接口ask()
  - 调用_run_workflow()
    - 运行 graph 工作流
    - 调用_extract_answer()
    - 调用_extract_sources()
    - 调用_extract_reasoning_steps()
- 4.流程图可视化工具
  - get_graph_visualization（PNG）
  - get_graph_mermaid（文本图）
  - get_graph_ascii（字符画）

## Factory

- 调用环境配置，创建一个对外接口。
