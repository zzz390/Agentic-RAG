import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[3] / "scripts" / "eval_rag.py"
SPEC = importlib.util.spec_from_file_location("eval_rag", SCRIPT)
assert SPEC and SPEC.loader
eval_rag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(eval_rag)


def test_row_from_response_serializes_context_and_dict_sources():
    row = eval_rag.row_from_response(
        "question",
        "agentic",
        200,
        10.04,
        {
            "answer": "answer",
            "sources": [{"title": "paper"}],
            "retrieved_contexts": ["chunk"],
        },
        None,
        reference="reference",
    )

    assert row["latency_ms"] == 10.0
    assert row["reference"] == "reference"
    assert row["retrieved_contexts"] == '["chunk"]'
    assert '"title": "paper"' in row["sources"]


def test_summary_uses_only_successfully_scored_faithfulness_rows():
    rows = [
        {"mode": "standard", "status_code": 200, "faithfulness": 1.0},
        {"mode": "standard", "status_code": 200, "faithfulness": 0.5},
        {"mode": "agentic", "status_code": 200, "faithfulness": ""},
    ]
    summary = eval_rag.build_summary(rows, judge_model="judge", threshold=1.0)

    assert summary["overall"]["faithfulness_scored"] == 2
    assert summary["overall"]["unsupported_responses"] == 1
    assert summary["overall"]["observed_unsupported_response_rate"] == 0.5
    assert summary["by_mode"]["agentic"]["observed_unsupported_response_rate"] is None
