## Prompts

- RAGPromptBuilder:把系统提示、检索到的论文片段、用户问题拼成完整提示词
- ResponseParser：把模型返回的 JSON / 半 JSON / 纯文本答案安全解析成标准格式，保证程序不崩溃

## OllamaClient

- 先health check，检查服务健康状态。获取本地可用模型列表。
- generate调用本地大模型生成回答，并自动解析Token、耗时、性能数据，供监控（langfuse）使用。
- generate_stream流式输出。
- generate_rag_answer接收用户问题+检索到的文档块 → 自动拼提示词 → 调用大模型 → 解析返回结果 → 输出带引用的标准 RAG 回答。
- generate_rag_answer_stream流式输出

## Factory

- 调用环境变量，并只缓存一次避免反复缓存。
