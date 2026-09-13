# RAG 离线评估

使用固定问题集批量调用标准 RAG 与 Agentic RAG，并通过 Ragas 自动评估答案是否受检索上下文支持。

## 前置条件

1. FastAPI 服务已启动，OpenSearch 中已有论文数据。
2. `.env` 已配置 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`；建议用 `OPENAI_MODEL_FALLBACK` 作为独立裁判模型。
3. 安装评测依赖：

```bash
pip install -e '.[eval]'
```

## 运行

```bash
# 标准 RAG 与 Agentic RAG 对比
python scripts/eval_rag.py

# 只评估一种模式
python scripts/eval_rag.py --standard-only
python scripts/eval_rag.py --agentic-only

# 指定回答模型、裁判模型和阈值
python scripts/eval_rag.py \
  --model qwen3.8-flash \
  --judge-model qwen3.7-flash \
  --faithfulness-threshold 1.0

# 只采集接口结果，不调用 Ragas
python scripts/eval_rag.py --no-ragas
```

脚本会生成：

- `eval_*.csv`：逐条答案、实际检索上下文、指标及错误信息。
- `eval_*.summary.json`：总体及分模式的均值和未受支持回答比例。

评测请求固定使用 `enable_memory=false`，避免历史对话污染；`include_contexts=true` 只为评测返回本次生成真正使用的上下文。

## 问题集格式

每行一个 JSON 对象。`reference` 可选；填写后会额外计算事实正确性和上下文召回率。

```json
{"query": "What is LoRA?", "reference": "LoRA freezes pretrained weights and trains low-rank adapters.", "notes": "fine-tuning"}
```

## 指标口径

| 指标 | 所需数据 | 含义 |
|---|---|---|
| `faithfulness` | 问题、回答、检索上下文 | 回答中的事实声明有多少能被上下文支持 |
| `context_precision` | 问题、回答、检索上下文 | 检索上下文与实际回答的相关程度 |
| `factual_correctness` | 回答、参考答案 | 回答与参考答案的事实一致性 |
| `context_recall` | 问题、检索上下文、参考答案 | 参考答案中的关键信息被检索覆盖的程度 |

汇总中的 `observed_unsupported_response_rate` 定义为：成功获得 Faithfulness 分数的回答中，分数低于指定阈值的比例。它是固定测试集、固定阈值和指定裁判模型下的观测值，不代表系统在所有问题上的绝对“幻觉率”。

低分样本可结合 Langfuse trace 定位是召回、重写、文档评分还是生成阶段的问题。
