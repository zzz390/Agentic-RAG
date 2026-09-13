# Redis 整答缓存策略

本文说明 **标准 RAG**、**流式 RAG** 与 **Agentic RAG** 在当前项目中的缓存行为、键设计与运维注意点。

相关代码：

- `src/services/cache/client.py` — 缓存读写
- `src/routers/ask.py` — 标准 `/ask` 与 `/stream`
- `src/routers/agentic_ask.py` — Agentic（**未接 Redis**）

---

## 1. 缓存类型：Exact Match 整答缓存

本项目 **不做**「检索 chunk 缓存」或「embedding 缓存」，只做：

> **同一套请求参数 → 直接返回上次生成的完整 `AskResponse`（含 answer、sources 等）**

命中后 **跳过**：BGE embedding、OpenSearch 检索、Ollama 生成。

---

## 2. 标准 RAG（`POST /api/v1/ask`）

### 读取时机

请求进入 `ask_question` 后 **第一步** 查 Redis（在 embedding / 检索 / 生成 **之前**）。

### 写入时机

整条链路成功生成 `AskResponse` 后 **最后一步** 写入 Redis。

### 不写入的情况

- 检索结果为空（`chunks_used=0`）时直接返回提示，**不会** `store_response`
- 缓存写入失败只打 warning，不影响正常响应

### 缓存 Key

对以下字段 JSON 序列化（`sort_keys=True`）后 SHA256，前缀 `exact_cache:`：

| 字段 | 说明 |
|------|------|
| `query` | 用户问题（**精确字符串**） |
| `model` | Ollama 模型名 |
| `top_k` | 检索条数 |
| `use_hybrid` | 是否请求混合检索 |
| `categories` | 分类过滤（排序后） |

**任意一项变化 → 新 key → 不命中。**

问句多一个空格、标点不同、同义改写，均视为 **不同请求**。

### 缓存 Value

`AskResponse` 的 JSON：

- `query`, `answer`, `sources`, `chunks_used`, `search_mode`

### TTL

默认 **6 小时**（`REDIS__TTL_HOURS`，见 `src/config.py`）。

### 陈旧答案风险

Key 中 **不含** 索引版本号。论文库 reindex 或上传新文档后，相同 query 在 TTL 内仍可能返回 **旧答案**。

**缓解建议（运维）：**

- 日更索引后缩短 TTL，或
- 未来在 key 中加入 `index_version`（reindex 脚本 bump 版本）

---

## 3. 流式 RAG（`POST /api/v1/stream`）

与标准 RAG **相同的 key / value 规则**：

- **读**：流式生成开始前查 Redis
- **写**：流式输出结束后写入完整答案
- **命中**：将缓存答案按空白拆词，模拟 `data:` 流式推送

---

## 4. Agentic RAG（`POST /api/v1/ask-agentic`）

### 当前行为

**未接入** `CacheDep`，每次请求完整跑 LangGraph（guardrail → retrieve → grade → … → generate）。

### 为何当前未做整答缓存（设计说明）

| 考量 | 说明 |
|------|------|
| 实现范围 | 课程/项目阶段优先保证可观测与多步推理；Agentic 路径未实现缓存 |
| 产品一致性 | 标准与 Agentic **可以** 共用同一套 exact key；当前选择是 **仅标准 RAG 启用** |
| 调试 | Agentic 响应含 `reasoning_steps`；开发期更倾向每次产生新 trace（Langfuse） |
| 陈旧数据 | 与标准 RAG 相同：索引更新后 cached 答案可能过时 |

**注意：** 「guardrail / grade 分数每次可能不同」影响的是 **不缓存时多次调用的答案差异**，**不是** Redis key 能否匹配。Key 只由 **请求参数** 决定，不由 LLM 中间结果决定。

### 若未来为 Agentic 增加缓存

**建议 key（在标准 5 字段基础上扩展）：**

```json
{
  "query": "...",
  "model": "deepseek-r1:7b",
  "top_k": 3,
  "use_hybrid": true,
  "categories": [],
  "graph_version": "v1",
  "guardrail_threshold": 60,
  "max_retrieval_attempts": 2
}
```

**不建议** 把某次 guardrail 分数、grade 结果写入 key（那是执行产物，不是请求参数）。

**失效策略：**

- TTL（与标准相同）
- `graph_version`：修改 LangGraph 节点 / prompt / 阈值时手动 bump
- `index_version`：OpenSearch 全量 reindex 后 bump

**可选策略：** 仅缓存 `retrieval_attempts == 1` 且未 rewrite 的响应，降低「多轮路径被固化」的风险。

---

## 5. 何时主动关闭或绕过缓存

| 场景 | 建议 |
|------|------|
| 开发 / 改 prompt | 关 Redis 或换 query 参数 |
| 索引刚更新 | 等待 TTL 过期或 flush Redis |
| 演示「实时检索」 | 临时禁用缓存 |
| 命中率极低 | 评估是否值得占内存 |

关闭方式：不启动 Redis、`REDIS__` 配置失败时 `cache_client` 为 `None`，或运维 flush DB。

---

## 6. 与 Langfuse 的关系

- **Redis**：加速 **重复** 请求，不记录推理细节
- **Langfuse**：记录每次（未命中缓存时）完整 trace / span

标准 RAG **缓存命中** 时不会产生新的 embedding / search / generation span（因为链路被短路）。

---

## 7. 快速对照表

| 接口 | Redis 读 | Redis 写 | Key 字段 |
|------|----------|----------|----------|
| `/api/v1/ask` | 请求入口 | 生成成功后 | query + model + top_k + use_hybrid + categories |
| `/api/v1/stream` | 流开始前 | 流结束后 | 同上 |
| `/api/v1/ask-agentic` | ❌ | ❌ | （未实现；见第 4 节建议） |

---

## 8. 相关文档

- RAG 三种模式总览：`docs/RAG-modes.md`
- Embedding 配置：`docs/embeddings.md`
