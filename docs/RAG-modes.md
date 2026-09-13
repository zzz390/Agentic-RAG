# RAG 问答模式说明

主要有三种 RAG 问答模式：**标准 RAG 问答**、**流式 RAG 问答**、**Agentic RAG 问答**。

---

## 标准 RAG 问答

走的是 **`POST /api/v1/ask`** 这条链路：

**用户问题 → 查缓存 → 从 OpenSearch 检索片段 → 把片段和问题拼进 prompt → 调 Ollama 生成答案 → 返回 JSON**

### HTTP 与请求体

一次请求 = **方法（如 POST）+ URL + Header +（可选）Body**；Body 里这次一般是 **JSON**。

用户提问之后，客户端代码会读取界面上的文字，放到 **`query`** 字段里，再**序列化成 JSON 字符串**作为 body。

客户端侧需要：配置好要请求的 **URL**、必要的 **Header**，再把用户问题和 **`top_k`** 等参数拼成一个 **JSON body**，组成一次请求（**POST + URL + Header + Body**），以 **HTTP POST** 发到服务端。

服务端 **FastAPI** 解析 body 里的 JSON，校验并转成 Python 里的 **`AskRequest`** 实例。这里的 **`AskRequest`** 就是对 JSON 的**结构化表示**。

只要用户（或前端、脚本）通过 **HTTP** 访问服务，请求就会进入跑 **FastAPI** 的进程。FastAPI 负责：接收 HTTP 请求、解析、调用 **`ask_question`** 这类函数、再返回 HTTP 响应。

### 服务端主流程（标准 RAG）

FastAPI 收到 POST，读出 body 里的 JSON，校验并转成 **`AskRequest`**，进入 **`ask_question`**，一般会为这次调用开启 **Langfuse** 追踪。

然后 **查 Redis 缓存**；未命中则 **检索、准备 chunks 和来源**；若能检索到就 **拼 prompt**，调用 **Ollama** 生成答案，把答案封装成 **`AskResponse`**，**写入缓存**，结束 Langfuse，通过 **HTTP 返回 JSON** 给客户端。

---

## Agentic RAG 问答

走的是 **`POST /api/v1/ask-agentic`** 这条链路：

**用户问题 →（无 Redis 整答缓存）→ LangGraph：护栏判断是否在领域内有意义（若域外则直接结束/拒答）→ 发起检索 → 工具执行：嵌入（可失败降级）+ OpenSearch 取片段 → 大模型对检索片段与问题做相关性打分 →（不相关则改写查询再检索，有次数上限）→（相关则）把片段与问题拼进上下文 → 调 Ollama 生成答案 → 封装为带 `reasoning_steps`、`retrieval_attempts`、`sources` 等的 JSON（**`AgenticAskResponse`**，不是标准 RAG 的 **`AskResponse`**）→ 通过 HTTP 返回；全程可配合 **Langfuse** 做节点级追踪。

### 客户端到服务端（与标准 RAG 类似）

先拿到用户问题，写入 **`query`**，序列化成 JSON，和 **`top_k`** 等参数一起组成 **JSON body**，再与方法 **POST**、**URL**、**Header** 拼成一次请求，发送到服务端。

服务端 FastAPI 收到 POST，解析 body 里的 JSON，开启 Langfuse 追踪，进入 **LangGraph**：

1. **检索前**：判断问题是否适合用论文库回答（分数与阈值比较）；不适用则直接结束；适用才进入后续步骤。
2. **发起检索**：通过**工具调用**执行检索；工具内为 **embed 嵌入** + **OpenSearch** 检索出文本 **chunks** 和来源。
3. **相关性打分**：大模型对检索文本与用户问题的相关性打分；得分低则 **改写查询** 后重新检索（有次数上限）；相关性足够则 **拼 prompt**，调用 **Ollama** 生成答案。
4. 最后把答案封装为 Agentic 的响应模型 **`AgenticAskResponse`**，结束 Langfuse，通过 **HTTP 返回 JSON** 给客户端。

### 为什么 Agentic 不用 Redis 整答缓存？

当前实现：**仅标准 RAG（`/ask`、`/stream`）使用 Redis**；Agentic 路径未接入缓存。

设计考量（详见 [`docs/cache.md`](cache.md)）：

1. **实现范围**：项目阶段优先保证 Agentic 多步推理与 Langfuse 可观测；缓存为可选增强。
2. **Key 规则**：若启用，可与标准 RAG 共用 `query + model + top_k + use_hybrid + categories`；扩展项可含 `graph_version`、`index_version`。
3. **Exact match 限制**：问句改一字即不命中，对两种模式相同。
4. **索引更新**：整答缓存可能在 TTL 内返回陈旧答案（标准 RAG 同样适用）。

---

## 流式 RAG 问答

走的是 **`POST /api/v1/stream`** 这条链路：

**用户问题 → 查缓存 → 从 OpenSearch 检索片段**（嵌入失败则退 **BM25**，与标准 RAG 相同）**→ 用 `create_rag_prompt` 拼 prompt**（流式路径不用结构化 prompt 分支）**→ 边生成答案边以 `data:` 形式推送 →（可选）把完整答案按 `AskResponse` 写入 Redis → `StreamingResponse` 返回**，**不调用 LangGraph**。

与标准 **`/ask`** 同样的**请求与检索链**，但用 **`generate_rag_answer_stream`** 把答案拆成多段 **`data:`** 推给客户端；可选 Redis；**prompt 只用 `create_rag_prompt`**。

### 与标准 RAG 的差异

- **HTTP 响应**：不是一次性返回完整 JSON，而是**分多段写出**。
- **缓存命中**：可直接把缓存答案用 **`.split()`** 按空白拆成词，再逐个输出以模拟流式。
