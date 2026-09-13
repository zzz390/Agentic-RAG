## Ask

- AskRequest是：请求体JSON的规范+校验+解析
- 客户端POST时body里JSON的规范。服务端拿着AskRequest去POST里面把body解析出来。
- FastAPI把body解析成request对象，后面代码直接用request.query就可以取到body里的内容而不用dict取值。

- AskResponse在这里的作用是和AskRequest反过来，把服务端处理好的内容序列化成JSON，放在HTTP响应的body里发给客户端
- AgenticAskResponse相当于在AskResponse的基础上另外多了几个参数
- FeedbackRequest只有用户用了agentic问答拿到回答，而且响应里带了trace_id，想把人工评分写回langfuse，就会再发一次feedback。

## Health

- ServiceStatus单个依赖项的健康结果，描述某一个下游（database、opensearch、ollama）是否正常
- HealthResponse整站健康检查的对外响应

## Search

- 只检索、不生产答案的API数据合同，只查opensearch返回论文/chunk列表。
- SearchRequest：较简化的搜索请求体：只有 query、分页、分类、是否按最新排序
- HybridSearchRequest：混合检索入参
- SearchHit单条检索结果
- SearchResponse搜索接口最终返回，整个搜索接口返回的最外层结构
