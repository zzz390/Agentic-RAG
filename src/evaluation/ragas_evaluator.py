"""使用 Ragas 对单条 RAG 问答进行离线评分。"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Awaitable

from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import (
    ContextPrecisionWithoutReference,
    ContextRecall,
    FactualCorrectness,
    Faithfulness,
)


@dataclass(slots=True)
class RagasScores:
    faithfulness: float | None = None
    context_precision: float | None = None
    factual_correctness: float | None = None
    context_recall: float | None = None
    ragas_error: str = ""

    def to_dict(self) -> dict[str, float | str | None]:
        return asdict(self)


def _numeric_score(result: Any) -> float:
    value = float(result.value if hasattr(result, "value") else result)
    if not math.isfinite(value):
        raise ValueError(f"Ragas returned a non-finite score: {value}")
    return round(value, 4)


class RagasEvaluator:
    """Ragas 0.4 单样本评测器，支持 OpenAI-compatible 服务。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 180.0,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY 未配置，无法运行 Ragas LLM 评测")
        if not model:
            raise ValueError("Ragas judge model 不能为空")

        self.model = model
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url.rstrip("/"), timeout=timeout)
        judge_llm = llm_factory(model, provider="openai", client=self.client, adapter="instructor")
        self.faithfulness = Faithfulness(llm=judge_llm)
        self.context_precision = ContextPrecisionWithoutReference(llm=judge_llm)
        self.factual_correctness = FactualCorrectness(llm=judge_llm)
        self.context_recall = ContextRecall(llm=judge_llm)

    async def close(self) -> None:
        await self.client.close()

    async def _run_metric(
        self,
        scores: RagasScores,
        field: str,
        operation: Awaitable[Any],
    ) -> None:
        try:
            setattr(scores, field, _numeric_score(await operation))
        except Exception as exc:  # 单个指标失败不应丢失其他指标
            message = f"{field}: {type(exc).__name__}: {exc}"
            scores.ragas_error = "; ".join(filter(None, [scores.ragas_error, message]))

    async def evaluate(
        self,
        *,
        user_input: str,
        response: str,
        retrieved_contexts: list[str],
        reference: str | None = None,
    ) -> RagasScores:
        scores = RagasScores()
        contexts = [context.strip() for context in retrieved_contexts if context and context.strip()]
        if not response.strip():
            scores.ragas_error = "empty response"
            return scores
        if not contexts:
            scores.ragas_error = "no retrieved contexts"
            return scores

        await self._run_metric(
            scores,
            "faithfulness",
            self.faithfulness.ascore(
                user_input=user_input,
                response=response,
                retrieved_contexts=contexts,
            ),
        )
        await self._run_metric(
            scores,
            "context_precision",
            self.context_precision.ascore(
                user_input=user_input,
                response=response,
                retrieved_contexts=contexts,
            ),
        )

        if reference and reference.strip():
            await self._run_metric(
                scores,
                "factual_correctness",
                self.factual_correctness.ascore(response=response, reference=reference),
            )
            await self._run_metric(
                scores,
                "context_recall",
                self.context_recall.ascore(
                    user_input=user_input,
                    retrieved_contexts=contexts,
                    reference=reference,
                ),
            )

        return scores
