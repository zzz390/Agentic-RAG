from unittest.mock import AsyncMock

import pytest

from src.evaluation.ragas_evaluator import RagasEvaluator, RagasScores, _numeric_score


class FakeResult:
    def __init__(self, value):
        self.value = value


def make_evaluator() -> RagasEvaluator:
    evaluator = object.__new__(RagasEvaluator)
    evaluator.faithfulness = AsyncMock()
    evaluator.context_precision = AsyncMock()
    evaluator.factual_correctness = AsyncMock()
    evaluator.context_recall = AsyncMock()
    return evaluator


def test_numeric_score_reads_metric_result_and_rejects_nan():
    assert _numeric_score(FakeResult(0.87654)) == 0.8765
    with pytest.raises(ValueError, match="non-finite"):
        _numeric_score(FakeResult(float("nan")))


@pytest.mark.asyncio
async def test_evaluate_scores_reference_free_metrics():
    evaluator = make_evaluator()
    evaluator.faithfulness.ascore.return_value = FakeResult(1.0)
    evaluator.context_precision.ascore.return_value = FakeResult(0.75)

    scores = await evaluator.evaluate(
        user_input="question",
        response="answer",
        retrieved_contexts=[" context "],
    )

    assert scores == RagasScores(faithfulness=1.0, context_precision=0.75)
    evaluator.factual_correctness.ascore.assert_not_called()
    evaluator.context_recall.ascore.assert_not_called()


@pytest.mark.asyncio
async def test_evaluate_adds_reference_metrics_and_keeps_partial_results():
    evaluator = make_evaluator()
    evaluator.faithfulness.ascore.side_effect = RuntimeError("judge unavailable")
    evaluator.context_precision.ascore.return_value = FakeResult(0.8)
    evaluator.factual_correctness.ascore.return_value = FakeResult(0.9)
    evaluator.context_recall.ascore.return_value = FakeResult(0.7)

    scores = await evaluator.evaluate(
        user_input="question",
        response="answer",
        retrieved_contexts=["context"],
        reference="reference answer",
    )

    assert scores.faithfulness is None
    assert scores.context_precision == 0.8
    assert scores.factual_correctness == 0.9
    assert scores.context_recall == 0.7
    assert "faithfulness: RuntimeError: judge unavailable" in scores.ragas_error


@pytest.mark.asyncio
async def test_evaluate_skips_rows_without_context():
    evaluator = make_evaluator()

    scores = await evaluator.evaluate(
        user_input="question",
        response="answer",
        retrieved_contexts=[],
    )

    assert scores.ragas_error == "no retrieved contexts"
    evaluator.faithfulness.ascore.assert_not_called()
